import React, { useState, useEffect } from 'react';
import { API_BASE } from '../utilities';

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

export default Settings;
