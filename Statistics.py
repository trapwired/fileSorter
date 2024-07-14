import os
import matplotlib.pyplot as plt

# Specify the directory you want to start from
rootDir = 'output'
folders = []
counts = []
percentages = []

total_count = 0

for dirName, subdirList, fileList in os.walk(rootDir):
    if dirName == rootDir:  # Only consider direct subdirectories of the root
        for subdir in subdirList:
            count = len(os.listdir(os.path.join(rootDir, subdir)))
            folders.append(subdir)
            counts.append(count)
            total_count += count

# Calculate the percentage for each folder
percentages = [(count / total_count * 100) for count in counts]

# Plotting the data
plt.figure(figsize=(10, 6))
bars = plt.bar(folders, counts)

plt.xlabel('Folder Names')
plt.ylabel('Number of Elements')
plt.title('Number of Elements in Each Folder')

# Adding percentages to the bars
for i, bar in enumerate(bars):
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + .05, f"{round(percentages[i], 0)}%", ha='center', va='bottom')

plt.xticks(rotation=90)  # Rotate labels for readability if they're long
plt.show()
