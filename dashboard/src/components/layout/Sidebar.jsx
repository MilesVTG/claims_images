import { NavLink } from 'react-router-dom';

function Sidebar() {
  return (
    <nav className="app-sidebar">
      <ul>
        <li>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
        </li>
        <li>
          <NavLink to="/claims">Claims</NavLink>
        </li>
      </ul>
    </nav>
  );
}

export default Sidebar;
