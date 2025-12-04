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

# --- Configuration ---
app = Flask(__name__, static_folder='static')
CORS(app)

# 1. Use absolute path (Avoid IIS file not found error)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'sops.db')

# --- PIconnect Integration (Mock Fallback) ---
PI = None
try:
    import PIconnect as PI
    PI_AVAILABLE = True
    # PI.PIConfig.DEFAULT_SERVER_NAME = "MyPIServer" # Uncomment and set if needed
except ImportError:
    PI_AVAILABLE = False
    print("PIconnect not found. PI Server Offline.")
except Exception as e:
    PI_AVAILABLE = False
    print(f"PIconnect initialization failed: {e}. PI Server Offline.")

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
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
    conn.close()

# --- Routes ---

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/processes', methods=['GET'])
def get_processes():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT p.id, p.name, p.updated_at, s.is_finished 
        FROM processes p 
        LEFT JOIN sessions s ON p.id = s.process_id 
        ORDER BY p.updated_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    # is_finished: None (no session), 0 (running), 1 (finished)
    return jsonify([{'id': r[0], 'name': r[1], 'updated_at': r[2], 'session_status': r[3]} for r in rows])

@app.route('/api/processes/<int:process_id>', methods=['GET'])
def get_process(process_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, xml_content, updated_at FROM processes WHERE id=?", (process_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify({'id': row[0], 'name': row[1], 'xml_content': row[2], 'updated_at': row[3]})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/processes', methods=['POST'])
def save_process():
    data = request.json
    name = data.get('name')
    xml_content = data.get('xml_content')
    
    
    conn = sqlite3.connect(DB_FILE)
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
             conn.close()
             return jsonify({'error': 'Nothing to update'}), 400
    else:
        if not name or not xml_content:
            conn.close()
            return jsonify({'error': 'Missing name or xml_content'}), 400
        c.execute("INSERT INTO processes (name, xml_content) VALUES (?, ?)", (name, xml_content))
        process_id = c.lastrowid
        
    conn.commit()
    conn.close()
    return jsonify({'id': process_id, 'message': 'Saved successfully'})

@app.route('/api/processes/<int:process_id>', methods=['DELETE'])
def delete_process(process_id):
    conn = sqlite3.connect(DB_FILE)
    conn.execute('DELETE FROM processes WHERE id = ?', (process_id,))
    conn.execute('DELETE FROM sessions WHERE process_id = ?', (process_id,))
    conn.commit()
    conn.close()
    return jsonify({'result': 'success'})

@app.route('/api/sessions/<int:process_id>', methods=['GET'])
def get_session(process_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Get the latest session
        c.execute("SELECT current_task_id, logs, is_finished FROM sessions WHERE process_id=? ORDER BY updated_at DESC LIMIT 1", (process_id,))
        row = c.fetchone()
        conn.close()
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
    
    conn = sqlite3.connect(DB_FILE)
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
    conn.close()
    return jsonify({'result': 'success'})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='pi_server_ip'")
    row = c.fetchone()
    conn.close()
    return jsonify({'pi_server_ip': row[0] if row else ''})
@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    ip = data.get('pi_server_ip')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pi_server_ip', ?)", (ip,))
    conn.commit()
    conn.close()
    return jsonify({'result': 'success'})

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    process_id = data.get('process_id')
    user_id = data.get('user_id')
    
    if not process_id or not user_id:
        return jsonify({'error': 'Missing params'}), 400
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Upsert heartbeat
    c.execute("INSERT OR REPLACE INTO active_users (process_id, user_id, last_heartbeat) VALUES (?, ?, CURRENT_TIMESTAMP)", (process_id, user_id))
    
    # Remove old heartbeats (> 30 seconds)
    c.execute("DELETE FROM active_users WHERE last_heartbeat < datetime('now', '-30 seconds')")
    
    # Count online users for this process
    c.execute("SELECT COUNT(DISTINCT user_id) FROM active_users WHERE process_id=?", (process_id,))
    count = c.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return jsonify({'online_count': count})

@app.route('/api/pi_status', methods=['GET'])
def get_pi_status():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='pi_server_ip'")
    row = c.fetchone()
    conn.close()
    
    ip = row[0] if row else ''
    if not ip:
        return jsonify({'status': 'Not Configured'})
        
    # Ping Check
    try:
        # -n 1 for Windows, -c 1 for Linux/Mac
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', ip]
        
        # Run ping command
        # creationflags=0x08000000 is CREATE_NO_WINDOW to hide console window on Windows
        if platform.system().lower() == 'windows':
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=0x08000000)
        else:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            return jsonify({'status': 'Connected'})
        else:
            return jsonify({'status': 'Offline'})
    except Exception as e:
        print(f"Ping failed: {e}")
        return jsonify({'status': 'Offline'})

@app.route('/api/get_tag_value')
def get_tag_value():
    tag_param = request.args.get('tag')
    if not tag_param:
        return jsonify({'error': 'No tag provided'}), 400
    
    tags = [t.strip() for t in tag_param.split(';') if t.strip()]
    results = []
    
    for tag_name in tags:
        if PI_AVAILABLE:
            try:
                with PI.PIServer() as server:
                    point = server.search(tag_name)[0]
                    value = point.current_value
                    results.append({'tag': tag_name, 'value': value, 'timestamp': datetime.datetime.now().isoformat(), 'source': 'PI Server'})
            except Exception as e:
                results.append({'tag': tag_name, 'value': 'Error', 'timestamp': datetime.datetime.now().isoformat(), 'source': 'PI Server (Error)'})
        else:
            results.append({'tag': tag_name, 'value': 'Offline', 'timestamp': datetime.datetime.now().isoformat(), 'source': 'System'})
            
    return jsonify(results)

# --- Embedded Frontend ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>數位流程指引系統</title>
    
    <!-- Local Static Assets -->
    <script src="{{ url_for('static', filename='js/tailwindcss.js') }}"></script>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/diagram-js.css') }}" />
    <link rel="stylesheet" href="{{ url_for('static', filename='css/bpmn.css') }}" />
    
    <!-- React & Babel -->
    <script src="{{ url_for('static', filename='js/react.js') }}"></script>
    <script src="{{ url_for('static', filename='js/react-dom.js') }}"></script>
    <script src="{{ url_for('static', filename='js/babel.js') }}"></script>
    
    <!-- BPMN-JS -->
    <script src="{{ url_for('static', filename='js/bpmn-modeler.js') }}"></script>
    
    <style>
        /* Google Material Dark Theme Variables */
        :root {
            --md-sys-color-background: #121212;
            --md-sys-color-surface: #1e1e1e;
            --md-sys-color-surface-variant: #2d2d2d;
            --md-sys-color-primary: #8ab4f8; /* Google Blue 200 */
            --md-sys-color-on-primary: #002d6f;
            --md-sys-color-secondary: #e8eaed;
            --md-sys-color-error: #f28b82; /* Red 200 */
            --md-sys-color-success: #81c995; /* Green 200 */
            --md-sys-color-on-surface: #e3e3e3;
            --md-sys-color-on-surface-variant: #c4c7c5;
            --md-sys-color-outline: #8e918f;
        }

        body { 
            font-family: 'Roboto', 'Inter', sans-serif; 
            background-color: var(--md-sys-color-background);
            color: var(--md-sys-color-on-surface);
        }
        
        .bpmn-container { 
            height: 100%; 
            width: 100%; 
            background: #fff; /* Canvas remains white for contrast */
            color: #1e293b; 
        }
        .bjs-powered-by { display: none; }
        
        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: var(--md-sys-color-background); }
        ::-webkit-scrollbar-thumb { background: var(--md-sys-color-surface-variant); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--md-sys-color-outline); }

        /* --- BPMN Editor Fixes --- */
        
        /* 3. Fix Context Pad (Quick Tools) Visibility */
        .djs-context-pad .entry {
            background-color: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            margin: 2px;
            width: 30px;
            height: 30px;
            display: flex;
            justify-content: center;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: all 0.2s;
        }
        
        .djs-context-pad .entry:hover {
            background-color: #eff6ff !important; /* Blue-50 */
            border-color: #3b82f6;
            transform: scale(1.1);
        }
        
        /* Force icon color to be dark */
        .djs-context-pad .entry i,
        .djs-context-pad .entry::before {
            color: #1e293b !important;
            opacity: 1 !important;
            font-size: 18px !important;
        }
        
        /* 1. Fix Direct Editing Text Color (was too pale on white canvas) */
        .djs-direct-editing-parent, 
        .djs-direct-editing-content {
            color: #000000 !important;
            background: #ffffff !important;
        }

        /* 2. Redesign Palette (Vertical 2-Columns + Drag Handle) */
        .djs-palette {
            width: 80px !important;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            position: absolute; /* Ensure it's absolute for dragging */
            top: 20px;
            left: 20px;
            user-select: none;
        }
        
        /* The Drag Handle */
        .palette-handle {
            height: 16px;
            background: #475569;
            cursor: move;
            border-radius: 3px 3px 0 0;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .palette-handle::after {
            content: "::::";
            color: #94a3b8;
            font-size: 10px;
            letter-spacing: 2px;
            line-height: 10px;
        }
        
        .djs-palette .djs-palette-entries {
            display: flex;
            flex-wrap: wrap;
            padding: 4px;
        }
        
        /* Target groups to ensure they flow */
        .djs-palette .group {
            width: 100%;
            display: flex;
            flex-wrap: wrap;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 4px;
            padding-bottom: 4px;
        }
        .djs-palette .group:last-child {
            border-bottom: none;
        }
        
        .djs-palette .entry {
            width: 50% !important;
            float: none !important;
            margin: 0 !important;
            height: 36px !important;
            display: flex !important;
            justify-content: center;
            align-items: center;
        }
        .djs-palette .separator {
            display: none !important;
        }

        /* Operator & Review Mode Specifics */
        .operator-mode .djs-palette,
        .operator-mode .djs-context-pad,
        .operator-mode .palette-handle,
        .review-mode .djs-palette,
        .review-mode .djs-context-pad,
        .review-mode .palette-handle {
            display: none !important;
        }

        /* Active Task Highlight */
        @keyframes blink {
            0% { opacity: 0.4; stroke-width: 4px; }
            50% { opacity: 1; stroke-width: 6px; }
            100% { opacity: 0.4; stroke-width: 4px; }
        }
        .djs-element.highlight .djs-visual > :nth-child(1) {
            stroke: #8ab4f8 !important; /* Google Blue 200 */
            stroke-width: 4px !important;
            fill: rgba(138, 180, 248, 0.1) !important;
            filter: drop-shadow(0 0 8px rgba(138, 180, 248, 0.6));
            animation: blink 1.5s infinite ease-in-out;
        }
        
        /* Completed Task Style */
        .djs-element.completed-task .djs-visual > :nth-child(1) {
            fill: #81c995 !important; /* Green fill matching timeline */
            stroke: #0f5132 !important;
        }

        /* Fix Element Template/Context Menu Popup Colors */
        .djs-popup {
            background: #1e1e1e !important;
            border: 1px solid #444 !important;
            color: #e3e3e3 !important;
        }
        .djs-popup .entry {
            color: #e3e3e3 !important;
        }
        .djs-popup .entry:hover {
            background-color: #333 !important;
            color: #fff !important;
        }
        .djs-popup-header {
            border-bottom: 1px solid #444 !important;
        }
        .djs-popup-body .entry.active {
            background-color: #333 !important;
        }

        /* Operator Mode Cursor Overrides */
        .operator-mode .djs-hit,
        .operator-mode .djs-visual rect, 
        .operator-mode .djs-visual circle, 
        .operator-mode .djs-visual polygon, 
        .operator-mode .djs-visual path,
        .operator-mode .djs-element { cursor: default !important; }
        
        .operator-mode .djs-element.has-hyperlink .djs-hit,
        .operator-mode .djs-element.has-hyperlink .djs-visual * { cursor: pointer !important; }
        
        .operator-mode .djs-cursor-move { cursor: default !important; } /* Disable crosshair */
        .operator-mode .djs-element:hover .djs-outline { stroke-width: 2px; stroke: #8ab4f8; } /* Optional hover effect */
        
        /* Review Mode Cursor Overrides */
        .review-mode .djs-hit,
        .review-mode .djs-visual rect, 
        .review-mode .djs-visual circle, 
        .review-mode .djs-visual polygon, 
        .review-mode .djs-visual path,
        .review-mode .djs-element { cursor: default !important; }
        
        .review-mode .djs-cursor-move { cursor: default !important; }
    </style>
</head>
<body class="h-screen overflow-hidden">
    <div id="root" class="h-full"></div>

    <script type="text/babel">
        const { useState, useEffect, useRef, useMemo, useCallback } = React;

        // --- Utils ---
        const API_BASE = "{{ url_for('index') }}api";
        
        // --- Draggable Palette Logic ---
        const makePaletteDraggable = (container) => {
            const checkExist = setInterval(() => {
                const palette = container.querySelector('.djs-palette');
                if (palette) {
                    clearInterval(checkExist);
                    if (!palette.querySelector('.palette-handle')) {
                        const handle = document.createElement('div');
                        handle.className = 'palette-handle';
                        palette.prepend(handle);
                        let isDragging = false;
                        let startX, startY, initialLeft, initialTop;
                        handle.addEventListener('mousedown', (e) => {
                            isDragging = true;
                            startX = e.clientX;
                            startY = e.clientY;
                            const rect = palette.getBoundingClientRect();
                            initialLeft = rect.left;
                            initialTop = rect.top;
                            e.preventDefault();
                        });
                        const onMouseMove = (e) => {
                            if (!isDragging) return;
                            const dx = e.clientX - startX;
                            const dy = e.clientY - startY;
                            palette.style.left = `${initialLeft + dx}px`;
                            palette.style.top = `${initialTop + dy}px`;
                            palette.style.right = 'auto';
                            palette.style.bottom = 'auto';
                        };
                        const onMouseUp = () => { isDragging = false; };
                        document.addEventListener('mousemove', onMouseMove);
                        document.addEventListener('mouseup', onMouseUp);
                    }
                }
            }, 500);
        };

        // --- New Components ---

        // Timeline Viewer
        const TimelineViewer = ({ logs, headerActions, onUpdateLog }) => {
            const scrollRef = useRef(null);
            
            useEffect(() => {
                if (scrollRef.current) {
                    scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
                }
            }, [logs]);

            return (
                <div className="h-full w-full bg-[#1e1e1e] border-b border-white/10 flex flex-col">
                    <div className="px-6 py-2 border-b border-white/5 flex justify-between items-center bg-[#252525]">
                        <div className="flex items-center gap-4">
                            <h3 className="text-sm font-medium text-white/70 uppercase tracking-wider mr-4">操作紀錄 Timeline</h3>
                            <div className="flex items-center gap-3 text-xs">
                                <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#8ab4f8]"></div><span className="text-white/60">任務開始</span></div>
                                <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[#81c995]"></div><span className="text-white/60">任務完成</span></div>
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            <span className="text-xs text-white/30">{logs.length} 筆紀錄</span>
                            {headerActions}
                        </div>
                    </div>
                    <div ref={scrollRef} className="flex-1 overflow-x-auto overflow-y-hidden flex items-start px-6 gap-8 scrollbar-thin pt-4 pb-8" onWheel={(e) => {
                        if (scrollRef.current) {
                            scrollRef.current.scrollLeft += e.deltaY;
                        }
                    }}>
                        {logs.length === 0 && (
                            <div className="text-white/20 text-sm italic w-full text-center">尚無操作紀錄...</div>
                        )}
                        {logs.map((log, idx) => (
                            <div key={idx} className="relative flex flex-col items-center min-w-[120px] group">
                                {/* Connector Line */}
                                {idx < logs.length - 1 && (
                                    <div className="absolute top-[18px] left-[50%] w-[calc(100%+32px)] h-[2px] bg-white/10 -z-0"></div>
                                )}
                                
                                {/* Node Circle */}
                                <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold z-10 mb-2 shadow-lg transition-transform group-hover:scale-110 ${
                                    log.message.includes('任務完成') ? 'bg-[#81c995] text-[#0f5132]' : 'bg-[#8ab4f8] text-[#002d6f]'
                                }`}>
                                    {idx + 1}
                                </div>
                                
                                <div className="text-xs text-white/50 mt-1">{log.time}</div>
                                <div className="text-sm font-medium text-white/90 mt-1 text-center px-2">{log.message.split(': ')[1] || log.message}</div>
                                
                                {/* Indicators Container */}
                                <div className="flex gap-2 mt-2">
                                    {/* Note Indicator */}
                                    {log.note && (
                                        <div 
                                            className="text-xs text-[#fbbc04] font-bold cursor-pointer animate-pulse hover:scale-110 transition border border-[#fbbc04]/30 px-2 py-0.5 rounded bg-[#fbbc04]/10"
                                            title={log.note}
                                            onClick={() => {
                                                if (onUpdateLog) {
                                                    const newNote = prompt('編輯備註:', log.note);
                                                    if (newNote !== null) {
                                                        onUpdateLog(idx, newNote);
                                                    }
                                                }
                                            }}
                                        >
                                            備註
                                        </div>
                                    )}

                                    {/* Data Indicator */}
                                    {log.value && log.value !== '-' && log.value !== '"-"' && (
                                        <div 
                                            className="text-xs text-[#81c995] font-bold cursor-help hover:scale-110 transition border border-[#81c995]/30 px-2 py-0.5 rounded bg-[#81c995]/10"
                                            title={log.value}
                                        >
                                            數據
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            );
        };

        
        // --- Components ---
        
        // Floating Task Window
        const FloatingTaskWindow = ({ task, onStart, onEnd, onFinish, onClose, note, setNote, tagValues, loadingTag }) => {
            if (!task) return null;

            const isRunning = task.status === 'running';
            const isCompleted = task.status === 'completed';
            const isEndEvent = task.type === 'bpmn:EndEvent';

            return (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
                    <div 
                        className="bg-[#1e1e1e] border border-white/10 rounded-2xl shadow-2xl w-[400px] overflow-hidden animate-scale-in"
                        onClick={e => e.stopPropagation()}
                    >
                        {/* Header */}
                        <div className="px-6 py-4 border-b border-white/10 flex justify-between items-center bg-[#252525]">
                            <h3 className="text-lg font-bold text-white/90">{task.name}</h3>
                            <button onClick={onClose} className="text-white/40 hover:text-white transition">✕</button>
                        </div>

                        {/* Body */}
                        <div className="p-6">
                            {/* PI Data Section */}
                            {task.tag && (
                                <div className="mb-6 bg-[#121212] rounded-xl p-4 border border-white/5">
                                    <div className="text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">即時數據 (PI Tag)</div>
                                    {loadingTag ? (
                                        <div className="text-white/40 text-sm animate-pulse">讀取中...</div>
                                    ) : (
                                        <div className="grid gap-2">
                                            {tagValues.map((tv, idx) => (
                                                <div key={idx} className="flex justify-between items-end">
                                                    <span className="text-white/60 text-sm">{tv.tag}</span>
                                                    <span className="text-[#81c995] font-mono font-bold">
                                                        {tv.value !== undefined ? Number(tv.value).toFixed(task.precision) : '-'} <span className="text-sm text-white/40">{task.unit}</span>
                                                    </span>
                                                </div>
                                            ))}
                                            {tagValues.length === 0 && <div className="text-white/30 text-sm">無數據</div>}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Note Section */}
                            <div className="mb-6">
                                <label className="block text-xs font-medium text-white/60 mb-2 uppercase tracking-wider">備註 / 紀錄</label>
                                <textarea 
                                    value={note}
                                    onChange={e => setNote(e.target.value)}
                                    className="w-full bg-[#2d2d2d] border border-white/10 rounded-xl p-3 text-white focus:border-[#8ab4f8] outline-none h-24 text-sm resize-none"
                                    placeholder="輸入操作備註..."
                                    disabled={isCompleted}
                                />
                            </div>

                            {/* Actions */}
                            <div className="flex gap-3">
                                {isEndEvent ? (
                                     <button 
                                        onClick={onFinish}
                                        className="w-full py-3 rounded-xl font-medium bg-[#f28b82] hover:bg-[#f6aea9] text-[#5c1e1e] transition shadow-lg shadow-red-500/20"
                                    >
                                        結束流程
                                    </button>
                                ) : (
                                    <>
                                        {!isRunning && !isCompleted && (
                                            <button 
                                                onClick={onStart}
                                                className="w-full py-3 rounded-xl font-medium bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] transition shadow-lg shadow-blue-500/20"
                                            >
                                                開始任務
                                            </button>
                                        )}
                                        
                                        {isRunning && (
                                            <button 
                                                onClick={onEnd}
                                                className="w-full py-3 rounded-xl font-medium bg-[#81c995] hover:bg-[#a8dab5] text-[#0f5132] transition shadow-lg shadow-green-500/20"
                                            >
                                                完成任務
                                            </button>
                                        )}

                                        {isCompleted && (
                                            <div className="w-full py-3 rounded-xl font-medium bg-[#2d2d2d] text-white/40 text-center border border-white/5 cursor-not-allowed">
                                                此任務已完成
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            );
        };

        // 1. Dashboard
        const Dashboard = ({ onNavigate }) => {
            const [processes, setProcesses] = useState([]);
            const [piStatus, setPiStatus] = useState('Checking...');
            const [editingId, setEditingId] = useState(null);
            const [editName, setEditName] = useState('');
            
            useEffect(() => {
                fetch(`${API_BASE}/processes`)
                    .then(res => res.json())
                    .then(data => setProcesses(data));
                
                checkStatus();
            }, []);

            const checkStatus = () => {
                fetch(`${API_BASE}/pi_status`)
                    .then(res => res.json())
                    .then(data => setPiStatus(data.status));
            };

            const startEditing = (p) => {
                setEditingId(p.id);
                setEditName(p.name);
            };

            const saveName = async (id) => {
                if (!editName.trim()) return;
                await fetch(`${API_BASE}/processes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id, name: editName })
                });
                setEditingId(null);
                // Refresh
                const res = await fetch(`${API_BASE}/processes`);
                setProcesses(await res.json());
            };

            const handleDelete = (id) => {
                if(confirm('確定要刪除嗎？')) {
                    fetch(`${API_BASE}/processes/${id}`, { method: 'DELETE' })
                        .then(() => setProcesses(processes.filter(p => p.id !== id)));
                }
            };

            const handleExport = (p) => {
                const blob = new Blob([p.xml_content], { type: 'text/xml' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${p.name || 'process'}.bpmn`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            };

            const handleImport = (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const text = e.target.result;
                    if (!text.includes('bpmndi:BPMNDiagram')) {
                        alert('匯入失敗：此 BPMN 檔案缺少圖形佈局資訊 (BPMNDiagram)，無法顯示。');
                        return;
                    }
                    const name = file.name.replace('.bpmn', '').replace('.xml', '');
                    await fetch(`${API_BASE}/processes`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, xml_content: text })
                    });
                    // Refresh
                    const res = await fetch(`${API_BASE}/processes`);
                    setProcesses(await res.json());
                };
                reader.readAsText(file);
            };

            return (
                <div className="p-8 max-w-7xl mx-auto h-full overflow-y-auto">
                    <div className="flex justify-between items-center mb-10 sticky top-0 bg-[#121212] z-10 py-4 border-b border-white/5">
                        <div className="flex items-center gap-4">
                            <div className="w-10 h-10 bg-blue-500/20 rounded-full flex items-center justify-center text-blue-300 font-bold text-xl">S</div>
                            <h1 className="text-2xl font-medium tracking-wide text-white/90">數位流程指引系統</h1>
                        </div>
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('editor')} className="bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-6 py-2 rounded-full font-medium shadow-sm transition flex items-center gap-2">
                                <span className="text-xl leading-none">+</span>
                                <span>新增流程</span>
                            </button>
                            <label className="cursor-pointer bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 px-5 py-2 rounded-full text-sm transition flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                                </svg>
                                <span>匯入 BPMN 流程</span>
                                <input type="file" accept=".bpmn,.xml" className="hidden" onChange={handleImport} />
                            </label>
                            <div className="flex items-center gap-2 bg-[#1e1e1e] px-4 py-2 rounded-full border border-white/5">
                                <div className={`w-2 h-2 rounded-full ${piStatus === 'Connected' ? 'bg-[#81c995] animate-pulse' : piStatus === 'Not Configured' ? 'bg-gray-400' : 'bg-[#f28b82]'}`}></div>
                                <span className="text-sm text-white/70">
                                    {piStatus === 'Connected' ? 'PI Server 連線正常' : 
                                     piStatus === 'Not Configured' ? '未設定 PI Server' : 'PI Server 離線'}
                                </span>
                            </div>
                            <button onClick={() => onNavigate('settings')} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 p-2 rounded-full transition" title="設定">
                                <span className="text-xl">⚙️</span>
                            </button>
                        </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {processes.map(p => {
                            const isRunning = p.session_status === 0;
                            return (
                                <div key={p.id} className={`bg-[#1e1e1e] p-6 rounded-2xl border transition-all duration-200 flex flex-col group ${isRunning ? 'border-[#81c995]/50 shadow-[0_4px_20px_rgba(129,201,149,0.1)]' : 'border-white/5 hover:border-white/20 hover:shadow-lg'}`}>
                                    <div className="flex-1 mb-6">
                                        <div className="flex justify-between items-start mb-3 h-8">
                                            {editingId === p.id ? (
                                                <div className="flex items-center gap-1 w-full">
                                                    <input 
                                                        type="text" 
                                                        value={editName} 
                                                        onChange={e => setEditName(e.target.value)}
                                                        className="bg-[#2d2d2d] text-white px-2 py-1 rounded border border-white/10 focus:border-[#8ab4f8] outline-none text-sm w-full"
                                                        autoFocus
                                                        onKeyDown={e => { if(e.key === 'Enter') saveName(p.id); else if(e.key === 'Escape') setEditingId(null); }}
                                                    />
                                                    <button onClick={() => saveName(p.id)} className="text-[#81c995] hover:text-green-400 px-1">✓</button>
                                                    <button onClick={() => setEditingId(null)} className="text-[#f28b82] hover:text-red-400 px-1">✕</button>
                                                </div>
                                            ) : (
                                                <div className="flex items-center gap-2 group/title w-full">
                                                    <h3 className="text-lg font-medium text-white/90 group-hover:text-[#8ab4f8] transition-colors truncate" title={p.name}>{p.name}</h3>
                                                    <button 
                                                        onClick={(e) => { e.stopPropagation(); startEditing(p); }}
                                                        className="opacity-0 group-hover/title:opacity-100 text-white/40 hover:text-[#8ab4f8] transition"
                                                        title="重新命名"
                                                    >
                                                        ✎
                                                    </button>
                                                </div>
                                            )}
                                            {isRunning && <span className="bg-[#81c995]/20 text-[#81c995] text-xs px-3 py-1 rounded-full font-medium ml-2 whitespace-nowrap">執行中</span>}
                                        </div>
                                        <p className="text-white/40 text-xs">最後編輯: {p.updated_at}</p>
                                    </div>
                                    
                                    <div className="grid grid-cols-2 gap-3 mb-3">
                                        <button onClick={() => onNavigate('operator', p.id)} className={`col-span-2 py-2.5 rounded-full text-sm font-medium transition ${isRunning ? 'bg-[#81c995] text-[#0f5132] hover:bg-[#a8dab5]' : 'bg-[#8ab4f8] text-[#002d6f] hover:bg-[#aecbfa]'}`}>
                                            {isRunning ? '繼續執行' : '開始執行'}
                                        </button>
                                        <button 
                                            onClick={() => !isRunning && onNavigate('editor', p.id)} 
                                            disabled={isRunning}
                                            className={`py-2 rounded-full text-sm transition ${isRunning ? 'bg-[#2d2d2d] text-white/20 cursor-not-allowed' : 'bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80'}`}
                                        >
                                            編輯
                                        </button>
                                        <button onClick={() => onNavigate('review', p.id)} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 py-2 rounded-full text-sm transition">回顧</button>
                                    </div>
                                    
                                    <div className="flex gap-2 pt-3 border-t border-white/5">
                                        <button onClick={() => handleExport(p)} className="flex-1 text-xs text-white/40 hover:text-[#8ab4f8] py-1 transition">匯出 BPMN</button>
                                        <button onClick={() => handleDelete(p.id)} className="flex-1 text-xs text-white/40 hover:text-[#f28b82] py-1 transition">刪除</button>
                                    </div>
                                </div>
                            );
                        })}
                        {processes.length === 0 && (
                            <div className="col-span-full flex flex-col items-center justify-center py-20 text-white/30 border-2 border-dashed border-white/10 rounded-3xl">
                                <div className="text-6xl mb-4">📂</div>
                                <p>尚無 SOP 流程，請點擊右上角新增或匯入。</p>
                            </div>
                        )}
                    </div>
                </div>
            );
        };

        // 2. Editor
        const Editor = ({ processId, onNavigate }) => {
            const containerRef = useRef(null);
            const modelerRef = useRef(null);
            const [name, setName] = useState('New Process');
            const [selectedElement, setSelectedElement] = useState(null);
            const [piTag, setPiTag] = useState('');
            const [piUnit, setPiUnit] = useState('');
            const [piPrecision, setPiPrecision] = useState(2);
            const [targetUrl, setTargetUrl] = useState('');
            const [elementName, setElementName] = useState('');
            const [alwaysOn, setAlwaysOn] = useState(false);
            
            // Text Annotation Styles
            const [textFontSize, setTextFontSize] = useState(12);
            const [textBold, setTextBold] = useState(false);
            const [textColor, setTextColor] = useState('#000000');
            const [textBgColor, setTextBgColor] = useState('transparent');
            const [nameFontSize, setNameFontSize] = useState(12); // New State for Name Font Size

            // Sticky Note State
            const [noteColor, setNoteColor] = useState('#fff2cc'); // Default Post-it Yellow
            const [borderColor, setBorderColor] = useState('#d6b656');
            const [noteOpacity, setNoteOpacity] = useState(1);
            const [htmlContent, setHtmlContent] = useState(''); // Store HTML content for sticky notes

            const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
            const [isFinalEnd, setIsFinalEnd] = useState(false);
            const [isPanelOpen, setIsPanelOpen] = useState(true); // 1. Collapsible Panel State
            const isComposing = useRef(false); // Track IME composition state

            const GOOGLE_COLORS = [
                '#EA4335', '#E91E63', '#9C27B0', '#673AB7', '#3F51B5', '#4285F4', '#03A9F4', 
                '#00BCD4', '#009688', '#34A853', '#8BC34A', '#CDDC39', '#FBBC05', '#FF9800'
            ];

            useEffect(() => {
                const modeler = new BpmnJS({ container: containerRef.current, keyboard: { bindTo: document } });
                modelerRef.current = modeler;
                makePaletteDraggable(containerRef.current);

                const loadDiagram = async () => {
                    let xml = '';
                    if (processId) {
                        const res = await fetch(`${API_BASE}/processes/${processId}`);
                        const data = await res.json();
                        setName(data.name);
                        xml = data.xml_content;
                    } else {
                        xml = `<?xml version="1.0" encoding="UTF-8"?><bpmn:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn"><bpmn:process id="Process_1" isExecutable="false"><bpmn:startEvent id="StartEvent_1"/></bpmn:process><bpmndi:BPMNDiagram id="BPMNDiagram_1"><bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1"><bpmndi:BPMNShape id="_BPMNShape_StartEvent_2" bpmnElement="StartEvent_1"><dc:Bounds x="173" y="102" width="36" height="36"/></bpmndi:BPMNShape></bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>`;
                    }
                    try { 
                        await modeler.importXML(xml); 
                        modeler.get('canvas').zoom('fit-viewport'); 
                        setHasUnsavedChanges(false); // Reset after load
                        
                        // Inject Custom Tools into Palette
                        setTimeout(() => {
                            const palette = containerRef.current.querySelector('.djs-palette-entries');
                            if (palette && !palette.querySelector('.custom-sticky-tool')) {
                                const group = document.createElement('div');
                                group.className = 'group custom-sticky-tool';
                                
                                const entry = document.createElement('div');
                                entry.className = 'entry';
                                entry.innerHTML = '<div style="font-family: serif; font-weight: bold; font-size: 18px;">T</div>';
                                entry.title = '新增便利貼';
                                entry.style.cursor = 'pointer';
                                entry.draggable = true;
                                
                                const createNote = (e) => {
                                    const elementFactory = modeler.get('elementFactory');
                                    const create = modeler.get('create');
                                    const bpmnFactory = modeler.get('bpmnFactory');
                                    
                                    const shape = elementFactory.createShape({ type: 'bpmn:Group' });
                                    const newDoc = bpmnFactory.create('bpmn:Documentation', { 
                                        text: JSON.stringify({ 
                                            noteColor: '#fff2cc', borderColor: '#d6b656', text: 'New Note', htmlContent: 'New Note'
                                        }) 
                                    });
                                    shape.businessObject.documentation = [newDoc];
                                    shape.width = 200; shape.height = 200;
                                    create.start(e, shape);
                                };

                                entry.addEventListener('click', createNote);
                                entry.addEventListener('dragstart', createNote);
                                
                                group.appendChild(entry);
                                palette.appendChild(group);
                            }
                        }, 500);

                    } catch (err) { console.error(err); }
                };
                loadDiagram();

                modeler.on('selection.changed', (e) => {
                    const selection = e.newSelection;
                    if (selection.length === 1) {
                        setIsPanelOpen(true); // Auto-open panel
                        const element = selection[0];
                        setSelectedElement(element);
                        setElementName(element.businessObject.name || '');
                        const docs = element.businessObject.documentation;
                        if (docs && docs.length > 0 && docs[0].text) {
                            try { 
                                const data = JSON.parse(docs[0].text);
                                setPiTag(data.piTag || ''); 
                                setPiUnit(data.piUnit || '');
                                setPiPrecision(data.piPrecision !== undefined ? data.piPrecision : 2);
                                setTargetUrl(data.targetUrl || '');
                                setIsFinalEnd(data.isFinalEnd || false);
                                setAlwaysOn(data.alwaysOn || false);
                                
                                // Load Text Styles
                                setTextFontSize(data.textFontSize || 12);
                                setTextBold(data.textBold || false);
                                setTextColor(data.textColor || '#000000');
                                setTextBgColor(data.textBgColor || 'transparent');
                                setNameFontSize(data.nameFontSize || 12);
                                
                                // Load Sticky Note Styles
                                setNoteColor(data.noteColor || '#fff2cc');
                                setBorderColor(data.borderColor || '#d6b656');
                                setNoteOpacity(data.noteOpacity !== undefined ? data.noteOpacity : 1);
                                setHtmlContent(data.htmlContent || '');
                            } catch(e) { 
                                setPiTag(''); setPiUnit(''); setPiPrecision(2); setTargetUrl(''); setIsFinalEnd(false); setAlwaysOn(false);
                                setTextFontSize(12); setTextBold(false); setTextColor('#000000'); setTextBgColor('transparent');
                                setNameFontSize(12);
                                setNoteColor('#fff2cc'); setBorderColor('#d6b656'); setNoteOpacity(1); setHtmlContent('');
                            }
                        } else { 
                            setPiTag(''); setPiUnit(''); setPiPrecision(2); setTargetUrl(''); setIsFinalEnd(false); setAlwaysOn(false);
                            setTextFontSize(12); setTextBold(false); setTextColor('#000000'); setTextBgColor('transparent');
                            setNameFontSize(12);
                            setNoteColor('#fff2cc'); setBorderColor('#d6b656'); setNoteOpacity(1); setHtmlContent('');
                        }
                    } else { 
                        setIsPanelOpen(false); // Auto-close panel
                        setSelectedElement(null); setElementName(''); setPiTag(''); setPiUnit(''); setPiPrecision(2); setTargetUrl(''); setIsFinalEnd(false); setAlwaysOn(false);
                        setTextFontSize(12); setTextBold(false); setTextColor('#000000'); setTextBgColor('transparent');
                        setNameFontSize(12);
                        setNoteColor('#fff2cc'); setBorderColor('#d6b656'); setNoteOpacity(1); setHtmlContent('');
                    }
                });
                
                modeler.on('element.changed', (e) => {
                    if (selectedElement && e.element.id === selectedElement.id) { setElementName(e.element.businessObject.name || ''); }
                });

                modeler.on('commandStack.changed', () => {
                    setHasUnsavedChanges(true);
                });

                // Disable Double Click for Sticky Notes (bpmn:Group)
                modeler.on('element.dblclick', 10000, (e) => {
                    if (e.element.type === 'bpmn:Group') {
                        return false; // Prevent default behavior (Label Editing)
                    }
                });

                // Mouse Wheel Zoom
                const handleWheel = (e) => {
                    e.preventDefault();
                    const canvas = modeler.get('canvas');
                    const currentZoom = canvas.zoom();
                    const factor = e.deltaY > 0 ? 0.995 : 1.005;
                    
                    const rect = containerRef.current.getBoundingClientRect();
                    const x = e.clientX - rect.left;
                    const y = e.clientY - rect.top;
                    
                    canvas.zoom(currentZoom * factor, { x, y });
                };
                
                const container = containerRef.current;
                container.addEventListener('wheel', handleWheel);

                return () => {
                    container.removeEventListener('wheel', handleWheel);
                    modeler.destroy();
                };
            }, [processId]);

            const handleBack = () => {
                if (hasUnsavedChanges) {
                    if (confirm('您有未儲存的變更，確定要離開嗎？')) {
                        onNavigate('dashboard');
                    }
                } else {
                    onNavigate('dashboard');
                }
            };

            const handleSave = async () => {
                const { xml } = await modelerRef.current.saveXML({ format: true });
                await fetch(`${API_BASE}/processes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: processId, name, xml_content: xml }) });
                setHasUnsavedChanges(false);
                alert('儲存成功！');
                // Do NOT navigate back
            };

            const createStickyNote = (e) => {
                if (!modelerRef.current) return;
                const elementFactory = modelerRef.current.get('elementFactory');
                const create = modelerRef.current.get('create');
                const bpmnFactory = modelerRef.current.get('bpmnFactory');
                
                const shape = elementFactory.createShape({ type: 'bpmn:Group' });
                
                // Init as Sticky Note
                const newDoc = bpmnFactory.create('bpmn:Documentation', { 
                    text: JSON.stringify({ 
                        noteColor: '#fff2cc',
                        borderColor: '#d6b656',
                        text: 'New Note',
                        htmlContent: 'New Note'
                    }) 
                });
                shape.businessObject.documentation = [newDoc];
                shape.width = 200; 
                shape.height = 200; 

                create.start(e.nativeEvent, shape);
            };

            const autoResizeElement = (element, text, fontSize, modeling) => {
                if (!text || !modeling) return;
                
                // 1. Measure Text
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                ctx.font = `bold ${fontSize}px Arial, sans-serif`;
                const metrics = ctx.measureText(text);
                const textWidth = metrics.width;
                
                let newWidth = element.width;
                let newHeight = element.height;
                let shouldResize = false;

                // 2. Task Resizing (Expand Width)
                if (element.type.includes('Task')) {
                    // Add padding
                    const requiredWidth = textWidth + 40;
                    if (requiredWidth > element.width) {
                        newWidth = requiredWidth;
                        shouldResize = true;
                    }
                }
                
                // 3. Pool/Lane Resizing (Disabled to prevent unwanted resizing)
                /*
                else if (element.type === 'bpmn:Participant' || element.type === 'bpmn:Lane') {
                    // Text is vertical, so Text Width -> Element Height
                    const requiredHeight = textWidth + 60;
                    if (requiredHeight > element.height) {
                        newHeight = requiredHeight;
                        shouldResize = true;
                    }
                }
                */

                if (shouldResize) {
                    modeling.resizeShape(element, {
                        x: element.x,
                        y: element.y,
                        width: newWidth,
                        height: newHeight
                    });
                }
            };

            const updateElementName = (val) => {
                setElementName(val);
                if (selectedElement && modelerRef.current) { 
                    const modeling = modelerRef.current.get('modeling');
                    modeling.updateLabel(selectedElement, val); 
                    autoResizeElement(selectedElement, val, nameFontSize, modeling);
                }
            };

            const updateElementProperties = (updates) => {
                const newData = {
                    piTag: updates.piTag !== undefined ? updates.piTag : piTag,
                    piUnit: updates.piUnit !== undefined ? updates.piUnit : piUnit,
                    piPrecision: updates.piPrecision !== undefined ? updates.piPrecision : piPrecision,
                    targetUrl: updates.targetUrl !== undefined ? updates.targetUrl : targetUrl,
                    isFinalEnd: updates.isFinalEnd !== undefined ? updates.isFinalEnd : isFinalEnd,
                    alwaysOn: updates.alwaysOn !== undefined ? updates.alwaysOn : alwaysOn,
                    textFontSize: updates.textFontSize !== undefined ? updates.textFontSize : textFontSize,
                    textBold: updates.textBold !== undefined ? updates.textBold : textBold,
                    textColor: updates.textColor !== undefined ? updates.textColor : textColor,
                    textBgColor: updates.textBgColor !== undefined ? updates.textBgColor : textBgColor,
                    nameFontSize: updates.nameFontSize !== undefined ? updates.nameFontSize : nameFontSize,
                    noteColor: updates.noteColor !== undefined ? updates.noteColor : noteColor,
                    borderColor: updates.borderColor !== undefined ? updates.borderColor : borderColor,
                    noteOpacity: updates.noteOpacity !== undefined ? updates.noteOpacity : noteOpacity,
                    htmlContent: updates.htmlContent !== undefined ? updates.htmlContent : htmlContent,
                };

                setPiTag(newData.piTag);
                setPiUnit(newData.piUnit);
                setPiPrecision(newData.piPrecision);
                setTargetUrl(newData.targetUrl);
                setIsFinalEnd(newData.isFinalEnd);
                setAlwaysOn(newData.alwaysOn);
                setTextFontSize(newData.textFontSize);
                setTextBold(newData.textBold);
                setTextColor(newData.textColor);
                setTextBgColor(newData.textBgColor);
                setNameFontSize(newData.nameFontSize);
                setNoteColor(newData.noteColor);
                setBorderColor(newData.borderColor);
                setNoteOpacity(newData.noteOpacity);
                setHtmlContent(newData.htmlContent);

                if (selectedElement && modelerRef.current) {
                    const modeling = modelerRef.current.get('modeling');
                    const bpmnFactory = modelerRef.current.get('bpmnFactory');
                    const elementRegistry = modelerRef.current.get('elementRegistry');

                    // If setting as Final End, uncheck others
                    if (newData.isFinalEnd && selectedElement.type === 'bpmn:EndEvent') {
                        const endEvents = elementRegistry.filter(e => e.type === 'bpmn:EndEvent' && e.id !== selectedElement.id);
                        let modified = false;
                        endEvents.forEach(e => {
                            const docs = e.businessObject.documentation;
                            if (docs && docs.length > 0 && docs[0].text) {
                                try {
                                    const d = JSON.parse(docs[0].text);
                                    if (d.isFinalEnd) {
                                        d.isFinalEnd = false;
                                        const newDoc = bpmnFactory.create('bpmn:Documentation', { text: JSON.stringify(d) });
                                        modeling.updateProperties(e, { documentation: [newDoc] });
                                        modified = true;
                                    }

                                } catch(err) {}
                            }
                        });
                        if (modified) alert('已移除其他 End Event 的最終標記，以此元件為主');
                    }

                    const newDoc = bpmnFactory.create('bpmn:Documentation', { 
                        text: JSON.stringify(newData) 
                    });
                    modeling.updateProperties(selectedElement, { documentation: [newDoc] });
                    
                    // Trigger Auto Resize
                    autoResizeElement(selectedElement, elementName, newData.nameFontSize, modeling);
                }
            };

            const getLightHex = (hex, factor = 0.2) => {
                const r = parseInt(hex.slice(1, 3), 16);
                const g = parseInt(hex.slice(3, 5), 16);
                const b = parseInt(hex.slice(5, 7), 16);
                
                const newR = Math.round(r + (255 - r) * (1 - factor));
                const newG = Math.round(g + (255 - g) * (1 - factor));
                const newB = Math.round(b + (255 - b) * (1 - factor));
                
                const toHex = (n) => {
                    const h = n.toString(16);
                    return h.length === 1 ? '0' + h : h;
                };
                
                return `#${toHex(newR)}${toHex(newG)}${toHex(newB)}`;
            };

            const updateElementColor = (color) => {
                if (selectedElement && modelerRef.current) {
                    const modeling = modelerRef.current.get('modeling');
                    modeling.setColor(selectedElement, {
                        stroke: color,
                        fill: getLightHex(color, 0.2) // 20% strength (very light)
                    });
                }
            };

            // Apply Text Styles to SVG
            useEffect(() => {
                if (!modelerRef.current) return;
                
                const applyStyles = () => {
                    const elementRegistry = modelerRef.current.get('elementRegistry');
                    const canvas = modelerRef.current.get('canvas');
                    
                    elementRegistry.forEach(element => {
                        const docs = element.businessObject.documentation;
                        if (docs && docs.length > 0 && docs[0].text) {
                            try {
                                const data = JSON.parse(docs[0].text);
                                const gfx = canvas.getGraphics(element);
                                
                                // 1. Apply Sticky Note Styles (Now using bpmn:Group)
                                if (element.type === 'bpmn:Group') {
                                    const text = gfx.querySelector('text');
                                    const path = gfx.querySelector('path');
                                    const rect = gfx.querySelector('rect'); // Groups usually have a rect or path
                                    
                                    // Reset Visibility First (Default State)
                                    if (text) text.style.display = 'block';
                                    if (path) path.style.display = 'block';
                                    if (rect) rect.style.display = 'block';
                                    
                                    // Remove old sticky elements if any
                                    const oldBg = gfx.querySelector('.sticky-bg');
                                    if (oldBg) oldBg.remove();
                                    const oldFo = gfx.querySelector('.sticky-fo');
                                    if (oldFo) oldFo.remove();

                                    // Always use Rich Text / Sticky Note Rendering for Groups created as Sticky Notes
                                    // Check if it has sticky note data
                                    if (data.noteColor || data.htmlContent) {
                                        // Hide default elements
                                        if (text) text.style.display = 'none';
                                        if (path) path.style.display = 'none';
                                        if (rect) rect.style.display = 'none';

                                        // 1. Background Rect
                                        const width = element.width || 300;
                                        const height = element.height || 300;
                                        
                                        const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                                        bgRect.classList.add('sticky-bg');
                                        bgRect.setAttribute('width', width);
                                        bgRect.setAttribute('height', height);
                                        bgRect.setAttribute('fill', data.noteColor || 'transparent');
                                        bgRect.setAttribute('stroke', data.borderColor || 'transparent');
                                        bgRect.setAttribute('fill-opacity', data.noteOpacity !== undefined ? data.noteOpacity : 1);
                                        bgRect.setAttribute('stroke-width', '1');
                                        gfx.prepend(bgRect);

                                        // 2. ForeignObject for Rich Text
                                        const fo = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                                        fo.classList.add('sticky-fo');
                                        fo.setAttribute('width', width);
                                        fo.setAttribute('height', height);
                                        fo.setAttribute('x', 0);
                                        fo.setAttribute('y', 0);
                                        
                                        // Content Div
                                        const div = document.createElement('div');
                                        div.style.width = '100%';
                                        div.style.height = '100%';
                                        div.style.padding = '10px';
                                        div.style.boxSizing = 'border-box';
                                        div.style.overflow = 'hidden';
                                        div.style.fontSize = `${data.textFontSize || 12}px`;
                                        div.style.fontWeight = data.textBold ? 'bold' : 'normal';
                                        div.style.color = data.textColor || '#000000';
                                        div.style.fontFamily = 'Arial, sans-serif';
                                        div.style.whiteSpace = 'pre-wrap'; // Preserve whitespace
                                        div.style.wordBreak = 'break-word';
                                        
                                        // Use stored HTML content or fallback to plain text
                                        div.innerHTML = data.htmlContent || (docs[0].text ? JSON.parse(docs[0].text).text : '') || '';
                                        
                                        fo.appendChild(div);
                                        gfx.appendChild(fo);
                                    }
                                }

                                // 2. Apply Name Font Size (For all elements)
                                if (data.nameFontSize) {
                                    const label = gfx.querySelector('.djs-label');
                                    if (label) {
                                        label.style.fontSize = `${data.nameFontSize}px`;
                                    }
                                }
                            } catch(e) {}
                        }
                    });
                };

                const eventBus = modelerRef.current.get('eventBus');
                eventBus.on('element.changed', applyStyles);
                eventBus.on('import.done', applyStyles);
                
                return () => {
                    eventBus.off('element.changed', applyStyles);
                    eventBus.off('import.done', applyStyles);
                };
            }, [modelerRef.current]); // Re-bind if modeler changes

            return (
                <div className="flex h-full flex-col bg-[#121212]">
                    <div className="bg-[#1e1e1e] px-6 py-3 flex justify-between items-center border-b border-white/5">
                        <div className="flex items-center gap-4">
                            <button onClick={handleBack} className="text-white/60 hover:text-white transition flex items-center gap-1">
                                <span className="text-lg">←</span> 返回
                            </button>
                            <input value={name} onChange={(e) => { setName(e.target.value); setHasUnsavedChanges(true); }} className="bg-[#2d2d2d] text-white px-4 py-1.5 rounded-full border-none outline-none focus:ring-2 focus:ring-[#8ab4f8]" placeholder="流程名稱" />
                            {hasUnsavedChanges && <span className="text-[#f28b82] text-xs font-medium animate-pulse">● 未儲存</span>}
                        </div>
                        <div className="flex gap-3 items-center">
                            <button onClick={() => window.open('http://10.122.51.60/MDserve/article/DigitalSOP/BPMN.md', '_blank')} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 w-8 h-8 rounded-full font-bold transition flex items-center justify-center text-sm" title="BPMN 說明">?</button>
                            <button onClick={handleSave} className="bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-6 py-1 rounded-full font-medium shadow-sm transition text-sm">儲存流程</button>
                            <button onClick={() => setIsPanelOpen(!isPanelOpen)} className={`bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 w-8 h-8 rounded-full transition flex items-center justify-center ${!isPanelOpen ? 'text-[#8ab4f8]' : ''}`} title={isPanelOpen ? '收起面板' : '展開面板'}>
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                                </svg>
                            </button>
                        </div>
                    </div>
                    <div className="flex-1 flex overflow-hidden relative">
                        <div className="flex-1 relative bg-white" ref={containerRef}></div>
                        
                        {/* Help Modal */}


                        <div className={`bg-[#1e1e1e] border-l border-white/5 overflow-y-auto transition-all duration-300 ease-in-out ${isPanelOpen ? 'w-80 p-6 opacity-100' : 'w-0 p-0 opacity-0 border-none'}`}>
                            <h3 className="font-medium text-white/90 mb-6 text-lg">屬性面板</h3>
                            {selectedElement ? (
                                <div>
                                    {selectedElement.type !== 'bpmn:Group' && (
                                        <div className="mb-5">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">名稱 (Name)</label>
                                            <input value={elementName} onChange={(e) => updateElementName(e.target.value)} className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition mb-2" placeholder="輸入名稱..." />
                                            
                                            {/* Name Font Size Control */}
                                            <div className="flex items-center justify-between">
                                                <span className="text-white/60 text-xs">字體大小</span>
                                                <select 
                                                    value={nameFontSize} 
                                                    onChange={(e) => updateElementProperties({ nameFontSize: parseInt(e.target.value) })}
                                                    className="bg-[#2d2d2d] text-white border border-white/10 rounded px-2 py-1 text-xs outline-none"
                                                >
                                                    {[12, 14, 16, 18, 20, 24, 30, 36].map(s => (
                                                        <option key={s} value={s}>{s}px</option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>
                                    )}

                                    {/* Text Annotation Styling */}
                                    {selectedElement.type === 'bpmn:Group' && (
                                        <div className="mb-5 border-t border-white/10 pt-4">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">便利貼設定 (Sticky Note)</label>
                                            
                                            {/* Note Color */}
                                            <div className="mb-3">
                                                <span className="text-white/60 text-sm block mb-1">背景顏色</span>
                                                <div className="flex gap-1 flex-wrap">
                                                    {['#fff2cc', '#fce5cd', '#e6b8af', '#d9ead3', '#c9daf8', '#d0e0e3', '#ead1dc', '#ffffff', 'transparent'].map(c => (
                                                        <button 
                                                            key={c}
                                                            onClick={() => updateElementProperties({ noteColor: c })}
                                                            className={`w-6 h-6 rounded border ${noteColor === c ? 'border-white scale-110' : 'border-white/10'}`}
                                                            style={ { backgroundColor: c } }
                                                            title={c}
                                                        />
                                                    ))}
                                                    <input 
                                                        type="color" 
                                                        value={noteColor} 
                                                        onChange={(e) => updateElementProperties({ noteColor: e.target.value })}
                                                        className="w-6 h-6 p-0 border-0 rounded overflow-hidden"
                                                    />
                                                </div>
                                            </div>

                                            {/* Border Color */}
                                            <div className="mb-3">
                                                <span className="text-white/60 text-sm block mb-1">邊框顏色</span>
                                                <div className="flex gap-1 flex-wrap">
                                                    {['#d6b656', '#e69138', '#cc0000', '#6aa84f', '#3c78d8', '#45818e', '#a64d79', '#000000', 'transparent'].map(c => (
                                                        <button 
                                                            key={c}
                                                            onClick={() => updateElementProperties({ borderColor: c })}
                                                            className={`w-6 h-6 rounded border ${borderColor === c ? 'border-white scale-110' : 'border-white/10'}`}
                                                            style={ { backgroundColor: c } }
                                                            title={c}
                                                        />
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Opacity */}
                                            <div className="mb-4">
                                                <div className="flex justify-between mb-1">
                                                    <span className="text-white/60 text-sm">透明度</span>
                                                    <span className="text-white/80 text-xs">{Math.round(noteOpacity * 100)}%</span>
                                                </div>
                                                <input 
                                                    type="range" 
                                                    min="0" 
                                                    max="1" 
                                                    step="0.1" 
                                                    value={noteOpacity} 
                                                    onChange={(e) => updateElementProperties({ noteOpacity: parseFloat(e.target.value) })}
                                                    className="w-full accent-[#8ab4f8] h-1 bg-white/10 rounded-lg appearance-none cursor-pointer"
                                                />
                                            </div>

                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider border-t border-white/10 pt-4">文字樣式 (Style)</label>
                                            
                                            {/* Font Size */}
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-white/60 text-sm">字體大小</span>
                                                <select 
                                                    value={textFontSize} 
                                                    onChange={(e) => updateElementProperties({ textFontSize: parseInt(e.target.value) })}
                                                    className="bg-[#2d2d2d] text-white border border-white/10 rounded px-2 py-1 text-sm outline-none"
                                                >
                                                    {[12, 14, 16, 18, 20, 24, 30, 36, 48, 64].map(s => (
                                                        <option key={s} value={s}>{s}px</option>
                                                    ))}
                                                </select>
                                            </div>

                                            {/* Bold - Removed global toggle for Sticky Note */}
                                            {/* Text Color - Removed global picker for Sticky Note */}

                                            {/* Rich Text Editor */}
                                            <div className="mt-4 border-t border-white/10 pt-4">
                                                    <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">內容編輯 (Content)</label>
                                                    <div className="bg-[#2d2d2d] rounded-lg border border-white/10 p-2">
                                                        <div className="flex gap-2 mb-2 border-b border-white/10 pb-2 flex-wrap">
                                                            <button 
                                                                onClick={() => {
                                                                    document.execCommand('bold', false, null);
                                                                    const editor = document.getElementById('sticky-wysiwyg');
                                                                    if (editor) {
                                                                        setHtmlContent(editor.innerHTML);
                                                                        updateElementProperties({ htmlContent: editor.innerHTML });
                                                                    }
                                                                }}
                                                                className="bg-white/10 hover:bg-white/20 text-white text-xs px-2 py-1 rounded font-bold"
                                                            >
                                                                B
                                                            </button>
                                                            <button 
                                                                onClick={() => {
                                                                    document.execCommand('underline', false, null);
                                                                    const editor = document.getElementById('sticky-wysiwyg');
                                                                    if (editor) {
                                                                        setHtmlContent(editor.innerHTML);
                                                                        updateElementProperties({ htmlContent: editor.innerHTML });
                                                                    }
                                                                }}
                                                                className="bg-white/10 hover:bg-white/20 text-white text-xs px-2 py-1 rounded font-medium underline"
                                                            >
                                                                U
                                                            </button>
                                                            <button 
                                                                onClick={() => {
                                                                    document.execCommand('hiliteColor', false, '#ffff00');
                                                                    const editor = document.getElementById('sticky-wysiwyg');
                                                                    if (editor) {
                                                                        setHtmlContent(editor.innerHTML);
                                                                        updateElementProperties({ htmlContent: editor.innerHTML });
                                                                    }
                                                                }}
                                                                className="bg-[#fbbc04] hover:bg-[#fdd663] text-black text-xs px-2 py-1 rounded font-medium"
                                                            >
                                                                Highlight
                                                            </button>
                                                            
                                                            {/* Text Color Picker in Toolbar */}
                                                            <div className="flex gap-1 items-center border-l border-white/10 pl-2">
                                                                {['#000000', '#ff0000', '#0000ff', '#ffffff'].map(c => (
                                                                    <button 
                                                                        key={c}
                                                                        onClick={() => {
                                                                            document.execCommand('foreColor', false, c);
                                                                            const editor = document.getElementById('sticky-wysiwyg');
                                                                            if (editor) {
                                                                                setHtmlContent(editor.innerHTML);
                                                                                updateElementProperties({ htmlContent: editor.innerHTML });
                                                                            }
                                                                        }}
                                                                        className="w-4 h-4 rounded-full border border-white/20 hover:scale-110 transition"
                                                                        style={ { backgroundColor: c } }
                                                                    />
                                                                ))}
                                                            </div>
                                                        </div>
                                                        
                                                        {/* WYSIWYG Editor */}
                                                        <div 
                                                            id="sticky-wysiwyg"
                                                            contentEditable
                                                            className="w-full bg-white text-black text-sm outline-none min-h-[100px] p-2 rounded-t mb-1 overflow-auto"
                                                            style={ { whiteSpace: 'pre-wrap' } }
                                                            dangerouslySetInnerHTML={ { __html: htmlContent } }
                                                            onCompositionStart={() => {
                                                                isComposing.current = true;
                                                            }}
                                                            onCompositionEnd={(e) => {
                                                                isComposing.current = false;
                                                                setHtmlContent(e.currentTarget.innerHTML);
                                                                updateElementProperties({ htmlContent: e.currentTarget.innerHTML });
                                                            }}
                                                            onInput={(e) => {
                                                                if (!isComposing.current) {
                                                                    setHtmlContent(e.currentTarget.innerHTML);
                                                                    updateElementProperties({ htmlContent: e.currentTarget.innerHTML });
                                                                }
                                                            }}
                                                        />
                                                        
                                                        {/* HTML Preview */}
                                                        <textarea 
                                                            readOnly
                                                            value={htmlContent} 
                                                            className="w-full bg-[#1e1e1e] text-white/50 text-xs outline-none h-[60px] font-mono p-2 rounded-b border-t border-white/10"
                                                            placeholder="HTML 預覽..."
                                                        />
                                                    </div>
                                                    <p className="text-white/40 text-xs mt-2">上方為編輯區，下方為 HTML 原始碼預覽。</p>
                                                </div>
                                        </div>
                                    )}

                                    {/* Color Picker (Standard) */}
                                    {selectedElement.type !== 'bpmn:Group' && (
                                        <div className="mb-5">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">外觀設定 (Color)</label>
                                            <div className="grid grid-cols-7 gap-2">
                                                {GOOGLE_COLORS.map(color => (
                                                    <button 
                                                        key={color} 
                                                        onClick={() => updateElementColor(color)}
                                                        className="w-6 h-6 rounded-full border border-white/10 hover:scale-110 transition"
                                                        style={ { backgroundColor: color } }
                                                    />
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    
                                    {/* PI Tag Config (Only for Tasks usually, but enabling for all for flexibility) */}
                                    {selectedElement.type !== 'bpmn:Group' && (
                                        <div className="mb-5">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">PI Tag 設定</label>
                                            <input 
                                                value={piTag} 
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    if (val.split(';').length > 4) {
                                                        alert('最多只能輸入 4 個 PI Tag');
                                                        return;
                                                    }
                                                    updateElementProperties({ piTag: val });
                                                }} 
                                                className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition mb-2" 
                                                placeholder="例如: Tag1;Tag2 (最多4個)" 
                                            />
                                            <input 
                                                value={piUnit} 
                                                onChange={(e) => updateElementProperties({ piUnit: e.target.value })} 
                                                className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition mb-2" 
                                                placeholder="單位 (例如: kg/hr)" 
                                            />
                                            <div className="flex items-center gap-2 bg-[#2d2d2d] border border-white/10 rounded-lg px-3 py-2 mb-2">
                                                <span className="text-white/60 text-sm whitespace-nowrap">小數點位數:</span>
                                                <input 
                                                    type="number" 
                                                    min="0" 
                                                    max="5"
                                                    value={piPrecision} 
                                                    onChange={(e) => updateElementProperties({ piPrecision: parseInt(e.target.value) })} 
                                                    className="w-full bg-transparent border-none outline-none text-white text-right"
                                                />
                                            </div>
                                            <label className="flex items-center gap-2 cursor-pointer bg-[#2d2d2d] p-2 rounded-lg border border-white/10 hover:border-[#8ab4f8] transition mb-2">
                                                <input 
                                                    type="checkbox" 
                                                    checked={alwaysOn} 
                                                    onChange={(e) => updateElementProperties({ alwaysOn: e.target.checked })} 
                                                    className="w-4 h-4 rounded border-gray-300 text-[#8ab4f8] focus:ring-[#8ab4f8]"
                                                />
                                                <span className="text-sm text-white/90 font-medium">Always On (常駐顯示)</span>
                                            </label>
                                        </div>
                                    )}
                                    {(selectedElement.type === 'bpmn:DataObjectReference' || selectedElement.type === 'bpmn:DataStoreReference') && (
                                        <div className="mb-5">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">超連結 (Hyperlink)</label>
                                            <input 
                                                value={targetUrl} 
                                                onChange={(e) => updateElementProperties({ targetUrl: e.target.value })} 
                                                className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition" 
                                                placeholder="例如: https://google.com" 
                                            />
                                            <p className="text-white/40 text-xs mt-2">執行模式下點擊此物件將開啟網頁。</p>
                                        </div>
                                    )}

                                    {/* Final End Config (For End Events) */}
                                    {selectedElement.type === 'bpmn:EndEvent' && (
                                        <div className="mb-5">
                                            <label className="flex items-center gap-2 cursor-pointer bg-[#2d2d2d] p-3 rounded-lg border border-white/10 hover:border-[#8ab4f8] transition">
                                                <input 
                                                    type="checkbox" 
                                                    checked={isFinalEnd} 
                                                    onChange={(e) => updateElementProperties({ isFinalEnd: e.target.checked })} 
                                                    className="w-4 h-4 rounded border-gray-300 text-[#8ab4f8] focus:ring-[#8ab4f8]"
                                                />
                                                <span className="text-sm text-white/90 font-medium">最終 END (Final END)</span>
                                            </label>
                                            <p className="text-white/40 text-xs mt-2">勾選後，流程必須執行到此節點才算真正完成。</p>
                                        </div>
                                    )}
                                </div>
                            ) : <p className="text-white/40 text-sm">請選擇流程圖中的元件以編輯屬性</p>}
                        </div>
                    </div>
                </div>
            );

        };

        // 3. Operator Mode (Execution)
        const Operator = ({ processId, onNavigate }) => {
            const containerRef = useRef(null);
            const viewerRef = useRef(null);
            const [process, setProcess] = useState(null);
            const [logs, setLogs] = useState([]);
            const [currentRunningTaskId, setCurrentRunningTaskId] = useState(null); 
            const [isFinished, setIsFinished] = useState(false);
            
            // Floating Window State
            const [showWindow, setShowWindow] = useState(false);
            const [windowTask, setWindowTask] = useState(null); 
            const [note, setNote] = useState('');
            const [tagValues, setTagValues] = useState([]);
            const [loadingTag, setLoadingTag] = useState(false);

            // Zoom
            const handleZoom = (delta) => {
                if (viewerRef.current) {
                    const canvas = viewerRef.current.get('canvas');
                    canvas.zoom(canvas.zoom() + delta);
                }
            };

            const logsRef = useRef(logs);
            const runningTaskRef = useRef(currentRunningTaskId);

            useEffect(() => { logsRef.current = logs; }, [logs]);
            useEffect(() => { runningTaskRef.current = currentRunningTaskId; }, [currentRunningTaskId]);

            // Check Predecessors
            const checkPredecessors = (element, currentLogs) => {
                if (!element || !element.incoming || element.incoming.length === 0) return true; 
                return element.incoming.every(connection => {
                    if (connection.source.type === 'bpmn:StartEvent') return true;
                    const sourceName = connection.source.businessObject.name;
                    return currentLogs.some(l => l.message.startsWith('任務完成') && l.message.includes(sourceName));
                });
            };

            useEffect(() => {
                // Define applyStyles locally
                const applyStyles = () => {
                    const viewer = viewerRef.current;
                    if (!viewer) return;
                    
                    const elementRegistry = viewer.get('elementRegistry');
                    const canvas = viewer.get('canvas');

                    elementRegistry.forEach(element => {
                        if (element.type === 'bpmn:TextAnnotation' || element.type === 'bpmn:Group') {
                            const businessObj = element.businessObject;
                            let data = {};
                            
                            if (businessObj.documentation && businessObj.documentation.length > 0) {
                                try {
                                    data = JSON.parse(businessObj.documentation[0].text);
                                } catch (e) {}
                            }

                            // Default for Group
                            if (element.type === 'bpmn:Group') {
                                if (!data.noteColor) data.noteColor = '#fff9c4';
                                if (!data.borderColor) data.borderColor = '#d6b656';
                            }

                            const hasStyle = data.noteColor || data.htmlContent || data.textFontSize || data.textColor || data.borderColor;
                            
                            if (hasStyle) {
                                try {
                                    const gfx = canvas.getGraphics(element);
                                    if (!gfx) return;

                                    // Clear
                                    const existingBg = gfx.querySelector('.sticky-bg');
                                    if (existingBg) existingBg.remove();
                                    const existingFo = gfx.querySelector('.sticky-fo');
                                    if (existingFo) existingFo.remove();

                                    // Hide defaults
                                    ['text', 'path', 'rect'].forEach(tag => {
                                        const el = gfx.querySelector(tag);
                                        if (el) el.style.display = 'none';
                                    });

                                    // Dimensions
                                    let width = element.width || (element.di && element.di.bounds && element.di.bounds.width) || 300;
                                    let height = element.height || (element.di && element.di.bounds && element.di.bounds.height) || 300;

                                    // 1. Background
                                    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                                    rect.setAttribute('class', 'sticky-bg');
                                    rect.setAttribute('width', width);
                                    rect.setAttribute('height', height);
                                    rect.setAttribute('rx', '10');
                                    rect.setAttribute('ry', '10');
                                    rect.setAttribute('fill', data.noteColor || '#fff9c4');
                                    rect.setAttribute('stroke', data.borderColor || '#d6b656');
                                    rect.setAttribute('stroke-width', '2');
                                    rect.setAttribute('fill-opacity', data.noteOpacity !== undefined ? data.noteOpacity : 1);
                                    
                                    const visual = gfx.querySelector('.djs-visual');
                                    if (visual) {
                                        if (visual.firstChild) visual.insertBefore(rect, visual.firstChild);
                                        else visual.appendChild(rect);
                                    }

                                    // 2. Content
                                    if (data.htmlContent) {
                                        const fo = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                                        fo.setAttribute('class', 'sticky-fo');
                                        fo.setAttribute('width', width - 20);
                                        fo.setAttribute('height', height - 20);
                                        fo.setAttribute('x', '10');
                                        fo.setAttribute('y', '10');
                                        
                                        const div = document.createElement('div');
                                        div.xmlns = 'http://www.w3.org/1999/xhtml';
                                        div.style.width = '100%';
                                        div.style.height = '100%';
                                        div.style.overflow = 'auto';
                                        div.style.fontSize = `${data.textFontSize || 14}px`;
                                        div.style.color = data.textColor || '#000000';
                                        div.innerHTML = data.htmlContent;
                                        
                                        fo.appendChild(div);
                                        if (visual) visual.appendChild(fo);
                                    }
                                } catch (e) { console.error(e); }
                            }
                        }
                    });
                };

                const load = async () => {
                    if (!processId) return;
                    
                    // 1. Get Process
                    const pRes = await fetch(`${API_BASE}/processes/${processId}`);
                    const pData = await pRes.json();
                    setProcess(pData);

                    // 2. Get Session
                    const sRes = await fetch(`${API_BASE}/sessions/${processId}`);
                    const sData = await sRes.json();
                    
                    let currentLogs = [];
                    if (sData && !sData.is_finished) {
                        currentLogs = sData.logs || [];
                        setLogs(currentLogs);
                        setCurrentRunningTaskId(sData.current_task_id);
                        setIsFinished(sData.is_finished);
                    } else {
                        // New Session (or restart if finished)
                        await fetch(`${API_BASE}/sessions`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ process_id: processId, current_task_id: null, logs: [], is_finished: false })
                        });
                        setLogs([]);
                        setCurrentRunningTaskId(null);
                        setIsFinished(false);
                    }

                    // 3. Init BPMN (Read-Only Mode)
                    if (viewerRef.current) viewerRef.current.destroy();
                    
                    // 3. Init BPMN (Read-Only Mode)
                    if (viewerRef.current) viewerRef.current.destroy();
                    const viewer = new BpmnJS({ container: containerRef.current });
                    viewerRef.current = viewer;
                    
                    // Init Custom State for Sync Access
                    viewer._customState = {
                        runningTaskId: currentRunningTaskId,
                        logs: currentLogs
                    };
                    
                    try {
                        await viewer.importXML(pData.xml_content);
                        viewer.get('canvas').zoom('fit-viewport');
                    } catch (err) {
                        console.error('BPMN Import Error:', err);
                    }
                    
                    // 4. Interaction Logic
                    const eventBus = viewer.get('eventBus');
                    const elementRegistry = viewer.get('elementRegistry');
                    const canvas = viewer.get('canvas');

                    // Disable default interactions
                    const events = [
                        'shape.move.start', 
                        'connection.create.start', 
                        'element.dblclick', 
                        'contextPad.open', 
                        'palette.create',
                        'shape.resize.start',
                        'connection.segment.move.start',
                        'bendlpoints.move.start',
                        'connection.layout.start',
                        'element.mousedown' // Careful with this one, might block selection. But we need click.
                    ];
                    
                    // We only want to block mousedown if it leads to a move/edit. 
                    events.forEach(event => {
                        eventBus.on(event, 10000, (e) => {
                            // Allow clicking on elements to open task window
                            if (event === 'element.mousedown') return; 
                            return false; 
                        });
                    });

                    eventBus.on('element.click', (e) => {
                        const element = e.element;
                        
                        // Handle Hyperlinks (DataObjectReference)
                        if (element.type === 'bpmn:DataObjectReference' || element.type === 'bpmn:DataStoreReference') {
                            const docs = element.businessObject.documentation;
                            if (docs && docs.length > 0 && docs[0].text) {
                                try {
                                    const data = JSON.parse(docs[0].text);
                                    if (data.targetUrl) {
                                        window.open(data.targetUrl, '_blank');
                                        return;
                                    }
                                } catch(e) {}
                            }
                        }

                        // Handle Tasks / Start Event / End Event
                        const interactableTypes = [
                            'bpmn:Task', 
                            'bpmn:UserTask', 
                            'bpmn:ServiceTask', 
                            'bpmn:SendTask', 
                            'bpmn:ReceiveTask', 
                            'bpmn:ManualTask', 
                            'bpmn:BusinessRuleTask', 
                            'bpmn:ScriptTask', 
                            'bpmn:CallActivity',
                            'bpmn:StartEvent', 
                            'bpmn:EndEvent'
                        ];

                        if (interactableTypes.includes(element.type)) {
                            // Use current state from ref/customState to avoid closure staleness
                            const currentLogs = viewer._customState.logs || [];
                            const activeTaskId = viewer._customState.runningTaskId;
                            
                            openTaskWindow(element, currentLogs, activeTaskId);
                        }
                    });
                    // 6. Highlight Running Task
                    if (sData && sData.current_task_id) {
                        try { 
                            // Ensure element exists before adding marker
                            if (elementRegistry.get(sData.current_task_id)) {
                                canvas.addMarker(sData.current_task_id, 'highlight'); 
                            }
                        } catch(e) { console.error('Error highlighting task:', e); }
                    }
                    
                    // 7. Colorize Completed Tasks
                    if (currentLogs.length > 0) {
                        const completedNames = currentLogs
                            .filter(l => l.message.startsWith('任務完成'))
                            .map(l => l.message.split(': ')[1]);
                        
                        elementRegistry.forEach(el => {
                            if (completedNames.includes(el.businessObject.name)) {
                                canvas.addMarker(el.id, 'completed-task');
                            }
                        });
                    }

                    // Apply Styles
                    setTimeout(applyStyles, 100);
                    setTimeout(applyStyles, 500);
                };

                load();
                
                return () => { 
                    if(viewerRef.current) {
                        viewerRef.current.destroy(); 
                    }
                };
            }, [processId]);

            // Always On PI Display Manager
            useEffect(() => {
                const viewer = viewerRef.current;
                if (!viewer || !process) return;

                const overlays = viewer.get('overlays');
                const elementRegistry = viewer.get('elementRegistry');
                const hasStarted = logs.length > 0;

                // 1. Clear overlays if not started
                if (!hasStarted) {
                    elementRegistry.forEach(element => {
                        const businessObj = element.businessObject;
                        if (businessObj.documentation && businessObj.documentation.length > 0) {
                            try {
                                const d = JSON.parse(businessObj.documentation[0].text);
                                if (d.alwaysOn) {
                                    overlays.remove({ element: element.id });
                                }
                            } catch(e) {}
                        }
                    });
                    return;
                }

                // 2. Find Always On Elements
                const alwaysOnElements = [];
                elementRegistry.forEach(element => {
                    const businessObj = element.businessObject;
                    if (businessObj.documentation && businessObj.documentation.length > 0) {
                        try {
                            const d = JSON.parse(businessObj.documentation[0].text);
                            if (d.alwaysOn && d.piTag) {
                                alwaysOnElements.push({
                                    id: element.id,
                                    name: businessObj.name || '未命名任務',
                                    tag: d.piTag,
                                    unit: d.piUnit || '',
                                    precision: d.piPrecision || 2
                                });
                            }
                        } catch(e) {}
                    }
                });

                if (alwaysOnElements.length === 0) return;

                // 3. Update Function
                const updateOverlays = async () => {
                    for (const el of alwaysOnElements) {
                        // Fix: Find overlay by checking if it contains our specific content ID
                        let overlay = overlays.get({ element: el.id }).find(o => o.html && o.html.querySelector(`#content-${el.id}`));
                        
                        // Fetch Data
                        let data = [];
                        try {
                            const res = await fetch(`${API_BASE}/get_tag_value?tag=${encodeURIComponent(el.tag)}`);
                            data = await res.json();
                        } catch(e) { console.error(e); }

                        if (!overlay) {
                            // Create Overlay Container
                            const container = document.createElement('div');
                            container.className = 'bg-[#1e1e1e] border border-white/20 rounded shadow-lg text-xs min-w-[150px] flex flex-col resize-x overflow-auto';
                            container.style.pointerEvents = 'auto'; // Enable interaction
                            container.style.position = 'absolute'; // For dragging relative to overlay root
                            
                            // Header (Drag handle + Toggle)
                            const header = document.createElement('div');
                            header.className = 'bg-[#2d2d2d] px-2 py-1 flex justify-between items-center cursor-move select-none border-b border-white/10';
                            header.innerHTML = `
                                <span class="text-white/60 font-medium truncate flex-1 min-w-0 mr-2" title="${el.name}">${el.name}</span>
                                <button class="text-white/40 hover:text-white transition focus:outline-none">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                    </svg>
                                </button>
                            `;
                            
                            // Content
                            const content = document.createElement('div');
                            content.id = `content-${el.id}`;
                            content.className = 'p-2';
                            
                            container.appendChild(header);
                            container.appendChild(content);

                            // Add to BPMN
                            const overlayId = overlays.add(el.id, {
                                type: 'always-on-pi', // Keep passing it, just in case
                                position: { bottom: 0, right: -10 },
                                html: container
                            });

                            // Toggle Logic
                            const toggleBtn = header.querySelector('button');
                            let isCollapsed = false;
                            toggleBtn.onclick = (e) => {
                                e.stopPropagation(); // Prevent drag
                                isCollapsed = !isCollapsed;
                                content.style.display = isCollapsed ? 'none' : 'block';
                                toggleBtn.innerHTML = isCollapsed ? 
                                    `<svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" /></svg>` : 
                                    `<svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>`;
                            };

                            // Drag Logic
                            let isDragging = false;
                            let startX, startY, initialLeft, initialTop;

                            header.onmousedown = (e) => {
                                e.stopPropagation(); // Prevent BPMN pan
                                isDragging = true;
                                startX = e.clientX;
                                startY = e.clientY;
                                
                                const style = window.getComputedStyle(container);
                                const matrix = new WebKitCSSMatrix(style.transform);
                                initialLeft = matrix.m41;
                                initialTop = matrix.m42;
                                
                                document.onmousemove = onMouseMove;
                                document.onmouseup = onMouseUp;
                            };

                            const onMouseMove = (e) => {
                                if (!isDragging) return;
                                const dx = e.clientX - startX;
                                const dy = e.clientY - startY;
                                container.style.transform = `translate(${initialLeft + dx}px, ${initialTop + dy}px)`;
                            };

                            const onMouseUp = () => {
                                isDragging = false;
                                document.onmousemove = null;
                                document.onmouseup = null;
                            };

                            // Initial Render
                            renderContent(content, data, el);

                        } else {
                            // Update Content
                            const content = overlay.html.querySelector(`#content-${el.id}`);
                            if (content) {
                                renderContent(content, data, el);
                            }
                        }
                    }
                };

                const renderContent = (container, data, el) => {
                    container.innerHTML = '';
                    data.forEach(item => {
                        const row = document.createElement('div');
                        row.className = 'flex justify-between gap-4 mb-1 last:mb-0';
                        
                        const label = document.createElement('span');
                        label.className = 'text-white/60 flex-1 min-w-0 break-all';
                        label.innerText = item.tag;
                        
                        const val = document.createElement('span');
                        val.className = 'text-[#81c995] font-mono font-bold';
                        const numVal = parseFloat(item.value);
                        val.innerText = !isNaN(numVal) ? numVal.toFixed(el.precision) : item.value;
                        
                        row.appendChild(label);
                        row.appendChild(val);
                        container.appendChild(row);
                    });

                    if (el.unit) {
                        const unitDiv = document.createElement('div');
                        unitDiv.className = 'text-right text-white/40 text-[10px] mt-1';
                        unitDiv.innerText = el.unit;
                        container.appendChild(unitDiv);
                    }
                };

                updateOverlays();
                const interval = setInterval(updateOverlays, 5000);
                return () => clearInterval(interval);

            }, [processId, logs.length > 0, process]);
            useEffect(() => {
                const container = containerRef.current;
                if (!container) return;

                const onWheel = (e) => {
                    if (viewerRef.current) {
                        // Allow Zoom (Ctrl + Wheel)
                        if (e.ctrlKey || e.metaKey) return;

                        e.preventDefault();
                        e.stopPropagation();
                        
                        const canvas = viewerRef.current.get('canvas');
                        const viewbox = canvas.viewbox();
                        
                        // Move viewbox x by deltaY
                        canvas.viewbox({
                            x: viewbox.x + e.deltaY,
                            y: viewbox.y,
                            width: viewbox.width,
                            height: viewbox.height
                        });
                    }
                };

                container.addEventListener('wheel', onWheel, { passive: false, capture: true });
                return () => container.removeEventListener('wheel', onWheel, { capture: true });
            }, []);

            // Real-time Synchronization (Polling)
            useEffect(() => {
                if (!processId) return;
                
                const syncSession = async () => {
                    try {
                        const res = await fetch(`${API_BASE}/sessions/${processId}`);
                        if (res.ok) {
                            const data = await res.json();
                            if (data) {
                                // Sync Logs
                                if (JSON.stringify(data.logs) !== JSON.stringify(logs)) {
                                    setLogs(data.logs);
                                    
                                    // Sync Visuals
                                    if (viewerRef.current) {
                                        viewerRef.current._customState = {
                                            runningTaskId: data.current_task_id,
                                            logs: data.logs
                                        };
                                        
                                        // Re-apply markers
                                        const canvas = viewerRef.current.get('canvas');
                                        const elementRegistry = viewerRef.current.get('elementRegistry');
                                        
                                        // Clear all markers first (inefficient but safe)
                                        elementRegistry.forEach(el => {
                                            canvas.removeMarker(el.id, 'highlight');
                                            canvas.removeMarker(el.id, 'completed-task');
                                        });

                                        // Re-calculate status based on logs
                                        const taskStatus = {};
                                        data.logs.forEach(log => {
                                            if (log.message.includes('任務開始:')) {
                                                const name = log.message.split(': ')[1].trim();
                                                taskStatus[name] = 'running';
                                            } else if (log.message.includes('任務完成:')) {
                                                const name = log.message.split(': ')[1].trim();
                                                taskStatus[name] = 'completed';
                                            }
                                        });

                                        elementRegistry.forEach(el => {
                                            const name = el.businessObject.name;
                                            if (name && taskStatus[name]) {
                                                if (taskStatus[name] === 'completed') {
                                                    canvas.addMarker(el.id, 'completed-task');
                                                } else if (taskStatus[name] === 'running') {
                                                    canvas.addMarker(el.id, 'highlight');
                                                }
                                            }
                                        });
                                    }
                                }
                                
                                // Sync Finished State
                                if (data.is_finished !== isFinished) {
                                    setIsFinished(data.is_finished);
                                }

                                // Sync Current Running Task (Optional, mainly for visual focus)
                                if (data.current_task_id !== currentRunningTaskId) {
                                    setCurrentRunningTaskId(data.current_task_id);
                                }
                            }
                        }
                    } catch (e) {
                        console.error("Sync error:", e);
                    }
                };

                const interval = setInterval(syncSession, 7000); // Poll every 7 seconds
                return () => clearInterval(interval);
            }, [processId, logs, isFinished, currentRunningTaskId]);

            // Helper to open window
            const openTaskWindow = (element, currentLogs, activeTaskId) => {
                const businessObj = element.businessObject;
                const docs = businessObj.documentation;
                let tag = '', unit = '', precision = 2;
                
                if (docs && docs.length > 0 && docs[0].text) {
                    try {
                        const d = JSON.parse(docs[0].text);
                        tag = d.piTag;
                        unit = d.piUnit;
                        precision = parseInt(d.piPrecision) || 2;
                    } catch(e) {}
                }

                // Check status
                let status = 'idle';
                const taskName = businessObj.name || '未命名任務';
                const startMsg = `任務開始: ${taskName}`;
                const endMsg = `任務完成: ${taskName}`;

                if (element.type === 'bpmn:StartEvent') {
                    // Start Event is complete if it has a start log
                    // Use loose matching for safety or strict if preferred. Sticking to strict for consistency with new logic.
                    // Actually, let's keep using the same logic as before for StartEvent but cleaner
                    if (currentLogs.some(l => l.message === startMsg)) status = 'completed';
                } else {
                    const hasStart = currentLogs.some(l => l.message === startMsg);
                    const hasEnd = currentLogs.some(l => l.message === endMsg);
                    
                    if (hasEnd) status = 'completed';
                    else if (hasStart) status = 'running';
                }

                // Check predecessors
                const canStart = checkPredecessors(element, currentLogs);

                setWindowTask({
                    id: element.id,
                    name: businessObj.name || '未命名任務',
                    type: element.type,
                    tag, unit, precision,
                    status,
                    canStart
                });
                
                setNote('');
                setTagValues([]);
                setShowWindow(true);

                // Fetch PI Data if tag exists
                if (tag) {
                    setLoadingTag(true);
                    fetch(`${API_BASE}/get_tag_value?tag=${encodeURIComponent(tag)}`)
                        .then(res => res.json())
                        .then(data => {
                            setTagValues(data);
                            setLoadingTag(false);
                        });
                }
            };

            const handleExportCSV = (logsToExport) => {
                if (!logsToExport || logsToExport.length === 0) return;

                // Build CSV String
                let csvString = "";
                
                // Add Metadata Line
                if (process && process.id && process.updated_at) {
                    csvString += `# Metadata: id=${process.id}, version=${process.updated_at}\\n`;
                }
                csvString += "Time,Source,Message,Value,Note\\n";
                
                logsToExport.forEach(log => {
                    const row = [
                        log.time,
                        log.source,
                        log.message,
                        `"${log.value}"`, // Quote value to handle commas
                        `"${log.note}"`
                    ].join(",");
                    csvString += row + "\\n";
                });

                const now = new Date();
                const timestamp = now.getFullYear() +
                    String(now.getMonth() + 1).padStart(2, '0') +
                    String(now.getDate()).padStart(2, '0') +
                    String(now.getHours()).padStart(2, '0') +
                    String(now.getMinutes()).padStart(2, '0');

                // Use Blob for correct encoding (BOM + UTF-8)
                const blob = new Blob(["\uFEFF" + csvString], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                
                const link = document.createElement("a");
                link.setAttribute("href", url);
                link.setAttribute("download", `${process.name}_${timestamp}.csv`);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
            };

            const handleUpdateLog = async (index, newNote) => {
                const newLogs = [...logs];
                if (newLogs[index]) {
                    newLogs[index].note = newNote;
                    setLogs(newLogs);
                    
                    // Sync Update
                    if (viewerRef.current) {
                        viewerRef.current._customState = {
                            runningTaskId: currentRunningTaskId,
                            logs: newLogs
                        };
                    }
                    
                    // Save to Backend
                    await fetch(`${API_BASE}/sessions`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            process_id: processId,
                            current_task_id: currentRunningTaskId,
                            logs: newLogs,
                            is_finished: isFinished
                        })
                    });
                }
            };

            const handleStartTask = async () => {
                if (!windowTask) return;
                
                // Fetch PI Data for Start Log if tags exist
                let startValStr = '-';
                if (windowTask.tag) {
                    try {
                        const res = await fetch(`${API_BASE}/get_tag_value?tag=${encodeURIComponent(windowTask.tag)}`);
                        const data = await res.json();
                        startValStr = data.map(t => {
                            const numVal = parseFloat(t.value);
                            const displayVal = !isNaN(numVal) ? numVal.toFixed(windowTask.precision || 2) : t.value;
                            return `${t.tag}=${displayVal} ${windowTask.unit || ''}`;
                        }).join(', ');
                    } catch(e) { console.error(e); }
                }

                // Special handling for Start Event: Atomic Start (No Complete Log)
                if (windowTask.type === 'bpmn:StartEvent') {
                     const newLogStart = {
                        time: new Date().toLocaleTimeString(),
                        source: 'User',
                        message: `任務開始: ${windowTask.name}`,
                        value: startValStr,
                        note: note
                    };
                    // Removed newLogEnd to prevent "Task Complete" in Timeline
                    
                    const newLogs = [...logs, newLogStart];
                    setLogs(newLogs);
                    setCurrentRunningTaskId(null); 
                    setWindowTask(prev => ({ ...prev, status: 'completed' }));
                    
                    // Sync Update
                    if (viewerRef.current) {
                        viewerRef.current._customState = {
                            runningTaskId: null,
                            logs: newLogs
                        };
                    }
                    
                    // Update Visuals
                    const canvas = viewerRef.current.get('canvas');
                    canvas.addMarker(windowTask.id, 'completed-task');
                    
                    // Save to Backend
                    await fetch(`${API_BASE}/sessions`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            process_id: processId,
                            current_task_id: null,
                            logs: newLogs,
                            is_finished: false
                        })
                    });
                    
                    setShowWindow(false);
                    
                    // Auto Export CSV for Start Event
                    // handleExportCSV(newLogs);
                    return;
                }

                const newLog = {
                    time: new Date().toLocaleTimeString(),
                    source: 'User',
                    message: `任務開始: ${windowTask.name}`,
                    value: startValStr,
                    note: note
                };
                const newLogs = [...logs, newLog];
                setLogs(newLogs);
                setCurrentRunningTaskId(windowTask.id);
                setWindowTask(prev => ({ ...prev, status: 'running' }));

                // Sync Update
                if (viewerRef.current) {
                    viewerRef.current._customState = {
                        runningTaskId: windowTask.id,
                        logs: newLogs
                    };
                }

                // Update Visuals
                const canvas = viewerRef.current.get('canvas');
                canvas.addMarker(windowTask.id, 'highlight');

                // Save to Backend
                await fetch(`${API_BASE}/sessions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        process_id: processId,
                        current_task_id: windowTask.id,
                        logs: newLogs,
                        is_finished: false
                    })
                });
                
                setShowWindow(false); // Close window after start
            };

            const handleCompleteTask = async () => {
                if (!windowTask) return;

                const valStr = tagValues.map(t => {
                    const numVal = parseFloat(t.value);
                    const displayVal = !isNaN(numVal) ? numVal.toFixed(windowTask.precision || 2) : t.value;
                    return `${t.tag}=${displayVal} ${windowTask.unit || ''}`;
                }).join(', ') || '-';

                const newLog = {
                    time: new Date().toLocaleTimeString(),
                    source: 'User',
                    message: `任務完成: ${windowTask.name}`,
                    value: valStr,
                    note: note
                };
                const newLogs = [...logs, newLog];
                setLogs(newLogs);
                setCurrentRunningTaskId(null); 
                setWindowTask(prev => ({ ...prev, status: 'completed' }));

                // Sync Update
                if (viewerRef.current) {
                    viewerRef.current._customState = {
                        runningTaskId: null,
                        logs: newLogs
                    };
                }

                // Update Visuals
                const canvas = viewerRef.current.get('canvas');
                canvas.removeMarker(windowTask.id, 'highlight');
                canvas.addMarker(windowTask.id, 'completed-task');

                // Save
                await fetch(`${API_BASE}/sessions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        process_id: processId,
                        current_task_id: null,
                        logs: newLogs,
                        is_finished: false 
                    })
                });
                
                setShowWindow(false);
            };

            const handleFinishProcess = async () => {
                if (!confirm('確定要結束整個流程並匯出紀錄嗎？')) return;
                
                const newLog = {
                    time: new Date().toLocaleTimeString(),
                    source: 'System',
                    message: '流程結束',
                    value: '-',
                    note: ''
                };
                const newLogs = [...logs, newLog];
                setLogs(newLogs);
                setIsFinished(true);

                await fetch(`${API_BASE}/sessions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        process_id: processId,
                        current_task_id: null,
                        logs: newLogs,
                        is_finished: true
                    })
                });
                alert('流程已完成！');
                setShowWindow(false); // Close the window
                
                // Auto Export CSV
                handleExportCSV(newLogs);
            };

            const [onlineCount, setOnlineCount] = useState(1);
            const userId = useMemo(() => 'user_' + Math.random().toString(36).substr(2, 9), []);

            // Heartbeat for Online Count
            useEffect(() => {
                if (!processId) return;

                const sendHeartbeat = async () => {
                    try {
                        const res = await fetch(`${API_BASE}/heartbeat`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ process_id: processId, user_id: userId })
                        });
                        if (res.ok) {
                            const data = await res.json();
                            setOnlineCount(data.online_count);
                        }
                    } catch (e) {
                        console.error("Heartbeat error:", e);
                    }
                };

                sendHeartbeat(); // Initial call
                const interval = setInterval(sendHeartbeat, 5000); // Every 5 seconds
                return () => clearInterval(interval);
            }, [processId, userId]);

            const headerActions = (
                <div className="flex gap-2 items-center">
                    <div className="bg-[#2d2d2d] px-3 py-1 rounded-full flex items-center gap-2 border border-white/10 mr-2" title="在線人數">
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                        </span>
                        <span className="text-white/80 text-xs font-medium">{onlineCount} 人在線</span>
                    </div>

                    <button 
                        onClick={() => handleExportCSV(logs)}
                        className="bg-[#81c995] hover:bg-[#a8dab5] text-[#0f5132] px-4 py-1 rounded-full font-medium shadow-sm transition text-sm"
                    >
                        匯出 CSV
                    </button>

                    {!isFinished && (
                        <button 
                            onClick={handleFinishProcess}
                            className="bg-[#f28b82] hover:bg-[#f6aea9] text-[#5c1e1e] px-6 py-1 rounded-full font-medium shadow-sm transition text-sm"
                        >
                            結束流程
                        </button>
                    )}
                    
                    <button 
                        onClick={() => onNavigate('dashboard')}
                        className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 px-4 py-1 rounded-full text-sm font-medium transition"
                    >
                        返回首頁
                    </button>
                </div>
            );

            return (
                <div className="flex flex-col h-full relative">
                    {/* Top: Timeline (1/4) */}
                    <div className="h-1/4 min-h-[180px] flex flex-col bg-[#1e1e1e]">
                        <TimelineViewer logs={logs} headerActions={headerActions} onUpdateLog={handleUpdateLog} />
                    </div>

                    {/* Bottom: BPMN (3/4) */}
                    <div className="flex-1 relative bg-white border-t-4 border-[#1e1e1e]">
                        <div ref={containerRef} className="w-full h-full operator-mode"></div>
                        
                        {/* Zoom Controls */}
                        <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
                            <button onClick={() => handleZoom(0.2)} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] font-bold text-xl">+</button>
                            <button onClick={() => handleZoom(-0.2)} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] font-bold text-xl">-</button>
                            <button onClick={() => viewerRef.current.get('canvas').zoom('fit-viewport')} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] text-xs">Fit</button>
                        </div>

                        {/* Floating Window */}
                        {showWindow && (
                            <FloatingTaskWindow 
                                task={windowTask} 
                                onStart={handleStartTask}
                                onEnd={handleCompleteTask}
                                onFinish={handleFinishProcess}
                                onClose={() => setShowWindow(false)}
                                note={note}
                                setNote={setNote}
                                tagValues={tagValues}
                                loadingTag={loadingTag}
                            />
                        )}
                        </div>
                </div>
            );
        };

        // 4. Review Mode
        const Review = ({ processId, onNavigate }) => {
            const containerRef = useRef(null);
            const [csvData, setCsvData] = useState([]);
            const viewerRef = useRef(null);
            const [processName, setProcessName] = useState('');
            const [isLoaded, setIsLoaded] = useState(false);

            // Helper to apply styles (Sticky Notes) - Reused from Operator logic
            const applyStyles = useCallback(() => {
                if (!viewerRef.current) return;
                const viewer = viewerRef.current;
                const canvas = viewer.get('canvas');
                const elementRegistry = viewer.get('elementRegistry');
                const graphicsFactory = viewer.get('graphicsFactory');

                const elements = elementRegistry.filter(e => e.type !== 'bpmn:Process');
                
                elements.forEach(element => {
                    const gfx = elementRegistry.getGraphics(element);
                    const businessObj = element.businessObject;
                    const docs = businessObj.documentation;
                    
                    if (element.type === 'bpmn:Group' || element.type === 'bpmn:TextAnnotation') {
                        try {
                            let data = {};
                            if (docs && docs.length > 0 && docs[0].text) {
                                data = JSON.parse(docs[0].text);
                            } else if (element.type === 'bpmn:Group') {
                                data = { noteColor: '#fff2cc', borderColor: '#d6b656' };
                            }

                            if (data.noteColor || data.htmlContent || data.textFontSize || data.textColor) {
                                // Sticky Note Logic (Simplified for Review - just render)
                                const path = gfx.querySelector('.djs-visual path');
                                if (path) path.style.display = 'none';
                                
                                const rect = gfx.querySelector('.djs-visual rect');
                                if (rect) rect.style.display = 'none';

                                let existing = gfx.querySelector('.sticky-bg');
                                if (existing) existing.remove();
                                let existingFo = gfx.querySelector('.sticky-fo');
                                if (existingFo) existingFo.remove();

                                const width = element.width;
                                const height = element.height;

                                const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                                bgRect.classList.add('sticky-bg');
                                bgRect.setAttribute('width', width);
                                bgRect.setAttribute('height', height);
                                bgRect.setAttribute('fill', data.noteColor || 'transparent');
                                bgRect.setAttribute('stroke', data.borderColor || 'transparent');
                                bgRect.setAttribute('fill-opacity', data.noteOpacity !== undefined ? data.noteOpacity : 1);
                                gfx.prepend(bgRect);

                                const fo = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
                                fo.classList.add('sticky-fo');
                                fo.setAttribute('width', width);
                                fo.setAttribute('height', height);
                                
                                const div = document.createElement('div');
                                div.style.width = '100%';
                                div.style.height = '100%';
                                div.style.padding = '10px';
                                div.style.boxSizing = 'border-box';
                                div.style.overflow = 'hidden';
                                div.style.fontSize = `${data.textFontSize || 12}px`;
                                div.style.fontWeight = data.textBold ? 'bold' : 'normal';
                                div.style.color = data.textColor || '#000000';
                                div.style.fontFamily = 'Arial, sans-serif';
                                div.style.whiteSpace = 'pre-wrap';
                                div.style.wordBreak = 'break-word';
                                div.innerHTML = data.htmlContent || (docs && docs[0] && docs[0].text ? JSON.parse(docs[0].text).text : '') || '';
                                
                                fo.appendChild(div);
                                gfx.appendChild(fo);
                            }
                            
                            if (data.nameFontSize) {
                                const label = gfx.querySelector('.djs-label');
                                if (label) label.style.fontSize = `${data.nameFontSize}px`;
                            }
                        } catch(e) {}
                    }
                });
            }, []);

            const [currentProcess, setCurrentProcess] = useState(null);

            useEffect(() => {
                if (!processId) return;
                const viewer = new BpmnJS({ container: containerRef.current });
                viewerRef.current = viewer;
                
                const load = async () => {
                    try {
                        const res = await fetch(`${API_BASE}/processes/${processId}`);
                        const data = await res.json();
                        setProcessName(data.name);
                        setCurrentProcess(data); // Store full process info for version check
                        await viewer.importXML(data.xml_content);
                        viewer.get('canvas').zoom('fit-viewport');
                        
                        // Lock Diagram
                        const eventBus = viewer.get('eventBus');
                        const events = [
                            'shape.move.start', 'connection.create.start', 'shape.resize.start',
                            'element.dblclick', 'contextPad.open', 'palette.create', 'autoPlace.start'
                        ];
                        events.forEach(event => eventBus.on(event, 10000, () => false));

                        // Apply Sticky Note Styles
                        setTimeout(applyStyles, 500);

                    } catch(e) { console.error(e); }
                };
                load();
                
                return () => { if(viewerRef.current) viewerRef.current.destroy(); };
            }, [processId, applyStyles]);

            // Sync Visuals with Logs
            useEffect(() => {
                if (!viewerRef.current || csvData.length === 0) return;
                const viewer = viewerRef.current;
                const canvas = viewer.get('canvas');
                const elementRegistry = viewer.get('elementRegistry');
                const modeling = viewer.get('modeling'); // Viewer doesn't have modeling, use Overlays or Markers

                // Reset all styles first if needed (optional)

                // Track status of each task
                const taskStatus = {}; // name -> 'running' | 'completed'

                csvData.forEach(log => {
                    if (log.message.includes('任務開始:')) {
                        const name = log.message.split(': ')[1].trim();
                        if (!taskStatus[name]) taskStatus[name] = 'running';
                    } else if (log.message.includes('任務完成:')) {
                        const name = log.message.split(': ')[1].trim();
                        taskStatus[name] = 'completed';
                    }
                });

                // Apply to Elements
                elementRegistry.forEach(element => {
                    const name = element.businessObject.name;
                    if (name && taskStatus[name]) {
                        const status = taskStatus[name];
                        if (status === 'completed') {
                            canvas.addMarker(element.id, 'completed'); // Use CSS class for gray fill
                            // Or use direct SVG manipulation if CSS isn't enough for fill
                            const gfx = elementRegistry.getGraphics(element);
                            const visual = gfx.querySelector('.djs-visual rect, .djs-visual circle, .djs-visual polygon');
                            if (visual) {
                                visual.style.fill = '#f0f0f0';
                                visual.style.stroke = '#999';
                            }
                        } else if (status === 'running') {
                            canvas.addMarker(element.id, 'highlight'); // Use existing highlight class
                        }
                    }
                });

            }, [csvData]);

            const parseCSVLine = (text) => {
                const result = [];
                let start = 0;
                let inQuotes = false;
                for (let i = 0; i < text.length; i++) {
                    if (text[i] === '"') {
                        inQuotes = !inQuotes;
                    } else if (text[i] === ',' && !inQuotes) {
                        let field = text.substring(start, i).trim();
                        if (field.startsWith('"') && field.endsWith('"')) {
                            field = field.substring(1, field.length - 1);
                        }
                        result.push(field);
                        start = i + 1;
                    }
                }
                let lastField = text.substring(start).trim();
                if (lastField.startsWith('"') && lastField.endsWith('"')) {
                    lastField = lastField.substring(1, lastField.length - 1);
                }
                result.push(lastField);
                return result;
            };

            const handleFileUpload = (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = (evt) => {
                    const text = evt.target.result;
                    const lines = text.split('\\n');
                    
                    let startIndex = 1; // Default skip header
                    
                    // Check Metadata
                    if (lines[0].startsWith('# Metadata:')) {
                        startIndex = 2; // Skip metadata + header
                        const metaParts = lines[0].substring(11).split(',');
                        let csvId = null;
                        let csvVersion = null;
                        
                        metaParts.forEach(part => {
                            const [key, val] = part.split('=').map(s => s.trim());
                            if (key === 'id') csvId = parseInt(val);
                            if (key === 'version') csvVersion = val;
                        });

                        if (currentProcess) {
                            if (csvId !== currentProcess.id) {
                                alert(`警告：此紀錄檔屬於不同的流程專案 (ID: ${csvId})，與目前專案 (ID: ${currentProcess.id}) 不符！`);
                            } else if (csvVersion !== currentProcess.updated_at) {
                                alert(`警告：此紀錄檔的版本 (${csvVersion}) 與目前流程版本 (${currentProcess.updated_at}) 不同，可能會導致顯示錯誤！`);
                            }
                        }
                    }

                    const data = lines.slice(startIndex).map(line => {
                        if (!line.trim()) return null;
                        const cols = parseCSVLine(line);
                        if (cols.length < 4) return null;
                        return { 
                            time: cols[0], 
                            source: cols[1], 
                            message: cols[2], 
                            value: cols[3], 
                            note: cols[4] || '' 
                        };
                    }).filter(x => x && x.time);
                    setCsvData(data);
                    setIsLoaded(true);
                };
                reader.readAsText(file);
            };

            const headerActions = (
                <div className="flex gap-2 items-center">
                    <button 
                        onClick={() => onNavigate('dashboard')}
                        className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 px-4 py-1 rounded-full text-sm font-medium transition"
                    >
                        返回首頁
                    </button>
                </div>
            );

            return (
                <div className="flex flex-col h-full relative">
                    {/* Top: Timeline (1/4) */}
                    <div className="h-1/4 min-h-[180px] flex flex-col bg-[#1e1e1e]">
                        <TimelineViewer logs={csvData} headerActions={headerActions} />
                    </div>

                    {/* Bottom: BPMN (3/4) */}
                    <div className="flex-1 relative bg-white border-t-4 border-[#1e1e1e]">
                        <div ref={containerRef} className="w-full h-full operator-mode"></div>
                        
                        {/* Import Overlay */}
                        {!isLoaded && (
                            <div className="absolute inset-0 bg-black/80 z-50 flex flex-col items-center justify-center">
                                <div className="bg-[#1e1e1e] p-8 rounded-2xl border border-white/10 text-center max-w-md">
                                    <div className="text-4xl mb-4">📂</div>
                                    <h3 className="text-xl font-bold text-white mb-2">匯入回顧資料</h3>
                                    <p className="text-white/60 mb-6 text-sm">請選擇先前匯出的 CSV 檔案以進行回顧。</p>
                                    
                                    <label className="bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-6 py-2 rounded-full font-bold cursor-pointer transition inline-flex items-center gap-2">
                                        <span>選擇檔案</span>
                                        <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
                                    </label>
                                </div>
                            </div>
                        )}

                        {/* Zoom Controls */}
                        <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
                            <button onClick={() => viewerRef.current.get('canvas').zoom(viewerRef.current.get('canvas').zoom() + 0.2)} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] font-bold text-xl">+</button>
                            <button onClick={() => viewerRef.current.get('canvas').zoom(viewerRef.current.get('canvas').zoom() - 0.2)} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] font-bold text-xl">-</button>
                            <button onClick={() => viewerRef.current.get('canvas').zoom('fit-viewport')} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] text-xs">Fit</button>
                        </div>
                    </div>
                </div>
            );
        };

        // 5. Settings
        const Settings = ({ onNavigate }) => {
            const [ip, setIp] = useState('');
            const [loading, setLoading] = useState(false);

            useEffect(() => {
                fetch(`${API_BASE}/settings`)
                    .then(res => res.json())
                    .then(data => setIp(data.pi_server_ip));
            }, []);

            const handleSave = async () => {
                setLoading(true);
                await fetch(`${API_BASE}/settings`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pi_server_ip: ip })
                });
                setLoading(false);
                alert('設定已儲存');
                onNavigate('dashboard');
            };

            return (
                <div className="flex h-full flex-col bg-[#121212] items-center justify-center">
                    <div className="bg-[#1e1e1e] p-8 rounded-2xl border border-white/5 w-full max-w-md shadow-xl">
                        <h2 className="text-2xl font-medium text-white/90 mb-6">系統設定</h2>
                        
                        <div className="mb-6">
                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">PI Server IP Address</label>
                            <input 
                                value={ip} 
                                onChange={(e) => setIp(e.target.value)} 
                                className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-4 py-3 text-white outline-none transition" 
                                placeholder="例如: 10.122.51.60" 
                            />
                            <p className="text-white/40 text-xs mt-2">系統將使用 Ping 指令檢查此 IP 的連線狀態。</p>
                        </div>
                        
                        <div className="flex gap-3">
                            <button onClick={() => onNavigate('dashboard')} className="flex-1 bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 py-3 rounded-full font-medium transition">取消</button>
                            <button onClick={handleSave} disabled={loading} className="flex-1 bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] py-3 rounded-full font-medium transition">
                                {loading ? '儲存中...' : '儲存設定'}
                            </button>
                        </div>
                    </div>
                </div>
            );
        };

        const App = () => {
            const [page, setPage] = useState('dashboard');
            const [activeProcessId, setActiveProcessId] = useState(null);
            const navigate = (target, id = null) => { setActiveProcessId(id); setPage(target); };
            return (
                <div className="h-full">
                    {page === 'dashboard' && <Dashboard onNavigate={navigate} />}
                    {page === 'editor' && <Editor processId={activeProcessId} onNavigate={navigate} />}
                    {page === 'operator' && <Operator processId={activeProcessId} onNavigate={navigate} />}
                    {page === 'review' && <Review processId={activeProcessId} onNavigate={navigate} />}
                    {page === 'settings' && <Settings onNavigate={navigate} />}
                </div>
            );
        };

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<App />);
    </script>
</body>
</html>
"""

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
init_db()

if __name__ == '__main__':
    # Ensure static folder exists
    if not os.path.exists('static'):
        print("WARNING: 'static' folder not found. Please run download_assets.ps1 first.")
    app.run(debug=True, port=5000, host='0.0.0.0')
