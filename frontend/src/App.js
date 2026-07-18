import React, { useEffect, useMemo, useState } from 'react';
import './App.css';

const API_BASE = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

const starterQuestions = [
  'How do we handle edge router failover?',
  'What metadata is required before AI can use telemetry?',
  'What controls prevent stale or unowned network knowledge?',
  'Can AI use draft or stale operational content for change execution?',
];

function scoreClass(score) {
  if (score >= 90) return 'score-good';
  if (score >= 75) return 'score-ok';
  return 'score-risk';
}

function App() {
  const [assets, setAssets] = useState([]);
  const [governance, setGovernance] = useState(null);
  const [query, setQuery] = useState('edge router failover rollback');
  const [question, setQuestion] = useState(starterQuestions[0]);
  const [matches, setMatches] = useState([]);
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState([]);
  const [activeAsset, setActiveAsset] = useState(null);
  const [notice, setNotice] = useState('Ready. The synthetic network knowledge corpus is loaded from knowledge_inputs/.');
  const [busy, setBusy] = useState('');

  const summary = governance?.summary || { asset_count: 0, average_readiness: 0, approved_count: 0, issue_count: 0 };
  const services = useMemo(() => [...new Set(assets.map((asset) => asset.service))].sort(), [assets]);

  useEffect(() => {
    refresh();
  }, []);

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Request failed');
    return data;
  }

  async function refresh() {
    setBusy('refresh');
    try {
      await request('/api/ingest', { method: 'POST' });
      const [assetData, governanceData] = await Promise.all([request('/api/assets'), request('/api/governance')]);
      setAssets(assetData.assets || []);
      setGovernance(governanceData);
      setActiveAsset(assetData.assets?.[0] || null);
      setNotice('Knowledge index refreshed from synthetic runbooks, SOPs, standards, policies, configs, telemetry, and incidents.');
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy('');
    }
  }

  async function runSearch(event) {
    event?.preventDefault();
    setBusy('search');
    try {
      const data = await request('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, min_readiness: 0, top_k: 8 }),
      });
      setMatches(data.matches || []);
      setNotice(`Retrieved ${data.matches?.length || 0} chunks with metadata and readiness signals.`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy('');
    }
  }

  async function askQuestion(event) {
    event?.preventDefault();
    setBusy('ask');
    try {
      const data = await request('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k: 4 }),
      });
      setAnswer(data.answer || '');
      setSources(data.sources || []);
      setNotice('Answer generated from retrieved network knowledge with source evidence.');
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <strong>Aegis Knowledge Hub</strong>
          <span>AI-ready network operations context</span>
        </div>
        <button type="button" onClick={refresh} disabled={busy !== ''}>
          {busy === 'refresh' ? 'Indexing...' : 'Re-index inputs'}
        </button>
      </header>

      <main className="workspace">
        <section className="overview">
          <div>
            <p className="eyebrow">Data Knowledge pillar demo</p>
            <h1>Govern, score, retrieve, and answer from network knowledge.</h1>
            <p>
              This portfolio app turns operational documents, configuration notes, telemetry summaries, and incident
              records into traceable context assets for AI and agentic workflows.
            </p>
          </div>
          <div className="score-card">
            <span>AI readiness</span>
            <strong>{summary.average_readiness}</strong>
            <small>{summary.asset_count} indexed assets</small>
          </div>
        </section>

        <section className="metric-grid">
          <article>
            <span>Assets</span>
            <strong>{summary.asset_count}</strong>
          </article>
          <article>
            <span>Approved</span>
            <strong>{summary.approved_count}</strong>
          </article>
          <article>
            <span>Control Issues</span>
            <strong>{summary.issue_count}</strong>
          </article>
          <article>
            <span>Services</span>
            <strong>{services.length}</strong>
          </article>
        </section>

        <section className="notice">{notice}</section>

        <section className="grid">
          <div className="left-column">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Knowledge assets</p>
                  <h2>Readiness queue</h2>
                </div>
              </div>
              <div className="asset-list">
                {assets.map((asset) => (
                  <button
                    type="button"
                    className={`asset-row ${activeAsset?.id === asset.id ? 'selected' : ''}`}
                    key={asset.id}
                    onClick={() => setActiveAsset(asset)}
                  >
                    <span className={`score-pill ${scoreClass(asset.readiness_score)}`}>{asset.readiness_score}</span>
                    <div>
                      <strong>{asset.title}</strong>
                      <em>{asset.asset_type} / {asset.service}</em>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section className="panel">
              <p className="eyebrow">Control coverage</p>
              <h2>Governance findings</h2>
              <div className="control-list">
                {(governance?.control_issues || []).map((item) => (
                  <article key={item.control}>
                    <span>{item.control.replace('_', ' ')}</span>
                    <strong>{item.count}</strong>
                  </article>
                ))}
              </div>
            </section>
          </div>

          <section className="panel detail-panel">
            {activeAsset ? (
              <>
                <div className="asset-header">
                  <div>
                    <p className="eyebrow">{activeAsset.asset_type}</p>
                    <h2>{activeAsset.title}</h2>
                    <p>{activeAsset.service} / {activeAsset.owner || 'Unowned'}</p>
                  </div>
                  <span className={`big-score ${scoreClass(activeAsset.readiness_score)}`}>{activeAsset.readiness_score}</span>
                </div>
                <div className="metadata-grid">
                  <article><span>Steward</span><strong>{activeAsset.metadata.steward || 'Missing'}</strong></article>
                  <article><span>Freshness</span><strong>{activeAsset.freshness_date || 'Missing'}</strong></article>
                  <article><span>Status</span><strong>{activeAsset.status}</strong></article>
                  <article><span>Lineage</span><strong>{activeAsset.metadata.lineage || 'Missing'}</strong></article>
                </div>
                <div className="issue-stack">
                  {activeAsset.issues.length ? (
                    activeAsset.issues.map((issue) => (
                      <article key={`${issue.control}-${issue.message}`}>
                        <strong>{issue.control.replace('_', ' ')}</strong>
                        <p>{issue.message}</p>
                      </article>
                    ))
                  ) : (
                    <article><strong>Ready for model use</strong><p>Required metadata, freshness, lineage, and supportability checks passed.</p></article>
                  )}
                </div>
                <pre className="content-preview">{activeAsset.content}</pre>
              </>
            ) : (
              <div className="empty-state">Index the sample corpus to inspect assets.</div>
            )}
          </section>
        </section>

        <section className="qa-grid">
          <section className="panel">
            <p className="eyebrow">Retrieval</p>
            <h2>Search indexed context</h2>
            <form className="search-form" onSubmit={runSearch}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} />
              <button type="submit" disabled={busy !== ''}>{busy === 'search' ? 'Searching...' : 'Search'}</button>
            </form>
            <div className="match-list">
              {matches.map((match) => (
                <article key={match.id}>
                  <span>{match.score} relevance / readiness {match.readiness_score}</span>
                  <strong>{match.title}</strong>
                  <p>{match.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <p className="eyebrow">Grounded answer</p>
            <h2>Ask the knowledge hub</h2>
            <div className="question-chips">
              {starterQuestions.map((item) => (
                <button type="button" key={item} onClick={() => setQuestion(item)}>{item}</button>
              ))}
            </div>
            <form className="ask-form" onSubmit={askQuestion}>
              <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} />
              <button type="submit" disabled={busy !== ''}>{busy === 'ask' ? 'Answering...' : 'Ask'}</button>
            </form>
            {answer ? (
              <div className="answer-card">
                <strong>Answer</strong>
                <p>{answer}</p>
              </div>
            ) : null}
            <div className="source-list">
              {sources.map((source) => (
                <article key={source.id}>
                  <strong>{source.title}</strong>
                  <span>{source.asset_type} / readiness {source.readiness_score}</span>
                </article>
              ))}
            </div>
          </section>
        </section>
      </main>
    </div>
  );
}

export default App;
