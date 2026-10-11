import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, ChevronDown, Clock3,
  Database, Filter, Gauge, MapPin, RefreshCw, Search, ShieldAlert,
  Truck, X,
} from "lucide-react";

type Level = "low" | "medium" | "high" | "critical";
type Supplier = { supplier_id: string; name?: string | null; country?: string | null; status?: string };
type Risk = { supplier_id: string; score: number; level: string; reasons?: { reason: string; points: number }[]; calculated_at: string; abnormal_telemetry?: string[] };
type Disruption = { supplier_id: string; event_id?: string | null; disruption_type: string; severity: string; message: string; starts_at?: string | null; ends_at?: string | null };
type SupplierRow = Supplier & { risk?: Risk; disruptions: Disruption[] };

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8090";
const levels: Level[] = ["low", "medium", "high", "critical"];

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function levelFor(score: number): Level {
  return score < 30 ? "low" : score < 60 ? "medium" : score < 80 ? "high" : "critical";
}
function formatTime(value?: string) {
  if (!value) return "No recent assessment";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
function initials(name: string) { return name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase(); }

export default function App() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [disruptions, setDisruptions] = useState<Disruption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<"all" | Level>("all");
  const [status, setStatus] = useState("all");
  const [lastUpdated, setLastUpdated] = useState<Date>();
  const [showSupplierForm, setShowSupplierForm] = useState(false);
  const [supplierForm, setSupplierForm] = useState({ supplier_id: "", name: "", country: "", status: "active" });
  const [savingSupplier, setSavingSupplier] = useState(false);
  const [supplierMessage, setSupplierMessage] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [supplierData, disruptionData] = await Promise.all([get<Supplier[]>("/suppliers"), get<Disruption[]>("/disruptions")]);
      const riskData = await Promise.all(supplierData.map(async (supplier) => {
        try { return await get<Risk>(`/risk/${encodeURIComponent(supplier.supplier_id)}`); } catch { return undefined; }
      }));
      setSuppliers(supplierData); setRisks(riskData.filter((item): item is Risk => Boolean(item))); setDisruptions(disruptionData); setLastUpdated(new Date());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to connect to the risk service.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void loadData(); }, [loadData]);

  const addSupplier = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSavingSupplier(true);
    setSupplierMessage("");
    try {
      await post<Supplier>("/suppliers", {
        supplier_id: supplierForm.supplier_id.trim(),
        name: supplierForm.name.trim() || undefined,
        country: supplierForm.country.trim() || undefined,
        status: supplierForm.status,
      });
      setSupplierForm({ supplier_id: "", name: "", country: "", status: "active" });
      setSupplierMessage("Supplier added successfully.");
      await loadData();
    } catch (caught) {
      setSupplierMessage(caught instanceof Error ? `Could not add supplier: ${caught.message}` : "Could not add supplier.");
    } finally {
      setSavingSupplier(false);
    }
  };

  const rows = useMemo<SupplierRow[]>(() => suppliers.map((supplier) => ({
    ...supplier,
    risk: risks.find((risk) => risk.supplier_id === supplier.supplier_id),
    disruptions: disruptions.filter((item) => item.supplier_id === supplier.supplier_id),
  })), [suppliers, risks, disruptions]);
  const filteredRows = rows.filter((row) => {
    const haystack = `${row.name || ""} ${row.supplier_id} ${row.country || ""}`.toLowerCase();
    return haystack.includes(query.toLowerCase()) && (level === "all" || levelFor(row.risk?.score ?? 0) === level) && (status === "all" || row.status === status);
  });
  const counts = rows.reduce<Record<Level, number>>((result, row) => { result[levelFor(row.risk?.score ?? 0)] += 1; return result; }, { low: 0, medium: 0, high: 0, critical: 0 });
  const scored = rows.filter((row) => row.risk);
  const average = scored.length ? Math.round(scored.reduce((sum, row) => sum + (row.risk?.score ?? 0), 0) / scored.length) : 0;
  const statuses = [...new Set(rows.map((row) => row.status).filter(Boolean))] as string[];
  const clearFilters = () => { setQuery(""); setLevel("all"); setStatus("all"); };

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Truck size={20} /></div><span>NEXUS</span></div>
      <nav><a className="active"><Gauge size={18} /> Overview</a><a><Database size={18} /> Suppliers <span className="nav-count">{rows.length}</span></a><a><ShieldAlert size={18} /> Disruptions <span className="nav-count">{disruptions.length}</span></a></nav>
      <div className="sidebar-footer"><div className="service-dot" /> Risk engine connected<div className="api-label">{API_URL}</div></div>
    </aside>
    <main className="content">
      <header className="topbar"><div><p className="eyebrow">Supply chain intelligence</p><h1>Supplier overview</h1><p className="subtitle">Monitor supplier health and emerging exposure across your network.</p></div><div className="topbar-actions"><button className="add-supplier" onClick={() => { setShowSupplierForm((shown) => !shown); setSupplierMessage(""); }}><Database size={16} /> {showSupplierForm ? "Close form" : "Add supplier"}</button><button className="refresh" onClick={() => void loadData()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} /> Refresh data</button></div></header>
      {error && <div className="error-banner"><AlertTriangle size={18} /><div><strong>Could not load live data</strong><span>{error}. Check that the risk engine is running at {API_URL}.</span></div><button onClick={() => void loadData()} aria-label="Retry"><RefreshCw size={16} /></button></div>}
      {showSupplierForm && <section className="panel supplier-form-panel"><div className="panel-heading"><div><h2>Add supplier</h2><p>Create a supplier record in the live risk engine.</p></div><Database className="accent-icon" /></div><form className="supplier-form" onSubmit={(event) => void addSupplier(event)}><label>Supplier ID<input required minLength={1} maxLength={128} value={supplierForm.supplier_id} onChange={(event) => setSupplierForm({ ...supplierForm, supplier_id: event.target.value })} placeholder="supplier-009" /></label><label>Supplier name<input value={supplierForm.name} onChange={(event) => setSupplierForm({ ...supplierForm, name: event.target.value })} placeholder="Example Manufacturing" /></label><label>Country<input value={supplierForm.country} onChange={(event) => setSupplierForm({ ...supplierForm, country: event.target.value })} placeholder="United States" /></label><label>Status<select value={supplierForm.status} onChange={(event) => setSupplierForm({ ...supplierForm, status: event.target.value })}><option value="active">Active</option><option value="inactive">Inactive</option><option value="pending">Pending</option></select></label><button className="submit-supplier" type="submit" disabled={savingSupplier}>{savingSupplier ? "Adding..." : "Add supplier"}</button></form>{supplierMessage && <p className={`supplier-message ${supplierMessage.startsWith("Could not") ? "error" : "success"}`} role="status">{supplierMessage}</p>}</section>}
      <section className="metrics">
        <Metric icon={<Database />} label="Total suppliers" value={loading ? "—" : rows.length.toString()} note={lastUpdated ? `Updated ${formatTime(lastUpdated.toISOString())}` : "Awaiting data"} />
        <Metric icon={<Gauge />} label="Average risk score" value={loading ? "—" : `${average}/100`} note={scored.length ? `${scored.length} assessed suppliers` : "No assessments yet"} />
        <Metric icon={<AlertTriangle />} label="Active disruptions" value={loading ? "—" : disruptions.length.toString()} note={disruptions.length ? "Requires attention" : "No disruptions reported"} trend={disruptions.length > 0 ? "warning" : "good"} />
        <Metric icon={<ShieldAlert />} label="Critical exposure" value={loading ? "—" : counts.critical.toString()} note={counts.critical ? "Immediate review recommended" : "No critical suppliers"} trend={counts.critical ? "danger" : "good"} />
      </section>
      <section className="risk-grid"><div className="panel risk-panel"><div className="panel-heading"><div><h2>Risk distribution</h2><p>Current supplier assessments by severity</p></div><span className="live-tag"><span /> Live</span></div><div className="bars">{levels.map((item) => <button className={`bar-row ${level === item ? "selected" : ""}`} key={item} onClick={() => setLevel(level === item ? "all" : item)}><span className={`level-dot ${item}`} /><span className="bar-label">{item}</span><div className="bar-track"><div className={`bar-fill ${item}`} style={{ width: `${rows.length ? Math.max(2, counts[item] / rows.length * 100) : 0}%` }} /></div><strong>{loading ? "—" : counts[item]}</strong></button>)}</div></div><div className="panel exposure-panel"><div className="panel-heading"><div><h2>Network exposure</h2><p>Risk score across assessed suppliers</p></div><ArrowUpRight className="accent-icon" /></div><div className="score-ring" style={{ "--score": `${average * 3.6}deg` } as React.CSSProperties}><div><strong>{loading ? "—" : average}</strong><span>avg score</span></div></div><div className="legend"><span><i className="low" />Lower exposure</span><span><i className="critical" />Higher exposure</span></div></div></section>
      <section className="panel suppliers-panel"><div className="panel-heading table-heading"><div><h2>Suppliers</h2><p>{filteredRows.length} of {rows.length} suppliers shown</p></div><div className="filters"><div className="search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search suppliers" aria-label="Search suppliers" />{query && <button onClick={() => setQuery("")} aria-label="Clear search"><X size={14} /></button>}</div><label className="select-wrap"><Filter size={15} /><select value={level} onChange={(event) => setLevel(event.target.value as "all" | Level)}><option value="all">All risk levels</option>{levels.map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</option>)}</select><ChevronDown size={14} /></label><label className="select-wrap"><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All statuses</option>{statuses.map((item) => <option key={item} value={item}>{item}</option>)}</select><ChevronDown size={14} /></label>{(query || level !== "all" || status !== "all") && <button className="clear" onClick={clearFilters}>Clear</button>}</div></div><div className="table-wrap"><table><thead><tr><th>Supplier</th><th>Location</th><th>Status</th><th>Risk score</th><th>Level</th><th>Last assessed</th><th>Disruptions</th></tr></thead><tbody>{loading ? <tr><td colSpan={7}><div className="empty-state"><RefreshCw className="spin" size={20} /><span>Loading supplier intelligence…</span></div></td></tr> : filteredRows.map((row) => { const itemLevel = levelFor(row.risk?.score ?? 0); return <tr key={row.supplier_id}><td><div className="supplier-cell"><span className={`avatar ${itemLevel}`}>{initials(row.name || row.supplier_id)}</span><div><strong>{row.name || row.supplier_id}</strong><small>{row.supplier_id}</small></div></div></td><td><span className="location"><MapPin size={14} />{row.country || "—"}</span></td><td><span className={`status ${row.status === "active" ? "active" : ""}`}>{row.status || "unknown"}</span></td><td><strong className="score">{row.risk ? Math.round(row.risk.score) : "—"}</strong><span className="score-max">/100</span></td><td><span className={`pill ${itemLevel}`}><span />{itemLevel}</span></td><td><span className="assessed"><Clock3 size={14} />{formatTime(row.risk?.calculated_at)}</span></td><td>{row.disruptions.length ? <span className="disruption-count"><AlertTriangle size={14} />{row.disruptions.length}</span> : <span className="muted">None</span>}</td></tr>; })}</tbody></table>{!loading && !filteredRows.length && <div className="empty-state"><Search size={22} /><strong>{rows.length ? "No suppliers match these filters" : "No supplier data yet"}</strong><span>{rows.length ? "Try broadening your search or clearing the filters." : "Supplier records will appear here when the risk engine receives data."}</span>{rows.length > 0 && <button className="clear" onClick={clearFilters}>Clear filters</button>}</div>}</div></section>
      {disruptions.length > 0 && <section className="panel disruptions-panel"><div className="panel-heading"><div><h2>Recent disruptions</h2><p>Events reported by the risk service</p></div><ArrowDownRight className="danger-icon" /></div><div className="disruption-list">{disruptions.slice(0, 4).map((item, index) => <div className="disruption" key={`${item.supplier_id}-${item.event_id || index}`}><span className={`severity ${item.severity}`} /><div><strong>{item.disruption_type}</strong><p>{item.message}</p><small>{item.supplier_id} · {item.starts_at ? formatTime(item.starts_at) : "Start time unavailable"}</small></div><span className={`pill ${item.severity}`}>{item.severity}</span></div>)}</div></section>}
    </main>
  </div>;
}

function Metric({ icon, label, value, note, trend }: { icon: React.ReactNode; label: string; value: string; note: string; trend?: "good" | "warning" | "danger" }) {
  return <article className="metric"><div className="metric-top"><span className="metric-icon">{icon}</span>{trend === "good" ? <ArrowDownRight className="trend good" /> : trend ? <ArrowUpRight className="trend danger" /> : null}</div><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><span className={`metric-note ${trend || ""}`}>{note}</span></article>;
}
