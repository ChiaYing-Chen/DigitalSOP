import os
import requests

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Create directories
os.makedirs(os.path.join(STATIC_DIR, 'js'), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, 'css'), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, 'fonts'), exist_ok=True)

# Assets to download
ASSETS = [
    # React
    {
        'url': 'https://unpkg.com/react@18/umd/react.development.js',
        'path': 'js/react.js'
    },
    {
        'url': 'https://unpkg.com/react-dom@18/umd/react-dom.development.js',
        'path': 'js/react-dom.js'
    },
    # Babel
    {
        'url': 'https://unpkg.com/@babel/standalone/babel.min.js',
        'path': 'js/babel.js'
    },
    # Tailwind CSS (Script version)
    {
        'url': 'https://cdn.tailwindcss.com',
        'path': 'js/tailwindcss.js'
    },
    # BPMN-JS Modeler (Includes Viewer logic usually, but let's get Modeler for Editor)
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/bpmn-modeler.development.js',
        'path': 'js/bpmn-modeler.js'
    },
     # BPMN-JS Viewer (For Operator/Review modes - lighter)
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/bpmn-navigated-viewer.development.js',
        'path': 'js/bpmn-viewer.js'
    },
    # BPMN-JS CSS
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/diagram-js.css',
        'path': 'css/diagram-js.css'
    },
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/css/bpmn.css',
        'path': 'css/bpmn.css'
    },
    # BPMN-JS Fonts
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.woff',
        'path': 'fonts/bpmn.woff'
    },
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.woff2',
        'path': 'fonts/bpmn.woff2'
    },
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.ttf',
        'path': 'fonts/bpmn.ttf'
    },
    {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.eot',
        'path': 'fonts/bpmn.eot'
    },
     {
        'url': 'https://unpkg.com/bpmn-js@14.0.0/dist/assets/bpmn-font/font/bpmn.svg',
        'path': 'fonts/bpmn.svg'
    }
]

def download_file(url, filepath):
    try:
        print(f"Downloading {url} to {filepath}...")
        response = requests.get(url)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        print("Success.")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def main():
    print(f"Downloading assets to {STATIC_DIR}...")
    for asset in ASSETS:
        full_path = os.path.join(STATIC_DIR, asset['path'])
        download_file(asset['url'], full_path)
    
    # Create a simple CSS file for font fix if needed
    # The bpmn.css usually expects fonts relative to it. 
    # We put css in /css and fonts in /fonts. 
    # bpmn.css expects ../font/bpmn.woff usually.
    # Our structure: static/css/bpmn.css and static/fonts/bpmn.woff
    # ../fonts/bpmn.woff works.
    
    print("All assets downloaded.")

if __name__ == "__main__":
    main()
