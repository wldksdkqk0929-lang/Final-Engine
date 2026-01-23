import os
import time
import shutil
from datetime import datetime, timedelta

def cleanup_files(directory, days_limit):
    if not os.path.exists(directory):
        return

    now = time.time()
    cutoff = now - (days_limit * 86400)
    deleted_count = 0

    print(f"🧹 [CLEANUP] Scanning {directory} (Limit: {days_limit} days)...")

    for root, dirs, files in os.walk(directory):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                # Check file modification time
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    deleted_count += 1
            except Exception as e:
                print(f"   Error deleting {file_path}: {e}")
    
    # Remove empty directories
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
            except:
                pass

    if deleted_count > 0:
        print(f"   🗑️  Deleted {deleted_count} old files in {directory}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")

    # [Unit 0 Policy]
    # Cache: 7 days
    # Out: 30 days
    # Metrics: 90 days
    
    cleanup_files(os.path.join(data_dir, "cache"), 7)
    cleanup_files(os.path.join(data_dir, "out"), 30)
    cleanup_files(os.path.join(data_dir, "metrics"), 90)

if __name__ == "__main__":
    main()
