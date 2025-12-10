import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import Editor from './components/Editor';
import Operator from './components/Operator';
import Review from './components/Review';
import Settings from './components/Settings';

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

export default App;
