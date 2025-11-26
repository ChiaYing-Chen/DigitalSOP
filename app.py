import os
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
DB_FILE = 'sops.db'

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
    
    conn.commit()
    conn.close()

# --- Routes ---

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

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
    c.execute("SELECT id, name, xml_content FROM processes WHERE id=?", (process_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify({'id': row[0], 'name': row[1], 'xml_content': row[2]})
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT current_task_id, logs, is_finished FROM sessions WHERE process_id=?", (process_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify({'current_task_id': row[0], 'logs': json.loads(row[1]), 'is_finished': bool(row[2])})
    return jsonify(None)

@app.route('/api/sessions', methods=['POST'])
def save_session():
    data = request.json
    process_id = data.get('process_id')
    current_task_id = data.get('current_task_id')
    logs = json.dumps(data.get('logs', []))
    is_finished = data.get('is_finished', False)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO sessions (process_id, current_task_id, logs, is_finished, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
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
    
    # Check if key exists, insert or update
    c.execute("SELECT 1 FROM settings WHERE key='pi_server_ip'")
    if c.fetchone():
        c.execute("UPDATE settings SET value=? WHERE key='pi_server_ip'", (ip,))
    else:
        c.execute("INSERT INTO settings (key, value) VALUES ('pi_server_ip', ?)", (ip,))
        
    conn.commit()
    conn.close()
    return jsonify({'result': 'success'})

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
    <script src="/static/js/tailwindcss.js"></script>
    <link rel="stylesheet" href="/static/css/diagram-js.css" />
    <link rel="stylesheet" href="/static/css/bpmn.css" />
    
    <!-- React & Babel -->
    <script src="/static/js/react.js"></script>
    <script src="/static/js/react-dom.js"></script>
    <script src="/static/js/babel.js"></script>
    
    <!-- BPMN-JS -->
    <script src="/static/js/bpmn-modeler.js"></script>
    
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
        const { useState, useEffect, useRef, useMemo } = React;

        // --- Utils ---
        const API_BASE = '/api';
        
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
        
        // --- Components ---
        
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
                a.download = `${p.name}.bpmn`;
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
            const [showHelp, setShowHelp] = useState(false);
            const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
            const [isFinalEnd, setIsFinalEnd] = useState(false);

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
                    } catch (err) { console.error(err); }
                };
                loadDiagram();

                modeler.on('selection.changed', (e) => {
                    const selection = e.newSelection;
                    if (selection.length === 1) {
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
                            } catch(e) { 
                                setPiTag(''); setPiUnit(''); setPiPrecision(2); setTargetUrl(''); setIsFinalEnd(false);
                            }
                        } else { 
                            setPiTag(''); setPiUnit(''); setPiPrecision(2); setTargetUrl(''); setIsFinalEnd(false);
                        }
                    } else { 
                        setSelectedElement(null); setElementName(''); setPiTag(''); setPiUnit(''); setPiPrecision(2); setTargetUrl(''); setIsFinalEnd(false);
                    }
                });
                
                modeler.on('element.changed', (e) => {
                    if (selectedElement && e.element.id === selectedElement.id) { setElementName(e.element.businessObject.name || ''); }
                });

                modeler.on('commandStack.changed', () => {
                    setHasUnsavedChanges(true);
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

            const updateElementName = (val) => {
                setElementName(val);
                if (selectedElement && modelerRef.current) { modelerRef.current.get('modeling').updateLabel(selectedElement, val); }
            };

            const updateElementProperties = (tag, unit, precision, url, finalEnd) => {
                setPiTag(tag);
                setPiUnit(unit);
                setPiPrecision(precision);
                setTargetUrl(url);
                setIsFinalEnd(finalEnd);
                
                if (selectedElement && modelerRef.current) {
                    const modeling = modelerRef.current.get('modeling');
                    const bpmnFactory = modelerRef.current.get('bpmnFactory');
                    const elementRegistry = modelerRef.current.get('elementRegistry');

                    // If setting as Final End, uncheck others
                    if (finalEnd && selectedElement.type === 'bpmn:EndEvent') {
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
                        text: JSON.stringify({ piTag: tag, piUnit: unit, piPrecision: parseInt(precision), targetUrl: url, isFinalEnd: finalEnd }) 
                    });
                    modeling.updateProperties(selectedElement, { documentation: [newDoc] });
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
                        <div className="flex gap-3">
                            <button onClick={() => setShowHelp(!showHelp)} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 w-10 h-10 rounded-full font-bold transition flex items-center justify-center" title="BPMN 說明">?</button>
                            <button onClick={handleSave} className="bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-6 py-2 rounded-full font-medium shadow-sm transition">儲存流程</button>
                        </div>
                    </div>
                    <div className="flex-1 flex overflow-hidden relative">
                        <div className="flex-1 relative bg-white" ref={containerRef}></div>
                        
                        {/* Help Modal */}
                        {showHelp && (
                            <div className="absolute top-4 right-80 w-80 bg-[#1e1e1e] border border-white/10 rounded-xl shadow-2xl p-6 z-20 text-white/90 overflow-y-auto max-h-[80%]">
                                <div className="flex justify-between items-center mb-4">
                                    <h3 className="font-bold text-lg text-[#8ab4f8]">BPMN 元件說明</h3>
                                    <button onClick={() => setShowHelp(false)} className="text-white/40 hover:text-white">✕</button>
                                </div>
                                <div className="space-y-4 text-sm">
                                    <div>
                                        <div className="font-bold text-[#81c995] mb-1">Start Event (開始)</div>
                                        <p className="text-white/60">流程的起點。每個流程至少需要一個開始事件。</p>
                                    </div>
                                    <div>
                                        <div className="font-bold text-[#81c995] mb-1">Task (任務)</div>
                                        <p className="text-white/60">流程中需要執行的具體工作或步驟。可綁定 PI Tag 顯示即時數據。</p>
                                    </div>
                                    <div>
                                        <div className="font-bold text-[#81c995] mb-1">Gateway (閘道)</div>
                                        <p className="text-white/60">用於控制流程的分支與合併。例如：根據條件走不同的路徑。</p>
                                    </div>
                                    <div>
                                        <div className="font-bold text-[#81c995] mb-1">End Event (結束)</div>
                                        <p className="text-white/60">流程的終點。表示該流程路徑已完成。</p>
                                    </div>
                                    <div>
                                        <div className="font-bold text-[#81c995] mb-1">Data Object (資料物件)</div>
                                        <p className="text-white/60">表示流程中使用的文件或數據。可設定超連結，點擊後開啟外部網頁。</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="w-80 bg-[#1e1e1e] border-l border-white/5 p-6 overflow-y-auto">
                            <h3 className="font-medium text-white/90 mb-6 text-lg">屬性面板</h3>
                            {selectedElement ? (
                                <div>
                                    <div className="mb-5">
                                        <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">ID</label>
                                        <input disabled value={selectedElement.id} className="w-full bg-[#2d2d2d] border-none rounded-lg px-3 py-2 text-white/60 text-sm font-mono" />
                                    </div>
                                    <div className="mb-5">
                                        <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">類型</label>
                                        <input disabled value={selectedElement.type} className="w-full bg-[#2d2d2d] border-none rounded-lg px-3 py-2 text-white/60 text-sm font-mono" />
                                    </div>
                                    <div className="mb-5">
                                        <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">名稱 (Name)</label>
                                        <input value={elementName} onChange={(e) => updateElementName(e.target.value)} className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition" placeholder="輸入名稱..." />
                                    </div>

                                    {/* Color Picker */}
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
                                    
                                    {/* PI Tag Config (Only for Tasks usually, but enabling for all for flexibility) */}
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
                                                updateElementProperties(val, piUnit, piPrecision, targetUrl);
                                            }} 
                                            className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition mb-2" 
                                            placeholder="例如: Tag1;Tag2 (最多4個)" 
                                        />
                                        <div className="flex gap-2">
                                            <div className="flex-1">
                                                <label className="block text-[10px] text-white/40 mb-1">工程單位</label>
                                                <input 
                                                    value={piUnit} 
                                                    onChange={(e) => updateElementProperties(piTag, e.target.value, piPrecision, targetUrl)} 
                                                    className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition text-sm" 
                                                    placeholder="例如: °C" 
                                                />
                                            </div>
                                            <div className="w-20">
                                                <label className="block text-[10px] text-white/40 mb-1">小數位數</label>
                                                <input 
                                                    type="number"
                                                    min="0"
                                                    max="5"
                                                    value={piPrecision} 
                                                    onChange={(e) => updateElementProperties(piTag, piUnit, e.target.value, targetUrl)} 
                                                    className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition text-sm" 
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Hyperlink Config (For Data Objects) */}
                                    {(selectedElement.type === 'bpmn:DataObjectReference' || selectedElement.type === 'bpmn:DataStoreReference') && (
                                        <div className="mb-5">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">超連結 (Hyperlink)</label>
                                            <input 
                                                value={targetUrl} 
                                                onChange={(e) => updateElementProperties(piTag, piUnit, piPrecision, e.target.value, isFinalEnd)} 
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
                                                    onChange={(e) => updateElementProperties(piTag, piUnit, piPrecision, targetUrl, e.target.checked)} 
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

        // 3. Operator (Execution Mode)
        const Operator = ({ processId, onNavigate }) => {
            const containerRef = useRef(null);
            const [logs, setLogs] = useState([]);
            const [currentTask, setCurrentTask] = useState(null);
            const [tagValues, setTagValues] = useState([]);
            const [loadingTag, setLoadingTag] = useState(false);
            const [note, setNote] = useState('');
            const [isFinished, setIsFinished] = useState(false);
            const viewerRef = useRef(null);
            const [processName, setProcessName] = useState('');
            const intervalRef = useRef(null);

            useEffect(() => {
                const viewer = new BpmnJS({ container: containerRef.current });
                viewerRef.current = viewer;
                const load = async () => {
                    const res = await fetch(`${API_BASE}/processes/${processId}`);
                    const data = await res.json();
                    setProcessName(data.name);
                    try {
                        await viewer.importXML(data.xml_content);
                        viewer.get('canvas').zoom('fit-viewport');
                        
                        // Restore Session
                        const sessionRes = await fetch(`${API_BASE}/sessions/${processId}`);
                        const sessionData = await sessionRes.json();
                        
                        if (sessionData) {
                            setLogs(sessionData.logs);
                            setIsFinished(sessionData.is_finished);
                            if (!sessionData.is_finished && sessionData.current_task_id) {
                                const element = viewer.get('elementRegistry').get(sessionData.current_task_id);
                                if (element) handleElementClick(element);
                            } else if (!sessionData.is_finished) {
                                // Fallback to start
                                const startEvents = viewer.get('elementRegistry').filter(e => e.type === 'bpmn:StartEvent');
                                if (startEvents.length > 0) handleElementClick(startEvents[0]);
                            }
                        } else {
                            addLog('系統', '流程已載入，準備開始');
                            const startEvents = viewer.get('elementRegistry').filter(e => e.type === 'bpmn:StartEvent');
                            if (startEvents.length > 0) handleElementClick(startEvents[0]);
                        }
                        
                        // Apply Cursor Styles & Hyperlink Markers
                        const canvas = viewer.get('canvas');
                        const elementRegistry = viewer.get('elementRegistry');
                        elementRegistry.forEach(element => {
                            const docs = element.businessObject.documentation;
                            if (docs && docs.length > 0 && docs[0].text) {
                                try {
                                    const data = JSON.parse(docs[0].text);
                                    if (data.targetUrl) {
                                        canvas.addMarker(element.id, 'has-hyperlink');
                                    }
                                } catch(e) {}
                            }
                        });
                        
                    } catch (err) { console.error(err); }
                };
                load();
                return () => {
                    if (intervalRef.current) clearInterval(intervalRef.current);
                    viewer.destroy();
                };
            }, [processId]);

            const saveSession = async (newLogs, currentTaskId, finished) => {
                await fetch(`${API_BASE}/sessions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        process_id: processId,
                        current_task_id: currentTaskId,
                        logs: newLogs,
                        is_finished: finished
                    })
                });
            };

            const [completedTaskIds, setCompletedTaskIds] = useState(new Set());

            useEffect(() => {
                const ids = new Set(logs.filter(l => l.taskId).map(l => l.taskId));
                setCompletedTaskIds(ids);
            }, [logs]);

            const addLog = (source, message, value = '-', note = '', taskId = null) => {
                const newLog = { time: new Date().toLocaleTimeString(), source, message, value, note, taskId };
                setLogs(prev => {
                    const updatedLogs = [...prev, newLog];
                    return updatedLogs;
                });
                return newLog; // Return for immediate usage
            };

            const updateOverlay = (elementId, data, precision, unit) => {
                if (!viewerRef.current) return;
                const overlays = viewerRef.current.get('overlays');
                overlays.remove({ element: elementId });
                if (data && data.length > 0) {
                    const htmlContent = data.map(d => `<div>${d.tag}: ${formatValue(d.value, precision, unit)}</div>`).join('');
                    overlays.add(elementId, {
                        position: { bottom: 10, right: 10 },
                        html: `<div style="background: #81c995; color: #0f5132; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2); text-align: right; line-height: 1.2;">${htmlContent}</div>`
                    });
                }
            };

            const fetchTagValue = async (tag) => {
                try {
                    const res = await fetch(`${API_BASE}/get_tag_value?tag=${encodeURIComponent(tag)}`);
                    const data = await res.json();
                    return data;
                } catch (e) {
                    console.error(e);
                    return [];
                }
            };

            const formatValue = (val, precision, unit) => {
                if (val === null || val === undefined || val === 'Error' || val === 'Offline') return val;
                const num = parseFloat(val);
                if (isNaN(num)) return val;
                return `${num.toFixed(precision)}${unit ? ' ' + unit : ''}`;
            };

            const checkPredecessors = (element) => {
                if (!element) return false;
                if (element.type === 'bpmn:StartEvent') return true;
                
                const incoming = element.businessObject.incoming;
                if (!incoming || incoming.length === 0) return true; // Isolated or implicit start

                // Check if at least one incoming flow comes from a completed task
                return incoming.some(flow => completedTaskIds.has(flow.sourceRef.id));
            };

            const handleElementClick = async (element) => {
                // Whitelist allowed types for interaction
                const allowedTypes = [
                    'bpmn:StartEvent', 'bpmn:EndEvent', 'bpmn:Task', 'bpmn:UserTask', 
                    'bpmn:ServiceTask', 'bpmn:ManualTask', 'bpmn:ScriptTask', 
                    'bpmn:BusinessRuleTask', 'bpmn:CallActivity', 'bpmn:SubProcess', 
                    'bpmn:ExclusiveGateway', 'bpmn:ParallelGateway', 'bpmn:InclusiveGateway', 
                    'bpmn:ComplexGateway', 'bpmn:EventBasedGateway', 
                    'bpmn:DataObjectReference', 'bpmn:DataStoreReference'
                ];
                
                if (!allowedTypes.includes(element.type)) return;

                // Clear previous interval
                if (intervalRef.current) {
                    clearInterval(intervalRef.current);
                    intervalRef.current = null;
                }
                
                // Clear previous overlays
                if (viewerRef.current) {
                    viewerRef.current.get('overlays').clear();
                }

                const docs = element.businessObject.documentation;
                let tag = null;
                let unit = '';
                let precision = 2;
                let targetUrl = '';

                if (docs && docs.length > 0 && docs[0].text) {
                    try { 
                        const data = JSON.parse(docs[0].text);
                        tag = data.piTag;
                        unit = data.piUnit || '';
                        precision = data.piPrecision !== undefined ? data.piPrecision : 2;
                        targetUrl = data.targetUrl || '';
                    } catch(e) {}
                }
                
                // Handle Hyperlink Click
                if (targetUrl) {
                    window.open(targetUrl, '_blank');
                    // We don't return here because we might still want to show details if it's also a task (unlikely but possible)
                    // But for Data Objects, usually they are just for reference.
                }

                setCurrentTask({ id: element.id, name: element.businessObject.name || element.id, tag, unit, precision, elementObj: element });
                
                // Highlight Logic
                if (viewerRef.current) {
                    const canvas = viewerRef.current.get('canvas');
                    const registry = viewerRef.current.get('elementRegistry');
                    // Remove highlight from all elements
                    registry.forEach(e => canvas.removeMarker(e.id, 'highlight'));
                    // Add highlight to current
                    canvas.addMarker(element.id, 'highlight');
                }

                if (tag) {
                    setLoadingTag(true);
                    try {
                        // Initial Fetch
                        const data = await fetchTagValue(tag);
                        setTagValues(data);
                        
                        const formattedVal = data.length > 0 ? formatValue(data[0].value, precision, unit) : '-';
                        const valStr = data.map(d => `${d.tag}=${formatValue(d.value, precision, unit)}`).join(', ');
                        
                        // Log Start Value
                        addLog('PI Server', `開始任務: ${element.businessObject.name || element.id}`, valStr, 'Start Value');
                        
                        // Update Overlay
                        if (data.length > 0) {
                            updateOverlay(element.id, data, precision, unit);
                        }

                        // Start Polling (10s)
                        intervalRef.current = setInterval(async () => {
                            const polledData = await fetchTagValue(tag);
                            setTagValues(polledData);
                            if (polledData.length > 0) {
                                updateOverlay(element.id, polledData, precision, unit);
                            }
                        }, 10000);

                    } catch (e) { 
                        addLog('Error', '讀取失敗'); 
                        setTagValues([]); 
                    } finally { 
                        setLoadingTag(false); 
                    }
                } else { 
                    setTagValues([]); 
                }
            };

            useEffect(() => {
                if (!viewerRef.current) return;
                const eventBus = viewerRef.current.get('eventBus');
                
                // Lock Diagram: Disable interactions
                const events = [
                    'shape.move.start',
                    'connection.create.start',
                    'shape.resize.start',
                    'element.dblclick', // Prevent direct editing
                    'contextPad.open', 
                    'palette.create', 
                    'autoPlace.start'
                ];
                const preventDefault = (e) => false;
                events.forEach(event => eventBus.on(event, 10000, preventDefault));

                const listener = (e) => {
                    handleElementClick(e.element);
                };
                eventBus.on('element.click', listener);

                // Tooltip for Hyperlinks
                eventBus.on('element.hover', (e) => {
                    const docs = e.element.businessObject.documentation;
                    if (docs && docs.length > 0 && docs[0].text) {
                        try {
                            const data = JSON.parse(docs[0].text);
                            if (data.targetUrl) {
                                viewerRef.current.get('overlays').add(e.element.id, 'url-tooltip', {
                                    position: { top: -25, left: 0 },
                                    html: `<div style="background: rgba(30,30,30,0.9); color: #8ab4f8; padding: 4px 8px; border-radius: 4px; font-size: 11px; border: 1px solid #8ab4f8; pointer-events: none; white-space: nowrap; z-index: 1000;">🔗 ${data.targetUrl}</div>`
                                });
                            }
                        } catch(err) {}
                    }
                });

                eventBus.on('element.out', (e) => {
                    viewerRef.current.get('overlays').remove({ type: 'url-tooltip' });
                });

                // Mouse Wheel Zoom
                const handleWheel = (e) => {
                    e.preventDefault();
                    const canvas = viewerRef.current.get('canvas');
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
                    eventBus.off('element.click', listener);
                    events.forEach(event => eventBus.off(event, preventDefault));
                    container.removeEventListener('wheel', handleWheel);
                };
            }, [viewerRef.current, completedTaskIds]); // Depend on completedTaskIds for validation updates? No, handleElementClick uses state.

            const handleRestart = async () => {
                if(!confirm('確定要重新開始流程嗎？所有紀錄將被清除。')) return;
                
                if (intervalRef.current) clearInterval(intervalRef.current);
                if (viewerRef.current) viewerRef.current.get('overlays').clear();

                setLogs([]);
                setCompletedTaskIds(new Set());
                setIsFinished(false);
                setNote('');
                
                // Reset to Start Event
                if (viewerRef.current) {
                    const startEvents = viewerRef.current.get('elementRegistry').filter(e => e.type === 'bpmn:StartEvent');
                    if (startEvents.length > 0) {
                        handleElementClick(startEvents[0]);
                        saveSession([], startEvents[0].id, false);
                    } else {
                        setCurrentTask(null);
                        saveSession([], null, false);
                    }
                }
                addLog('系統', '流程已重置');
            };

            const handleAbort = async () => {
                const reason = prompt('請輸入中止原因：');
                if (reason === null) return; // Cancelled
                
                if (intervalRef.current) clearInterval(intervalRef.current);
                
                const newLog = { time: new Date().toLocaleTimeString(), source: 'User', message: `流程中止: ${reason}`, value: '-', note };
                const updatedLogs = [...logs, newLog];
                setLogs(updatedLogs);
                setNote('');
                
                // Find End Event to move token there
                let endEventId = null;
                if (viewerRef.current) {
                    const endEvents = viewerRef.current.get('elementRegistry').filter(e => e.type === 'bpmn:EndEvent');
                    if (endEvents.length > 0) {
                        endEventId = endEvents[0].id;
                        // Remove highlight from current
                        if (currentTask) {
                            viewerRef.current.get('canvas').removeMarker(currentTask.id, 'highlight');
                            viewerRef.current.get('overlays').clear();
                        }
                    }
                }
                
                setIsFinished(true);
                setCurrentTask(null);
                saveSession(updatedLogs, endEventId, true);
                alert('流程已中止');
            };

            const handleComplete = async () => {
                if (!currentTask) return;
                
                // Log End Value if tag exists
                let finalValStr = '-';
                if (currentTask.tag) {
                    const data = await fetchTagValue(currentTask.tag);
                    finalValStr = data.map(d => `${d.tag}=${formatValue(d.value, currentTask.precision, currentTask.unit)}`).join(', ');
                }

                const newLog = { time: new Date().toLocaleTimeString(), source: 'User', message: `完成任務: ${currentTask.name}`, value: finalValStr, note: note || 'End Value', taskId: currentTask.id };
                const updatedLogs = [...logs, newLog];
                setLogs(updatedLogs);
                setNote('');
                
                // Clear Interval & Overlays
                if (intervalRef.current) clearInterval(intervalRef.current);
                if (viewerRef.current) viewerRef.current.get('overlays').clear();

                const element = currentTask.elementObj;
                let nextTaskId = null;
                let finished = false;

                // Check if this is a Final End Event being completed manually
                if (element.type === 'bpmn:EndEvent') {
                    let isFinal = false;
                    const docs = element.businessObject.documentation;
                    if (docs && docs.length > 0 && docs[0].text) {
                        try { isFinal = JSON.parse(docs[0].text).isFinalEnd; } catch(err) {}
                    }
                    
                    if (isFinal) {
                        finished = true;
                        alert('流程已完成！');
                        setCurrentTask(null);
                        viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                    } else {
                        alert('此分支已結束。');
                        setCurrentTask(null);
                        viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                    }
                } else if (element && element.businessObject.outgoing && element.businessObject.outgoing.length > 0) {
                    const nextFlow = element.businessObject.outgoing[0];
                    const targetNode = nextFlow.targetRef;
                    if (viewerRef.current) {
                        const targetElement = viewerRef.current.get('elementRegistry').get(targetNode.id);
                        if (targetElement) {
                            handleElementClick(targetElement);
                            nextTaskId = targetElement.id;
                        }
                    }
                } else { 
                    alert('無後續任務'); 
                    setCurrentTask(null);
                    if(viewerRef.current) viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                }
                
                saveSession(updatedLogs, nextTaskId, finished);
                if (finished) setIsFinished(true);
            };

            const handleSkip = async () => {
                if (!currentTask) return;
                
                // Log End Value (Skipped)
                let finalValStr = '-';
                if (currentTask.tag) {
                    const data = await fetchTagValue(currentTask.tag);
                    finalValStr = data.map(d => `${d.tag}=${formatValue(d.value, currentTask.precision, currentTask.unit)}`).join(', ');
                }

                const newLog = { time: new Date().toLocaleTimeString(), source: 'User', message: `跳過任務: ${currentTask.name}`, value: finalValStr, note: note || 'Skipped (End Value)' };
                const updatedLogs = [...logs, newLog];
                setLogs(updatedLogs);
                setNote('');
                
                if (intervalRef.current) clearInterval(intervalRef.current);
                if (viewerRef.current) viewerRef.current.get('overlays').clear();
                
                // Logic same as complete for moving forward
                const element = currentTask.elementObj;
                let nextTaskId = null;
                let finished = false;
                
                if (element && element.businessObject.outgoing && element.businessObject.outgoing.length > 0) {
                    const nextFlow = element.businessObject.outgoing[0];
                    const targetNode = nextFlow.targetRef;
                    if (viewerRef.current) {
                        const targetElement = viewerRef.current.get('elementRegistry').get(targetNode.id);
                        if (targetElement) {
                             if (targetElement.type === 'bpmn:EndEvent') {
                                finished = true;
                                alert('流程已完成！');
                                setCurrentTask(null);
                                viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                            } else {
                                handleElementClick(targetElement);
                                nextTaskId = targetElement.id;
                            }
                        }
                    }
                } else {
                    finished = true;
                    setCurrentTask(null);
                    if(viewerRef.current) viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                }
                setIsFinished(finished);
                saveSession(updatedLogs, nextTaskId, finished);
            };

            const exportCSV = () => {
                const headers = ['Time', 'Source', 'Message', 'Value', 'Note'];
                const csvContent = [headers.join(','), ...logs.map(l => `${l.time},${l.source},${l.message},"${l.value}","${l.note || ''}"`)].join('\\n');
                const blob = new Blob(["\\ufeff" + csvContent], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.setAttribute('download', `${processName}_log.csv`);
                document.body.appendChild(link);
                link.click();
            };

            return (
                <div className="flex h-full flex-col bg-[#121212]">
                    <div className="bg-[#1e1e1e] px-6 py-3 flex justify-between items-center border-b border-white/5">
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('dashboard')} className="text-white/60 hover:text-white transition flex items-center gap-1">
                                <span className="text-lg">←</span> 暫存並返回
                            </button>
                            <h2 className="text-xl font-medium text-white/90">{processName} <span className="text-white/40 text-sm ml-2">(執行模式)</span></h2>
                        </div>
                        <div className="flex gap-3">
                            {!isFinished && (
                                <button onClick={handleAbort} className="px-4 py-2 rounded-full font-medium transition bg-[#f28b82] text-[#002d6f] hover:bg-[#f28b82]/90">
                                    中止流程
                                </button>
                            )}
                            <button onClick={handleRestart} className="px-4 py-2 rounded-full font-medium transition bg-[#f28b82]/10 text-[#f28b82] hover:bg-[#f28b82]/20 border border-[#f28b82]/20">
                                重新開始
                            </button>
                            <button onClick={exportCSV} disabled={!isFinished} className={`px-6 py-2 rounded-full font-medium transition ${isFinished ? 'bg-[#81c995] text-[#0f5132] hover:bg-[#a8dab5]' : 'bg-[#2d2d2d] text-white/30 cursor-not-allowed'}`}>
                                {isFinished ? '匯出 CSV' : '未完成不可匯出'}
                            </button>
                        </div>
                    </div>
                    <div className="flex-1 flex overflow-hidden">
                        <div className="flex-1 bg-white relative operator-mode" ref={containerRef}></div>
                        <div className="w-96 bg-[#1e1e1e] border-l border-white/5 flex flex-col shadow-xl z-10">
                            <div className="p-4 border-b border-white/5">
                                <h3 className="font-medium text-white/90 mb-2 text-lg">當前任務</h3>
                                {currentTask ? (
                                    <div className="animate-fade-in">
                                        <div className="text-xl font-bold text-[#8ab4f8] mb-3">{currentTask.name}</div>
                                        
                                        {loadingTag ? <div className="text-white/60 animate-pulse">讀取數據中...</div> : (
                                            <div className={`grid gap-2 ${tagValues.length >= 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
                                                {tagValues.map((tv, idx) => (
                                                    <div key={idx} className="bg-[#2d2d2d] p-3 rounded-xl border border-white/5">
                                                        <div className="text-[10px] text-white/60 mb-0.5 truncate" title={tv.tag}>{tv.tag}</div>
                                                        <div className="text-lg font-mono text-[#81c995] truncate">
                                                            {formatValue(tv.value, currentTask.precision, currentTask.unit)}
                                                        </div>
                                                        <div className="text-[10px] text-white/40 mt-0.5 flex justify-between">
                                                            <span>{tv.timestamp.split('T')[1].split('.')[0]}</span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        <div className="mt-3">
                                            <label className="block text-[10px] font-medium text-[#8ab4f8] mb-1 uppercase tracking-wider">備註 (Note)</label>
                                            <textarea 
                                                value={note} 
                                                onChange={(e) => setNote(e.target.value)} 
                                                className="w-full bg-[#2d2d2d] border border-white/10 rounded-xl p-2 text-white focus:border-[#8ab4f8] outline-none h-20 text-sm resize-none"
                                                placeholder="輸入備註..."
                                            />
                                        </div>
                                        <div className="mt-6 flex gap-3">
                                            <button 
                                                onClick={handleComplete} 
                                                disabled={!checkPredecessors(currentTask.elementObj)}
                                                className={`flex-1 py-3 rounded-full font-medium transition ${checkPredecessors(currentTask.elementObj) ? 'bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f]' : 'bg-[#2d2d2d] text-white/30 cursor-not-allowed'}`}
                                            >
                                                {checkPredecessors(currentTask.elementObj) ? '完成任務' : '請先完成前置任務'}
                                            </button>
                                            <button onClick={handleSkip} className="flex-1 bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 py-3 rounded-full font-medium transition">跳過</button>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-center mt-10">
                                        {isFinished ? 
                                            <div className="text-[#81c995] font-bold text-xl flex flex-col items-center gap-2">
                                                <span className="text-4xl">🎉</span>
                                                <span>流程已完成</span>
                                            </div> : 
                                            <p className="text-white/40">點擊流程圖中的任務以開始操作</p>
                                        }
                                    </div>
                                )}
                            </div>
                            <div className="flex-1 overflow-y-auto p-6 font-mono text-sm bg-[#121212]">
                                <h4 className="text-[#8ab4f8] text-xs font-bold uppercase tracking-wider mb-4 sticky top-0 bg-[#121212] py-2">執行紀錄</h4>
                                {logs.map((l, i) => (
                                    <div key={i} className="mb-4 border-l-2 border-[#2d2d2d] pl-4 relative">
                                        <div className="absolute -left-[5px] top-1 w-2 h-2 rounded-full bg-[#2d2d2d]"></div>
                                        <div className="flex justify-between items-baseline mb-1">
                                            <span className="text-white/40 text-xs">{l.time}</span>
                                            <span className="text-[#8ab4f8] text-xs font-bold">{l.source}</span>
                                        </div>
                                        <div className="text-white/80 mb-1">{l.message}</div>
                                        {l.value !== '-' && <div className="text-[#81c995] text-xs bg-[#81c995]/10 inline-block px-2 py-0.5 rounded">Value: {l.value}</div>}
                                        {l.note && <div className="text-[#fdd663] text-xs mt-2 bg-[#fdd663]/10 p-2 rounded border border-[#fdd663]/20">Note: {l.note}</div>}
                                    </div>
                                ))}
                            </div>
                        </div>
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
            const [selectedLogIndex, setSelectedLogIndex] = useState(null);

            useEffect(() => {
                if (!processId) return;
                const viewer = new BpmnJS({ container: containerRef.current });
                viewerRef.current = viewer;
                
                const load = async () => {
                    try {
                        const res = await fetch(`${API_BASE}/processes/${processId}`);
                        const data = await res.json();
                        setProcessName(data.name);
                        await viewer.importXML(data.xml_content);
                        viewer.get('canvas').zoom('fit-viewport');
                        
                        // Lock Diagram
                        const eventBus = viewer.get('eventBus');
                        const events = [
                            'shape.move.start', 'connection.create.start', 'shape.resize.start',
                            'element.dblclick', 'contextPad.open', 'palette.create', 'autoPlace.start'
                        ];
                        events.forEach(event => eventBus.on(event, 10000, () => false));

                        // Tooltip for Hyperlinks
                        eventBus.on('element.hover', (e) => {
                            const docs = e.element.businessObject.documentation;
                            if (docs && docs.length > 0 && docs[0].text) {
                                try {
                                    const data = JSON.parse(docs[0].text);
                                    if (data.targetUrl) {
                                        viewer.get('overlays').add(e.element.id, 'url-tooltip', {
                                            position: { top: -25, left: 0 },
                                            html: `<div style="background: rgba(30,30,30,0.9); color: #8ab4f8; padding: 4px 8px; border-radius: 4px; font-size: 11px; border: 1px solid #8ab4f8; pointer-events: none; white-space: nowrap; z-index: 1000;">🔗 ${data.targetUrl}</div>`
                                        });
                                    }
                                } catch(err) {}
                            }
                        });

                        eventBus.on('element.out', (e) => {
                            viewer.get('overlays').remove({ type: 'url-tooltip' });
                        });
                        
                    } catch(err) {
                        console.error(err);
                        alert('流程載入失敗');
                    }
                };
                load();
                return () => viewer.destroy();
            }, [processId]);

            // Robust CSV Parser
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
                const reader = new FileReader();
                reader.onload = (evt) => {
                    const text = evt.target.result;
                    const lines = text.split('\\n').slice(1); // Skip header
                    const data = lines.map(line => {
                        if (!line.trim()) return null;
                        const cols = parseCSVLine(line);
                        if (cols.length < 4) return null;
                        // Format: Time, Source, Message, Value, Note
                        return { 
                            time: cols[0], 
                            source: cols[1], 
                            message: cols[2], 
                            value: cols[3], 
                            note: cols[4] || '' 
                        };
                    }).filter(x => x && x.time);
                    setCsvData(data);
                };
                reader.readAsText(file);
            };

            const handleLogClick = (row, index) => {
                setSelectedLogIndex(index);
                if (!viewerRef.current) return;

                const canvas = viewerRef.current.get('canvas');
                const elementRegistry = viewerRef.current.get('elementRegistry');
                const overlays = viewerRef.current.get('overlays');

                // Clear previous
                overlays.clear();
                elementRegistry.forEach(e => canvas.removeMarker(e.id, 'highlight'));

                // Extract Task Name from Message
                // Patterns: "開始任務: Name", "完成任務: Name", "跳過任務: Name"
                let taskName = row.message;
                if (taskName.includes(': ')) {
                    taskName = taskName.split(': ')[1].trim();
                }

                // Find Element by Name
                const element = elementRegistry.filter(e => e.businessObject.name === taskName)[0];
                
                if (element) {
                    // Highlight
                    canvas.addMarker(element.id, 'highlight');
                    
                    // Show Overlay if Value exists and is not '-'
                    if (row.value && row.value !== '-' && row.value !== '"-"') {
                        // Value format: "Tag1=10.00 Unit, Tag2=20.00 Unit"
                        // Split by comma but respect if there are other commas (though formatValue doesn't produce commas inside value usually)
                        // The formatValue output is: `${d.tag}=${val}` joined by ', '
                        // We can split by ', ' safely enough for now
                        const parts = row.value.split(', ');
                        const htmlContent = parts.map(p => `<div>${p}</div>`).join('');
                        
                        overlays.add(element.id, {
                            position: { bottom: 10, right: 10 },
                            html: `<div style="background: #81c995; color: #0f5132; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2); text-align: right; line-height: 1.2;">${htmlContent}</div>`
                        });
                        
                        // Center view
                        // canvas.scrollToElement(element); // Optional: might be too jumpy
                    }
                }
            };

            // Keyboard Navigation
            useEffect(() => {
                const handleKeyDown = (e) => {
                    if (csvData.length === 0) return;
                    
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        setSelectedLogIndex(prev => {
                            const next = prev === null ? 0 : Math.min(prev + 1, csvData.length - 1);
                            handleLogClick(csvData[next], next);
                            return next;
                        });
                    } else if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        setSelectedLogIndex(prev => {
                            const next = prev === null ? 0 : Math.max(prev - 1, 0);
                            handleLogClick(csvData[next], next);
                            return next;
                        });
                    }
                };
                
                window.addEventListener('keydown', handleKeyDown);
                return () => window.removeEventListener('keydown', handleKeyDown);
            }, [csvData]); // Re-bind when data changes

            return (
                <div className="flex h-full flex-col bg-[#121212]">
                    <div className="bg-[#1e1e1e] px-6 py-3 flex justify-between items-center border-b border-white/5">
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('dashboard')} className="text-white/60 hover:text-white transition flex items-center gap-1">
                                <span className="text-lg">←</span> 返回
                            </button>
                            <h2 className="text-xl font-medium text-white/90">{processName} <span className="text-white/40 text-sm ml-2">(歷史回顧)</span></h2>
                        </div>
                        <div className="flex gap-4">
                            <label className="cursor-pointer bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-4 py-2 rounded-full font-medium transition shadow-sm">
                                匯入 Log (CSV)
                                <input type="file" accept=".csv" className="hidden" onChange={handleFileUpload} />
                            </label>
                        </div>
                    </div>
                    <div className="flex-1 flex overflow-hidden">
                        <div className="flex-1 bg-white relative review-mode" ref={containerRef}>
                            {!processId && <div className="absolute inset-0 flex items-center justify-center text-slate-400">錯誤：未指定流程 ID</div>}
                        </div>
                        <div className="w-96 bg-[#1e1e1e] border-l border-white/5 overflow-y-auto p-6">
                            <h3 className="font-medium text-white/90 mb-4 text-lg">操作紀錄</h3>
                            {csvData.length === 0 ? <p className="text-white/40 text-center py-10">請上傳 CSV 檔案以檢視紀錄</p> : (
                                <div className="space-y-3">
                                    {csvData.map((row, i) => (
                                        <div 
                                            key={i} 
                                            onClick={() => handleLogClick(row, i)}
                                            className={`text-sm p-3 rounded-xl border transition cursor-pointer group ${selectedLogIndex === i ? 'bg-[#2d2d2d] border-[#8ab4f8] ring-1 ring-[#8ab4f8]' : 'bg-[#2d2d2d] border-white/5 hover:border-white/20'}`}
                                        >
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="text-white/40 text-xs">{row.time}</span>
                                                <span className="text-[#8ab4f8] text-xs font-bold">{row.source}</span>
                                            </div>
                                            <div className="text-white/80 group-hover:text-white">{row.message}</div>
                                            
                                            {/* Value Display: Hide if '-' */}
                                            {row.value && row.value !== '-' && row.value !== '"-"' && (
                                                <div className="mt-2 text-[#81c995] text-xs bg-[#81c995]/10 inline-block px-2 py-1 rounded w-full">
                                                    {row.value.split(', ').map((v, idx) => (
                                                        <div key={idx}>{v}</div>
                                                    ))}
                                                </div>
                                            )}
                                            
                                            {row.note && row.note !== '""' && !(row.note === 'End Value' && (row.value === '-' || row.value === '"-"')) && (
                                                <div className="text-[#fdd663] text-xs mt-2 bg-[#fdd663]/10 p-2 rounded border border-[#fdd663]/20">Note: {row.note}</div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
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

if __name__ == '__main__':
    # Initialize Database
    init_db()
    
    # Ensure static folder exists
    if not os.path.exists('static'):
        print("WARNING: 'static' folder not found. Please run download_assets.ps1 first.")
    app.run(debug=True, port=5000, host='0.0.0.0')
