import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  CloudCog,
  Command,
  Factory,
  FileSearch,
  GitBranch,
  Globe2,
  Layers3,
  Menu,
  MoreHorizontal,
  PackageSearch,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Ship,
  Sparkles,
  Truck,
  X,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import ShipmentMap from "./ShipmentMap";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  type Dashboard,
  type EventRecord,
  type GraphData,
  type Incident,
  type Page,
  type ModelEvaluation,
  type Shipment,
  type ShipmentDetail,
  type ShipmentPrediction,
  type Supplier,
  saveToken,
} from "./api";

const ForceGraph2D = lazy(() => import("react-force-graph-2d"));

type View =
  | "overview"
  | "suppliers"
  | "shipments"
  | "graph"
  | "risk"
  | "events"
  | "incidents"
  | "ai";

const navGroups = [
  {
    label: "CONTROL TOWER",
    links: [
      { id: "overview" as const, name: "Executive overview", icon: Layers3 },
      { id: "suppliers" as const, name: "Supplier intelligence", icon: Factory },
      { id: "shipments" as const, name: "Shipment monitoring", icon: Truck },
    ],
  },
  {
    label: "INTELLIGENCE",
    links: [
      { id: "graph" as const, name: "Knowledge graph", icon: GitBranch },
      { id: "risk" as const, name: "Risk & explainability", icon: Shield },
      { id: "events" as const, name: "Event monitor", icon: Activity },
    ],
  },
  {
    label: "RESPONSE",
    links: [
      { id: "incidents" as const, name: "Incident management", icon: AlertTriangle },
      { id: "ai" as const, name: "AI recommendations", icon: Sparkles },
    ],
  },
];

const titles: Record<View, string> = {
  overview: "Executive overview",
  suppliers: "Supplier intelligence",
  shipments: "Shipment monitoring",
  graph: "Knowledge graph",
  risk: "Risk & explainability",
  events: "Event monitor",
  incidents: "Incident management",
  ai: "AI recommendations",
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function shortId(value: string): string {
  return value.length > 15 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [suppliers, setSuppliers] = useState<Page<Supplier> | null>(null);
  const [events, setEvents] = useState<Page<EventRecord> | null>(null);
  const [incidents, setIncidents] = useState<Page<Incident> | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [selectedSupplier, setSelectedSupplier] = useState<string | null>(null);
  const [supplierDetail, setSupplierDetail] = useState<Record<string, unknown> | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphData["nodes"][number] | null>(null);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [tokenDraft, setTokenDraft] = useState("");
  const [showTokenDialog, setShowTokenDialog] = useState(false);
  const [incidentDialog, setIncidentDialog] = useState(false);
  const [editingIncident, setEditingIncident] = useState<Incident | null>(null);
  const [incidentEditForm, setIncidentEditForm] = useState({
    owner: "",
    investigation_notes: "",
  });
  const [pendingIncidentEvent, setPendingIncidentEvent] = useState<EventRecord | undefined>();
  const [incidentForm, setIncidentForm] = useState({
    title: "",
    description: "",
    severity: "medium",
    owner: "",
    investigation_notes: "",
  });
  const [recommendation, setRecommendation] = useState<Record<string, unknown> | null>(null);
  const [recommendationSupplier, setRecommendationSupplier] = useState("");
  const [recommendationQuestion, setRecommendationQuestion] = useState("");
  const [eventPage, setEventPage] = useState(1);
  const [incidentPage, setIncidentPage] = useState(1);
  const [supplierPage, setSupplierPage] = useState(1);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
        const data = await api<Dashboard>("/api/v1/dashboard");
      setDashboard(data);
      setUpdatedAt(new Date());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load API data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (view === "suppliers" || view === "ai") {
      const query = new URLSearchParams({ page: String(supplierPage), page_size: "25" });
      if (search) query.set("search", search);
      void api<Page<Supplier>>(`/api/v1/suppliers?${query}`)
        .then(setSuppliers)
        .catch((cause) => setError(cause.message));
    }
    if (view === "events") {
      const query = new URLSearchParams({ page: String(eventPage), page_size: "25" });
      if (sourceFilter) query.set("source_system", sourceFilter);
      if (search) query.set("supplier_id", search);
      void api<Page<EventRecord>>(`/api/v1/events?${query}`)
        .then(setEvents)
        .catch((cause) => setError(cause.message));
    }
    if (view === "incidents") {
      void api<Page<Incident>>(`/api/v1/incidents?page=${incidentPage}&page_size=25`)
        .then(setIncidents)
        .catch((cause) => setError(cause.message));
    }
    if (view === "graph") {
      void api<GraphData>("/api/v1/graph?limit=300")
        .then(setGraph)
        .catch((cause) => setError(cause.message));
    }
  }, [view, search, sourceFilter, updatedAt, eventPage, incidentPage, supplierPage]);

  useEffect(() => {
    if (!selectedSupplier) {
      setSupplierDetail(null);
      return;
    }
    void api<Record<string, unknown>>(
      `/api/v1/suppliers/${encodeURIComponent(selectedSupplier)}`,
    )
      .then(setSupplierDetail)
      .catch((cause) => setError(cause.message));
  }, [selectedSupplier]);

  const eventData = useMemo(
    () => dashboard?.event_activity ?? [],
    [dashboard],
  );

  async function createIncident(event?: EventRecord) {
    try {
      const response = await api<Incident>("/api/v1/incidents", {
        method: "POST",
        body: JSON.stringify({
          ...incidentForm,
          owner: incidentForm.owner.trim() || null,
          supplier_external_id: event?.supplier_external_id ?? selectedSupplier,
          event_id: event?.event_id,
        }),
      });
      setIncidents((current) =>
        current
          ? { ...current, items: [response, ...current.items], total: current.total + 1 }
          : current,
      );
      setDashboard((current) =>
        current
          ? {
              ...current,
              recent_incidents: [response, ...current.recent_incidents].slice(0, 5),
            }
          : current,
      );
      setIncidentDialog(false);
      setPendingIncidentEvent(undefined);
      setIncidentForm({
        title: "",
        description: "",
        severity: "medium",
        owner: "",
        investigation_notes: "",
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Incident could not be saved.");
    }
  }

  async function updateIncident(id: string, status: string) {
    try {
      const response = await api<Incident>(`/api/v1/incidents/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setIncidents((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => (item.id === id ? response : item)),
            }
          : current,
      );
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Incident update failed.");
    }
  }

  async function saveIncidentDetails() {
    if (!editingIncident) return;
    try {
      const response = await api<Incident>(`/api/v1/incidents/${editingIncident.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          owner: incidentEditForm.owner.trim() || null,
          investigation_notes: incidentEditForm.investigation_notes,
        }),
      });
      setIncidents((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === response.id ? response : item,
              ),
            }
          : current,
      );
      setDashboard((current) =>
        current
          ? {
              ...current,
              recent_incidents: current.recent_incidents.map((item) =>
                item.id === response.id ? response : item,
              ),
            }
          : current,
      );
      setEditingIncident(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Incident details could not be saved.");
    }
  }

  async function generateRecommendation() {
    setLoading(true);
    setRecommendation(null);
    try {
      const response = await api<Record<string, unknown>>("/api/v1/recommendations", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: recommendationSupplier || undefined,
          question:
            recommendationQuestion ||
            "Summarize current operational concerns and suggest investigation steps.",
        }),
      });
      setRecommendation(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Recommendation failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Globe2 size={21} /></div>
          <div><strong>nexus</strong><span>SUPPLY CHAIN INTELLIGENCE</span></div>
          <button className="icon-button mobile-menu" aria-label="Toggle navigation" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((open) => !open)}><Menu size={18} /></button>
        </div>
        <div className="workspace-switch">
          <div className="workspace-icon"><Command size={17} /></div>
          <div><strong>Global Operations</strong><span>Control tower</span></div>
          <ChevronDown size={15} />
        </div>
        <nav aria-label="Main navigation" className={mobileNavOpen ? "mobile-nav-open" : ""}>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.links.map(({ id, name, icon: Icon }) => (
                <button
                  className={`nav-link ${view === id ? "active" : ""}`}
                  key={id}
                  onClick={() => { setView(id); setMobileNavOpen(false); }}
                  aria-current={view === id ? "page" : undefined}
                >
                  <Icon size={17} strokeWidth={1.8} /><span>{name}</span>
                  {id === "incidents" && (dashboard?.recent_incidents.length ?? 0) > 0 && (
                    <span className="nav-count">{dashboard?.recent_incidents.length}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="region-card">
            <div className="region-header"><span className="online-dot" /> SYSTEM STATUS</div>
            <div className="region-row"><span>Pipeline</span><strong>{dashboard?.service_readiness.postgres ? "Operational" : "Checking"}</strong></div>
            <div className="region-row"><span>Knowledge graph</span><strong>{dashboard?.service_readiness.neo4j ? "Connected" : "Unavailable"}</strong></div>
            <div className="region-row"><span>Data refresh</span><strong>15 sec</strong></div>
          </div>
          <button className="profile-row" onClick={() => setShowTokenDialog(true)}>
            <div className="avatar">OP</div><div><strong>Operations team</strong><span>Workspace access</span></div><MoreHorizontal size={17} />
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14} /><strong>{titles[view]}</strong></div>
          <div className="topbar-actions">
            {dashboard?.data_provenance.synthetic_data_present && (
              <span
                className="provenance-badge"
                title={`${dashboard.data_provenance.simulated_events} simulated events and ${dashboard.data_provenance.simulated_shipments} simulated shipments · ${dashboard.data_provenance.mode}`}
              >
                {dashboard.data_provenance.mode === "development-demo" ? "SYNTHETIC DEMO" : "SIMULATED DATA"}
              </span>
            )}
            <span className="live-status"><span className="online-dot" /> POLLING · 15S</span>
            <span className="updated-label"><Clock3 size={14} /> {updatedAt ? `Updated ${formatDate(updatedAt.toISOString())}` : "Connecting"}</span>
            <button className="icon-button" onClick={() => void refresh()} aria-label="Refresh data"><RefreshCw size={17} className={loading ? "spin" : ""} /></button>
            <button className="top-avatar" onClick={() => setShowTokenDialog(true)} aria-label="API access settings">OP</button>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">{view === "overview" ? `${new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" }).format(new Date()).toUpperCase()} · GLOBAL NETWORK` : "SUPPLYCHAINNEXUS · OPERATIONS"}</div>
              <h1>{titles[view]}</h1>
              <p>{viewDescriptions[view]}</p>
            </div>
            {view === "incidents" && <button className="button button-primary" onClick={() => setIncidentDialog(true)}><Plus size={16} /> New investigation</button>}
            {view === "events" && <button className="button button-quiet" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh stream</button>}
          </div>
          {error && <div className="error-banner" role="alert"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss"><X size={15} /></button></div>}
          {view === "overview" && dashboard && <Overview dashboard={dashboard} eventData={eventData} onNavigate={setView} onSupplier={setSelectedSupplier} />}
          {view === "suppliers" && <SupplierView data={suppliers} search={search} setSearch={(value) => { setSearch(value); setSupplierPage(1); }} page={supplierPage} setPage={setSupplierPage} onSelect={setSelectedSupplier} />}
          {view === "shipments" && <ShipmentView demoMode={dashboard?.data_provenance.mode === "development-demo"} />}
          {view === "graph" && <GraphView data={graph} selectedNode={selectedNode} onSelect={setSelectedNode} />}
          {view === "risk" && <RiskView readiness={dashboard?.model_readiness ?? {}} onSupplier={() => setView("suppliers")} />}
          {view === "events" && <EventsView data={events} page={eventPage} setPage={setEventPage} search={search} setSearch={(value) => { setSearch(value); setEventPage(1); }} source={sourceFilter} setSource={(value) => { setSourceFilter(value); setEventPage(1); }} onInvestigate={(event) => { setIncidentForm({ title: `Investigate ${event.event_type}`, description: `Review event ${event.event_id} and its observed payload.`, severity: "medium", owner: "", investigation_notes: "" }); setPendingIncidentEvent(event); setIncidentDialog(true); }} />}
          {view === "incidents" && <IncidentsView data={incidents} page={incidentPage} setPage={setIncidentPage} onStatus={updateIncident} onCreate={() => setIncidentDialog(true)} onEdit={(incident) => { setEditingIncident(incident); setIncidentEditForm({ owner: incident.owner ?? "", investigation_notes: incident.investigation_notes }); }} />}
          {view === "ai" && <RecommendationView suppliers={suppliers} selected={recommendationSupplier} setSelected={setRecommendationSupplier} question={recommendationQuestion} setQuestion={setRecommendationQuestion} onGenerate={() => void generateRecommendation()} result={recommendation} loading={loading} />}
        </div>
      </main>

      {supplierDetail && <SupplierDrawer detail={supplierDetail} onClose={() => { setSupplierDetail(null); setSelectedSupplier(null); }} onInvestigate={() => { setIncidentForm({ title: `Supplier review: ${selectedSupplier}`, description: "Investigate the latest supplier telemetry and operational signals.", severity: "medium", owner: "", investigation_notes: "" }); setIncidentDialog(true); }} />}
      {incidentDialog && <IncidentModal form={incidentForm} setForm={setIncidentForm} onClose={() => { setIncidentDialog(false); setPendingIncidentEvent(undefined); }} onSubmit={() => void createIncident(pendingIncidentEvent)} />}
      {editingIncident && <IncidentUpdateModal form={incidentEditForm} setForm={setIncidentEditForm} onClose={() => setEditingIncident(null)} onSubmit={() => void saveIncidentDetails()} />}
      {showTokenDialog && <TokenModal value={tokenDraft} setValue={setTokenDraft} onClose={() => setShowTokenDialog(false)} onSave={() => { saveToken(tokenDraft.trim()); setShowTokenDialog(false); setTokenDraft(""); void refresh(); }} />}
    </div>
  );
}

const viewDescriptions: Record<View, string> = {
  overview: "Persisted supplier health, network activity, and operational response.",
  suppliers: "Understand supplier activity and evidence-backed operational signals.",
  shipments: "Shipment records and delay estimates appear when verified data is available.",
  graph: "Explore entities and relationships recorded by the event projection.",
  risk: "Model readiness, observed indicators, and transparent heuristic assessments.",
  events: "Inspect validated events flowing through the supply-chain pipeline.",
  incidents: "Track investigations recorded by your operations team.",
  ai: "Generate evidence-grounded suggestions from the data currently on record.",
};

function Overview({ dashboard, eventData, onNavigate, onSupplier }: { dashboard: Dashboard; eventData: Dashboard["event_activity"]; onNavigate: (view: View) => void; onSupplier: (id: string) => void }) {
  const metrics = [
    { label: "Suppliers monitored", value: dashboard.kpis.suppliers.toLocaleString(), detail: "Persisted supplier records", icon: Factory, tone: "blue" },
    { label: "Events processed", value: dashboard.kpis.events.toLocaleString(), detail: "Validated event history", icon: Activity, tone: "mint" },
    { label: "Shipment records", value: dashboard.kpis.shipments.toLocaleString(), detail: "Persisted shipment records", icon: Ship, tone: "blue" },
    { label: "Sensor alerts · 24h", value: dashboard.kpis.sensor_alerts_24h.toLocaleString(), detail: "Above configured thresholds", icon: AlertTriangle, tone: "amber" },
    { label: "Open disruptions", value: dashboard.kpis.open_disruptions.toLocaleString(), detail: "Unresolved disruption records", icon: ShieldCheck, tone: "violet" },
  ];
  return <>
    <div className="metrics-grid">
      {metrics.map(({ label, value, detail, icon: Icon, tone }) => (
        <article className="metric-card" key={label}>
          <div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={17} /></span></div>
          <div className="metric-value">{value}</div><div className="metric-detail"><span className="neutral-trend"><Check size={13} /></span>{detail}</div>
        </article>
      ))}
    </div>
    <div className="dashboard-grid">
      <section className="panel activity-panel">
        <div className="panel-heading"><div><h2>Network activity</h2><p>Event volume · last 14 days · received time</p></div><button className="select-chip" onClick={() => onNavigate("events")}>Event monitor <ChevronDown size={14} /></button></div>
        {eventData.length ? <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={eventData} margin={{ top: 14, right: 9, bottom: 2, left: -19 }}>
              <defs><linearGradient id="eventFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#57d3c3" stopOpacity={0.25} /><stop offset="100%" stopColor="#57d3c3" stopOpacity={0.01} /></linearGradient></defs>
              <CartesianGrid stroke="#243147" vertical={false} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} tickFormatter={(value: string) => new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#131d2c", border: "1px solid #2a3850", borderRadius: 10, color: "#e8eef7" }} labelFormatter={(value) => formatDate(String(value))} />
              <Area type="monotone" dataKey="count" stroke="#57d3c3" strokeWidth={2.5} fill="url(#eventFill)" activeDot={{ r: 4, fill: "#57d3c3", stroke: "#101827", strokeWidth: 2 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div> : <EmptyState icon={<Activity size={20} />} title="No recent activity" text="Event activity will appear here once timestamps are available." />}
        <div className="chart-legend"><span><i className="legend-dot mint-bg" />Persisted events</span><span className="chart-note">Database received timestamps</span></div>
      </section>
      <section className="panel readiness-panel">
        <div className="panel-heading"><div><h2>Platform readiness</h2><p>Services and predictive capabilities</p></div><button className="icon-button" aria-label="Readiness information"><CircleHelp size={17} /></button></div>
        <div className="readiness-list">
          <ReadinessItem icon={<CloudCog size={17} />} label="PostgreSQL event store" ready={dashboard.service_readiness.postgres} detail={dashboard.service_readiness.postgres ? "Connected · data available" : "Connection unavailable"} />
          <ReadinessItem icon={<GitBranch size={17} />} label="Neo4j knowledge graph" ready={dashboard.service_readiness.neo4j} detail={dashboard.service_readiness.neo4j ? "Projection online" : "Graph service unavailable"} />
          {Object.values(dashboard.model_readiness).map((model) => <ReadinessItem key={model.model_name} icon={<Shield size={17} />} label={model.model_name.includes("shipment") ? "Shipment delay model" : "Supplier risk model"} ready={model.ready} detail={model.ready ? `${model.sample_count} training examples` : model.reason ?? "Training data unavailable"} />)}
        </div>
        <div className="risk-distribution">
          <div className="risk-distribution-head"><strong>Recorded risk assessments</strong><span>Latest per supplier</span></div>
          {dashboard.risk_distribution.length ? dashboard.risk_distribution.map((item) => <div className="distribution-row" key={item.category}><span className={`severity-dot ${item.category}`} /><span>{item.category}</span><strong>{item.count}</strong></div>) : <p>No persisted risk assessments are available.</p>}
        </div>
        <button className="text-link" onClick={() => onNavigate("risk")}>Explore risk readiness <ChevronRight size={15} /></button>
      </section>
    </div>
    <section className="panel recent-panel">
      <div className="panel-heading"><div><h2>Latest network events</h2><p>Most recently persisted event records</p></div><button className="text-link" onClick={() => onNavigate("events")}>View event monitor <ChevronRight size={15} /></button></div>
      <EventTable events={dashboard.recent_events} onSupplier={onSupplier} />
    </section>
    <div className="lower-grid">
      <section className="panel"><div className="panel-heading"><div><h2>Investigation queue</h2><p>Recent tracked incidents</p></div><button className="icon-button" onClick={() => onNavigate("incidents")} aria-label="Open incidents"><ChevronRight size={17} /></button></div>
        {dashboard.recent_incidents.length ? <div className="incident-compact">{dashboard.recent_incidents.map((item) => <div className="incident-compact-row" key={item.id}><span className={`severity-dot ${item.severity}`} /><div><strong>{item.title}</strong><small>{item.status} · {formatDate(item.updated_at)}</small></div><ChevronRight size={15} /></div>)}</div> : <EmptyState icon={<ShieldCheck size={19} />} title="No investigations recorded" text="Create an incident when your team begins an investigation." />}
      </section>
      <section className="panel ai-callout"><div className="ai-orb"><Sparkles size={20} /></div><div><div className="eyebrow">INTELLIGENCE ASSISTANT</div><h2>Turn signals into next steps</h2><p>Ask for suggestions grounded in persisted supplier or event data. Azure OpenAI availability is shown in the response.</p><button className="button button-primary" onClick={() => onNavigate("ai")}>Open recommendations <ArrowUpRight size={15} /></button></div></section>
    </div>
  </>;
}

function ReadinessItem({ icon, label, ready, detail }: { icon: React.ReactNode; label: string; ready: boolean; detail: string }) {
  return <div className="readiness-item"><span className={`readiness-icon ${ready ? "good" : ""}`}>{icon}</span><div className="readiness-copy"><strong>{label}</strong><span>{detail}</span></div><span className={`status-pill ${ready ? "ready" : "unavailable"}`}>{ready ? "READY" : "NOT READY"}</span></div>;
}

function EventTable({ events, onSupplier }: { events: EventRecord[]; onSupplier: (id: string) => void }) {
  return events.length ? <div className="table-scroll"><table><thead><tr><th>EVENT</th><th>SUPPLIER</th><th>SOURCE</th><th>OCCURRED</th><th>STATUS</th></tr></thead><tbody>
    {events.map((event) => <tr key={event.event_id}><td><div className="event-cell"><span className={`event-source-icon ${event.source_system === "supplier_erp" ? "erp" : ""}`}>{event.source_system === "supplier_erp" ? <Factory size={15} /> : <Activity size={15} />}</span><div><strong>{event.event_type}</strong><small>{shortId(event.event_id)}</small></div></div></td><td><button className="inline-link" onClick={() => onSupplier(event.supplier_external_id)}>{event.supplier_external_id}</button></td><td><span className="source-label">{event.source_system === "supplier_erp" ? "Supplier ERP" : "Sensor network"}</span></td><td className="time-cell">{formatDate(event.occurred_at)}</td><td><span className={`status-pill ${event.graph_projected === false ? "unavailable" : "ready"}`}>{event.graph_projected === false ? "PENDING" : "PERSISTED"}</span></td></tr>)}
  </tbody></table></div> : <EmptyState icon={<FileSearch size={20} />} title="No events found" text="Validated sensor and ERP records will appear here." />;
}

function SupplierView({ data, search, setSearch, page, setPage, onSelect }: { data: Page<Supplier> | null; search: string; setSearch: (value: string) => void; page: number; setPage: (page: number) => void; onSelect: (id: string) => void }) {
  return <section className="panel list-panel"><div className="list-toolbar"><div><h2>Supplier directory</h2><p>{data ? `${data.total} persisted supplier records` : "Loading supplier records"}</p></div><label className="search-field"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search suppliers…" /></label></div>
    {data?.items.length ? <div className="table-scroll"><table><thead><tr><th>SUPPLIER</th><th>STATUS ON RECORD</th><th>DOMAIN</th><th>LAST EVENT</th><th>UPDATED</th><th></th></tr></thead><tbody>
      {data.items.map((supplier) => <tr key={supplier.id} className="click-row" onClick={() => onSelect(supplier.external_id)}><td><div className="event-cell"><span className="supplier-avatar"><Factory size={16} /></span><div><strong>{supplier.name}</strong><small>{supplier.external_id}</small></div></div></td><td><span className="status-pill neutral">{String(supplier.metadata?.status ?? "NOT PROVIDED")}</span></td><td>{supplier.domain ?? "—"}</td><td>{formatDate(supplier.last_event_at)}</td><td>{formatDate(supplier.updated_at)}</td><td><ChevronRight size={16} /></td></tr>)}
    </tbody></table></div> : <EmptyState icon={<Factory size={20} />} title={data ? "No suppliers match" : "Loading supplier directory"} text={data ? "Try a different search term." : "Supplier records will load from PostgreSQL."} />}
    {data && data.total > data.page_size && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
  </section>;
}

function ShipmentView({ demoMode }: { demoMode: boolean }) {
  const [data, setData] = useState<Page<Shipment> | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ShipmentDetail | null>(null);
  const [prediction, setPrediction] = useState<ShipmentPrediction | null>(null);
  const [predictionError, setPredictionError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void api<Page<Shipment>>(`/api/v1/shipments?page=${page}&page_size=25`)
      .then((response) => {
        if (active) setData(response);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Shipments could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, refreshKey]);

  async function selectShipment(shipmentId: string) {
    setSelected(null);
    setPrediction(null);
    setPredictionError("");
    try {
      const detail = await api<ShipmentDetail>(`/api/v1/shipments/${encodeURIComponent(shipmentId)}`);
      setSelected(detail);
      try {
        const result = await api<ShipmentPrediction>(`/api/v1/shipments/${encodeURIComponent(shipmentId)}/prediction`);
        setPrediction(result);
      } catch (cause) {
        setPredictionError(cause instanceof Error ? cause.message : "Delay prediction is unavailable.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Shipment details could not be loaded.");
    }
  }

  return (
    <div className="shipment-view">
      {demoMode && <div className="info-note shipment-provenance"><CircleHelp size={15} /> DEMO WORKSPACE: all shipment records, outcomes, and map coordinates are synthetic and are not operational facts.</div>}
      {error && <div className="error-banner" role="alert"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setRefreshKey((key) => key + 1)} aria-label="Retry loading shipments"><RefreshCw size={15} /></button></div>}
      {loading && !data ? <section className="panel"><EmptyState icon={<Ship size={20} />} title="Loading shipment records" text="Reading persisted shipment data from the application API." /></section>
        : data?.items.length ? <>
          <section className="panel shipment-map-panel">
            <div className="panel-heading"><div><h2>Recorded shipment routes</h2><p>Only persisted origin and destination coordinates are shown</p></div><span className="status-pill ready">{data.total} SHIPMENTS</span></div>
            <ShipmentMap shipments={data.items} onSelect={(shipmentId) => void selectShipment(shipmentId)} />
            <p className="map-attribution-note">Map tiles © OpenStreetMap contributors. Connecting lines are visual aids, not navigable routes or live positions.</p>
          </section>
          <section className="panel list-panel">
            <div className="list-toolbar"><div><h2>Shipment records</h2><p>{data.total} persisted records · page {data.page}</p></div><span className="status-pill neutral">OUTCOMES ARE RECORDED FACTS</span></div>
            <div className="table-scroll"><table><thead><tr><th>SHIPMENT</th><th>SUPPLIER</th><th>ORIGIN → DESTINATION</th><th>PLANNED ARRIVAL</th><th>ACTUAL OUTCOME</th><th>DATA</th></tr></thead><tbody>
              {data.items.map((shipment) => <tr key={shipment.shipment_id} className="click-row" onClick={() => void selectShipment(shipment.shipment_id)}>
                <td><button className="inline-link" onClick={(event) => { event.stopPropagation(); void selectShipment(shipment.shipment_id); }}>{shipment.shipment_id} <ChevronRight size={14} /></button></td>
                <td>{shipment.supplier_external_id}</td>
                <td>{shipment.origin_name} → {shipment.destination_name}</td>
                <td>{formatDate(shipment.planned_arrival)}</td>
                <td>{shipment.actual_arrival ? `${formatDate(shipment.actual_arrival)} · ${shipment.actual_delay_hours == null ? "delay not recorded" : `${shipment.actual_delay_hours.toFixed(1)} h`}` : "Not yet observed"}</td>
                <td><span className={`status-pill ${shipment.simulated ? "neutral" : "ready"}`}>{shipment.simulated ? "SIMULATED" : "RECORDED"}</span></td>
              </tr>)}
            </tbody></table></div>
            {data.total > data.page_size && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
          </section>
        </> : <section className="panel"><EmptyState icon={<Ship size={20} />} title={data ? "No shipment records available" : "Shipment data unavailable"} text={data ? "No shipments with persisted route records are available in this workspace. Routes and delay outcomes are never fabricated." : "The API did not return shipment records."} /></section>}
      {selected && <div className="drawer-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
        <aside className="detail-drawer" role="dialog" aria-modal="true" aria-label={`Shipment ${selected.shipment.shipment_id}`}>
          <div className="drawer-header"><span className="eyebrow">SHIPMENT RECORD</span><button className="icon-button" onClick={() => setSelected(null)} aria-label="Close shipment details"><X size={18} /></button></div>
          <h2>{selected.shipment.shipment_id}</h2>
          <p>{selected.shipment.origin_name} → {selected.shipment.destination_name}</p>
          {selected.synthetic && <div className="info-note shipment-provenance"><CircleHelp size={15} /> Synthetic demo record. Do not interpret its coordinates or outcomes as real operations.</div>}
          <dl className="property-list">
            <div><dt>Supplier</dt><dd>{selected.shipment.supplier_external_id}</dd></div>
            <div><dt>Planned departure</dt><dd>{formatDate(selected.shipment.planned_departure)}</dd></div>
            <div><dt>Planned arrival</dt><dd>{formatDate(selected.shipment.planned_arrival)}</dd></div>
            <div><dt>Actual arrival</dt><dd>{formatDate(selected.shipment.actual_arrival)}</dd></div>
            <div><dt>Recorded delay</dt><dd>{selected.shipment.actual_delay_hours == null ? "Unknown" : `${selected.shipment.actual_delay_hours.toFixed(1)} hours`}</dd></div>
          </dl>
          <section className="detail-section"><h3>Delay model</h3>
            {prediction ? <>
              {prediction.prediction.development_model && <div className="info-note shipment-provenance"><CircleHelp size={15} /> Development model trained on synthetic data; this is not an operational forecast.</div>}
              {prediction.prediction_is_retrospective && <p className="muted-copy">Retrospective estimate: the shipment has a recorded outcome.</p>}
              <div className="score-card"><div><span className="eyebrow">PREDICTED DELAY</span><strong>{prediction.prediction.predicted_delay_hours.toFixed(1)} h</strong></div><span className="status-pill ready">{prediction.prediction.model_version}</span></div>
              {prediction.evaluation && <EvaluationSummary evaluation={prediction.evaluation.temporal_evaluation} />}
              <h4>Model explanation</h4>
              {prediction.explanation.contributions.map((item) => <div className="model-meta" key={item.feature_name}><span>{item.feature_name.replaceAll("_", " ")}{item.imputed ? " · imputed" : ""}</span><strong>{item.contribution.toFixed(3)}</strong></div>)}
            </> : <p className="unavailable-copy">{predictionError || "Checking model readiness…"}</p>}
          </section>
        </aside>
      </div>}
    </div>
  );
}

function GraphView({ data, selectedNode, onSelect }: { data: GraphData | null; selectedNode: GraphData["nodes"][number] | null; onSelect: (node: GraphData["nodes"][number] | null) => void }) {
  const graphData = useMemo(() => ({
    nodes: (data?.nodes ?? []).map((node) => ({ ...node })),
    links: (data?.edges ?? []).map((edge) => ({ source: edge.source, target: edge.target, label: edge.type })),
  }), [data]);
  return <Suspense fallback={<section className="panel graph-panel"><EmptyState icon={<GitBranch size={20} />} title="Loading graph explorer" text="Preparing the interactive visualization." /></section>}><section className="panel graph-panel"><div className="panel-heading"><div><h2>Recorded supply network</h2><p>Neo4j entities and persisted relationships only</p></div><span className={`status-pill ${data ? "ready" : "unavailable"}`}>{data ? `${data.nodes.length} NODES` : "CONNECTING"}</span></div>
    {data?.nodes.length ? <div className="graph-layout"><div className="graph-canvas"><ForceGraph2D graphData={graphData} backgroundColor="#0f1826" nodeRelSize={5} linkColor={() => "#33445b"} linkWidth={1.2} linkDirectionalArrowLength={3} linkDirectionalArrowRelPos={1} nodeColor={(node: object) => (node as { label?: string }).label === "Supplier" ? "#57d3c3" : "#83a9ff"} nodeLabel={(node: object) => { const item = node as GraphData["nodes"][number]; return `${item.label}: ${item.identifier}`; }} onNodeClick={(node: object) => onSelect(node as GraphData["nodes"][number])} nodeCanvasObject={(node: object, ctx: CanvasRenderingContext2D, scale: number) => { const item = node as GraphData["nodes"][number] & { x?: number; y?: number }; if (item.x == null || item.y == null) return; const radius = (item.label === "Supplier" ? 5 : 3.5) / Math.sqrt(scale); ctx.beginPath(); ctx.arc(item.x, item.y, radius, 0, 2 * Math.PI); ctx.fillStyle = item.label === "Supplier" ? "#57d3c3" : "#83a9ff"; ctx.fill(); if (selectedNode?.id === item.id && scale > 0.65) { ctx.font = `${12 / scale}px Inter, sans-serif`; ctx.fillStyle = "#e9f1fc"; ctx.fillText(item.identifier, item.x + radius + 2, item.y + 4); } }} /></div>
      <aside className="graph-inspector"><div className="inspector-title"><div><span className="eyebrow">GRAPH INSPECTOR</span><h3>{selectedNode?.label ?? "Select an entity"}</h3></div>{selectedNode && <button className="icon-button" onClick={() => onSelect(null)} aria-label="Close graph details"><X size={15} /></button>}</div>
        {selectedNode ? <><div className="selected-id">{selectedNode.identifier}</div><dl className="property-list">{Object.entries(selectedNode.properties).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value ?? "—")}</dd></div>)}</dl></> : <p className="muted-copy">Click a supplier or event node to inspect its recorded properties.</p>}
        <div className="graph-legend"><span><i className="legend-dot mint-bg" />Supplier</span><span><i className="legend-dot blue-bg" />Events and entities</span></div>
        {data && !data.dependency_relationships_available && <div className="info-note"><CircleHelp size={15} /> No supplier dependency relationships have been ingested.</div>}
      </aside></div> : <EmptyState icon={<GitBranch size={20} />} title={data ? "Graph has no entities yet" : "Connecting to Neo4j"} text={data ? "Entities appear after events have been projected." : "Graph records will load from the Neo4j projection."} />}
  </section></Suspense>;
}

function RiskView({ readiness, onSupplier }: { readiness: Dashboard["model_readiness"]; onSupplier: () => void }) {
  return <div className="risk-layout"><section className="panel risk-summary"><div className="eyebrow">RISK SIGNALS</div><h2>Transparent evidence, not false certainty.</h2><p>Model predictions are shown only when a trained artifact is available. Heuristic scores are kept separate from calibrated probability and unknown stays unknown.</p><button className="button button-quiet" onClick={onSupplier}>Open supplier intelligence <ArrowUpRight size={15} /></button></section>
    <div className="model-cards">{Object.entries(readiness).map(([key, model]) => <article className="panel model-card" key={key}><div className="model-card-head"><span className="metric-icon violet"><Shield size={17} /></span><span className={`status-pill ${model.ready ? "ready" : "unavailable"}`}>{model.ready ? "READY" : "NOT READY"}</span></div><h3>{key === "supplier_risk" ? "Supplier risk · Random Forest" : "Shipment delay · LightGBM"}</h3><p>{model.reason ?? "A versioned trained model artifact is available."}</p>    <div className="model-meta"><span>Training records</span><strong>{model.sample_count}</strong></div><div className="model-meta"><span>Model output</span><strong>{model.ready ? "Predictions enabled" : "Unavailable"}</strong></div>{model.development_model && <div className="info-note shipment-provenance"><CircleHelp size={15} /> Development-only model; metrics do not represent operational performance.</div>}{model.evaluation?.temporal_evaluation && <EvaluationSummary evaluation={model.evaluation.temporal_evaluation} />}</article>)}</div>
    <section className="panel heuristic-card"><div className="heuristic-head"><span className="metric-icon amber"><CircleHelp size={18} /></span><div><h3>Composite risk assessment</h3><p>Versioned weighted heuristic · not a calibrated disruption probability</p></div></div><div className="heuristic-body"><div className="unknown-score"><span>SUPPLIER-SPECIFIC</span><strong>On demand</strong><small>Open a supplier profile for its current feature snapshot, coverage, score, and weighted contributors.</small></div><div className="signal-list"><div><Check size={15} /><span>Available telemetry, disruption, supplier status, and model signals may contribute</span></div><div><Check size={15} /><span>Missing inputs remain unknown; low risk is shown only when supported</span></div><div><Check size={15} /><span>SHAP appears only when a trained model artifact is available</span></div></div></div></section>
  </div>;
}

function EvaluationSummary({ evaluation }: { evaluation: ModelEvaluation }) {
  const fields = [
    ["Evaluation samples", evaluation.evaluation_sample_count],
    ["Balanced accuracy", evaluation.balanced_accuracy],
    ["Macro F1", evaluation.macro_f1],
    ["Mean absolute error", evaluation.mean_absolute_error],
    ["Root mean squared error", evaluation.root_mean_squared_error],
    ["Baseline MAE", evaluation.median_baseline_mae],
  ].filter(([, value]) => value != null);
  if (!fields.length) return <p className="muted-copy">No holdout evaluation metrics were recorded.</p>;
  const baselineWarning = evaluation.mean_absolute_error != null
    && evaluation.median_baseline_mae != null
    && evaluation.mean_absolute_error > evaluation.median_baseline_mae;
  return <div className="evaluation-summary"><h4>Temporal holdout evaluation</h4>{baselineWarning && <p className="unavailable-copy">This model did not outperform the median-delay baseline on this holdout.</p>}{fields.map(([label, value]) => <div className="model-meta" key={String(label)}><span>{label}</span><strong>{typeof value === "number" ? value.toFixed(3) : String(value)}</strong></div>)}</div>;
}

function EventsView({ data, page, setPage, search, setSearch, source, setSource, onInvestigate }: { data: Page<EventRecord> | null; page: number; setPage: (page: number) => void; search: string; setSearch: (value: string) => void; source: string; setSource: (value: string) => void; onInvestigate: (event: EventRecord) => void }) {
  return <section className="panel list-panel"><div className="list-toolbar"><div><h2>Validated event stream</h2><p>{data ? `${data.total} matching persisted events` : "Loading event history"}</p></div><div className="toolbar-controls"><label className="search-field"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter supplier ID…" /></label><select className="filter-select" value={source} onChange={(event) => setSource(event.target.value)} aria-label="Filter source"><option value="">All sources</option><option value="sensor_simulator">Sensor simulator</option><option value="supplier_erp">Supplier ERP</option></select></div></div>
    {data?.items.length ? <div className="table-scroll"><table><thead><tr><th>EVENT TYPE</th><th>SUPPLIER</th><th>SOURCE</th><th>OCCURRED AT</th><th>PROCESSING</th><th></th></tr></thead><tbody>{data.items.map((event) => <tr key={event.event_id}><td><div className="event-cell"><span className={`event-source-icon ${event.source_system === "supplier_erp" ? "erp" : ""}`}>{event.source_system === "supplier_erp" ? <Factory size={15} /> : <Activity size={15} />}</span><div><strong>{event.event_type}</strong><small>{shortId(event.event_id)}</small></div></div></td><td>{event.supplier_external_id}</td><td>{event.source_system === "supplier_erp" ? "Supplier ERP" : "Sensor simulator"}</td><td>{formatDate(event.occurred_at)}</td><td><span className={`status-pill ${event.graph_projected ? "ready" : "neutral"}`}>{event.graph_projected ? "PERSISTED · GRAPHED" : "PERSISTED"}</span></td><td><button className="icon-button" onClick={() => onInvestigate(event)} aria-label={`Create investigation for ${event.event_id}`}><Plus size={16} /></button></td></tr>)}</tbody></table></div> : <EmptyState icon={<PackageSearch size={20} />} title={data ? "No events match these filters" : "Loading event history"} text={data ? "Change the supplier or source filter." : "Recent persisted events will appear here."} />}
    {data && data.total > data.page_size && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
  </section>;
}

function IncidentsView({ data, page, setPage, onStatus, onCreate, onEdit }: { data: Page<Incident> | null; page: number; setPage: (page: number) => void; onStatus: (id: string, status: string) => void; onCreate: () => void; onEdit: (incident: Incident) => void }) {
  return <section className="panel list-panel"><div className="list-toolbar"><div><h2>Investigation register</h2><p>{data ? `${data.total} explicitly recorded investigations` : "Loading incident records"}</p></div><button className="button button-primary" onClick={onCreate}><Plus size={16} /> Create investigation</button></div>
    {data?.items.length ? <div className="table-scroll"><table><thead><tr><th>INVESTIGATION</th><th>SEVERITY</th><th>STATUS</th><th>OWNER</th><th>LINKED EVIDENCE</th><th>UPDATED</th><th></th></tr></thead><tbody>{data.items.map((incident) => <tr key={incident.id}><td><div><strong>{incident.title}</strong><small className="table-subtitle">{incident.description}</small><small className="table-subtitle">{incident.investigation_notes || "No investigation notes"}</small>{incident.simulated && <small className="table-subtitle">Synthetic demo investigation</small>}</div></td><td><span className={`severity-tag ${incident.severity}`}>{incident.severity}</span></td><td><span className="status-pill neutral">{incident.status}</span></td><td>{incident.owner || "Unassigned"}</td><td>{incident.event_id ? `Event ${shortId(incident.event_id)}` : incident.supplier_external_id ?? "Manual"}</td><td>{formatDate(incident.updated_at)}</td><td><div className="incident-actions"><button className="icon-button" onClick={() => onEdit(incident)} aria-label={`Edit owner and notes for ${incident.title}`}><FileSearch size={15} /></button><select className="row-action" value={incident.status} onChange={(event) => onStatus(incident.id, event.target.value)} aria-label={`Update status for ${incident.title}`}><option value={incident.status}>{incident.status}</option>{(incidentTransitions[incident.status] ?? [incident.status]).filter((status) => status !== incident.status).map((status) => <option value={status} key={status}>{status}</option>)}</select></div></td></tr>)}</tbody></table></div> : <EmptyState icon={<ShieldCheck size={20} />} title={data ? "No investigations on record" : "Loading investigations"} text={data ? "Incident records are created by your team; events do not automatically become incidents." : "Incident history will appear here."} />}
    {data && data.total > data.page_size && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
  </section>;
}

const incidentTransitions: Record<string, string[]> = {
  open: ["open", "investigating", "resolved"],
  investigating: ["investigating", "mitigating", "resolved"],
  mitigating: ["mitigating", "investigating", "resolved"],
  resolved: ["resolved"],
};

function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return <div className="pagination-bar"><span>{first}–{last} of {total}</span><div><button className="button button-quiet" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button><button className="button button-quiet" disabled={last >= total} onClick={() => onPage(page + 1)}>Next</button></div></div>;
}

function RecommendationView({ suppliers, selected, setSelected, question, setQuestion, onGenerate, result, loading }: { suppliers: Page<Supplier> | null; selected: string; setSelected: (value: string) => void; question: string; setQuestion: (value: string) => void; onGenerate: () => void; result: Record<string, unknown> | null; loading: boolean }) {
  return <div className="recommendation-layout"><section className="panel recommendation-form"><div className="ai-orb"><Bot size={21} /></div><div className="eyebrow">EVIDENCE-GROUNDED ASSISTANT</div><h2>What would you like to investigate?</h2><p>Suggestions are generated from the persisted records you select. Azure OpenAI credentials are only used by the backend.</p><label className="field-label">Supplier evidence<select value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Choose supplier…</option>{suppliers?.items.map((supplier) => <option value={supplier.external_id} key={supplier.id}>{supplier.name} · {supplier.external_id}</option>)}</select></label><label className="field-label">Question<textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask for observed concerns and investigation steps…" rows={4} /></label><button className="button button-primary full-button" disabled={!selected || loading} onClick={onGenerate}><Sparkles size={16} /> {loading ? "Reviewing evidence…" : "Generate recommendation"}</button><div className="privacy-note"><ShieldCheck size={15} /> Data is minimized and secrets stay on the API service.</div></section>
    <section className="panel recommendation-result"><div className="panel-heading"><div><h2>Recommendation output</h2><p>Suggestions are not actions or verified outcomes</p></div><span className={`status-pill ${result?.generated ? "ready" : "neutral"}`}>{result?.generated ? "MODEL GENERATED" : "AWAITING REQUEST"}</span></div>
      {result ? <><div className="result-state">{result.generated ? <Sparkles size={18} /> : <CircleHelp size={18} />}<strong>{result.generated ? "Suggestion generated" : "Recommendation unavailable"}</strong></div>{typeof result.recommendation === "string" && <p className="recommendation-copy">{result.recommendation}</p>}{typeof result.reason === "string" && <p className="unavailable-copy">{result.reason}</p>}<EvidenceList title="Supporting evidence" items={result.evidence as string[] | undefined} /><EvidenceList title="Uncertainties" items={result.uncertainty as string[] | undefined} /></> : <EmptyState icon={<Sparkles size={20} />} title="No recommendation generated" text="Choose a supplier and submit a question to begin." />}
    </section></div>;
}

function EvidenceList({ title, items }: { title: string; items?: string[] }) {
  return <div className="evidence-list"><h3>{title}</h3>{items?.length ? items.map((item, index) => <div className="evidence-item" key={`${title}-${index}`}><Check size={14} /><span>{item}</span></div>) : <p>No additional detail reported.</p>}</div>;
}

function SupplierDrawer({ detail, onClose, onInvestigate }: { detail: Record<string, unknown>; onClose: () => void; onInvestigate: () => void }) {
  const [history, setHistory] = useState<EventRecord[]>([]);
  const supplier = detail.supplier as Supplier;
  const features = detail.features as Record<string, unknown>;
  const assessment = detail.assessment as Record<string, unknown>;
  const assessmentComponents = assessment.components as Record<string, number | null> | undefined;
  const weightedContributions = assessment.weighted_contributions as Record<string, number | null> | undefined;
  const prediction = detail.prediction as {
    category?: string;
    model_version?: string;
    development_model?: boolean;
  } | null;
  const explanation = detail.explanation as { contributions?: { feature_name: string; value: number | null; contribution: number; imputed?: boolean }[] } | null;
  useEffect(() => {
    void api<Page<EventRecord>>(
      `/api/v1/suppliers/${encodeURIComponent(supplier.external_id)}/events?page=1&page_size=8`,
    )
      .then((page) => setHistory(page.items))
      .catch(() => setHistory([]));
  }, [supplier.external_id]);
  return <div className="drawer-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="detail-drawer" role="dialog" aria-modal="true" aria-label={`Supplier ${supplier.name}`}>
    <div className="drawer-header"><span className="eyebrow">SUPPLIER PROFILE</span><button className="icon-button" onClick={onClose} aria-label="Close supplier profile"><X size={18} /></button></div>
    <div className="supplier-hero"><span className="supplier-avatar large"><Factory size={20} /></span><div><h2>{supplier.name}</h2><p>{supplier.external_id}</p>{supplier.identity_source === "event_only" && <small className="identity-note">Identity not provided · events observed</small>}</div></div>
    <div className="drawer-actions"><button className="button button-primary" onClick={onInvestigate}><Plus size={15} /> Start investigation</button><span className="status-pill neutral">{String(supplier.metadata?.status ?? "STATUS UNKNOWN")}</span></div>
    <div className="detail-section"><div className="section-title"><h3>Risk assessment</h3><span className={`severity-tag ${String(assessment.severity)}`}>{String(assessment.severity)}</span></div><div className="score-card"><div><span className="eyebrow">COMPOSITE HEURISTIC · NOT A PROBABILITY</span><strong>{assessment.score == null ? "Unknown" : `${Number(assessment.score).toFixed(1)} / 100`}</strong></div><span className="coverage-value">{Math.round(Number(assessment.coverage ?? 0) * 100)}%<small>coverage</small></span></div><div className="assessment-components"><h4>Current components · normalized signals</h4>{Object.entries(assessmentComponents ?? {}).map(([name, value]) => <div className="model-meta" key={name}><span>{name.replaceAll("_", " ")}</span><strong>{value == null ? "Unknown" : `${(value * 100).toFixed(1)}% · +${(weightedContributions?.[name] ?? 0).toFixed(2)} pts`}</strong></div>)}</div>{prediction ? <><div className="prediction-note"><ShieldCheck size={16} /> Model prediction · {prediction.category ?? "Unknown"} · {prediction.model_version ?? "unversioned"}</div>{prediction.development_model && <div className="info-note shipment-provenance"><CircleHelp size={15} /> Development-only model trained on synthetic data; not an operational risk classification.</div>}</> : <div className="unavailable-note"><CircleHelp size={16} /> Trained supplier-risk model not available. Risk labels are required.</div>}</div>
    <div className="detail-section"><h3>Current feature snapshot</h3><div className="feature-grid">{Object.entries(features ?? {}).filter(([key]) => !["supplier_id", "as_of"].includes(key)).map(([key, value]) => <div className="feature-tile" key={key}><small>{key.replaceAll("_", " ")}</small><strong>{value == null ? "Unknown" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value)}</strong></div>)}</div></div>
    <div className="detail-section"><h3>Model explainability</h3>{explanation?.contributions?.length ? <div className="shap-list">{explanation.contributions.slice().sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 8).map((item) => <div className="shap-row" key={item.feature_name}><span>{item.feature_name.replaceAll("_", " ")}</span><strong className={item.contribution > 0 ? "risk-up" : "risk-down"}>{item.contribution > 0 ? "+" : ""}{item.contribution.toFixed(4)}</strong><small>{item.imputed ? "missing value imputed" : item.value ?? "—"}</small></div>)}</div> : <div className="unavailable-note"><FileSearch size={16} /> SHAP explanations appear only for an available trained model.</div>}</div>
    <div className="detail-section"><h3>Latest event facts</h3><div className="feature-grid"><div className="feature-tile"><small>Temperature mean · 24h</small><strong>{String(features.temperature_mean_c ?? "No telemetry")}{features.temperature_mean_c != null ? " °C" : ""}</strong></div><div className="feature-tile"><small>Telemetry events · 24h</small><strong>{String(features.telemetry_count_24h ?? 0)}</strong></div><div className="feature-tile"><small>Disruptions · 30d</small><strong>{String(features.disruptions_30d ?? 0)}</strong></div><div className="feature-tile"><small>Active disruptions</small><strong>{String(features.active_disruptions ?? 0)}</strong></div></div></div>
    <div className="detail-section"><h3>Recent event history</h3>{history.length ? <div className="supplier-history">{history.map((event) => <div className="supplier-history-row" key={event.event_id}><span className="event-source-icon"><Activity size={14} /></span><div><strong>{event.event_type}</strong><small>{event.source_system} · {formatDate(event.occurred_at)}</small></div></div>)}</div> : <p className="muted-copy">No persisted events are available for this supplier.</p>}</div>
  </aside></div>;
}

function IncidentModal({ form, setForm, onClose, onSubmit }: { form: { title: string; description: string; severity: string; owner: string; investigation_notes: string }; setForm: (value: { title: string; description: string; severity: string; owner: string; investigation_notes: string }) => void; onClose: () => void; onSubmit: () => void }) {
  return <div className="modal-backdrop" role="presentation"><form className="modal-card" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}><div className="modal-heading"><div><span className="eyebrow">OPERATIONS RESPONSE</span><h2>Create investigation</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button></div><p>Incident records are explicit team investigations, not automatically inferred events.</p><label className="field-label">Title<input required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label className="field-label">Description<textarea required maxLength={10000} rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><label className="field-label">Investigation notes<textarea maxLength={20000} rows={3} value={form.investigation_notes} onChange={(event) => setForm({ ...form, investigation_notes: event.target.value })} placeholder="Optional initial findings" /></label><div className="form-two"><label className="field-label">Severity<select value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label><label className="field-label">Owner<input maxLength={200} value={form.owner} onChange={(event) => setForm({ ...form, owner: event.target.value })} placeholder="Optional" /></label></div><div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary" type="submit">Save investigation</button></div></form></div>;
}

function IncidentUpdateModal({ form, setForm, onClose, onSubmit }: { form: { owner: string; investigation_notes: string }; setForm: (value: { owner: string; investigation_notes: string }) => void; onClose: () => void; onSubmit: () => void }) {
  return <div className="modal-backdrop" role="presentation"><form className="modal-card" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}><div className="modal-heading"><div><span className="eyebrow">INVESTIGATION TRACKING</span><h2>Update assignment and notes</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button></div><label className="field-label">Owner<input maxLength={200} value={form.owner} onChange={(event) => setForm({ ...form, owner: event.target.value })} placeholder="Unassigned" /></label><label className="field-label">Investigation notes<textarea maxLength={20000} rows={6} value={form.investigation_notes} onChange={(event) => setForm({ ...form, investigation_notes: event.target.value })} /></label><div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary" type="submit">Save updates</button></div></form></div>;
}

function TokenModal({ value, setValue, onClose, onSave }: { value: string; setValue: (value: string) => void; onClose: () => void; onSave: () => void }) {
  return <div className="modal-backdrop" role="presentation"><form className="modal-card token-card" onSubmit={(event) => { event.preventDefault(); onSave(); }}><div className="modal-heading"><div><span className="eyebrow">API ACCESS</span><h2>Connection settings</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button></div><p>Use a configured bearer token if API authentication is enabled. It is kept in this browser’s local storage and never bundled into the frontend.</p><label className="field-label">Bearer token<input type="password" autoComplete="off" value={value} onChange={(event) => setValue(event.target.value)} placeholder="Leave blank for local unauthenticated development" /></label><div className="modal-actions"><button type="button" className="button button-quiet" onClick={() => { saveToken(""); onClose(); }}>Clear token</button><button className="button button-primary" type="submit">Save settings</button></div></form></div>;
}

function EmptyState({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="empty-state"><span className="empty-icon">{icon}</span><strong>{title}</strong><p>{text}</p></div>;
}

export default App;
