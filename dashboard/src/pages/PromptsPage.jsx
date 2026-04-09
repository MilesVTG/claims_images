import { useState, useEffect, useCallback } from 'react';
import api from '../api/client';

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

function TerminalSpinner() {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 120);
    return () => clearInterval(id);
  }, []);
  return <span className="terminal-spinner">{SPINNER_FRAMES[frame]}</span>;
}

const PROMPT_USAGE = {
  fraud_system_instruction: {
    path: 'Worker → Gemini → system instruction',
    desc: 'Sets the investigator persona for all Gemini fraud analysis calls. Loaded once per claim analysis.',
  },
  fraud_analysis_template: {
    path: 'Worker → Gemini → per-claim analysis',
    desc: 'Main analysis template. Dynamic fields filled at runtime: contract history, EXIF data, Vision results. Defines the JSON response schema Gemini must follow.',
  },
  photo_qa_system: {
    path: 'API → Photo Q&A → system instruction',
    desc: 'System instruction for the photo question-answering feature. Sets the analyst persona for user-initiated photo queries.',
  },
  photo_qa_template: {
    path: 'API → Photo Q&A → user question',
    desc: 'Template for user questions about individual photos. Injects existing analysis context and the user question.',
  },
  high_risk_email_template: {
    path: 'Worker → Email Service → alert body',
    desc: 'Email body sent when a claim exceeds the high-risk threshold. Dynamic fields: claim ID, contract, score, flags, dashboard URL.',
  },
  high_risk_email_subject: {
    path: 'Worker → Email Service → alert subject',
    desc: 'Subject line for high-risk alert emails. Dynamic fields: claim ID, risk score.',
  },
  batch_analysis_template: {
    path: 'Worker → Gemini → batch processing',
    desc: 'Template for batch photo analysis. Not yet wired — reserved for future batch processing pipeline.',
  },
};

function PromptsPage() {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [editContent, setEditContent] = useState('');
  const [editVersion, setEditVersion] = useState('');
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'ok'|'error', msg }

  useEffect(() => {
    fetchPrompts();
  }, []);

  async function fetchPrompts() {
    setLoading(true);
    setError('');
    try {
      const data = await api.get('/prompts');
      setPrompts(data);
    } catch (err) {
      setError(err.message || 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  }

  const selectPrompt = useCallback(async (slug) => {
    setSelected(slug);
    setFeedback(null);
    setDetailLoading(true);
    try {
      const data = await api.get(`/prompts/${slug}`);
      setDetail(data);
      setEditContent(data.content || '');
      setEditVersion(String((data.version || 0) + 1));
    } catch (err) {
      setDetail(null);
      setFeedback({ type: 'error', msg: err.message || 'Failed to load prompt' });
    } finally {
      setDetailLoading(false);
    }
  }, []);

  async function handleSave() {
    if (!selected || !detail) return;
    setSaving(true);
    setFeedback(null);
    try {
      const version = parseInt(editVersion, 10);
      const body = { content: editContent };
      if (!isNaN(version)) {
        body.version = version;
      }
      const updated = await api.patch(`/prompts/${selected}`, body);
      setDetail(updated);
      setEditVersion(String((updated.version || 0) + 1));
      setFeedback({ type: 'ok', msg: `Saved v${updated.version}` });
      // Refresh list to show updated version
      const list = await api.get('/prompts');
      setPrompts(list);
    } catch (err) {
      setFeedback({ type: 'error', msg: err.message || 'Save failed' });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="page prompts-page">
        <h1>System Prompts</h1>
        <p className="loading-state"><TerminalSpinner /> Fetching prompts...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page prompts-page">
        <h1>System Prompts</h1>
        <p className="error-state">{error}</p>
      </div>
    );
  }

  return (
    <div className="page prompts-page">
      <h1>System Prompts</h1>
      <div className="prompts-layout">
        {/* Left panel: prompt list */}
        <div className="prompts-list">
          <div className="prompts-list__header">// select prompt</div>
          {prompts.length === 0 ? (
            <p className="empty-state">No prompts found.</p>
          ) : (
            <ul>
              {prompts.map((p) => (
                <li
                  key={p.slug}
                  className={
                    'prompts-list__item' +
                    (selected === p.slug ? ' prompts-list__item--selected' : '')
                  }
                  onClick={() => selectPrompt(p.slug)}
                >
                  <span className="prompts-list__slug">{p.slug}</span>
                  <span className="prompts-list__meta">
                    <span className="prompts-list__version">[v{p.version}]</span>
                    <span className="prompts-list__category">{p.category}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Right panel: editor */}
        <div className="prompts-editor">
          {!selected && !detailLoading && (
            <div className="prompts-editor__empty">
              <span className="prompts-editor__empty-text">
                {'<'}- select a prompt to edit
              </span>
            </div>
          )}

          {detailLoading && (
            <div className="prompts-editor__loading">
              <TerminalSpinner /> Loading prompt...
            </div>
          )}

          {selected && detail && !detailLoading && (
            <>
              {/* Info fields — two columns */}
              <div className="prompts-info prompts-info--split">
                <div className="prompts-info__left">
                  <dl className="meta-pairs">
                    <dt>slug</dt>
                    <dd>{detail.slug}</dd>
                    <dt>name</dt>
                    <dd>{detail.name}</dd>
                    <dt>category</dt>
                    <dd>{detail.category}</dd>
                    <dt>model</dt>
                    <dd>{detail.model || '--'}</dd>
                  </dl>
                </div>
                <div className="prompts-info__right">
                  {PROMPT_USAGE[detail.slug] && (
                    <div className="prompts-info__usage">
                      <div className="prompts-info__path">
                        <span className="prompts-info__path-label">pipeline:</span>
                        <span className="prompts-info__path-value">{PROMPT_USAGE[detail.slug].path}</span>
                      </div>
                      <div className="prompts-info__desc">{PROMPT_USAGE[detail.slug].desc}</div>
                    </div>
                  )}
                  <dl className="meta-pairs">
                    <dt>version</dt>
                    <dd>v{detail.version}</dd>
                    <dt>active</dt>
                    <dd>{detail.is_active ? 'yes' : 'no'}</dd>
                    <dt>updated</dt>
                    <dd>{formatTimestamp(detail.updated_at)}</dd>
                  </dl>
                </div>
              </div>

              {/* Content editor */}
              <label className="prompts-editor__label">// content</label>
              <textarea
                className="prompts-editor__textarea"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                spellCheck={false}
              />

              {/* Version + save row */}
              <div className="prompts-editor__actions">
                <label className="prompts-editor__version-label">
                  version:
                  <input
                    type="number"
                    className="prompts-editor__version-input"
                    value={editVersion}
                    onChange={(e) => setEditVersion(e.target.value)}
                    min="1"
                  />
                </label>
                <button
                  className="prompts-editor__save"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? <><TerminalSpinner /> saving...</> : '[save]'}
                </button>
              </div>

              {/* Feedback */}
              {feedback && (
                <div
                  className={
                    'prompts-editor__feedback' +
                    (feedback.type === 'ok'
                      ? ' prompts-editor__feedback--ok'
                      : ' prompts-editor__feedback--error')
                  }
                >
                  {feedback.type === 'ok' ? '[OK] ' : '[ERROR] '}
                  {feedback.msg}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function formatTimestamp(ts) {
  if (!ts) return '--';
  try {
    return new Date(ts).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

export default PromptsPage;
