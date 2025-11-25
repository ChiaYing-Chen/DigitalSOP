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
        body { font-family: 'Inter', sans-serif; }
        .bpmn-container { 
            height: 100%; 
            width: 100%; 
            background: white; 
            color: #1e293b; /* Force dark text inside the white canvas */
        }
        .bjs-powered-by { display: none; }
        
        /* Custom Scrollbar for Dark Mode */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #1e293b; }
        ::-webkit-scrollbar-thumb { background: #475569; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #64748b; }

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
    </style>
</head>
<body class="bg-slate-900 text-slate-100 h-screen overflow-hidden">
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
            const [piStatus, setPiStatus] = useState('CHECKING');
            const fileInputRef = useRef(null);
            
            useEffect(() => {
                loadProcesses();
                fetch(`${API_BASE}/pi_status`)
                    .then(res => res.json())
                    .then(data => setPiStatus(data.status))
                    .catch(() => setPiStatus('ERROR'));
            }, []);

            const loadProcesses = () => {
                fetch(`${API_BASE}/processes`).then(res => res.json()).then(data => setProcesses(data));
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
                URL.revokeObjectURL(url);
            };

            const handleImport = (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = async (evt) => {
                    const xml = evt.target.result;
                    const name = file.name.replace('.bpmn', '').replace('.xml', '');
                    await fetch(`${API_BASE}/processes`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, xml_content: xml })
                    });
                    alert('匯入成功！');
                    loadProcesses();
                };
                reader.readAsText(file);
                e.target.value = ''; // Reset input
            };

            return (
                <div className="p-8 max-w-6xl mx-auto">
                    <div className="flex justify-between items-center mb-8">
                        <div className="flex items-center gap-4">
                            <h1 className="text-3xl font-bold text-blue-400">工業 SOP 指引系統</h1>
                            <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold border ${piStatus === 'CONNECTED' ? 'bg-green-900/30 border-green-500 text-green-400' : 'bg-red-900/30 border-red-500 text-red-400'}`}>
                                <div className={`w-2 h-2 rounded-full ${piStatus === 'CONNECTED' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
                                {piStatus === 'CONNECTED' ? 'PI Server 連線正常' : 'PI Server 離線 (Mock)'}
                            </div>
                        </div>
                        <div className="flex gap-4">
                            <input type="file" ref={fileInputRef} onChange={handleImport} accept=".bpmn,.xml" className="hidden" />
                            <button onClick={() => fileInputRef.current.click()} className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded shadow flex items-center gap-2">
                                <span>匯入 SOP</span>
                            </button>
                            <button onClick={() => onNavigate('editor')} className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded shadow flex items-center gap-2">
                                <span>+ 新增 SOP</span>
                            </button>
                        </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {processes.map(p => {
                            const isRunning = p.session_status === 0;
                            return (
                                <div key={p.id} className={`bg-slate-800 p-6 rounded-lg border transition shadow-lg flex flex-col ${isRunning ? 'border-green-500/50 shadow-green-900/20' : 'border-slate-700 hover:border-blue-500'}`}>
                                    <div className="flex-1">
                                        <div className="flex justify-between items-start">
                                            <h3 className="text-xl font-semibold mb-2">{p.name}</h3>
                                            {isRunning && <span className="bg-green-900 text-green-300 text-xs px-2 py-1 rounded-full animate-pulse">執行中</span>}
                                        </div>
                                        <p className="text-slate-400 text-sm mb-4">最後編輯: {p.updated_at}</p>
                                    </div>
                                    <div className="flex gap-2 flex-wrap mt-4">
                                        <button onClick={() => onNavigate('editor', p.id)} className="bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded text-sm flex-1">編輯</button>
                                        <button onClick={() => onNavigate('operator', p.id)} className={`px-3 py-1 rounded text-sm flex-1 text-white ${isRunning ? 'bg-green-600 hover:bg-green-500' : 'bg-green-700 hover:bg-green-600'}`}>
                                            {isRunning ? '繼續執行' : '執行'}
                                        </button>
                                        <button onClick={() => onNavigate('review', p.id)} className="bg-purple-700 hover:bg-purple-600 px-3 py-1 rounded text-sm flex-1">回顧</button>
                                    </div>
                                    <div className="flex gap-2 mt-2">
                                        <button onClick={() => handleExport(p)} className="bg-blue-900/50 hover:bg-blue-800 px-3 py-1 rounded text-sm text-blue-200 flex-1 border border-blue-800">匯出</button>
                                        <button onClick={() => handleDelete(p.id)} className="bg-red-900/50 hover:bg-red-900 px-3 py-1 rounded text-sm text-red-200 flex-1 border border-red-900">刪除</button>
                                    </div>
                                </div>
                            );
                        })}
                        {processes.length === 0 && <div className="col-span-full text-center py-12 text-slate-500">尚無 SOP 流程，請點擊右上角新增或匯入。</div>}
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
                <div className="flex h-full flex-col">
                    <div className="bg-slate-800 p-4 flex justify-between items-center border-b border-slate-700">
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('dashboard')} className="text-slate-400 hover:text-white">← 返回</button>
                            <input value={name} onChange={(e) => setName(e.target.value)} className="bg-slate-700 text-white px-3 py-1 rounded border border-slate-600" placeholder="流程名稱" />
                        </div>
                        <button onClick={handleSave} className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded shadow">儲存流程</button>
                    </div>
                    <div className="flex-1 flex overflow-hidden">
                        <div className="flex-1 relative bg-white" ref={containerRef}></div>
                        <div className="w-80 bg-slate-800 border-l border-slate-700 p-4 overflow-y-auto">
                            <h3 className="font-bold mb-4 text-lg border-b border-slate-700 pb-2">屬性面板</h3>
                            {selectedElement ? (
                                <div>
                                    <div className="mb-4"><label className="block text-sm text-slate-400 mb-1">ID</label><input disabled value={selectedElement.id} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-500" /></div>
                                    <div className="mb-4"><label className="block text-sm text-slate-400 mb-1">類型</label><input disabled value={selectedElement.type} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-500" /></div>
                                    <div className="mb-4"><label className="block text-sm text-slate-400 mb-1">名稱 (Name)</label><input value={elementName} onChange={(e) => updateElementName(e.target.value)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-white focus:border-blue-500 outline-none" placeholder="輸入名稱..." /></div>
                                    <div className="mb-4 p-3 bg-slate-700/50 rounded border border-blue-500/30">
                                        <label className="block text-sm text-blue-300 mb-1 font-bold">PI Tag 設定</label>
                                        <input value={piTag} onChange={(e) => updatePiTag(e.target.value)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 focus:border-blue-500 outline-none" placeholder="例如: TAG1;TAG2" />
                                        <p className="text-xs text-slate-400 mt-1">輸入 PI Server 上的 Tag 名稱，多個 Tag 請用分號 (;) 區隔</p>
                                    </div>
                                </div>
                            ) : <p className="text-slate-500 text-center mt-10">請選擇一個元素以編輯屬性</p>}
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
                    // Save session asynchronously (using current state for task ID might be stale, so we rely on handleComplete to save state properly)
                    // But for simple logs, we just save logs.
                    // Actually, let's only save in handleComplete/Skip to ensure consistency, 
                    // or save here but we need currentTask.id. 
                    // To simplify, we will save in handleComplete/Skip.
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
                if (viewerRef.current) {
                    const canvas = viewerRef.current.get('canvas');
                    // canvas.addMarker(element.id, 'highlight'); // Optional
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
                const listener = (e) => {
                    handleElementClick(e.element);
                    viewerRef.current.get('canvas').addMarker(e.element.id, 'highlight');
                };
                eventBus.on('element.click', listener);
                return () => eventBus.off('element.click', listener);
            }, [viewerRef.current]);

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
                            } else {
                                handleElementClick(targetElement);
                                viewerRef.current.get('canvas').addMarker(targetElement.id, 'highlight');
                                nextTaskId = targetElement.id;
                            }
                        }
                    }
                } else { 
                    alert('流程結束或無後續任務'); 
                    finished = true;
                    setCurrentTask(null);
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
                            } else {
                                handleElementClick(targetElement);
                                viewerRef.current.get('canvas').addMarker(targetElement.id, 'highlight');
                                nextTaskId = targetElement.id;
                            }
                        }
                    }
                } else {
                    finished = true;
                    setCurrentTask(null);
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
                <div className="flex h-full flex-col">
                    <div className="bg-slate-800 p-4 flex justify-between items-center border-b border-slate-700">
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('dashboard')} className="text-slate-400 hover:text-white">← 暫存並返回</button>
                            <h2 className="text-xl font-bold">{processName} (執行模式)</h2>
                        </div>
                        <button onClick={exportCSV} disabled={!isFinished} className={`px-4 py-2 rounded text-white ${isFinished ? 'bg-green-600 hover:bg-green-500' : 'bg-slate-600 cursor-not-allowed'}`}>
                            {isFinished ? '匯出 CSV' : '未完成不可匯出'}
                        </button>
                    </div>
                    <div className="flex-1 flex overflow-hidden">
                        <div className="flex-1 bg-white relative operator-mode" ref={containerRef}></div>
                        <div className="w-96 bg-slate-800 border-l border-slate-700 flex flex-col">
                            <div className="p-4 border-b border-slate-700 bg-slate-900">
                                <h3 className="font-bold text-lg mb-2 text-blue-400">當前任務</h3>
                                {currentTask ? (
                                    <div>
                                        <p className="text-xl font-semibold mb-2">{currentTask.name}</p>
                                        <p className="text-sm text-slate-400">ID: {currentTask.id}</p>
                                        {currentTask.tag && (
                                            <div className="mt-4 bg-slate-800 p-3 rounded border border-blue-500/50">
                                                <p className="text-xs text-blue-300 mb-2">PI Tag 數據 ({currentTask.tag})</p>
                                                {loadingTag ? <p className="animate-pulse">讀取中...</p> : (
                                                    <div className="space-y-2">
                                                        {tagValues.map((tv, idx) => (
                                                            <div key={idx} className="flex justify-between items-center border-b border-slate-700 pb-1 last:border-0">
                                                                <span className="text-sm text-slate-400">{tv.tag}</span>
                                                                <div className="text-right">
                                                                    <span className="block text-xl font-mono font-bold text-green-400">{tv.value}</span>
                                                                    <span className="text-[10px] text-slate-500">{tv.source}</span>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                        <div className="mt-4">
                                            <label className="block text-sm text-slate-400 mb-1">備註 (Note)</label>
                                            <textarea 
                                                value={note} 
                                                onChange={(e) => setNote(e.target.value)} 
                                                className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white focus:border-blue-500 outline-none h-20 text-sm"
                                                placeholder="輸入備註..."
                                            />
                                        </div>
                                        <div className="mt-4 flex gap-2">
                                            <button onClick={handleComplete} className="flex-1 bg-blue-600 hover:bg-blue-500 py-2 rounded text-white">完成任務 (下一步)</button>
                                            <button onClick={handleSkip} className="flex-1 bg-slate-600 hover:bg-slate-500 py-2 rounded text-white">跳過</button>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-center mt-10">
                                        {isFinished ? <p className="text-green-400 font-bold text-xl">流程已完成</p> : <p className="text-slate-500">點擊流程圖中的任務以開始操作</p>}
                                    </div>
                                )}
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 font-mono text-sm">
                                <h4 className="text-slate-400 mb-2 sticky top-0 bg-slate-800">執行紀錄</h4>
                                {logs.map((l, i) => (
                                    <div key={i} className="mb-2 border-b border-slate-700/50 pb-1">
                                        <div className="flex justify-between">
                                            <span className="text-slate-500">[{l.time}]</span>
                                            <span className="text-blue-300">{l.source}</span>
                                        </div>
                                        <div className="mt-1">{l.message}</div>
                                        {l.value !== '-' && <div className="text-green-400 text-xs mt-1">Value: {l.value}</div>}
                                        {l.note && <div className="text-yellow-200/70 text-xs mt-1 bg-yellow-900/20 p-1 rounded">Note: {l.note}</div>}
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
                <div className="flex h-full flex-col">
                    <div className="bg-slate-800 p-4 flex justify-between items-center border-b border-slate-700">
                        <div className="flex items-center gap-4">
                            <button onClick={() => onNavigate('dashboard')} className="text-slate-400 hover:text-white">← 返回</button>
                            <h2 className="text-xl font-bold">{processName} (歷史回顧)</h2>
                        </div>
                        <div className="flex gap-4">
                            <label className="cursor-pointer bg-blue-700 hover:bg-blue-600 px-3 py-1 rounded text-sm">
                                匯入 Log (CSV)
                                <input type="file" accept=".csv" className="hidden" onChange={handleFileUpload} />
                            </label>
                        </div>
                    </div>
                    <div className="flex-1 flex overflow-hidden">
                        <div className="flex-1 bg-white relative review-mode" ref={containerRef}>
                            {!processId && <div className="absolute inset-0 flex items-center justify-center text-slate-400">錯誤：未指定流程 ID</div>}
                        </div>
                        <div className="w-80 bg-slate-800 border-l border-slate-700 overflow-y-auto p-4">
                            <h3 className="font-bold mb-4">操作紀錄</h3>
                            {csvData.length === 0 ? <p className="text-slate-500">請上傳 CSV 檔案</p> : (
                                <div className="space-y-2">
                                    {csvData.map((row, i) => (
                                        <div key={i} className="text-sm border-l-2 border-slate-600 pl-2 hover:bg-slate-700 p-1 rounded cursor-pointer">
                                            <div className="text-slate-400 text-xs">{row.time}</div>
                                            <div>{row.message}</div>
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
