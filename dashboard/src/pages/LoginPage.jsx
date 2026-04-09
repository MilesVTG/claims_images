import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import MatrixText from '../components/effects/MatrixText';

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

function TerminalSpinner() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 120);
    return () => clearInterval(id);
  }, []);
  return <span className="terminal-spinner">{SPINNER_FRAMES[frame]}</span>;
}

function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  // Redirect already-authenticated users away from login
  const existingToken = sessionStorage.getItem('token');
  if (existingToken) {
    navigate('/', { replace: true });
    return null;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSuccess(false);
    setLoading(true);
    try {
      const res = await api.post('/auth/login', { username, password });
      sessionStorage.setItem('token', res.token);
      setSuccess(true);
      setTimeout(() => navigate('/'), 800);
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1 className="fraudi-title">
          <MatrixText text="FRAUDI" className="fraudi-title__text" delay={200} />
        </h1>
        <p className="login-subtitle">Fraud Review &amp; Analysis<br />of Uploaded Damage Images</p>
        {error && <p className="error">{error}</p>}
        {success && <p className="login-success">Authenticated</p>}
        <label>
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
            placeholder="enter username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            placeholder="enter password"
          />
        </label>
        <button type="submit" disabled={loading || success}>
          {loading ? (
            <><TerminalSpinner /> Authenticating...</>
          ) : success ? (
            '[OK] Redirecting...'
          ) : (
            'Sign In'
          )}
        </button>
      </form>
    </div>
  );
}

export default LoginPage;
