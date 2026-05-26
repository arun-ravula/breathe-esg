import React, { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { getTenants, getStats, getBatches, getRecords, approveRecord, rejectRecord, flagRecord, ingestFile } from './api';
import './App.css';

// ─── Color System ─────────────────────────────────────────────────────────────
const STATUS_COLORS = {
  pending: '#C8A84B',
  approved: '#4CAF82',
  rejected: '#E05252',
  suspicious: '#E07B30',
};
const SCOPE_COLORS = { 1: '#2D6BE4', 2: '#43B89C', 3: '#9B59B6' };
const CATEGORY_ICONS = {
  fuel: '⛽', electricity: '⚡', flight: '✈️',
  hotel: '🏨', ground_transport: '🚗', procurement: '📦',
};

function fmt(n, decimals = 0) {
  if (n == null) return '—';
  const num = parseFloat(n);
  if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
  if (num >= 1e3) return (num / 1e3).toFixed(1) + 'k';
  return num.toFixed(decimals);
}

function ScopeTag({ scope }) {
  return (
    <span className="scope-tag" style={{ background: SCOPE_COLORS[scope] + '22', color: SCOPE_COLORS[scope], border: `1px solid ${SCOPE_COLORS[scope]}44` }}>
      S{scope}
    </span>
  );
}

function StatusBadge({ status }) {
  return (
    <span className="status-badge" style={{ background: STATUS_COLORS[status] + '20', color: STATUS_COLORS[status] }}>
      {status}
    </span>
  );
}

function FlagsList({ flags }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="flags-list">
      {flags.map((f, i) => <span key={i} className="flag-item">⚠ {f}</span>)}
    </div>
  );
}

// ─── Dashboard Stats ──────────────────────────────────────────────────────────
function DashboardPanel({ tenantId }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (!tenantId) return;
    getStats(tenantId).then(r => setStats(r.data)).catch(console.error);
  }, [tenantId]);

  if (!stats) return <div className="loading">Loading stats…</div>;

  const scopeData = stats.by_scope.map(s => ({
    name: `Scope ${s.scope}`,
    co2e: parseFloat(s.co2e || 0) / 1000, // tonnes
    color: SCOPE_COLORS[s.scope],
  }));

  const statusData = stats.by_status.map(s => ({
    name: s.review_status,
    value: s.count,
    color: STATUS_COLORS[s.review_status] || '#888',
  }));

  const categoryData = stats.by_category.slice(0, 6).map(c => ({
    name: c.category.replace('_', ' '),
    co2e: parseFloat(c.co2e || 0) / 1000,
  }));

  const totalTonnes = (parseFloat(stats.total_co2e_kg) / 1000).toFixed(1);

  return (
    <div className="dashboard-panel">
      <div className="stat-cards">
        <div className="stat-card accent">
          <div className="stat-label">Total Emissions</div>
          <div className="stat-value">{totalTonnes}<span className="stat-unit"> t CO₂e</span></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Records</div>
          <div className="stat-value">{stats.total_records}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Batches</div>
          <div className="stat-value">{stats.batch_count}</div>
        </div>
        <div className="stat-card warn">
          <div className="stat-label">Needs Review</div>
          <div className="stat-value">
            {(stats.by_status.find(s => s.review_status === 'pending')?.count || 0) +
             (stats.by_status.find(s => s.review_status === 'suspicious')?.count || 0)}
          </div>
        </div>
      </div>

      <div className="charts-row">
        <div className="chart-box">
          <h3>Emissions by Scope (t CO₂e)</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={scopeData}>
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#888' }} />
              <YAxis tick={{ fontSize: 11, fill: '#888' }} />
              <Tooltip formatter={(v) => [v.toFixed(1) + ' t', 'CO₂e']} />
              {scopeData.map(d => (
                <Bar key={d.name} dataKey="co2e" fill={d.color} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-box">
          <h3>Review Status</h3>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={statusData} dataKey="value" cx="50%" cy="50%" outerRadius={65} label={({name, value}) => `${name} (${value})`} labelLine={false} fontSize={10}>
                {statusData.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-box">
          <h3>Top Categories (t CO₂e)</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={categoryData} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#888' }} />
              <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: '#888' }} />
              <Tooltip formatter={(v) => [v.toFixed(1) + ' t', 'CO₂e']} />
              <Bar dataKey="co2e" fill="#2D6BE4" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

// ─── Ingest Panel ─────────────────────────────────────────────────────────────
function IngestPanel({ tenantId, onIngested }) {
  const [sourceType, setSourceType] = useState('sap');
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async () => {
    if (!file || !tenantId) return;
    setLoading(true); setResult(null); setError(null);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('source_type', sourceType);
    fd.append('tenant_id', tenantId);
    try {
      const r = await ingestFile(fd);
      setResult(r.data);
      onIngested();
    } catch (e) {
      setError(e.response?.data?.error || e.message);
    } finally {
      setLoading(false);
    }
  };

  const sources = [
    { value: 'sap', label: 'SAP Fuel & Procurement', desc: 'MM60/ME2M semicolon-delimited export' },
    { value: 'utility', label: 'Utility / Electricity', desc: 'Portal CSV (meter, period, kWh)' },
    { value: 'travel', label: 'Corporate Travel', desc: 'Concur/Navan-style export' },
  ];

  return (
    <div className="ingest-panel">
      <h2>Ingest Data</h2>
      <div className="source-selector">
        {sources.map(s => (
          <div key={s.value}
               className={`source-card ${sourceType === s.value ? 'active' : ''}`}
               onClick={() => setSourceType(s.value)}>
            <div className="source-title">{s.label}</div>
            <div className="source-desc">{s.desc}</div>
          </div>
        ))}
      </div>

      <div className="file-drop-zone">
        <input type="file" accept=".csv,.txt,.tsv" id="file-input"
               onChange={e => setFile(e.target.files[0])} style={{ display: 'none' }} />
        <label htmlFor="file-input" className="file-label">
          {file ? `✓ ${file.name}` : '+ Choose CSV file'}
        </label>
      </div>

      <button className="btn btn-primary" onClick={handleSubmit}
              disabled={!file || !tenantId || loading}>
        {loading ? 'Processing…' : 'Ingest File'}
      </button>

      {result && (
        <div className="ingest-result success">
          <strong>Done!</strong> {result.rows_total} rows — {result.rows_ok} parsed,{' '}
          {result.rows_failed} failed, {result.rows_suspicious} suspicious
        </div>
      )}
      {error && <div className="ingest-result error">Error: {error}</div>}

      <div className="sample-note">
        <strong>Sample files:</strong> Download sample CSVs to test ingestion. Each is modelled on
        real-world formats (SAP MM flat file, UK/IN utility portal, Concur travel export).
        <div className="sample-links">
          <button className="btn-link" onClick={() => downloadSample('sap')}>SAP sample ↓</button>
          <button className="btn-link" onClick={() => downloadSample('utility')}>Utility sample ↓</button>
          <button className="btn-link" onClick={() => downloadSample('travel')}>Travel sample ↓</button>
        </div>
      </div>
    </div>
  );
}

const SAMPLES = {
  sap: `Buchungsdatum;Werk;Material;Kurztext;Menge;ME;Betrag;Bewegungsart;Kostenstelle
20240401;1001;10000042;Diesel HSD;3000;L;270000;201;CC1001
20240410;1002;10000043;Petrol Unleaded;500;L;55000;201;CC1002
20240415;1001;10000042;Diesel HSD;2800;L;252000;201;CC1001`,

  utility: `meter_id,site,period_start,period_end,consumption,unit,tariff
MET-010,Factory Block A,2024-04-01,2024-04-30,112000,kWh,Industrial HT
MET-011,Office,2024-04-01,2024-04-30,6200,kWh,Commercial`,

  travel: `trip_id,travel_date,type,origin,destination,distance_km,nights,employee,class,cost_center,hotel_name
TRP-100,2024-04-05,Flight,BOM,DEL,,,Priya,Economy,CC-SALES,
TRP-101,2024-04-05,Hotel,,DEL,,1,Priya,,,Taj Palace
TRP-102,2024-04-06,Flight,DEL,BOM,,,Priya,Economy,CC-SALES,`,
};

function downloadSample(type) {
  const blob = new Blob([SAMPLES[type]], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url;
  a.download = `sample_${type}.csv`; a.click();
}

// ─── Record Row ───────────────────────────────────────────────────────────────
function RecordRow({ rec, onAction }) {
  const [expanded, setExpanded] = useState(false);
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);

  const action = async (fn, label) => {
    setLoading(true);
    try { await fn(rec.id, note); onAction(); }
    catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <>
      <tr className={`record-row status-${rec.review_status} ${expanded ? 'expanded' : ''}`}
          onClick={() => setExpanded(!expanded)}>
        <td><ScopeTag scope={rec.scope} /></td>
        <td>{CATEGORY_ICONS[rec.category]} {rec.category_display}</td>
        <td className="mono">{rec.activity_date}</td>
        <td className="mono right">
          {rec.raw_quantity != null ? `${fmt(rec.raw_quantity)} ${rec.raw_unit}` : '—'}
        </td>
        <td className="mono right bold">
          {rec.co2e_kg != null ? `${fmt(rec.co2e_kg)} kg` : '—'}
        </td>
        <td>{rec.location_ref || rec.location_label || '—'}</td>
        <td><StatusBadge status={rec.review_status} /></td>
        <td>
          {rec.flags && rec.flags.length > 0 && <span className="flag-count">⚠ {rec.flags.length}</span>}
        </td>
      </tr>
      {expanded && (
        <tr className="detail-row">
          <td colSpan={8}>
            <div className="detail-panel">
              <div className="detail-grid">
                <div>
                  <div className="detail-label">Raw Description</div>
                  <div>{rec.raw_description || '—'}</div>
                </div>
                <div>
                  <div className="detail-label">Normalized Quantity</div>
                  <div className="mono">{rec.quantity_normalized} {rec.quantity_unit_normalized}</div>
                </div>
                <div>
                  <div className="detail-label">Emission Factor</div>
                  <div className="mono">{rec.emission_factor} kg CO₂e / {rec.quantity_unit_normalized}</div>
                  <div className="detail-source">{rec.emission_factor_source}</div>
                </div>
                <div>
                  <div className="detail-label">CO₂e</div>
                  <div className="mono bold">{parseFloat(rec.co2e_kg || 0).toLocaleString()} kg</div>
                </div>
              </div>
              <FlagsList flags={rec.flags} />
              {!rec.is_locked && rec.review_status !== 'approved' && (
                <div className="action-bar">
                  <input className="note-input" placeholder="Add a note (optional)…"
                         value={note} onChange={e => setNote(e.target.value)} />
                  <button className="btn btn-approve" disabled={loading}
                          onClick={(e) => { e.stopPropagation(); action(approveRecord, 'approve'); }}>
                    ✓ Approve
                  </button>
                  <button className="btn btn-reject" disabled={loading}
                          onClick={(e) => { e.stopPropagation(); action(rejectRecord, 'reject'); }}>
                    ✗ Reject
                  </button>
                  <button className="btn btn-flag" disabled={loading}
                          onClick={(e) => { e.stopPropagation(); action((id) => flagRecord(id, note || 'Manually flagged'), 'flag'); }}>
                    ⚠ Flag
                  </button>
                </div>
              )}
              {rec.is_locked && <div className="locked-note">🔒 Locked for audit</div>}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─── Records Table ────────────────────────────────────────────────────────────
function RecordsTable({ tenantId, refreshKey }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ review_status: '', scope: '', category: '' });
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [actionKey, setActionKey] = useState(0);

  const load = useCallback(() => {
    if (!tenantId) return;
    setLoading(true);
    const params = { tenant: tenantId, page, ...Object.fromEntries(Object.entries(filters).filter(([,v]) => v)) };
    getRecords(params).then(r => {
      setRecords(r.data.results || r.data);
      setTotal(r.data.count || (r.data.results || r.data).length);
    }).finally(() => setLoading(false));
  }, [tenantId, page, filters, actionKey, refreshKey]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (k, v) => { setFilters(f => ({ ...f, [k]: v })); setPage(1); };

  return (
    <div className="records-section">
      <div className="filter-bar">
        <select value={filters.review_status} onChange={e => setFilter('review_status', e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="suspicious">Suspicious</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select value={filters.scope} onChange={e => setFilter('scope', e.target.value)}>
          <option value="">All scopes</option>
          <option value="1">Scope 1</option>
          <option value="2">Scope 2</option>
          <option value="3">Scope 3</option>
        </select>
        <select value={filters.category} onChange={e => setFilter('category', e.target.value)}>
          <option value="">All categories</option>
          <option value="fuel">Fuel</option>
          <option value="electricity">Electricity</option>
          <option value="flight">Flight</option>
          <option value="hotel">Hotel</option>
          <option value="ground_transport">Ground Transport</option>
        </select>
        <span className="record-count">{total} records</span>
      </div>

      {loading && <div className="loading">Loading…</div>}

      <table className="records-table">
        <thead>
          <tr>
            <th>Scope</th><th>Category</th><th>Date</th><th>Quantity</th>
            <th>CO₂e</th><th>Location</th><th>Status</th><th>Flags</th>
          </tr>
        </thead>
        <tbody>
          {records.map(r => (
            <RecordRow key={r.id} rec={r} onAction={() => { setActionKey(k => k + 1); }} />
          ))}
        </tbody>
      </table>

      <div className="pagination">
        <button disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
        <span>Page {page} of {Math.ceil(total / 50) || 1}</span>
        <button disabled={page * 50 >= total} onClick={() => setPage(p => p + 1)}>Next →</button>
      </div>
    </div>
  );
}

// ─── Batches Panel ────────────────────────────────────────────────────────────
function BatchesPanel({ tenantId, refreshKey }) {
  const [batches, setBatches] = useState([]);

  useEffect(() => {
    if (!tenantId) return;
    getBatches(tenantId).then(r => setBatches(r.data.results || r.data)).catch(console.error);
  }, [tenantId, refreshKey]);

  return (
    <div className="batches-panel">
      <h2>Ingestion History</h2>
      <table className="records-table">
        <thead>
          <tr><th>Source</th><th>File</th><th>Date</th><th>Total</th><th>OK</th><th>Failed</th><th>Suspicious</th><th>Status</th></tr>
        </thead>
        <tbody>
          {batches.map(b => (
            <tr key={b.id}>
              <td><span className="source-pill">{b.source_type}</span></td>
              <td className="mono" style={{ fontSize: 11 }}>{b.filename}</td>
              <td className="mono">{b.created_at?.slice(0, 10)}</td>
              <td className="right">{b.row_count_total}</td>
              <td className="right" style={{ color: '#4CAF82' }}>{b.row_count_ok}</td>
              <td className="right" style={{ color: '#E05252' }}>{b.row_count_failed}</td>
              <td className="right" style={{ color: '#E07B30' }}>{b.row_count_suspicious}</td>
              <td><StatusBadge status={b.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── App Root ─────────────────────────────────────────────────────────────────
export default function App() {
  const [tenants, setTenants] = useState([]);
  const [tenantId, setTenantId] = useState('');
  const [tab, setTab] = useState('dashboard');
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    getTenants().then(r => {
      const list = r.data.results || r.data;
      setTenants(list);
      if (list.length > 0) setTenantId(list[0].id);
    }).catch(console.error);
  }, []);

  const refresh = () => setRefreshKey(k => k + 1);

  const currentTenant = tenants.find(t => t.id === tenantId);

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          <span className="logo-leaf">◈</span>
          <span className="logo-text">Breathe<span className="logo-esg">ESG</span></span>
        </div>
        <nav className="nav-tabs">
          {[['dashboard', 'Dashboard'], ['records', 'Review Queue'], ['ingest', 'Ingest'], ['batches', 'History']].map(([v, l]) => (
            <button key={v} className={`nav-tab ${tab === v ? 'active' : ''}`} onClick={() => setTab(v)}>{l}</button>
          ))}
        </nav>
        <div className="tenant-selector">
          <select value={tenantId} onChange={e => setTenantId(e.target.value)}>
            {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
      </header>

      <main className="main-content">
        {!tenantId && <div className="empty-state">Select a tenant to begin.</div>}
        {tenantId && (
          <>
            {tab === 'dashboard' && (
              <>
                <div className="page-header">
                  <h1>{currentTenant?.name}</h1>
                  <p>Q1 2024 — Emissions review dashboard</p>
                </div>
                <DashboardPanel tenantId={tenantId} key={refreshKey} />
              </>
            )}
            {tab === 'records' && (
              <>
                <div className="page-header">
                  <h1>Review Queue</h1>
                  <p>Click any row to expand, review flags, and approve or reject</p>
                </div>
                <RecordsTable tenantId={tenantId} refreshKey={refreshKey} />
              </>
            )}
            {tab === 'ingest' && (
              <>
                <div className="page-header">
                  <h1>Ingest New Data</h1>
                  <p>Upload a CSV for {currentTenant?.name}</p>
                </div>
                <IngestPanel tenantId={tenantId} onIngested={refresh} />
              </>
            )}
            {tab === 'batches' && (
              <>
                <div className="page-header">
                  <h1>Ingestion History</h1>
                  <p>All uploads and their parse results</p>
                </div>
                <BatchesPanel tenantId={tenantId} refreshKey={refreshKey} />
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
