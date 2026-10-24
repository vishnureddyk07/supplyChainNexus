export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type EventRecord = {
  event_id: string;
  event_type: string;
  source_system: string;
  supplier_external_id: string;
  occurred_at: string;
  received_at: string;
  graph_projected?: boolean;
  payload?: Record<string, unknown>;
};

export type Supplier = {
  id: string;
  external_id: string;
  name: string;
  domain?: string;
  metadata?: Record<string, unknown>;
  updated_at?: string;
  last_event_at?: string | null;
  identity_source?: string;
};

export type Incident = {
  id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  owner?: string | null;
  supplier_external_id?: string | null;
  event_id?: string | null;
  investigation_notes: string;
  created_at: string;
  updated_at: string;
  simulated?: boolean;
};

export type Shipment = {
  shipment_id: string;
  supplier_external_id: string;
  origin_name: string;
  origin_latitude: number;
  origin_longitude: number;
  destination_name: string;
  destination_latitude: number;
  destination_longitude: number;
  planned_departure: string;
  planned_arrival: string;
  actual_arrival: string | null;
  actual_delay_hours: number | null;
  simulated: boolean;
};

export type ShipmentDetail = {
  shipment: Shipment;
  mode: string;
  synthetic: boolean;
};

export type ShipmentPrediction = {
  prediction: {
    predicted_delay_hours: number;
    model_version: string;
    development_model: boolean;
    predicted_at: string;
  };
  features: Record<string, unknown>;
  explanation: {
    model_name: string;
    contributions: {
      feature_name: string;
      value: number | null;
      contribution: number;
      imputed: boolean;
    }[];
  };
  evaluation: ModelEvaluationReport | null;
  simulated: boolean;
  prediction_is_retrospective: boolean;
};

export type ModelEvaluation = {
  model_name?: string;
  development_data: boolean;
  training_sample_count: number;
  evaluation_sample_count: number;
  accuracy?: number;
  balanced_accuracy?: number;
  macro_f1?: number;
  mean_absolute_error?: number;
  root_mean_squared_error?: number;
  median_baseline_mae?: number;
};

export type ModelEvaluationReport = {
  development_data: boolean;
  temporal_evaluation: ModelEvaluation;
};

export type ModelReadiness = {
  model_name: string;
  ready: boolean;
  sample_count: number;
  reason?: string;
  development_model: boolean;
  evaluation: ModelEvaluationReport | null;
};

export type Dashboard = {
  kpis: {
    suppliers: number;
    events: number;
    sensor_alerts_24h: number;
    open_disruptions: number;
    shipments: number;
  };
  data_provenance: {
    simulated_events: number;
    simulated_shipments: number;
    synthetic_data_present: boolean;
    mode: string;
  };
  event_activity: { date: string; count: number }[];
  recent_events: EventRecord[];
  recent_incidents: Incident[];
  risk_distribution: { category: string; count: number }[];
  model_readiness: Record<string, ModelReadiness>;
  service_readiness: Record<string, boolean>;
};

export type GraphData = {
  nodes: {
    id: string;
    label: string;
    identifier: string;
    properties: Record<string, unknown>;
  }[];
  edges: { source: string; target: string; type: string }[];
  dependency_relationships_available: boolean;
};

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

function token(): string {
  return window.localStorage.getItem("scn-api-token") ?? "";
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.detail ?? `API request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export function saveToken(value: string): void {
  if (value) window.localStorage.setItem("scn-api-token", value);
  else window.localStorage.removeItem("scn-api-token");
}
