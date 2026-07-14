
import os
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

def debug():
    print(f"Base Dir: {settings.BASE_DIR}")
    print(f"Output Dir: {settings.OUTPUT_DIR}")
    
    if not os.path.exists(settings.OUTPUT_DIR):
        print("Output dir does not exist! Creating...")
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    else:
        print("Output dir exists.")
        
    # Try writing
    test_file = os.path.join(settings.OUTPUT_DIR, "test_debug.txt")
    try:
        with open(test_file, "w") as f:
            f.write("Hello World")
        print(f"Successfully wrote to {test_file}")
    except Exception as e:
        print(f"Failed to write: {e}")
        return

    # Try reading
    try:
        with open(test_file, "r") as f:
            content = f.read()
        print(f"Successfully read: {content}")
    except Exception as e:
        print(f"Failed to read: {e}")
        
    # Check exists
    if os.path.exists(test_file):
        print("os.path.exists returned True")
    else:
        print("os.path.exists returned False")

if __name__ == "__main__":
    debug()
