import React, { useState, useEffect } from 'react';
import { API_BASE } from '../utilities';

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
        if (confirm('確定要刪除嗎？')) {
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
                                                onKeyDown={e => { if (e.key === 'Enter') saveName(p.id); else if (e.key === 'Escape') setEditingId(null); }}
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

export default Dashboard;
