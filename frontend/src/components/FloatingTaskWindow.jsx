import React from 'react';

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

export default FloatingTaskWindow;
