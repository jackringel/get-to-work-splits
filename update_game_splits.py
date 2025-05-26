#read current splits file
#ask user: upload best segs or pb or best exits
#write that column to game splits file
import os

if __name__ == "__main__":
    input_file = "splits.txt"
    output_file = input("Path to game splits file (including the text file itself): ")
    with open(input_file, 'r') as f:
        data = f.read()
    n = int(input('Which comparison to use (1 for PB, 2 for best segments, 3 for best exits): '))
    lines = data.split('\n')
    numbers = []
    for line in lines:
        numbers.append(str(line.split(',')[n]))
    output_data = f'''<?xml version="1.0" encoding="utf-8"?>
<SpeedrunTimerData xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <times>
    <float>{numbers[0]}</float>
    <float>{numbers[1]}</float>
    <float>{numbers[2]}</float>
    <float>{numbers[3]}</float>
    <float>{numbers[4]}</float>
    <float>{numbers[5]}</float>
    <float>{numbers[6]}</float>
    <float>{numbers[7]}</float>
    <float>{numbers[8]}</float>
    <float>{numbers[9]}</float>
    <float>{numbers[10]}</float>
  </times>
</SpeedrunTimerData>'''
    with open(output_file, 'w') as f:
        f.write(output_data)
