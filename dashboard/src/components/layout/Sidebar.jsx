import { NavLink } from 'react-router-dom';

function Sidebar({ open, onToggle }) {
  return (
    <nav className={`app-sidebar ${open ? '' : 'app-sidebar--collapsed'}`}>
      <button className="sidebar-toggle" onClick={onToggle} title={open ? 'Collapse sidebar' : 'Expand sidebar'}>
        {open ? '[<<]' : '[>>]'}
      </button>
      {open && (
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
      )}
    </nav>
  );
}

export default Sidebar;
