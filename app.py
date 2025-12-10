import os
import sys
import sqlite3
import json
import random
import datetime
import datetime
import subprocess
import platform
from flask import Flask, render_template_string, request, jsonify, send_from_directory
from flask_cors import CORS
from contextlib import contextmanager

# --- Configuration ---
app = Flask(__name__, static_folder='static')
CORS(app)

# --- Vite Frontend Routes ---
@app.route('/assets/<path:path>')
def serve_assets(path):
    return send_from_directory(os.path.join(app.static_folder, 'dist', 'assets'), path)


# 1. Use absolute path (Avoid IIS file not found error)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'sops.db')

# --- Logging Setup for Startup Analysis ---
import time
STARTUP_LOG = os.path.join(BASE_DIR, 'startup_stats.log')
def log_startup(msg):
    with open(STARTUP_LOG, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.datetime.now()} - {msg}\n")

log_startup("App initialization started")

# --- PIconnect Integration (Mock Fallback) ---
# --- PIconnect Integration (Lazy Loading) ---
PI = None
PI_AVAILABLE = None  # None: not checked yet, True: available, False: failed

def lazy_load_pi():
    global PI, PI_AVAILABLE
    if PI_AVAILABLE is not None:
        return PI_AVAILABLE
    
    t_start = time.time()
    try:
        log_startup("Importing PIconnect (Lazy Load)...")
        import PIconnect as ImportedPI
        PI = ImportedPI
        PI_AVAILABLE = True
        # PI.PIConfig.DEFAULT_SERVER_NAME = "MyPIServer"
        log_startup(f"PIconnect lazy loaded successfully in {time.time() - t_start:.4f}s")
    except ImportError:
        PI_AVAILABLE = False
        log_startup(f"PIconnect not found (Lazy Load). (Took {time.time() - t_start:.4f}s)")
        print("PIconnect not found. PI Server Offline.")
    except Exception as e:
        PI_AVAILABLE = False
        log_startup(f"PIconnect lazy init failed: {e} (Took {time.time() - t_start:.4f}s)")
        print(f"PIconnect initialization failed: {e}. PI Server Offline.")
    
    return PI_AVAILABLE


log_startup("App initialization finished")

# --- Database Setup ---
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    try:
        # Enable Write-Ahead Logging for better concurrency
        conn.execute('PRAGMA journal_mode=WAL;')
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        
        # Create processes table
        c.execute('''
            CREATE TABLE IF NOT EXISTS processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                xml_content TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create sessions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_id INTEGER,
                current_task_id TEXT,
                logs TEXT,
                is_finished BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(process_id) REFERENCES processes(id)
            )
        ''')
        
        # Create settings table
        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Create active_users table for heartbeat
        c.execute('''
            CREATE TABLE IF NOT EXISTS active_users (
                process_id INTEGER,
                user_id TEXT,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (process_id, user_id)
            )
        ''')
        
        conn.commit()

# --- Routes ---

@app.route('/')
def index():
    try:
        return send_from_directory(os.path.join(app.static_folder, 'dist'), 'index.html')
    except Exception as e:
        import traceback
        return f"<h1>Internal Server Error (Captured)</h1><pre>{traceback.format_exc()}</pre>", 500

@app.errorhandler(500)
def internal_error(error):
    import traceback
    return jsonify({
        'error': 'Internal Server Error',
        'message': str(error),
        'traceback': traceback.format_exc()
    }), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/processes', methods=['GET'])
@app.route('/api/processes', methods=['GET'])
def get_processes():
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT p.id, p.name, p.updated_at, s.is_finished 
                FROM processes p 
                LEFT JOIN sessions s ON p.id = s.process_id 
                ORDER BY p.updated_at DESC
            """)
            rows = c.fetchall()
        # is_finished: None (no session), 0 (running), 1 (finished)
        return jsonify([{'id': r[0], 'name': r[1], 'updated_at': r[2], 'session_status': r[3]} for r in rows])
    except Exception as e:
        import traceback
        print(f"API Error: {e}")
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/processes/<int:process_id>', methods=['GET'])
@app.route('/api/processes/<int:process_id>', methods=['GET'])
def get_process(process_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, xml_content, updated_at FROM processes WHERE id=?", (process_id,))
        row = c.fetchone()
    if row:
        return jsonify({'id': row[0], 'name': row[1], 'xml_content': row[2], 'updated_at': row[3]})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/processes', methods=['POST'])
def save_process():
    data = request.json
    name = data.get('name')
    xml_content = data.get('xml_content')
    
    
    with get_db() as conn:
        c = conn.cursor()
        process_id = data.get('id')
        
        if process_id:
            if name and xml_content:
                 c.execute("UPDATE processes SET name=?, xml_content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, xml_content, process_id))
            elif name:
                 c.execute("UPDATE processes SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, process_id))
            elif xml_content:
                 c.execute("UPDATE processes SET xml_content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (xml_content, process_id))
            else:
                 return jsonify({'error': 'Nothing to update'}), 400
        else:
            if not name or not xml_content:
                return jsonify({'error': 'Missing name or xml_content'}), 400
            c.execute("INSERT INTO processes (name, xml_content) VALUES (?, ?)", (name, xml_content))
            process_id = c.lastrowid
            
        conn.commit()
    return jsonify({'id': process_id, 'message': 'Saved successfully'})

@app.route('/api/processes/<int:process_id>', methods=['DELETE'])
@app.route('/api/processes/<int:process_id>', methods=['DELETE'])
def delete_process(process_id):
    with get_db() as conn:
        conn.execute('DELETE FROM processes WHERE id = ?', (process_id,))
        conn.execute('DELETE FROM sessions WHERE process_id = ?', (process_id,))
        conn.commit()
    return jsonify({'result': 'success'})

@app.route('/api/sessions/<int:process_id>', methods=['GET'])
@app.route('/api/sessions/<int:process_id>', methods=['GET'])
def get_session(process_id):
    try:
        with get_db() as conn:
            c = conn.cursor()
            # Get the latest session
            c.execute("SELECT current_task_id, logs, is_finished FROM sessions WHERE process_id=? ORDER BY updated_at DESC LIMIT 1", (process_id,))
            row = c.fetchone()
        
        if row:
            logs_data = []
            try:
                if row[1]:
                    logs_data = json.loads(row[1])
            except Exception as e:
                print(f"Error parsing logs for process {process_id}: {e}")
                logs_data = []
                
            return jsonify({'current_task_id': row[0], 'logs': logs_data, 'is_finished': bool(row[2])})
        return jsonify(None)
    except Exception as e:
        print(f"Database error in get_session: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sessions', methods=['POST'])
def save_session():
    data = request.json
    process_id = data.get('process_id')
    current_task_id = data.get('current_task_id')
    logs = json.dumps(data.get('logs', []))
    is_finished = data.get('is_finished', False)
    
    with get_db() as conn:
        c = conn.cursor()
        
        # Check if session exists
        c.execute("SELECT process_id FROM sessions WHERE process_id=?", (process_id,))
        row = c.fetchone()
        
        if row:
            c.execute("UPDATE sessions SET current_task_id=?, logs=?, is_finished=?, updated_at=CURRENT_TIMESTAMP WHERE process_id=?",
                      (current_task_id, logs, is_finished, process_id))
        else:
            c.execute("INSERT INTO sessions (process_id, current_task_id, logs, is_finished, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                      (process_id, current_task_id, logs, is_finished))
                      
        conn.commit()
    return jsonify({'result': 'success'})

@app.route('/api/settings', methods=['GET'])
@app.route('/api/settings', methods=['GET'])
def get_settings():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='pi_server_ip'")
        row = c.fetchone()
    return jsonify({'pi_server_ip': row[0] if row else ''})
@app.route('/api/settings', methods=['POST'])
@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    ip = data.get('pi_server_ip')
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pi_server_ip', ?)", (ip,))
        conn.commit()
    return jsonify({'result': 'success'})

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    process_id = data.get('process_id')
    user_id = data.get('user_id')
    
    if not process_id or not user_id:
        return jsonify({'error': 'Missing params'}), 400
        
    with get_db() as conn:
        c = conn.cursor()
        
        # Upsert heartbeat
        c.execute("INSERT OR REPLACE INTO active_users (process_id, user_id, last_heartbeat) VALUES (?, ?, CURRENT_TIMESTAMP)", (process_id, user_id))
        
        # Remove old heartbeats (> 30 seconds)
        c.execute("DELETE FROM active_users WHERE last_heartbeat < datetime('now', '-30 seconds')")
        
        # Count online users for this process
        c.execute("SELECT COUNT(DISTINCT user_id) FROM active_users WHERE process_id=?", (process_id,))
        count = c.fetchone()[0]
        
        conn.commit()
    
    return jsonify({'online_count': count})

@app.route('/api/pi_status', methods=['GET'])
@app.route('/api/pi_status', methods=['GET'])
def get_pi_status():
    try:
        # Check if PIconnect is installed and available
        if not PI_AVAILABLE:
            return jsonify({'status': 'Offline', 'message': 'PI SDK Access Failed (ImportError)'})

        # Use PIconnect to verify connection
        try:
             # Try to connect to default server or specific server if needed
             # Since PIconnect uses AF SDK, simpliest check is to access PIServer list or default one
             server_name = None
             with PI.PIServer() as server:
                 server_name = server.server_name
                 # Optional: Try to read a test point if needed, but connection open is usually enough
             
             return jsonify({'status': 'Connected', 'server': server_name})
        except Exception as pi_err:
             print(f"PI Connect Error: {pi_err}")
             return jsonify({'status': 'Offline', 'message': str(pi_err)})

    except Exception as e:
        import traceback
        print(f"PI Status Error: {e}")
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/get_tag_value')
def get_tag_value():
    tag_param = request.args.get('tag')
    if not tag_param:
        return jsonify({'error': 'No tag provided'}), 400
    
    tags = [t.strip() for t in tag_param.split(';') if t.strip()]
    results = []
    
    # Lazy Load PI
    is_pi_ready = lazy_load_pi()

    if is_pi_ready and PI:
        try:
             # Optimization: Connect ONCE, then loop through tags
             with PI.PIServer() as server:
                 for tag_name in tags:
                     try:
                         # Use server.search to find point, then get value
                         # Note: Optimally we would use PIServers return multiple points, but PIconnect usage here is simple
                         # Assuming server.search returns a list of PIPoint
                         points = server.search(tag_name)
                         if points:
                             point = points[0]
                             value = point.current_value
                             results.append({'tag': tag_name, 'value': value, 'timestamp': datetime.datetime.now().isoformat(), 'source': 'PI Server'})
                         else:
                             results.append({'tag': tag_name, 'value': 'Not Found', 'timestamp': datetime.datetime.now().isoformat(), 'source': 'PI Server'})
                     except Exception as tag_err:
                         results.append({'tag': tag_name, 'value': 'Error', 'timestamp': datetime.datetime.now().isoformat(), 'source': 'PI Server (Error)'})
        except Exception as conn_err:
             # If server connection fails entirely
             for tag_name in tags:
                 results.append({'tag': tag_name, 'value': 'Connection Error', 'timestamp': datetime.datetime.now().isoformat(), 'source': 'PI Server (Offline)', 'error': str(conn_err)})
    else:
        for tag_name in tags:
             results.append({'tag': tag_name, 'value': 'Offline', 'timestamp': datetime.datetime.now().isoformat(), 'source': 'System (PI Mode: Off)'})
            
    return jsonify(results)

# --- Embedded Frontend ---

# 2. Add IIS Middleware (Handle sub-path issue)
class IISMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Set your IIS Application Alias
        script_name = '/DigitalSOP' 
        
        # Force SCRIPT_NAME so url_for generates correct paths
        environ['SCRIPT_NAME'] = script_name
        
        # Check if PATH_INFO contains the prefix and strip it if needed
        path = environ.get('PATH_INFO', '')
        if path.startswith(script_name):
            environ['PATH_INFO'] = path[len(script_name):]
            
        return self.app(environ, start_response)

# Apply Middleware
# Apply Middleware
app.wsgi_app = IISMiddleware(app.wsgi_app)

# Initialize Database (Must run on import for IIS)
# Initialize Database (Must run on import for IIS)
try:
    init_db()
except Exception as e:
    print(f"Database initialization failed: {e}")

if __name__ == '__main__':
    # Ensure static folder exists
    if not os.path.exists('static'):
        print("WARNING: 'static' folder not found. Please run download_assets.ps1 first.")
    app.run(debug=True, port=5000, host='0.0.0.0')
