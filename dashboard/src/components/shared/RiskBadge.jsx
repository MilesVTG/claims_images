function riskLevel(score) {
  if (score < 30) return 'low';
  if (score <= 70) return 'medium';
  return 'high';
}

function RiskBadge({ score }) {
  const level = riskLevel(score);
  return (
    <span className={`risk-badge risk-badge--${level}`}>
      {score}
    </span>
  );
}

export default RiskBadge;
