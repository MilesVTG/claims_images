import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';

const MOBILE_BREAKPOINT = 768;

function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= MOBILE_BREAKPOINT);

  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    function handleChange(e) {
      if (e.matches) setSidebarOpen(false);
    }
    mql.addEventListener('change', handleChange);
    return () => mql.removeEventListener('change', handleChange);
  }, []);

  return (
    <div className="app-shell">
      <Header />
      <div className="app-body">
        <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen((v) => !v)} />
        <main className={`app-content ${sidebarOpen ? '' : 'app-content--expanded'}`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppShell;
