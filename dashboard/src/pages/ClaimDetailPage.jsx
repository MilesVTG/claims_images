import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../api/client';
import RiskGauge from '../components/shared/RiskGauge';
import RiskBadge from '../components/shared/RiskBadge';
import StatusBadge from '../components/shared/StatusBadge';
import RedFlagsList from '../components/shared/RedFlagsList';
import PhotoGallery from '../components/shared/PhotoGallery';

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

function TerminalSpinner() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 120);
    return () => clearInterval(id);
  }, []);
  return <span className="terminal-spinner">{SPINNER_FRAMES[frame]}</span>;
}

function ClaimDetailPage() {
  const { contractId, claimId } = useParams();
  const [claim, setClaim] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchClaim();
  }, [contractId, claimId]);

  async function fetchClaim() {
    setLoading(true);
    setError('');
    try {
      const data = await api.get(`/claims/${contractId}/${claimId}`);
      setClaim(data);
    } catch (err) {
      setError(err.message || 'Failed to load claim');
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="page"><p className="loading-state"><TerminalSpinner /> Loading claim details...</p></div>;
  if (error) return <div className="page"><p className="error-state">{error}</p></div>;
  if (!claim) return <div className="page"><p className="empty-state">Claim not found.</p></div>;

  const photos = claim.photos || [];
  const redFlags = claim.red_flags || [];
  const analysis = claim.gemini_analysis || claim.analysis || {};
  const narrative = analysis.narrative || analysis.summary || analysis.text || '';
  const contractHistory = claim.contract_history || [];

  return (
    <div className="page claim-detail-page">
      <div className="claim-detail-header">
        <Link to="/claims" className="back-link">{'<-'} Back to Claims</Link>
        <h1>Claim {claimId}</h1>
        <StatusBadge status={claim.status} />
      </div>

      {/* Top row: overview + risk gauge */}
      <div className="detail-grid">
        <div className="detail-card">
          <h2>Overview</h2>
          <dl className="meta-pairs">
            <dt>Contract ID</dt>
            <dd>{contractId}</dd>
            <dt>Claim ID</dt>
            <dd>{claimId}</dd>
            <dt>Status</dt>
            <dd><StatusBadge status={claim.status} /></dd>
            <dt>Submitted</dt>
            <dd>{formatDate(claim.submission_date)}</dd>
            <dt>Photos</dt>
            <dd>{photos.length}</dd>
          </dl>
        </div>

        <div className="detail-card">
          <h2>Risk Score</h2>
          <RiskGauge score={claim.risk_score ?? 0} />
        </div>

        {/* Red Flags */}
        <div className="detail-card">
          <h2>Red Flags ({redFlags.length})</h2>
          <RedFlagsList flags={redFlags} />
        </div>

        {/* Gemini Analysis */}
        <div className="detail-card">
          <h2>AI Analysis</h2>
          {narrative ? (
            <div className="analysis-narrative">{narrative}</div>
          ) : (
            <p className="empty-state">No analysis narrative available.</p>
          )}
        </div>
      </div>

      {/* Photo Gallery — full width */}
      <div className="detail-card detail-card--full" style={{ marginBottom: '1.5rem' }}>
        <h2>Photos</h2>
        <PhotoGallery photos={photos} />
      </div>

      {/* Contract History */}
      {contractHistory.length > 0 && (
        <div className="detail-card detail-card--full">
          <h2>Contract History</h2>
          <table className="history-table">
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Date</th>
                <th>Risk</th>
                <th>Status</th>
                <th>Photos</th>
              </tr>
            </thead>
            <tbody>
              {contractHistory.map((h, i) => (
                <tr key={h.claim_id || i}>
                  <td>{h.claim_id || h.id}</td>
                  <td>{formatDate(h.submission_date || h.date)}</td>
                  <td><RiskBadge score={h.risk_score ?? 0} /></td>
                  <td><StatusBadge status={h.status} /></td>
                  <td>{h.photo_count ?? '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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

export default ClaimDetailPage;
