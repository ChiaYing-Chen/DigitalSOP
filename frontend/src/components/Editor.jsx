import React, { useState, useEffect, useRef } from 'react';
import BpmnModeler from 'bpmn-js/lib/Modeler';
import 'bpmn-js/dist/assets/diagram-js.css';
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn.css';
import { API_BASE, makePaletteDraggable, getLightHex } from '../utilities';

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

    // Resize State
    const [elementWidth, setElementWidth] = useState('');
    const [elementHeight, setElementHeight] = useState('');

    const GOOGLE_COLORS = [
        '#EA4335', '#E91E63', '#9C27B0', '#673AB7', '#3F51B5', '#4285F4', '#03A9F4',
        '#00BCD4', '#009688', '#34A853', '#8BC34A', '#CDDC39', '#FBBC05', '#FF9800'
    ];

    useEffect(() => {
        const modeler = new BpmnModeler({
            container: containerRef.current,
            keyboard: { bindTo: document }
        });
        modelerRef.current = modeler;
        makePaletteDraggable(containerRef.current);

        // Force Enable Resizing via Runtime Interception
        try {
            const eventBus = modeler.get('eventBus');
            console.log("EventBus retrieved, registering resize interceptor...");

            // Priority 9999 to override everything
            eventBus.on('rule.call', 9999, function (e) {
                if (e.rule === 'elements.resize' || e.rule === 'shape.resize') {
                    // console.log("Resize rule intercepted for:", e.context); // Uncomment for verbose debug
                    return true; // Force allow
                }
            });
            console.log("Resize interceptor registered.");
        } catch (e) {
            console.error("Failed to register resize interceptor:", e);
        }

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
                    if (!containerRef.current) return;
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
                setElementWidth(element.width);
                setElementHeight(element.height);
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
                    } catch (e) {
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

            // Check if containerRef is still valid
            if (containerRef.current) {
                const rect = containerRef.current.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                canvas.zoom(currentZoom * factor, { x, y });
            }
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

    const applyResize = () => {
        if (selectedElement && modelerRef.current) {
            const modeling = modelerRef.current.get('modeling');
            modeling.resizeShape(selectedElement, {
                x: selectedElement.x,
                y: selectedElement.y,
                width: Number(elementWidth),
                height: Number(elementHeight)
            });
        }
    };

    // Helper to update name
    const updateElementName = (newName) => {
        setElementName(newName);
        if (selectedElement && modelerRef.current) {
            const modeling = modelerRef.current.get('modeling');
            modeling.updateLabel(selectedElement, newName);
            // Trigger auto resize logic if needed (simplified)
        }
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

                        } catch (err) { }
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

    const updateElementColor = (color) => {
        if (selectedElement && modelerRef.current) {
            const modeling = modelerRef.current.get('modeling');
            modeling.setColor(selectedElement, {
                stroke: color,
                fill: getLightHex(color, 0.2) // 20% strength (very light)
            });
        }
    };

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
                    } catch (e) { }
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
                    <button onClick={() => window.open('AboutBPMN.md', '_blank')} className="bg-[#2d2d2d] hover:bg-[#3c3c3c] text-white/80 w-8 h-8 rounded-full font-bold transition flex items-center justify-center text-sm" title="BPMN 說明">?</button>
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

                            {/* Size Control for Tasks */}
                            {(selectedElement.type.includes('Task') || selectedElement.type === 'bpmn:Participant') && (
                                <div className="mb-5 border-t border-white/10 pt-4">
                                    <label className="block text-xs font-medium text-[#8ab4f8] mb-2 uppercase tracking-wider">尺寸 (Size)</label>
                                    <div className="flex gap-2">
                                        <div className="flex-1">
                                            <span className="text-white/60 text-xs block mb-1">寬度 (Width)</span>
                                            <input
                                                type="number"
                                                value={elementWidth}
                                                onChange={(e) => setElementWidth(e.target.value)}
                                                onBlur={applyResize}
                                                onKeyDown={(e) => e.key === 'Enter' && applyResize()}
                                                className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-2 py-1 text-white outline-none text-sm"
                                            />
                                        </div>
                                        <div className="flex-1">
                                            <span className="text-white/60 text-xs block mb-1">高度 (Height)</span>
                                            <input
                                                type="number"
                                                value={elementHeight}
                                                onChange={(e) => setElementHeight(e.target.value)}
                                                onBlur={applyResize}
                                                onKeyDown={(e) => e.key === 'Enter' && applyResize()}
                                                className="w-full bg-[#2d2d2d] border border-white/10 focus:border-[#8ab4f8] rounded-lg px-2 py-1 text-white outline-none text-sm"
                                            />
                                        </div>
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
                                                    style={{ backgroundColor: c }}
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
                                                    style={{ backgroundColor: c }}
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
                                                            style={{ backgroundColor: c }}
                                                        />
                                                    ))}
                                                </div>
                                            </div>

                                            {/* WYSIWYG Editor */}
                                            <div
                                                id="sticky-wysiwyg"
                                                contentEditable
                                                className="w-full bg-white text-black text-sm outline-none min-h-[100px] p-2 rounded-t mb-1 overflow-auto"
                                                style={{ whiteSpace: 'pre-wrap' }}
                                                dangerouslySetInnerHTML={{ __html: htmlContent }}
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
                                                style={{ backgroundColor: color }}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* PI Tag Config */}
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
                    ) : (
                        <p className="text-white/40 text-sm">請選擇流程圖中的元件以編輯屬性</p>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Editor;
