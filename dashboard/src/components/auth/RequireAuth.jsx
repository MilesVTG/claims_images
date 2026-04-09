import { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import api from '../../api/client';

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

function TerminalSpinner() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 120);
    return () => clearInterval(id);
  }, []);
  return <span className="terminal-spinner">{SPINNER_FRAMES[frame]}</span>;
}

function RequireAuth({ children }) {
  const [status, setStatus] = useState('checking'); // checking | ok | denied

  useEffect(() => {
    verify();

    function handlePageShow(event) {
      if (event.persisted) verify();
    }
    window.addEventListener('pageshow', handlePageShow);
    return () => window.removeEventListener('pageshow', handlePageShow);
  }, []);

  async function verify() {
    const token = sessionStorage.getItem('token');
    if (!token) {
      setStatus('denied');
      return;
    }
    try {
      await api.get('/auth/me');
      setStatus('ok');
    } catch {
      sessionStorage.removeItem('token');
      setStatus('denied');
    }
  }

  if (status === 'checking') {
    return (
      <div className="auth-checking">
        <TerminalSpinner /> Verifying session...
      </div>
    );
  }
  if (status === 'denied') return <Navigate to="/login" replace />;
  return children;
}

export default RequireAuth;
