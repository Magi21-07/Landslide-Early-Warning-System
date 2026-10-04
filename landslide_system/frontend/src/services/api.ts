import axios from 'axios';

// Use explicit IPv4 127.0.0.1 — avoids Windows DNS resolving localhost → IPv6 ::1 which causes connection timeouts
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
// API key for the X-API-Key header — matches settings.API_KEY in src/api/config.py
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-api-key-secret';

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  // 30s timeout — risk evaluation via live CHIRPS/GEE pipeline can take 10–25s
  timeout: 30000,
});

// Attach X-API-Key to every request — required by verify_api_key dependency on protected routes
apiClient.interceptors.request.use((config) => {
  config.headers['X-API-Key'] = API_KEY;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error?.response?.status, error?.response?.data || error?.message);
    return Promise.reject(error);
  }
);

export const getSystemStatus = async () => {
  const res = await axios.get(`${API_BASE}/`);
  return res.data;
};

export const getRiskMap = async () => {
  const res = await apiClient.get('/geospatial/risk-map');
  return res.data;
};

export const getRiskAtLocation = async (latitude: number, longitude: number) => {
  // Coordinate search uses ?mock=true to avoid triggering the slow CHIRPS/GEE live pipeline.
  // The risk engine's mock predictor returns a plausible synthetic result instantly (<1s).
  // Remove ?mock=true if you want to evaluate against live satellite rainfall data.
  const res = await apiClient.post('/risk/evaluate?mock=true', { latitude, longitude });
  return res.data;
};

export const getRiskHistory = async (location_id: string, limit: number = 30) => {
  const res = await apiClient.get('/risk/history', { params: { location_id, limit } });
  return res.data;
};

export const getRecentRainfall = async (latitude: number, longitude: number, days: number = 15) => {
  const res = await apiClient.get('/rainfall/recent', { params: { latitude, longitude, days } });
  return res.data;
};

export const getRainfallSummary = async (latitude: number, longitude: number) => {
  const res = await apiClient.get('/rainfall/summary', { params: { latitude, longitude } });
  return res.data;
};

export interface DemoSimulationRequest {
  target_id?: string;
  rainfall_3d_mm: number;
  soil_moisture_pct: number;
  terrain_slope: number;
  trigger_telegram: boolean;
}

export interface DemoSimulationResponse {
  simulation_id: string;
  target_id: string;
  applied_overrides: Record<string, number>;
  risk_response: {
    risk_level: string;
    risk_score?: number;
    probability: number;
    top_risk_factors?: Array<{ factor: string; contribution: string }>;
    top_shap_factors?: Array<{ factor: string; shap_value: number }>;
  };
  alert_summary?: Record<string, unknown>;
  delivery_status?: Record<string, unknown>;
}

export const simulateRiskScenario = async (payload: DemoSimulationRequest): Promise<DemoSimulationResponse> => {
  const res = await apiClient.post('/demo/simulate', payload);
  return res.data;
};
