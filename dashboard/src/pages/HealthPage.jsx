import { useState, useEffect } from 'react';
import api from '../api/client';

const TABS = [
  { id: 'unit', label: 'UNIT' },
  { id: 'integration', label: 'INTEGRATION' },
  { id: 'psychometrics', label: 'PSYCHOMETRICS' },
];

const PSYCHOMETRICS_SECTIONS = [
  { id: 'golden-dataset', label: 'golden dataset regression' },
  { id: 'concept-drift', label: 'concept drift detection' },
  { id: 'data-drift', label: 'data drift monitoring' },
];

// Display order for unit test categories
const CATEGORY_ORDER = [
  'worker_services',
  'api_config',
  'api_claims',
  'api_dashboard',
  'api_auth',
  'api_prompts',
  'api_health',
  'golden_regression',
  'pipeline_e2e',
];

function formatCategory(cat) {
  return cat.replace(/_/g, ' ');
}

function TestRow({ label, status = 'pending', passed = 0, failed = 0, total = 0 }) {
  let statusText;
  let statusClass;

  if (status === 'pass') {
    statusText = `[ ${passed}/${total} pass ]`;
    statusClass = 'health-status--pass';
  } else if (status === 'fail') {
    statusText = `[ ${passed}/${total} pass  ${failed} fail ]`;
    statusClass = 'health-status--fail';
  } else {
    statusText = '[ -- pending ]';
    statusClass = 'health-status--pending';
  }

  return (
    <div className="health-row">
      <span className="health-row__label">&gt; {label}</span>
      <span className="health-row__dots" />
      <span className={`health-row__status ${statusClass}`}>{statusText}</span>
    </div>
  );
}

function formatTimestamp(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }) + ' ' + d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function UnitTab({ latestRun, resultsByCategory }) {
  if (!latestRun) {
    return (
      <div className="health-tab-content">
        <div className="health-section">
          <div className="health-section__header">// unit test suites</div>
          <div className="health-section__placeholder">[ -- no runs ]</div>
        </div>
      </div>
    );
  }

  // Build category summary rows
  const categoryRows = CATEGORY_ORDER
    .filter((cat) => resultsByCategory[cat])
    .map((cat) => {
      const tests = resultsByCategory[cat];
      const total = tests.length;
      const passed = tests.filter((t) => t.status === 'passed').length;
      const failed = tests.filter((t) => t.status === 'failed' || t.status === 'error').length;
      const rowStatus = failed > 0 ? 'fail' : 'pass';
      return { cat, total, passed, failed, rowStatus };
    });

  // Include any categories not in the predefined order
  const knownCats = new Set(CATEGORY_ORDER);
  Object.keys(resultsByCategory)
    .filter((cat) => !knownCats.has(cat))
    .forEach((cat) => {
      const tests = resultsByCategory[cat];
      const total = tests.length;
      const passed = tests.filter((t) => t.status === 'passed').length;
      const failed = tests.filter((t) => t.status === 'failed' || t.status === 'error').length;
      const rowStatus = failed > 0 ? 'fail' : 'pass';
      categoryRows.push({ cat, total, passed, failed, rowStatus });
    });

  return (
    <div className="health-tab-content">
      <div className="health-section">
        <div className="health-section__header">// unit test suites</div>
        {categoryRows.map((row) => (
          <TestRow
            key={row.cat}
            label={formatCategory(row.cat)}
            status={row.rowStatus}
            passed={row.passed}
            failed={row.failed}
            total={row.total}
          />
        ))}
      </div>
    </div>
  );
}

function IntegrationTab() {
  return (
    <div className="health-tab-content">
      <div className="health-section">
        <div className="health-section__placeholder">
          // integration tests not yet configured
        </div>
      </div>
    </div>
  );
}

function PsychometricsTab() {
  return (
    <div className="health-tab-content">
      <div className="health-section">
        <div className="health-section__header">// model quality checks</div>
        {PSYCHOMETRICS_SECTIONS.map((sec) => (
          <TestRow key={sec.id} label={sec.label} />
        ))}
      </div>
    </div>
  );
}

function HealthPage() {
  const [activeTab, setActiveTab] = useState('unit');
  const [latestRun, setLatestRun] = useState(null);
  const [resultsByCategory, setResultsByCategory] = useState({});
  const [running, setRunning] = useState(false);
  const [loadingLatest, setLoadingLatest] = useState(true);

  const fetchLatest = async () => {
    try {
      const data = await api.get('/health/tests/latest');
      setLatestRun(data.run);
      setResultsByCategory(data.results_by_category || {});
    } catch {
      // silently ignore — no runs yet
    } finally {
      setLoadingLatest(false);
    }
  };

  useEffect(() => {
    fetchLatest();
  }, []);

  const handleRunTests = async () => {
    setRunning(true);
    try {
      await api.post('/health/tests/run');
      await fetchLatest();
    } catch {
      // ignore
    } finally {
      setRunning(false);
    }
  };

  const runSummary = latestRun
    ? `// last run: ${formatTimestamp(latestRun.started_at)} -- ${latestRun.passed} passed, ${latestRun.failed} failed`
    : '// no test runs yet';

  const TAB_COMPONENTS = {
    unit: () => <UnitTab latestRun={latestRun} resultsByCategory={resultsByCategory} />,
    integration: () => <IntegrationTab />,
    psychometrics: () => <PsychometricsTab />,
  };
  const ActiveComponent = TAB_COMPONENTS[activeTab];

  return (
    <div className="page health-page">
      <h1>Health</h1>

      <div className="health-controls">
        <button
          className="health-run-btn"
          onClick={handleRunTests}
          disabled={running}
        >
          {running ? '[ running tests... ]' : '[ run tests ]'}
        </button>
        <span className="health-run-summary">{loadingLatest ? '' : runSummary}</span>
      </div>

      <div className="health-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={
              'health-tab' +
              (activeTab === tab.id ? ' health-tab--active' : '')
            }
            onClick={() => setActiveTab(tab.id)}
          >
            [ {tab.label} ]
          </button>
        ))}
      </div>

      <div className="health-panel">
        <ActiveComponent />
      </div>
    </div>
  );
}

export default HealthPage;
