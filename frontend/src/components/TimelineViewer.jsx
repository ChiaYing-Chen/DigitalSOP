import React, { useEffect, useRef } from 'react';
import { formatTimelineTime } from '../utilities';

const TimelineViewer = ({ logs, headerActions, onUpdateLog, piStatusNode }) => {
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
                    {piStatusNode}
                    <span className="text-xs text-white/30">{logs.length} 筆紀錄</span>
                    {headerActions}
                </div>
            </div>
            <div ref={scrollRef} className="flex-1 overflow-x-auto overflow-y-hidden flex items-start px-6 gap-8 scrollbar-thin py-3" onWheel={(e) => {
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
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold z-10 mb-1 shadow-lg transition-transform group-hover:scale-110 ${log.message.includes('任務完成') ? 'bg-[#81c995] text-[#0f5132]' : 'bg-[#8ab4f8] text-[#002d6f]'
                            }`}>
                            {idx + 1}
                        </div>

                        <div className="text-xs text-white/50 mt-0.5">{formatTimelineTime(log.time)}</div>
                        <div className="text-sm font-medium text-white/90 mt-0.5 text-center px-2">{log.message.split(': ')[1] || log.message}</div>

                        {/* Indicators Container */}
                        <div className="flex gap-2 mt-1.5">
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

export default TimelineViewer;
