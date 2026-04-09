import { NavLink } from 'react-router-dom';

function Sidebar() {
  return (
    <nav className="app-sidebar">
      <ul>
        <li>
          <NavLink to="/" end>
            dashboard
          </NavLink>
        </li>
        <li>
          <NavLink to="/claims">claims</NavLink>
        </li>
        <li>
          <NavLink to="/prompts">prompts</NavLink>
        </li>
      </ul>
    </nav>
  );
}

export default Sidebar;
