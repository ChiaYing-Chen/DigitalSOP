import os
import sqlite3
import json
import random
import datetime
from flask import Flask, render_template_string, request, jsonify, send_from_directory
from flask_cors import CORS

# --- Configuration ---
app = Flask(__name__, static_folder='static')
CORS(app)
DB_FILE = 'sops.db'

# --- PIconnect Integration (Mock Fallback) ---
try:
    import PIconnect as PI
    PI_AVAILABLE = True
    # PI.PIConfig.DEFAULT_SERVER_NAME = "MyPIServer" # Uncomment and set if needed
except ImportError:
    PI_AVAILABLE = False
    print("PIconnect not found. Using Mock mode.")
except Exception as e:
    PI_AVAILABLE = False
    print(f"PIconnect initialization failed: {e}. Using Mock mode.")

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  xml_content TEXT NOT NULL,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (process_id INTEGER PRIMARY KEY,
                  current_task_id TEXT,
                  logs TEXT,
                  is_finished BOOLEAN,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(process_id) REFERENCES processes(id) ON DELETE CASCADE)''')
    conn.commit()
    conn.close()

init_db()

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
    
    if not name or not xml_content:
        return jsonify({'error': 'Missing name or xml_content'}), 400
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    process_id = data.get('id')
    if process_id:
        c.execute("UPDATE processes SET name=?, xml_content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, xml_content, process_id))
    else:
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
                results.append({'tag': tag_name, 'value': round(random.uniform(20.0, 100.0), 2), 'timestamp': datetime.datetime.now().isoformat(), 'source': 'Mock (Error)'})
        else:
            results.append({'tag': tag_name, 'value': round(random.uniform(20.0, 100.0), 2), 'timestamp': datetime.datetime.now().isoformat(), 'source': 'Mock'})
            
    return jsonify(results)

# --- Embedded Frontend ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>本地工業 SOP 系統</title>
    
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
            
            useEffect(() => {
                fetch(`${API_BASE}/processes`)
                    .then(res => res.json())
                    .then(data => setProcesses(data));
                
                fetch(`${API_BASE}/pi_status`)
                    .then(res => res.json())
                    .then(data => setPiStatus(data.status));
            }, []);

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
                            <h1 className="text-2xl font-medium tracking-wide text-white/90">工業 SOP 指引系統</h1>
                        </div>
                        <div className="flex items-center gap-6">
                            <div className="flex items-center gap-2 bg-[#1e1e1e] px-4 py-2 rounded-full border border-white/5">
                                <div className={`w-2 h-2 rounded-full ${piStatus === 'Connected' ? 'bg-[#81c995] animate-pulse' : 'bg-[#f28b82]'}`}></div>
                                <span className="text-sm text-white/70">{piStatus === 'Connected' ? 'PI Server 連線正常' : 'Mock Mode'}</span>
                            </div>
                            <label className="cursor-pointer bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 px-5 py-2 rounded-full text-sm transition flex items-center gap-2">
                                <span>匯入 SOP</span>
                                <input type="file" accept=".bpmn,.xml" className="hidden" onChange={handleImport} />
                            </label>
                            <button onClick={() => onNavigate('editor')} className="bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-6 py-2 rounded-full font-medium shadow-sm transition flex items-center gap-2">
                                <span className="text-xl leading-none">+</span>
                                <span>新增 SOP</span>
                            </button>
                        </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {processes.map(p => {
                            const isRunning = p.session_status === 0;
                            return (
                                <div key={p.id} className={`bg-[#1e1e1e] p-6 rounded-2xl border transition-all duration-200 flex flex-col group ${isRunning ? 'border-[#81c995]/50 shadow-[0_4px_20px_rgba(129,201,149,0.1)]' : 'border-white/5 hover:border-white/20 hover:shadow-lg'}`}>
                                    <div className="flex-1 mb-6">
                                        <div className="flex justify-between items-start mb-3">
                                            <h3 className="text-lg font-medium text-white/90 group-hover:text-[#8ab4f8] transition-colors">{p.name}</h3>
                                            {isRunning && <span className="bg-[#81c995]/20 text-[#81c995] text-xs px-3 py-1 rounded-full font-medium">執行中</span>}
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
            const [elementName, setElementName] = useState('');

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
                    try { await modeler.importXML(xml); modeler.get('canvas').zoom('fit-viewport'); } catch (err) { console.error(err); }
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
                            try { setPiTag(JSON.parse(docs[0].text).piTag || ''); } catch(e) { setPiTag(''); }
                        } else { setPiTag(''); }
                    } else { setSelectedElement(null); setElementName(''); setPiTag(''); }
                });
                
                modeler.on('element.changed', (e) => {
                    if (selectedElement && e.element.id === selectedElement.id) { setElementName(e.element.businessObject.name || ''); }
                });
                return () => modeler.destroy();
            }, [processId]);

            const handleSave = async () => {
                const { xml } = await modelerRef.current.saveXML({ format: true });
                await fetch(`${API_BASE}/processes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: processId, name, xml_content: xml }) });
                alert('儲存成功！');
                onNavigate('dashboard');
            };

            const updateElementName = (val) => {
                setElementName(val);
                if (selectedElement && modelerRef.current) { modelerRef.current.get('modeling').updateLabel(selectedElement, val); }
            };

            const updatePiTag = (val) => {
                setPiTag(val);
                if (selectedElement && modelerRef.current) {
                    const modeling = modelerRef.current.get('modeling');
                    const bpmnFactory = modelerRef.current.get('bpmnFactory');
                    const newDoc = bpmnFactory.create('bpmn:Documentation', { text: JSON.stringify({ piTag: val }) });
                    modeling.updateProperties(selectedElement, { documentation: [newDoc] });
                }
            };

            return (
                <div className="flex h-full flex-col bg-[#121212]">
                    <div className="bg-[#1e1e1e] px-6 py-3 flex justify-between items-center border-b border-white/5">
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('dashboard')} className="text-white/60 hover:text-white transition flex items-center gap-1">
                                <span className="text-lg">←</span> 返回
                            </button>
                            <input value={name} onChange={(e) => setName(e.target.value)} className="bg-[#2d2d2d] text-white px-4 py-1.5 rounded-full border-none outline-none focus:ring-2 focus:ring-[#8ab4f8]" placeholder="流程名稱" />
                        </div>
                        <button onClick={handleSave} className="bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] px-6 py-2 rounded-full font-medium shadow-sm transition">儲存流程</button>
                    </div>
                    <div className="flex-1 flex overflow-hidden">
                        <div className="flex-1 relative bg-white" ref={containerRef}></div>
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
                                    <div className="mb-5">
                                        <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">PI Tag 設定</label>
                                        <input 
                                            value={piTag} 
                                            onChange={(e) => updatePiTag(e.target.value)} 
                                            className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-3 py-2 text-white outline-none transition" 
                                            placeholder="例如: SINUSOID; CDT158" 
                                        />
                                        <p className="text-white/40 text-xs mt-2">支援多個 Tag，請用分號 (;) 分隔</p>
                                    </div>
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
                    } catch (err) { console.error(err); }
                };
                load();
                return () => viewer.destroy();
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

            const addLog = (source, message, value = '-', note = '') => {
                const newLog = { time: new Date().toLocaleTimeString(), source, message, value, note };
                setLogs(prev => {
                    const updatedLogs = [...prev, newLog];
                    return updatedLogs;
                });
            };

            const handleElementClick = async (element) => {
                const docs = element.businessObject.documentation;
                let tag = null;
                if (docs && docs.length > 0 && docs[0].text) {
                    try { tag = JSON.parse(docs[0].text).piTag; } catch(e) {}
                }
                setCurrentTask({ id: element.id, name: element.businessObject.name || element.id, tag, elementObj: element });
                
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
                        const res = await fetch(`${API_BASE}/get_tag_value?tag=${encodeURIComponent(tag)}`);
                        const data = await res.json();
                        setTagValues(data);
                        const valStr = data.map(d => `${d.tag}=${d.value}`).join(', ');
                        addLog('PI Server', `讀取 Tag: ${tag}`, valStr);
                    } catch (e) { addLog('Error', '讀取失敗'); setTagValues([]); } finally { setLoadingTag(false); }
                } else { setTagValues([]); }
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
                return () => {
                    eventBus.off('element.click', listener);
                    events.forEach(event => eventBus.off(event, preventDefault));
                };
            }, [viewerRef.current]);

            const handleRestart = async () => {
                if(!confirm('確定要重新開始流程嗎？所有紀錄將被清除。')) return;
                
                setLogs([]);
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
                        }
                    }
                }
                
                setIsFinished(true);
                setCurrentTask(null);
                saveSession(updatedLogs, endEventId, true);
                alert('流程已中止');
            };

            const handleComplete = () => {
                if (!currentTask) return;
                const newLog = { time: new Date().toLocaleTimeString(), source: 'User', message: `完成任務: ${currentTask.name}`, value: '-', note };
                const updatedLogs = [...logs, newLog];
                setLogs(updatedLogs);
                setNote('');
                
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
                                // Remove highlight on finish
                                viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                            } else {
                                handleElementClick(targetElement);
                                nextTaskId = targetElement.id;
                            }
                        }
                    }
                } else { 
                    alert('流程結束或無後續任務'); 
                    finished = true;
                    setCurrentTask(null);
                    if(viewerRef.current) viewerRef.current.get('canvas').removeMarker(element.id, 'highlight');
                }
                setIsFinished(finished);
                saveSession(updatedLogs, nextTaskId, finished);
            };

            const handleSkip = () => {
                if (!currentTask) return;
                const newLog = { time: new Date().toLocaleTimeString(), source: 'User', message: `跳過任務: ${currentTask.name}`, value: '-', note };
                const updatedLogs = [...logs, newLog];
                setLogs(updatedLogs);
                setNote('');
                
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
                            <div className="p-6 border-b border-white/5">
                                <h3 className="font-medium text-white/90 mb-4 text-lg">當前任務</h3>
                                {currentTask ? (
                                    <div className="animate-fade-in">
                                        <div className="text-2xl font-bold text-[#8ab4f8] mb-4">{currentTask.name}</div>
                                        
                                        {loadingTag ? <div className="text-white/60 animate-pulse">讀取數據中...</div> : (
                                            <div className="space-y-3">
                                                {tagValues.map((tv, idx) => (
                                                    <div key={idx} className="bg-[#2d2d2d] p-4 rounded-xl border border-white/5">
                                                        <div className="text-xs text-white/60 mb-1">{tv.tag}</div>
                                                        <div className="text-2xl font-mono text-[#81c995]">{tv.value}</div>
                                                        <div className="text-xs text-white/40 mt-1 flex justify-between">
                                                            <span>{tv.timestamp.split('T')[1].split('.')[0]}</span>
                                                            <span>{tv.source}</span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        <div className="mt-6">
                                            <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">備註 (Note)</label>
                                            <textarea 
                                                value={note} 
                                                onChange={(e) => setNote(e.target.value)} 
                                                className="w-full bg-[#2d2d2d] border border-white/10 rounded-xl p-3 text-white focus:border-[#8ab4f8] outline-none h-24 text-sm resize-none"
                                                placeholder="輸入備註..."
                                            />
                                        </div>
                                        <div className="mt-6 flex gap-3">
                                            <button onClick={handleComplete} className="flex-1 bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#002d6f] py-3 rounded-full font-medium transition">完成任務</button>
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
                        
                    } catch(err) {
                        console.error(err);
                        alert('流程載入失敗');
                    }
                };
                load();
                return () => viewer.destroy();
            }, [processId]);

            const handleFileUpload = (e) => {
                const file = e.target.files[0];
                const reader = new FileReader();
                reader.onload = (evt) => {
                    const text = evt.target.result;
                    const lines = text.split('\\n').slice(1);
                    const data = lines.map(line => {
                        const [time, source, message, value] = line.split(',');
                        return { time, source, message, value };
                    }).filter(x => x.time);
                    setCsvData(data);
                };
                reader.readAsText(file);
            };

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
                                        <div key={i} className="text-sm bg-[#2d2d2d] p-3 rounded-xl border border-white/5 hover:border-[#8ab4f8] transition cursor-pointer group">
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="text-white/40 text-xs">{row.time}</span>
                                                <span className="text-[#8ab4f8] text-xs font-bold">{row.source}</span>
                                            </div>
                                            <div className="text-white/80 group-hover:text-white">{row.message}</div>
                                            {row.value && row.value !== '-' && <div className="mt-2 text-[#81c995] text-xs bg-[#81c995]/10 inline-block px-2 py-0.5 rounded">Value: {row.value}</div>}
                                        </div>
                                    ))}
                                </div>
                            )}
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
    # Ensure static folder exists
    if not os.path.exists('static'):
        print("WARNING: 'static' folder not found. Please run download_assets.ps1 first.")
    app.run(debug=True, port=5000, host='0.0.0.0')
