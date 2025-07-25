# Split 한 파일 중에서 빈 파일은 없나 확인용용
# 2KB 파일 중 0xFF로 채워진 파일을 찾는 프로그램


import os
import sys

def check_ff_files(directory):
    """
    Checks for files in a directory that are 2KB in size and filled with 0xFF.

    Args:
        directory (str): The path to the directory to check.
    """
    print(f"Checking files in: {directory}")
    sys.stdout.flush()

    found_files = False
    try:
        files = sorted(os.listdir(directory))
        print(f"Found {len(files)} files to check.")
        sys.stdout.flush()
    except FileNotFoundError:
        print(f"Error: Directory not found at {directory}")
        return

    total_files = len(files)
    for i, filename in enumerate(files):
        if (i + 1) % 500 == 0:
            print(f"Processing file {i + 1}/{total_files}...")
            sys.stdout.flush()

        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            try:
                if os.path.getsize(filepath) == 2048:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                        if content == b'\xff' * 2048:
                            print(f"Found file with all 0xFF content: {filename}")
                            sys.stdout.flush()
                            found_files = True
            except Exception as e:
                print(f"Error processing file {filename}: {e}")
                sys.stdout.flush()

    if not found_files:
        print("No 2KB files filled with 0xFF were found.")
    else:
        print("Finished checking all files.")
    sys.stdout.flush()

if __name__ == "__main__":
    target_directory = r"c:\Users\147gk\Documents\nand reader\output_splits"
    check_ff_files(target_directory)
