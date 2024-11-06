import os
import shutil
import time

def force_delete_directory(path):
    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        try:
            # Remove read-only flags
            for root, dirs, files in os.walk(path):
                for dir in dirs:
                    os.chmod(os.path.join(root, dir), 0o777)
                for file in files:
                    os.chmod(os.path.join(root, file), 0o777)
            
            # Delete the directory
            shutil.rmtree(path)
            print(f"Successfully deleted {path}")
            return True
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            attempt += 1
            time.sleep(1)  # Wait a second before retrying
    
    print(f"Failed to delete {path} after {max_attempts} attempts")
    return False

# Usage
path_to_delete = r"D:\development\repos\MyCSharpProject"
force_delete_directory(path_to_delete) 