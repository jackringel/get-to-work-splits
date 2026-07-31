"""Tkinter interface: watch saves and load comparisons from one window."""

from __future__ import annotations

import contextlib
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import store
from .cli import SETTING_GAME_FILE, resolve_game_file
from .gamefile import GAME_FILE_NAME
from .model import Comparison, IngestResult, format_time
from .tracker import SplitsTracker, Watcher

#: How often the UI drains results posted by the watcher thread.
UI_POLL_MS = 150


class SplitsApp(ttk.Frame):
    def __init__(self, master: tk.Tk, game_file: Path) -> None:
        super().__init__(master, padding=12)
        self.master.title("Get To Work Splits")
        self.master.minsize(430, 300)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tracker = SplitsTracker(game_file)
        self.selected = tk.StringVar(value=Comparison.PB.value)
        self._results: queue.Queue[IngestResult] = queue.Queue()
        self._totals: dict[Comparison, ttk.Label] = {}

        self._build()
        self._refresh_totals()

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

        self.status_label = ttk.Label(self, text="Watching for saves...", font=("", 10, "bold"))
        self.status_label.grid(row=1, column=0, sticky="w", pady=(10, 2))

        self.detail_label = ttk.Label(self, text="Save your splits in game after each run.")
        self.detail_label.grid(row=2, column=0, sticky="w")

        ttk.Separator(self).grid(row=3, column=0, sticky="ew", pady=12)

        group = ttk.LabelFrame(self, text="Compare against", padding=10)
        group.grid(row=4, column=0, sticky="ew")
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
        buttons.grid(row=5, column=0, sticky="ew", pady=(12, 0))
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

    def _refresh_totals(self) -> None:
        for comparison, label in self._totals.items():
            total = self.tracker.database.total_for(comparison)
            label.configure(text=format_time(total) if total else "incomplete")

    def _drain_results(self) -> None:
        latest: IngestResult | None = None
        while True:
            try:
                latest = self._results.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.status_label.configure(text=latest.summary())
            self.detail_label.configure(text="Recorded from your last save.")
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
        settings[SETTING_GAME_FILE] = chosen
        store.save_settings(settings)
        self.watcher = Watcher(self.tracker, self._results.put)
        self.watcher.start()
        self._update_path_label()
        self._refresh_totals()

    def _load(self) -> None:
        comparison = Comparison(self.selected.get())
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
