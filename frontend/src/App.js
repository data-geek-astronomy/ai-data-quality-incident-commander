import React, { useEffect, useMemo, useState } from 'react';
import './App.css';

const API_BASE = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

const datasetKinds = [
  { id: 'orders', label: 'Commerce Orders' },
  { id: 'payments', label: 'Payments Ledger' },
  { id: 'events', label: 'Product Events' },
];

const statusOptions = ['open', 'investigating', 'fix_ready', 'resolved'];

const demoCopy = {
  orders: {
    headline: 'Revenue report changed overnight',
    detail: 'Finds missing totals, duplicate orders, and unusual customer states before leaders see the wrong number.',
  },
  payments: {
    headline: 'Payments ledger looks wrong',
    detail: 'Spots broken fields, negative charges, and processor changes that can create finance noise.',
  },
  events: {
    headline: 'Product analytics dropped',
    detail: 'Detects tracking gaps, bad timestamps, and app events that stopped behaving normally.',
  },
};

const statusLabels = {
  open: 'New',
  investigating: 'Reviewing',
  fix_ready: 'Fix ready',
  resolved: 'Resolved',
};

const issueLabels = {
  'Schema contract broken': 'Required business field is missing',
  'Duplicate records detected': 'Repeated records found',
  'Primary key collision': 'Record IDs are repeating',
  'Null spike': 'Important values are missing',
  'Metric collapse': 'A key number stopped moving',
  'Numeric outlier burst': 'Unexpected number spike',
  'Invalid negative business metric': 'Negative value needs review',
  'Timestamp parsing failure': 'Dates are not reading correctly',
  'Unexpected category drift': 'New value appeared unexpectedly',
  'Distribution shift': 'The pattern changed from normal',
};

function severityClass(value) {
  return `severity severity-${value || 'low'}`;
}

function App() {
  const [demoDatasets, setDemoDatasets] = useState([]);
  const [sampleUploads, setSampleUploads] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [activeIncident, setActiveIncident] = useState(null);
  const [selectedKind, setSelectedKind] = useState('orders');
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedSample, setSelectedSample] = useState(null);
  const [postmortem, setPostmortem] = useState('');
  const [status, setStatus] = useState({ tone: 'idle', message: 'Ready. Choose a scenario to see the product in action.' });
  const [busy, setBusy] = useState('');

  const summary = useMemo(() => {
    const open = incidents.filter((item) => item.status !== 'resolved').length;
    const critical = incidents.filter((item) => item.severity === 'critical').length;
    const avgHealth = incidents.length
      ? Math.round(incidents.reduce((total, item) => total + item.health_score, 0) / incidents.length)
      : 100;
    return { open, critical, avgHealth };
  }, [incidents]);

  useEffect(() => {
    loadDemos();
    loadSampleUploads();
    loadIncidents();
  }, []);

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.message || 'Request failed');
    }
    return data;
  }

  async function loadDemos() {
    try {
      const data = await request('/api/demo-datasets');
      setDemoDatasets(data.datasets || []);
    } catch {
      setDemoDatasets([]);
    }
  }

  async function loadSampleUploads() {
    try {
      const data = await request('/api/sample-uploads');
      setSampleUploads(data.samples || []);
    } catch {
      setSampleUploads([]);
    }
  }

  async function loadIncidents() {
    try {
      const data = await request('/api/incidents');
      setIncidents(data.incidents || []);
      if (!activeIncident && data.incidents?.length) {
        setActiveIncident(data.incidents[0]);
      }
    } catch {
      setIncidents([]);
    }
  }

  async function analyzeDemo(kind) {
    setBusy(`demo-${kind}`);
    setStatus({ tone: 'pending', message: 'Checking the data and building an incident brief...' });
    setPostmortem('');
    try {
      const data = await request(`/api/analyze-demo/${kind}`, { method: 'POST' });
      setActiveIncident(data.incident);
      await loadIncidents();
      setStatus({ tone: 'success', message: `Found ${data.incident.issues.length} risks and prepared a response plan.` });
    } catch (error) {
      setStatus({ tone: 'error', message: error.message });
    } finally {
      setBusy('');
    }
  }

  async function analyzeSample(sample) {
    setSelectedKind(sample.data_type);
    setSelectedSample(sample);
    setSelectedFile(null);
    setBusy(`sample-${sample.id}`);
    setPostmortem('');
    setStatus({ tone: 'pending', message: `${sample.filename} selected. Reviewing sample data now...` });
    try {
      const data = await request(`/api/analyze-sample/${sample.id}`, { method: 'POST' });
      setActiveIncident(data.incident);
      await loadIncidents();
      setStatus({ tone: 'success', message: `${sample.name} sample loaded and reviewed automatically.` });
    } catch (error) {
      setStatus({ tone: 'error', message: error.message });
    } finally {
      setBusy('');
    }
  }

  async function uploadDataset(event) {
    event.preventDefault();
    if (!selectedFile) {
      setStatus({ tone: 'error', message: 'Choose a CSV file first.' });
      return;
    }
    const form = new FormData();
    form.append('file', selectedFile);
    setBusy('upload');
    setPostmortem('');
    setStatus({ tone: 'pending', message: `Reviewing ${selectedFile.name}...` });
    try {
      const data = await request(`/api/analyze?dataset_kind=${selectedKind}`, {
        method: 'POST',
        body: form,
      });
      setActiveIncident(data.incident);
      await loadIncidents();
      setStatus({ tone: 'success', message: 'Review complete. The response plan is ready.' });
    } catch (error) {
      setStatus({ tone: 'error', message: error.message });
    } finally {
      setBusy('');
    }
  }

  async function updateIncidentStatus(nextStatus) {
    if (!activeIncident) return;
    setBusy('status');
    try {
      const data = await request(`/api/incidents/${activeIncident.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus }),
      });
      setActiveIncident(data.incident);
      await loadIncidents();
      setStatus({ tone: 'success', message: `Status updated to ${statusLabels[nextStatus]}.` });
    } catch (error) {
      setStatus({ tone: 'error', message: error.message });
    } finally {
      setBusy('');
    }
  }

  async function generatePostmortem() {
    if (!activeIncident) return;
    setBusy('postmortem');
    try {
      const data = await request(`/api/incidents/${activeIncident.id}/postmortem`);
      setPostmortem(data.markdown || '');
      setStatus({ tone: 'success', message: 'Summary generated and ready to share.' });
    } catch (error) {
      setStatus({ tone: 'error', message: error.message });
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <nav className="nav">
          <strong>Clearline AI</strong>
          <span>Data Reliability Copilot</span>
        </nav>
        <div className="hero-grid">
          <div>
            <p className="eyebrow">For teams that run on trustworthy data</p>
            <h1>Catch bad data before it breaks business decisions.</h1>
            <p className="subtitle">
              Clearline watches incoming datasets, explains what changed, recommends the next action,
              and turns every issue into a clean response brief.
            </p>
            <div className="hero-actions">
              <a href="#workspace">Try live demo</a>
              <span>No setup required</span>
            </div>
          </div>
          <div className="hero-card">
            <div className="pulse-row">
              <span className="pulse-dot" />
              Live data review
            </div>
            <strong>{summary.avgHealth}</strong>
            <p>Trust score across reviewed datasets</p>
            <div className="mini-bars">
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>
        </div>
      </header>

      <main id="workspace" className="main-grid">
        <section className="panel command-panel">
          <div className="panel-heading">
            <div>
              <p className="section-label">Live product demo</p>
              <h2>Choose a business moment to protect</h2>
            </div>
          </div>

          <div className="demo-grid">
            {demoDatasets.map((dataset) => (
              <button
                className="demo-card"
                key={dataset.id}
                type="button"
                onClick={() => analyzeDemo(dataset.id)}
                disabled={busy !== ''}
              >
                <span>{dataset.name}</span>
                <strong>{demoCopy[dataset.id]?.headline || dataset.name}</strong>
                <p>{demoCopy[dataset.id]?.detail || dataset.description}</p>
                <em>{busy === `demo-${dataset.id}` ? 'Reviewing...' : 'Review data'}</em>
              </button>
            ))}
          </div>

          <form className="upload-box" onSubmit={uploadDataset}>
            <label>
              Data type
              <select value={selectedKind} onChange={(event) => setSelectedKind(event.target.value)}>
                {datasetKinds.map((kind) => (
                  <option key={kind.id} value={kind.id}>
                    {kind.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Bring your own CSV
              <input
                type="file"
                accept=".csv"
                onChange={(event) => {
                  setSelectedFile(event.target.files?.[0] || null);
                  setSelectedSample(null);
                }}
              />
            </label>
            {selectedSample ? (
              <div className="selected-sample">
                <span>Selected sample</span>
                <strong>{selectedSample.filename}</strong>
              </div>
            ) : null}
            <button type="submit" disabled={busy !== ''}>
              {busy === 'upload' ? 'Reviewing...' : 'Review upload'}
            </button>
          </form>

          <div className="sample-upload-panel">
            <div>
              <p className="section-label">Ready sample data</p>
              <h3>Click a sample to load and run it</h3>
            </div>
            <div className="sample-upload-grid">
              {sampleUploads.map((sample) => (
                <button
                  className={`sample-upload-card ${selectedSample?.id === sample.id ? 'selected' : ''}`}
                  key={sample.id}
                  type="button"
                  onClick={() => analyzeSample(sample)}
                  disabled={busy !== ''}
                >
                  <span>{sample.filename}</span>
                  <strong>{sample.scenario}</strong>
                  <p>{sample.overview}</p>
                  <div className="sample-meta">
                    <em>{sample.row_count} rows</em>
                    <em>{sample.columns.length} fields</em>
                  </div>
                  <b>{busy === `sample-${sample.id}` ? 'Running...' : 'Use this sample'}</b>
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className={`status-strip status-${status.tone}`}>{status.message}</section>

        <section className="panel metric-panel">
          <article>
            <span>Active reviews</span>
            <strong>{summary.open}</strong>
          </article>
          <article>
            <span>Urgent risks</span>
            <strong>{summary.critical}</strong>
          </article>
          <article>
            <span>Trust score</span>
            <strong>{summary.avgHealth}</strong>
          </article>
        </section>

        <section className="panel incident-list-panel">
          <div className="panel-heading compact">
            <div>
              <p className="section-label">Recent reviews</p>
              <h2>Response queue</h2>
            </div>
          </div>
          <div className="incident-list">
            {incidents.length === 0 ? (
              <p className="empty-state">No reviews yet. Start with a live demo above.</p>
            ) : (
              incidents.map((incident) => (
                <button
                  type="button"
                  key={incident.id}
                  className={`incident-row ${activeIncident?.id === incident.id ? 'selected' : ''}`}
                  onClick={() => {
                    setActiveIncident(incident);
                    setPostmortem('');
                  }}
                >
                  <span className={severityClass(incident.severity)}>{incident.severity}</span>
                  <strong>{incident.dataset_name}</strong>
                  <em>{statusLabels[incident.status] || incident.status}</em>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="panel detail-panel">
          {!activeIncident ? (
            <div className="empty-detail">
              <p className="section-label">Response plan</p>
              <h2>Select a review to see what changed and what to do next.</h2>
            </div>
          ) : (
            <>
              <div className="detail-header">
                <div>
                  <p className="section-label">Review {activeIncident.id}</p>
                  <h2>{activeIncident.dataset_label}</h2>
                  <p>{activeIncident.dataset_name}</p>
                </div>
                <div className="health-ring">
                  <span>{activeIncident.health_score}</span>
                  <small>trust</small>
                </div>
              </div>

              <div className="status-actions">
                {statusOptions.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={activeIncident.status === option ? 'active' : ''}
                    onClick={() => updateIncidentStatus(option)}
                    disabled={busy !== ''}
                  >
                    {statusLabels[option]}
                  </button>
                ))}
              </div>

              <div className="current-stage">
                <span>Current stage</span>
                <strong>{statusLabels[activeIncident.status] || activeIncident.status}</strong>
                <p>
                  {activeIncident.status === 'open'
                    ? 'A new review is waiting for someone to look at it.'
                    : activeIncident.status === 'investigating'
                      ? 'The team is reviewing the signals and likely cause.'
                      : activeIncident.status === 'fix_ready'
                        ? 'Recommended actions are ready to apply or hand off.'
                        : 'This review is resolved and ready to archive.'}
                </p>
              </div>

              <div className="insight-card">
                <span className={severityClass(activeIncident.severity)}>{activeIncident.severity}</span>
                <h3>What likely happened</h3>
                <p>{activeIncident.root_cause}</p>
              </div>

              <div className="split-grid">
                <div>
                  <h3>Signals found</h3>
                  <div className="stack">
                    {activeIncident.issues.map((item) => (
                      <article className="issue-card" key={`${item.title}-${item.column}-${item.metric}`}>
                        <span className={severityClass(item.severity)}>{item.severity}</span>
                        <strong>{issueLabels[item.title] || item.title}</strong>
                        <p>{item.detail}</p>
                      </article>
                    ))}
                  </div>
                </div>

                <div>
                  <h3>Recommended actions</h3>
                  <div className="stack">
                    {activeIncident.recommended_fixes.map((fix) => (
                      <article className="fix-card" key={fix.title}>
                        <strong>{fix.title}</strong>
                        <details>
                          <summary>Implementation detail</summary>
                          <code>{fix.python}</code>
                        </details>
                      </article>
                    ))}
                  </div>
                </div>
              </div>

              <div className="evidence-grid">
                <article>
                  <span>Rows</span>
                  <strong>{activeIncident.row_count}</strong>
                </article>
                <article>
                  <span>Columns</span>
                  <strong>{activeIncident.column_count}</strong>
                </article>
                <article>
                  <span>Change</span>
                  <strong>{activeIncident.evidence.distribution_shift_psi}</strong>
                </article>
              </div>

              <button className="postmortem-button" type="button" onClick={generatePostmortem} disabled={busy !== ''}>
                {busy === 'postmortem' ? 'Generating...' : 'Generate executive summary'}
              </button>

              {postmortem ? <pre className="postmortem">{postmortem}</pre> : null}
            </>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
