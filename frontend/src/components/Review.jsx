import React, { useState, useEffect, useRef, useCallback } from 'react';
import BpmnJS from 'bpmn-js/dist/bpmn-viewer.production.min.js';
import TimelineViewer from './TimelineViewer';
import { API_BASE } from '../utilities';

const Review = ({ processId, onNavigate }) => {
    const containerRef = useRef(null);
    const [csvData, setCsvData] = useState([]);
    const viewerRef = useRef(null);
    const [processName, setProcessName] = useState('');
    const [isLoaded, setIsLoaded] = useState(false);
    const [currentProcess, setCurrentProcess] = useState(null);

    // Helper to apply styles (Sticky Notes) - Reused from Operator logic
    const applyStyles = useCallback(() => {
        if (!viewerRef.current) return;
        const viewer = viewerRef.current;
        const canvas = viewer.get('canvas');
        const elementRegistry = viewer.get('elementRegistry');

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
                } catch (e) { }
            }
        });
    }, []);

    useEffect(() => {
        if (!processId) return;
        if (viewerRef.current) viewerRef.current.destroy();

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

            } catch (e) { console.error(e); }
        };
        load();

        return () => { if (viewerRef.current) viewerRef.current.destroy(); };
    }, [processId, applyStyles]);

    // Sync Visuals with Logs
    useEffect(() => {
        if (!viewerRef.current || csvData.length === 0) return;
        const viewer = viewerRef.current;
        const canvas = viewer.get('canvas');
        const elementRegistry = viewer.get('elementRegistry');

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
                    canvas.addMarker(element.id, 'completed-task'); // CSS class override

                    // Direct SVG override for fill
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
            const lines = text.split('\n');

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

export default Review;
