import { useState, useEffect } from 'react';
import api from '../api/client';

const TABS = [
  { id: 'unit', label: 'UNIT' },
  { id: 'integration', label: 'INTEGRATION' },
  { id: 'psychometrics', label: 'PSYCHOMETRICS' },
];

const RUN_LABELS = {
  unit: 'run unit tests',
  integration: 'run int tests',
  psychometrics: 'run psycho tests',
};

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

function SectionHeader({ title, runLabel, running, onRun }) {
  return (
    <div className="health-section__header health-section__header--with-btn">
      <span>// {title}</span>
      <button
        className="health-run-btn"
        onClick={onRun}
        disabled={running}
      >
        {running ? '[ running... ]' : `[ ${runLabel} ]`}
      </button>
    </div>
  );
}

function UnitTab({ latestRun, resultsByCategory, running, onRun }) {
  // Build category summary rows
  const categoryRows = CATEGORY_ORDER
    .map((cat) => {
      const tests = resultsByCategory[cat];
      if (!tests) return { cat, total: 0, passed: 0, failed: 0, rowStatus: 'pending' };
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

  const summary = latestRun
    ? `// last run: ${formatTimestamp(latestRun.started_at)} -- ${latestRun.passed} passed, ${latestRun.failed} failed`
    : null;

  return (
    <div className="health-tab-content">
      <div className="health-section">
        <SectionHeader
          title="unit test suites"
          runLabel={RUN_LABELS.unit}
          running={running}
          onRun={onRun}
        />
        {summary && <div className="health-run-summary">{summary}</div>}
        {!latestRun && !running ? (
          <div className="health-section__placeholder">[ -- no runs ]</div>
        ) : (
          categoryRows.map((row) => (
            <TestRow
              key={row.cat}
              label={formatCategory(row.cat)}
              status={row.rowStatus}
              passed={row.passed}
              failed={row.failed}
              total={row.total}
            />
          ))
        )}
      </div>
    </div>
  );
}

function IntegrationTab({ latestRun, resultsByCategory, running, onRun }) {
  const categoryRows = Object.keys(resultsByCategory).map((cat) => {
    const tests = resultsByCategory[cat];
    const total = tests.length;
    const passed = tests.filter((t) => t.status === 'passed').length;
    const failed = tests.filter((t) => t.status === 'failed' || t.status === 'error').length;
    return { cat, total, passed, failed, rowStatus: failed > 0 ? 'fail' : 'pass' };
  });

  const summary = latestRun
    ? `// last run: ${formatTimestamp(latestRun.started_at)} -- ${latestRun.passed} passed, ${latestRun.failed} failed`
    : null;

  return (
    <div className="health-tab-content">
      <div className="health-section">
        <SectionHeader
          title="integration test suites"
          runLabel={RUN_LABELS.integration}
          running={running}
          onRun={onRun}
        />
        {summary && <div className="health-run-summary">{summary}</div>}
        {!latestRun && !running ? (
          <div className="health-section__placeholder">[ -- no runs ]</div>
        ) : (
          categoryRows.map((row) => (
            <TestRow
              key={row.cat}
              label={formatCategory(row.cat)}
              status={row.rowStatus}
              passed={row.passed}
              failed={row.failed}
              total={row.total}
            />
          ))
        )}
      </div>
    </div>
  );
}

function PsychometricsTab({ latestRun, resultsByCategory, running, onRun }) {
  const categoryRows = Object.keys(resultsByCategory).map((cat) => {
    const tests = resultsByCategory[cat];
    const total = tests.length;
    const passed = tests.filter((t) => t.status === 'passed').length;
    const failed = tests.filter((t) => t.status === 'failed' || t.status === 'error').length;
    return { cat, total, passed, failed, rowStatus: failed > 0 ? 'fail' : 'pass' };
  });

  const summary = latestRun
    ? `// last run: ${formatTimestamp(latestRun.started_at)} -- ${latestRun.passed} passed, ${latestRun.failed} failed`
    : null;

  return (
    <div className="health-tab-content">
      <div className="health-section">
        <SectionHeader
          title="model quality checks"
          runLabel={RUN_LABELS.psychometrics}
          running={running}
          onRun={onRun}
        />
        {summary && <div className="health-run-summary">{summary}</div>}
        {!latestRun && !running ? (
          <>
            {PSYCHOMETRICS_SECTIONS.map((sec) => (
              <TestRow key={sec.id} label={sec.label} />
            ))}
          </>
        ) : (
          categoryRows.map((row) => (
            <TestRow
              key={row.cat}
              label={formatCategory(row.cat)}
              status={row.rowStatus}
              passed={row.passed}
              failed={row.failed}
              total={row.total}
            />
          ))
        )}
      </div>
    </div>
  );
}

function HealthPage() {
  const [activeTab, setActiveTab] = useState('unit');

  // Per-type state
  const [unitRun, setUnitRun] = useState(null);
  const [unitResults, setUnitResults] = useState({});
  const [intRun, setIntRun] = useState(null);
  const [intResults, setIntResults] = useState({});
  const [psychoRun, setPsychoRun] = useState(null);
  const [psychoResults, setPsychoResults] = useState({});
  const [running, setRunning] = useState(null); // which type is running

  const fetchLatest = async (type, setRun, setResults) => {
    try {
      const data = await api.get(`/health/tests/latest?type=${type}`);
      setRun(data.run);
      setResults(data.results_by_category || {});
    } catch {
      // no runs yet
    }
  };

  useEffect(() => {
    fetchLatest('unit', setUnitRun, setUnitResults);
    fetchLatest('integration', setIntRun, setIntResults);
    fetchLatest('psychometrics', setPsychoRun, setPsychoResults);
  }, []);

  const handleRun = async (type, setRun, setResults) => {
    setRunning(type);
    try {
      await api.post(`/health/tests/run?run_type=${type}`);
      await fetchLatest(type, setRun, setResults);
    } catch {
      // ignore
    } finally {
      setRunning(null);
    }
  };

  const TAB_COMPONENTS = {
    unit: () => (
      <UnitTab
        latestRun={unitRun}
        resultsByCategory={unitResults}
        running={running === 'unit'}
        onRun={() => handleRun('unit', setUnitRun, setUnitResults)}
      />
    ),
    integration: () => (
      <IntegrationTab
        latestRun={intRun}
        resultsByCategory={intResults}
        running={running === 'integration'}
        onRun={() => handleRun('integration', setIntRun, setIntResults)}
      />
    ),
    psychometrics: () => (
      <PsychometricsTab
        latestRun={psychoRun}
        resultsByCategory={psychoResults}
        running={running === 'psychometrics'}
        onRun={() => handleRun('psychometrics', setPsychoRun, setPsychoResults)}
      />
    ),
  };
  const ActiveComponent = TAB_COMPONENTS[activeTab];

  return (
    <div className="page health-page">
      <h1>Health</h1>

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
