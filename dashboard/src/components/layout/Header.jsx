import { useNavigate } from 'react-router-dom';
import MatrixText from '../effects/MatrixText';

function Header() {
  const navigate = useNavigate();

  function handleLogout() {
    sessionStorage.removeItem('token');
    navigate('/login');
  }

  return (
    <header className="app-header">
      <div className="header-brand">
        <MatrixText text="FRAUDI" className="header-brand__text" delay={100} />
      </div>
      <button className="header-logout" onClick={handleLogout}>
        [sign out]
      </button>
    </header>
  );
}

export default Header;
