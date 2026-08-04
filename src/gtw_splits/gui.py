"""Tkinter interface: watch saves and load comparisons from one window."""

from __future__ import annotations

import contextlib
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import store
from .cli import resolve_game_file
from .gamefile import GAME_FILE_NAME
from .model import Comparison, IngestResult, format_progress
from .tracker import SplitsTracker, Watcher
from .version import version_string

#: How often the UI drains results posted by the watcher thread.
UI_POLL_MS = 150


class SplitsApp(ttk.Frame):
    def __init__(self, master: tk.Tk, game_file: Path) -> None:
        super().__init__(master, padding=12)
        # The running commit, not just the version: this window keeps running
        # the code it was started with, so a stale one has to be visible.
        self.master.title(f"Get To Work Splits  --  {version_string()}")
        self.master.minsize(430, 330)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tracker = SplitsTracker(game_file)
        self.selected = tk.StringVar(value=Comparison.PB.value)
        self.recording = tk.BooleanVar(value=self.tracker.recording)
        self._results: queue.Queue[IngestResult] = queue.Queue()
        self._totals: dict[Comparison, ttk.Label] = {}

        self._build()
        self._refresh_totals()
        self._show_idle_status()

        self.watcher = Watcher(self.tracker, self._results.put)
        self.watcher.start()
        self.after(UI_POLL_MS, self._drain_results)
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout ------------------------------------------------------------

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        self.path_label = ttk.Label(header, text="", foreground="#666")
        self.path_label.grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Change...", command=self._choose_file, width=10).grid(
            row=0, column=1, sticky="e"
        )
        self._update_path_label()

        self.status_label = ttk.Label(self, text="", font=("", 10, "bold"))
        self.status_label.grid(row=1, column=0, sticky="w", pady=(10, 2))

        self.detail_label = ttk.Label(self, text="Save your splits in game after each run.")
        self.detail_label.grid(row=2, column=0, sticky="w")

        ttk.Checkbutton(
            self,
            text="Record saved runs",
            variable=self.recording,
            command=self._toggle_recording,
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        ttk.Separator(self).grid(row=4, column=0, sticky="ew", pady=12)

        group = ttk.LabelFrame(self, text="Compare against", padding=10)
        group.grid(row=5, column=0, sticky="ew")
        group.columnconfigure(1, weight=1)

        for row, comparison in enumerate(Comparison):
            ttk.Radiobutton(
                group,
                text=comparison.label,
                value=comparison.value,
                variable=self.selected,
            ).grid(row=row, column=0, sticky="w", pady=2)
            total = ttk.Label(group, text="--", anchor="e")
            total.grid(row=row, column=1, sticky="e", padx=(20, 0))
            self._totals[comparison] = total

        buttons = ttk.Frame(self)
        buttons.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        ttk.Label(
            buttons,
            text="Loading overwrites the game's splits file (a backup is kept).",
            foreground="#666",
            wraplength=280,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Load into game", command=self._load).grid(
            row=0, column=1, sticky="e"
        )

    def _update_path_label(self) -> None:
        path = self.tracker.game_file
        shown = str(path)
        if len(shown) > 52:
            shown = f"...{shown[-49:]}"
        state = "" if path.is_file() else "  (not saved yet)"
        self.path_label.configure(text=f"{shown}{state}")

    # -- behaviour ---------------------------------------------------------

    def _show_idle_status(self) -> None:
        """Say what the tool will do with the next save, before there is one."""
        if self.tracker.recording:
            self.status_label.configure(text="Watching for saves...")
            self.detail_label.configure(text="Save your splits in game after each run.")
        else:
            self.status_label.configure(text="Recording paused")
            self.detail_label.configure(text="Saves are ignored. Loading still works.")

    def _toggle_recording(self) -> None:
        self.tracker.set_recording(self.recording.get())
        self._show_idle_status()

    def _refresh_totals(self) -> None:
        database = self.tracker.database
        for comparison, label in self._totals.items():
            total, reach = database.progress_for(comparison)
            label.configure(text=format_progress(total, reach, database.split_count))

    def _drain_results(self) -> None:
        latest: IngestResult | None = None
        while True:
            try:
                latest = self._results.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            if latest.ignored_reason and not self.tracker.recording:
                detail = "Turn recording on to keep runs like this one."
            elif latest.changed:
                detail = "Recorded from your last save."
            else:
                detail = "Nothing new from your last save."
            self.status_label.configure(text=latest.summary())
            self.detail_label.configure(text=detail)
            self._refresh_totals()
            self._update_path_label()
        self.after(UI_POLL_MS, self._drain_results)

    def _choose_file(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select best_split_times.txt",
            initialfile=GAME_FILE_NAME,
            initialdir=str(self.tracker.game_file.parent),
            filetypes=[("Splits file", "*.txt"), ("All files", "*.*")],
        )
        if not chosen:
            return
        self.watcher.stop()
        self.tracker = SplitsTracker(Path(chosen))
        settings = store.load_settings()
        settings[store.SETTING_GAME_FILE] = chosen
        store.save_settings(settings)
        self.watcher = Watcher(self.tracker, self._results.put)
        self.watcher.start()
        self.recording.set(self.tracker.recording)
        self._update_path_label()
        self._refresh_totals()
        self._show_idle_status()

    def _load(self) -> None:
        comparison = Comparison(self.selected.get())

        # A run saved in the last half-second is about to be overwritten;
        # record it first so the prompt below sees the true totals too.
        if self.tracker.ingest_current_file().changed:
            self._refresh_totals()

        total = self.tracker.database.total_for(comparison)
        if not total:
            proceed = messagebox.askyesno(
                "Incomplete comparison",
                f"{comparison.label} does not have a time for every split yet.\n\n"
                "Load it anyway?",
            )
            if not proceed:
                return
        try:
            backup = self.tracker.load_into_game(comparison)
        except Exception as exc:
            messagebox.showerror("Could not load splits", str(exc))
            return
        self.status_label.configure(text=f"Loaded {comparison.label}")
        self.detail_label.configure(
            text=f"Backup: {backup.name}" if backup else "No previous file to back up."
        )

    def _on_close(self) -> None:
        self.watcher.stop()
        self.master.destroy()


def run_gui(game_file: str | None = None) -> int:
    path = resolve_game_file(game_file)
    root = tk.Tk()
    with contextlib.suppress(tk.TclError):
        root.call("tk", "scaling", 1.3)
    SplitsApp(root, path)
    root.mainloop()
    return 0
