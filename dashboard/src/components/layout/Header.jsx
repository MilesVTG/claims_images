import { useNavigate } from 'react-router-dom';

function Header() {
  const navigate = useNavigate();

  function handleLogout() {
    sessionStorage.removeItem('token');
    navigate('/login');
  }

  return (
    <header className="app-header">
      <div className="header-brand">Claims Dashboard</div>
      <button className="header-logout" onClick={handleLogout}>
        Sign Out
      </button>
    </header>
  );
}

export default Header;
