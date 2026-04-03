function StatusBadge({ status }) {
  const key = (status || 'pending').toLowerCase().replace(/\s+/g, '-');
  return (
    <span className={`status-badge status-badge--${key}`}>
      {status}
    </span>
  );
}

export default StatusBadge;
