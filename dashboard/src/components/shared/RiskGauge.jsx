function riskLevel(score) {
  if (score < 30) return 'low';
  if (score <= 70) return 'medium';
  return 'high';
}

function riskColor(score) {
  if (score < 30) return 'var(--color-success)';
  if (score <= 70) return 'var(--color-warning)';
  return 'var(--color-danger)';
}

function RiskGauge({ score }) {
  const level = riskLevel(score);
  return (
    <div className="risk-gauge">
      <span className="risk-gauge__score" style={{ color: riskColor(score) }}>
        {score}
      </span>
      <div className="risk-gauge__bar">
        <div
          className={`risk-gauge__fill risk-gauge__fill--${level}`}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
    </div>
  );
}

export default RiskGauge;
