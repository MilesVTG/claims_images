import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import RiskBadge from '../components/shared/RiskBadge';
import StatusBadge from '../components/shared/StatusBadge';

function ClaimsListPage() {
  const navigate = useNavigate();
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [riskMin, setRiskMin] = useState('');
  const [riskMax, setRiskMax] = useState('');

  // Sort
  const [sortKey, setSortKey] = useState('submission_date');
  const [sortDir, setSortDir] = useState('desc');

  useEffect(() => {
    fetchClaims();
  }, []);

  async function fetchClaims() {
    setLoading(true);
    setError('');
    try {
      const data = await api.get('/claims');
      setClaims(Array.isArray(data) ? data : data.items || data.claims || []);
    } catch (err) {
      setError(err.message || 'Failed to load claims');
    } finally {
      setLoading(false);
    }
  }

  // Filter + sort
  const filtered = useMemo(() => {
    let result = [...claims];

    if (statusFilter) {
      result = result.filter(
        (c) => (c.status || '').toLowerCase() === statusFilter.toLowerCase()
      );
    }

    const minVal = riskMin !== '' ? Number(riskMin) : null;
    const maxVal = riskMax !== '' ? Number(riskMax) : null;
    if (minVal !== null) {
      result = result.filter((c) => (c.risk_score ?? 0) >= minVal);
    }
    if (maxVal !== null) {
      result = result.filter((c) => (c.risk_score ?? 0) <= maxVal);
    }

    result.sort((a, b) => {
      let aVal = a[sortKey];
      let bVal = b[sortKey];

      if (aVal == null) aVal = '';
      if (bVal == null) bVal = '';

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
      }

      const cmp = String(aVal).localeCompare(String(bVal));
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [claims, statusFilter, riskMin, riskMax, sortKey, sortDir]);

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  function sortIndicator(key) {
    if (sortKey !== key) return <span className="sort-indicator">--</span>;
    return (
      <span className="sort-indicator sort-indicator--active">
        {sortDir === 'asc' ? ' ↑' : ' ↓'}
      </span>
    );
  }

  // Gather unique statuses for filter dropdown
  const statuses = useMemo(() => {
    const set = new Set(claims.map((c) => c.status).filter(Boolean));
    return Array.from(set).sort();
  }, [claims]);

  function handleRowClick(claim) {
    const contractId = claim.contract_id || claim.contractId;
    const claimId = claim.claim_id || claim.claimId || claim.id;
    navigate(`/claims/${contractId}/${claimId}`);
  }

  const columns = [
    { key: 'claim_id', label: 'Claim ID' },
    { key: 'contract_id', label: 'Contract' },
    { key: 'risk_score', label: 'Risk Score' },
    { key: 'status', label: 'Status' },
    { key: 'submission_date', label: 'Submitted' },
    { key: 'photo_count', label: 'Photos' },
  ];

  return (
    <div className="page claims-list-page">
      <h1>Claims</h1>

      <div className="filter-bar">
        <label>
          Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Risk Min
          <input
            type="number"
            min="0"
            max="100"
            value={riskMin}
            onChange={(e) => setRiskMin(e.target.value)}
            placeholder="0"
            style={{ width: '70px' }}
          />
        </label>
        <label>
          Risk Max
          <input
            type="number"
            min="0"
            max="100"
            value={riskMax}
            onChange={(e) => setRiskMax(e.target.value)}
            placeholder="100"
            style={{ width: '70px' }}
          />
        </label>
      </div>

      {loading && <p className="loading-state">Loading claims...</p>}
      {error && <p className="error-state">{error}</p>}

      {!loading && !error && filtered.length === 0 && (
        <p className="empty-state">No claims match the current filters.</p>
      )}

      {!loading && !error && filtered.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} onClick={() => handleSort(col.key)}>
                  {col.label}
                  {sortIndicator(col.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((claim, i) => (
              <tr key={claim.claim_id || claim.id || i} onClick={() => handleRowClick(claim)}>
                <td>{claim.claim_id || claim.id}</td>
                <td>{claim.contract_id}</td>
                <td>
                  <RiskBadge score={claim.risk_score ?? 0} />
                </td>
                <td>
                  <StatusBadge status={claim.status} />
                </td>
                <td>{formatDate(claim.submission_date)}</td>
                <td>{claim.photo_count ?? '--'}</td>
              </tr>
            ))}
          </tbody>
        </table>
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

export default ClaimsListPage;
