import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, monitored_file, output_file, process_function):
        self.monitored_file = monitored_file
        self.output_file = output_file
        self.process_function = process_function

    def on_modified(self, event):
        if event.src_path == self.monitored_file:
            print(f"File {self.monitored_file} has been modified.")
            self.read_and_write_file()

    def read_and_write_file(self):
        try:
            # Read from the splits
            with open(self.monitored_file, 'r') as f:
                new_data = f.read()

            # Read the current content of the pb/best segments file if it exists
            if os.path.exists(self.output_file):
                with open(self.output_file, 'r') as f:
                    current_data = f.read()
            else:
                current_data = ""  # If the file doesn't exist yet, start with an empty string

            # Get new data to write to file
            processed_data = self.process_function(current_data, new_data)

            # Write the processed data to the output file
            with open(self.output_file, 'w') as f:
                f.write(processed_data)
            
            print(f"Processed data has been written to {self.output_file}.")
        except Exception as e:
            print(f"Error: {e}")

def monitor_file(monitored_file, output_file, process_function):
    event_handler = FileChangeHandler(monitored_file, output_file, process_function)
    observer = Observer()
    observer.schedule(event_handler, os.path.dirname(monitored_file), recursive=False)
    
    try:
        print(f"Monitoring {monitored_file} for changes...")
        observer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def parse_data(current_data, new_data):
    # get list of saved splits when file updates
    lines = new_data.split('\n')
    new_splits = [float(line[11:-8]) for line in lines[3:-2]]
    # because the game saves whatever current split you're on, delete that one
    for i in range(len(new_splits)):
        if not new_splits[i]:
            new_splits[i-1]=0.0
    # parse other file (11 rows, 3 cols - one for each comparison)
    if not current_data:
        pb_splits = [0]*11
        best_segs = [0]*11
        best_exits = [0]*11
    else:
        lines = current_data.split('\n')
        pb_splits = [float(line.split(',')[0]) for line in lines]
        best_segs = [float(line.split(',')[1]) for line in lines]
        best_exits = [float(line.split(',')[2]) for line in lines]
    # update pb splits column if new splits are better
    if ((pb_splits[10] and new_splits[10] and new_splits[10] < pb_splits[10])
        or (new_splits[10] and not pb_splits[10])):
        pb_splits = new_splits
    # update any best segment that is improved in new splits
    for i in range(11):
        if ((new_splits[i] and best_segs[i] and new_splits[i] < best_segs[i])
            or (new_splits[i] and not best_segs[i])):
            best_segs[i] = new_splits[i]
    # calculate best exit times from best exit splits, update if better
    best_exits_cumulative = [0]*11
    new_exits_cumulative = [0]*11
    new_best_exits = best_exits
    for i in range(11):
        if best_exits[i]:
            best_exits_cumulative[i] = sum(best_exits[:i+1])
        if new_splits[i]:
            new_exits_cumulative[i] = sum(new_splits[:i+1])
        if ((new_exits_cumulative[i] and best_exits_cumulative[i] and
             new_exits_cumulative[i] < best_exits_cumulative[i])
            or (new_exits_cumulative[i] and not best_exits_cumulative[i])):
            best_exits_cumulative[i] = new_exits_cumulative[i]
            new_best_exits[i] = best_exits_cumulative[i] - best_exits_cumulative[i-1]
    # create new CSV
    output = ''
    for i in range(11):
        output += str(pb_splits[i])+','+str(best_segs[i])+','+str(new_best_exits[i])+'\n'
    return output[:-1]
    

if __name__ == "__main__":
    monitored_file = input("Path to game splits file (including the text file itself: ")
    output_file = "splits.txt"
    monitor_file(monitored_file, output_file, parse_data)
