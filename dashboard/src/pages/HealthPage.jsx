import { useState } from 'react';

const TABS = [
  { id: 'unit', label: 'UNIT' },
  { id: 'integration', label: 'INTEGRATION' },
  { id: 'psychometrics', label: 'PSYCHOMETRICS' },
];

const UNIT_CATEGORIES = [
  { id: 'worker-services', label: 'worker services' },
  { id: 'api-config', label: 'api config/deps' },
  { id: 'api-claims', label: 'api claims' },
  { id: 'api-dashboard', label: 'api dashboard' },
  { id: 'api-auth', label: 'api auth' },
  { id: 'api-prompts', label: 'api prompts' },
];

const PSYCHOMETRICS_SECTIONS = [
  { id: 'golden-dataset', label: 'golden dataset regression' },
  { id: 'concept-drift', label: 'concept drift detection' },
  { id: 'data-drift', label: 'data drift monitoring' },
];

function TestRow({ label, status = 'pending', passed, failed, total }) {
  let statusText;
  let statusClass;

  if (status === 'pass') {
    statusText = `[ ${passed}/${total} passed ]`;
    statusClass = 'health-status--pass';
  } else if (status === 'fail') {
    statusText = `[ ${failed}/${total} failed ]`;
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

function UnitTab() {
  return (
    <div className="health-tab-content">
      <div className="health-section">
        <div className="health-section__header">// unit test suites</div>
        {UNIT_CATEGORIES.map((cat) => (
          <TestRow key={cat.id} label={cat.label} />
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

const TAB_COMPONENTS = {
  unit: UnitTab,
  integration: IntegrationTab,
  psychometrics: PsychometricsTab,
};

function HealthPage() {
  const [activeTab, setActiveTab] = useState('unit');
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
