import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import RiskBadge from '../components/shared/RiskBadge';
import StatusBadge from '../components/shared/StatusBadge';

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

function TerminalSpinner() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 120);
    return () => clearInterval(id);
  }, []);
  return <span className="terminal-spinner">{SPINNER_FRAMES[frame]}</span>;
}

function DashboardPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSummary();
  }, []);

  async function fetchSummary() {
    setLoading(true);
    setError('');
    try {
      const data = await api.get('/dashboard/summary');
      setSummary(data);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard summary');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="page dashboard-page">
        <h1>Dashboard</h1>
        <p className="loading-state"><TerminalSpinner /> Fetching dashboard data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page dashboard-page">
        <h1>Dashboard</h1>
        <p className="error-state">{error}</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="page dashboard-page">
        <h1>Dashboard</h1>
        <p className="empty-state">No summary data available.</p>
      </div>
    );
  }

  const totalClaims = summary.total_claims ?? 0;
  const highRiskCount = summary.high_risk_count ?? 0;
  const processing = summary.processing_count ?? summary.processing ?? 0;
  const completed = summary.completed_count ?? summary.completed ?? 0;
  const flagged = summary.flagged_count ?? summary.flagged ?? 0;
  const pending = summary.pending_count ?? summary.pending ?? 0;
  const recentFlagged = summary.recent_flagged ?? summary.recent_flagged_claims ?? [];

  return (
    <div className="page dashboard-page">
      <h1>Dashboard</h1>

      {/* KPI Cards */}
      <div className="dashboard-cards">
        <div className="kpi-card">
          <span className="kpi-value">{totalClaims}</span>
          <span className="kpi-label">Total Claims</span>
        </div>
        <div className="kpi-card kpi-card--danger">
          <span className="kpi-value">{highRiskCount}</span>
          <span className="kpi-label">High Risk</span>
        </div>
        <div className="kpi-card kpi-card--warning">
          <span className="kpi-value">{flagged}</span>
          <span className="kpi-label">Flagged</span>
        </div>
        <div className="kpi-card kpi-card--info">
          <span className="kpi-value">{processing}</span>
          <span className="kpi-label">Processing</span>
        </div>
        <div className="kpi-card kpi-card--success">
          <span className="kpi-value">{completed}</span>
          <span className="kpi-label">Completed</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-value">{pending}</span>
          <span className="kpi-label">Pending</span>
        </div>
      </div>

      {/* Recent Flagged Claims */}
      <div className="detail-card detail-card--full" style={{ marginTop: '1.5rem' }}>
        <h2>Recent Flagged Claims</h2>
        {recentFlagged.length === 0 ? (
          <p className="empty-state">No flagged claims.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Contract</th>
                <th>Risk Score</th>
                <th>Status</th>
                <th>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {recentFlagged.map((claim, i) => {
                const contractId = claim.contract_id || claim.contractId;
                const claimId = claim.claim_id || claim.claimId || claim.id;
                return (
                  <tr
                    key={claimId || i}
                    onClick={() => navigate(`/claims/${contractId}/${claimId}`)}
                  >
                    <td>{claimId}</td>
                    <td>{contractId}</td>
                    <td><RiskBadge score={claim.risk_score ?? 0} /></td>
                    <td><StatusBadge status={claim.status} /></td>
                    <td>{formatDate(claim.submission_date)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '--';
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export default DashboardPage;
