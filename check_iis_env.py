import sys
import os
import importlib.util

print("=== IIS Environment Check ===")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Python Executable: {sys.executable}")

# Check wfastcgi
try:
    import wfastcgi
    print(f"wfastcgi Location: {os.path.dirname(wfastcgi.__file__)}")
    print(f"wfastcgi File: {wfastcgi.__file__}")
except ImportError:
    print("ERROR: wfastcgi module not found in this environment!")
    # Try to find it manually in site-packages
    for path in sys.path:
        potential_path = os.path.join(path, 'wfastcgi.py')
        if os.path.exists(potential_path):
            print(f"Found wfastcgi manually at: {potential_path}")

print("\n=== Suggested web.config 'scriptProcessor' value ===")
try:
    import wfastcgi
    print(f"{sys.executable}|{wfastcgi.__file__}")
except:
    print("Cannot suggest value because wfastcgi is missing.")
