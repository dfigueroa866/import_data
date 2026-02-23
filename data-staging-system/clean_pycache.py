
import os
import shutil
import sys

def clean_pycache(root_dir):
    print(f"Cleaning __pycache__ in {root_dir}")
    count = 0
    for root, dirs, files in os.walk(root_dir):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            print(f"Removing: {pycache_path}")
            try:
                shutil.rmtree(pycache_path)
                count += 1
            except Exception as e:
                print(f"Error removing {pycache_path}: {e}")
                
        # Also remove .pyc files if they exist outside __pycache__
        for file in files:
            if file.endswith(".pyc"):
                pyc_path = os.path.join(root, file)
                print(f"Removing file: {pyc_path}")
                try:
                    os.remove(pyc_path)
                    count += 1
                except Exception as e:
                    print(f"Error removing {pyc_path}: {e}")
                    
    print(f"Cleaned {count} items.")

if __name__ == "__main__":
    clean_pycache(os.getcwd())
