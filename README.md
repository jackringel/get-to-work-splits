# get-to-work-splits
REQUIREMENTS:
watchdog (pip install watchdog)

These two files, in tandem, allow you to have better split comparisons for your ingame Get To Work Timer.

update_personal_splits will read your ingame splits file (when run, it will prompt for the file path) every time you save your splits (as such, recommended usage is to save your splits with every run, as this is the only way to save best segments and best exits - don't worry about overwriting your PB, as the second file allows you to set your ingame splits to your desired comparison, including your saved PB.) It will create (or update) a 'splits.txt' file in the same folder as these files (download the files to the same folder!) with three columns - one for PB comparison, one for best exits, and one for best segments. Again, I recommend running this program whenever you start a session and saving after every attempt, but not while running the other program (KEYBOARD INTERRUPT OR CLOSE THE PROGRAM when done using).

update_game_splits is the opposite - it reads from personal splits and updates game splits with your desired comparison. File should stay named 'splits.txt' and stay in the same folder. Usage: input '1' for PB comparison, '2' for best segments comparison, and '3' for best exits comparison. Personal splits file must exist already (i.e. you should have run the previous program at least once).
