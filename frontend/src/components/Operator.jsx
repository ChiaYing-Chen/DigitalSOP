import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import BpmnJS from 'bpmn-js/dist/bpmn-viewer.production.min.js';
import TimelineViewer from './TimelineViewer';
import FloatingTaskWindow from './FloatingTaskWindow';
import { API_BASE, getCurrentTime } from '../utilities';

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
    const [piConnecting, setPiConnecting] = useState(false);
    const [piStatus, setPiStatus] = useState('Checking...');
    const [onlineCount, setOnlineCount] = useState(1);
    const [isTimelineCollapsed, setIsTimelineCollapsed] = useState(false);
    const userId = useMemo(() => 'user_' + Math.random().toString(36).substr(2, 9), []);

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

    // Check PI Status on Mount
    useEffect(() => {
        fetch(`${API_BASE}/pi_status`)
            .then(res => res.json())
            .then(data => setPiStatus(data.status));
    }, []);

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
                        } catch (e) { }
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

            // 5. Custom Wheel Interaction (Zoom/Pan)
            const container = containerRef.current;
            const handleWheel = (event) => {
                if (event.ctrlKey) {
                    // Zoom
                    event.preventDefault();
                    event.stopPropagation();
                    const zoom = canvas.zoom();
                    const newZoom = zoom - (event.deltaY * 0.001);
                    canvas.zoom(newZoom, {
                        x: event.clientX - container.getBoundingClientRect().left,
                        y: event.clientY - container.getBoundingClientRect().top
                    });
                } else {
                    // Horizontal Scroll
                    event.preventDefault();
                    event.stopPropagation();
                    canvas.scroll({ dx: -event.deltaY, dy: 0 });
                }
            };
            if (container) {
                container.addEventListener('wheel', handleWheel, { passive: false });

                // 6. Custom Mouse Drag (Pan)
                let isDragging = false;
                let lastX, lastY;

                const handleMouseDown = (event) => {
                    // Left click (0), no checks on target to allow "drag anywhere" style, 
                    // providing it doesn't conflict with interactive elements logic too much.
                    // Ideally, we should check if we clicked on an empty space, but users want to drag "the view".
                    if (event.button === 0) {
                        isDragging = true;
                        lastX = event.clientX;
                        lastY = event.clientY;
                        container.style.cursor = 'grabbing';
                    }
                };

                const handleMouseMove = (event) => {
                    if (isDragging) {
                        const dx = event.clientX - lastX;
                        const dy = event.clientY - lastY;
                        canvas.scroll({ dx: dx, dy: dy });
                        lastX = event.clientX;
                        lastY = event.clientY;
                    }
                };

                const handleMouseUp = () => {
                    isDragging = false;
                    container.style.cursor = 'default';
                };

                container.addEventListener('mousedown', handleMouseDown);
                window.addEventListener('mousemove', handleMouseMove);
                window.addEventListener('mouseup', handleMouseUp);

                viewer.on('destroy', () => {
                    container.removeEventListener('wheel', handleWheel);
                    container.removeEventListener('mousedown', handleMouseDown);
                    window.removeEventListener('mousemove', handleMouseMove);
                    window.removeEventListener('mouseup', handleMouseUp);
                });
            }

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
                'connection.layout.start'
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
                // Block interaction if process is finished
                if (viewer._customState && viewer._customState.isFinished) return;

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
                        } catch (e) { }
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
                } catch (e) { console.error('Error highlighting task:', e); }
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
                    } catch (e) { }
                }
            });

            const overlays = viewer.get('overlays');

            if (alwaysOnElements.length > 0) {
                // 3. Update Function
                const updateOverlays = async () => {
                    for (const el of alwaysOnElements) {
                        // Fix: Find overlay by checking if it contains our specific content ID
                        // Check if overlays service exists and get
                        if (!overlays) return;

                        let overlay = overlays.get({ element: el.id }).find(o => o.html && o.html.querySelector(`#content-${el.id}`));

                        // Fetch Data
                        let data = [];
                        try {
                            if (!viewer._hasConnectedPI) setPiConnecting(true); // Start loading
                            const res = await fetch(`${API_BASE}/get_tag_value?tag=${encodeURIComponent(el.tag)}`);
                            data = await res.json();
                            viewer._hasConnectedPI = true; // Mark as connected
                        } catch (e) { console.error(e); }
                        finally { setPiConnecting(false); } // Stop loading

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
                            overlays.add(el.id, {
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
                                // Use WebKitCSSMatrix for parsing transform for simplicity
                                let m41 = 0, m42 = 0;
                                if (window.WebKitCSSMatrix) {
                                    const matrix = new WebKitCSSMatrix(style.transform);
                                    m41 = matrix.m41;
                                    m42 = matrix.m42;
                                }
                                initialLeft = m41;
                                initialTop = m42;

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

                // Expose interval clearer
                const interval = setInterval(updateOverlays, 5000);
                viewer._customInterval = interval;
                updateOverlays();
            }

        };

        load();

        return () => {
            if (viewerRef.current) {
                if (viewerRef.current._customInterval) clearInterval(viewerRef.current._customInterval);
                viewerRef.current.destroy();
            }
        };
    }, [processId]);

    // Always On PI Display Manager - Cleanup overlaps with above load, but kept separate in original for clarity.
    // Merged into Load above for cleaner React lifecycle handling.

    // Reactive Visual Sync (BPMN Markers & State)
    useEffect(() => {
        if (!viewerRef.current) return;

        // Update State for Listeners (Avoid Stale Closures)
        viewerRef.current._customState = {
            runningTaskId: currentRunningTaskId,
            logs: logs,
            isFinished: isFinished
        };

        const canvas = viewerRef.current.get('canvas');
        const elementRegistry = viewerRef.current.get('elementRegistry');

        // Clear all markers
        elementRegistry.forEach(el => {
            canvas.removeMarker(el.id, 'highlight');
            canvas.removeMarker(el.id, 'completed-task');
        });

        // Calculate status from logs
        const taskStatusByName = {};
        const taskStatusByID = {};

        logs.forEach(log => {
            let status = null;
            let name = null;

            if (log.message.startsWith('任務開始:')) {
                status = 'running';
                name = log.message.substring(5).trim(); // Remove '任務開始:'
            } else if (log.message.startsWith('任務完成:')) {
                status = 'completed';
                name = log.message.substring(5).trim(); // Remove '任務完成:'
            }

            if (status) {
                if (log.taskId) {
                    taskStatusByID[log.taskId] = status;
                }
                if (name) {
                    taskStatusByName[name] = status;
                }
            }
        });

        // Apply markers
        elementRegistry.forEach(el => {
            const id = el.id;
            const name = el.businessObject.name;

            let status = null;

            // Priority 1: Match by ID (New robust method)
            if (taskStatusByID[id]) {
                status = taskStatusByID[id];
            }
            // Priority 2: Match by Name (Fallback for old logs)
            else if (name && taskStatusByName[name]) {
                status = taskStatusByName[name];
            }

            if (status) {
                if (status === 'completed') {
                    canvas.addMarker(id, 'completed-task');
                } else if (status === 'running') {
                    canvas.addMarker(id, 'highlight');
                }
            }
        });
    }, [logs, isFinished, currentRunningTaskId]);

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
                        }

                        // Sync Finished State
                        if (data.is_finished !== isFinished) {
                            setIsFinished(data.is_finished);
                        }

                        // Sync Current Running Task
                        if (data.current_task_id !== currentRunningTaskId) {
                            setCurrentRunningTaskId(data.current_task_id);
                        }
                    }
                }
            } catch (e) {
                console.error("Sync error:", e);
            }
        };

        const interval = setInterval(syncSession, 3000); // Poll every 3 seconds
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
            } catch (e) { }
        }

        // Check status
        let status = 'idle';
        const taskName = businessObj.name || '未命名任務';
        const startMsg = `任務開始: ${taskName}`;
        const endMsg = `任務完成: ${taskName}`;

        if (element.type === 'bpmn:StartEvent') {
            // Start Event is complete if it has a start log
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
            csvString += `# Metadata: id=${process.id}, version=${process.updated_at}\n`;
        }
        csvString += "Time,Source,Message,Value,Note\n";

        logsToExport.forEach(log => {
            const row = [
                log.time,
                log.source,
                log.message,
                `"${log.value}"`, // Quote value to handle commas
                `"${log.note}"`
            ].join(",");
            csvString += row + "\n";
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
            } catch (e) { console.error(e); }
        }

        // Special handling for Start Event: Atomic Start (No Complete Log)
        if (windowTask.type === 'bpmn:StartEvent') {
            const newLogStart = {
                time: getCurrentTime(),
                source: 'User',
                message: `任務開始: ${windowTask.name}`,
                value: startValStr,
                note: note
            };

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
            return;
        }

        const newLog = {
            time: getCurrentTime(),
            source: 'User',
            message: `任務開始: ${windowTask.name}`,
            value: startValStr,
            note: note,
            taskId: windowTask.id // Track Task ID for robust matching
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
            time: getCurrentTime(),
            source: 'User',
            message: `任務完成: ${windowTask.name}`,
            value: valStr,
            note: note,
            taskId: windowTask.id // Track Task ID for robust matching
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
            time: getCurrentTime(),
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
        <div className="flex items-center gap-2">
            <button onClick={() => handleExportCSV(logs)} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 p-2 rounded-full transition" title="匯出 CSV">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
            </button>
            {!isFinished && (
                <button onClick={handleFinishProcess} className="bg-[#f28b82] hover:bg-[#f6aea9] text-[#601410] px-4 py-1.5 rounded-full text-xs font-bold transition">
                    結束
                </button>
            )}
            <button onClick={() => onNavigate('dashboard')} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 p-2 rounded-full transition" title="返回首頁">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
                </svg>
            </button>
            <button
                onClick={() => setIsTimelineCollapsed(!isTimelineCollapsed)}
                className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 p-2 rounded-full transition ml-2"
                title={isTimelineCollapsed ? "展開時間軸" : "收合時間軸"}
            >
                {isTimelineCollapsed ? (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                    </svg>
                ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
                    </svg>
                )}
            </button>
        </div>
    );

    return (
        <div className="flex flex-col h-full bg-[#1e1e1e]">
            {/* 1. Timeline (Collapsible) */}
            <div className={`${isTimelineCollapsed ? 'h-[54px] min-h-[54px]' : 'h-1/5 min-h-[220px]'} border-b border-white/10 relative z-10 shrink-0 transition-all duration-300 ease-in-out overflow-hidden`}>
                <TimelineViewer
                    logs={logs}
                    headerActions={headerActions}
                    piStatusNode={(
                        <div onClick={() => onNavigate('settings')} className="flex items-center gap-2 bg-[#1e1e1e] px-3 py-1.5 rounded-full border border-white/5 cursor-pointer hover:bg-white/5 transition mr-4">
                            <div className={`w-2 h-2 rounded-full ${piStatus === 'Connected' ? 'bg-[#81c995] animate-pulse' : piStatus === 'Not Configured' ? 'bg-gray-400' : 'bg-[#f28b82]'}`}></div>
                            <span className="text-xs text-white/70 whitespace-nowrap">
                                {piStatus === 'Connected' ? 'PI 連線正常' :
                                    piStatus === 'Not Configured' ? 'PI 未設定' : 'PI 離線'}
                            </span>
                        </div>
                    )}
                    onUpdateLog={handleUpdateLog}
                />
            </div>

            {/* 2. BPMN Viewer (Flex Grow) */}
            <div className="flex-1 relative bg-white border-t-4 border-[#1e1e1e] min-h-0">
                <div ref={containerRef} className="w-full h-full operator-mode"></div>



                {/* Import Overlay */}
                {!process && (
                    <div className="absolute inset-0 bg-black/80 z-50 flex flex-col items-center justify-center">
                        <div className="text-white/40">Loading...</div>
                    </div>
                )}

                {/* Zoom Controls */}
                <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
                    <button onClick={() => handleZoom(0.2)} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] font-bold text-xl">+</button>
                    <button onClick={() => handleZoom(-0.2)} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] font-bold text-xl">-</button>
                    <button onClick={() => { if (viewerRef.current) viewerRef.current.get('canvas').zoom('fit-viewport'); }} className="w-10 h-10 bg-[#1e1e1e] text-white rounded-full shadow-lg hover:bg-[#333] text-xs">Fit</button>
                </div>

                {/* Task Window */}
                {showWindow && windowTask && (
                    <FloatingTaskWindow
                        task={windowTask}
                        onClose={() => setShowWindow(false)}
                        onStart={handleStartTask}
                        onEnd={handleCompleteTask}
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

export default Operator;
