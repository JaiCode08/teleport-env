import time
import os
import sys

def main():
    count_file = "count.txt"
    start_count = 0

    if os.path.exists(count_file):
        with open(count_file, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                start_count = int(content)

    print(f"Counter Server started. PID: {os.getpid()}", flush=True)

    count = start_count
    while True:
        count += 1
        with open(count_file, "w") as f:
            f.write(str(count))
        print(f"Count: {count}", flush=True)
        time.sleep(1)

if __name__ == "__main__":
    main()
