function RedFlagsList({ flags }) {
  if (!flags || flags.length === 0) {
    return <p>No red flags identified.</p>;
  }

  return (
    <ul className="red-flags-list">
      {flags.map((flag, i) => {
        const severity = (flag.severity || 'medium').toLowerCase();
        return (
          <li key={i} className="red-flag-item">
            <span className={`red-flag-severity red-flag-severity--${severity}`} />
            <span className="red-flag-text">
              {flag.description || flag.text || flag}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default RedFlagsList;
