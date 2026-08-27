import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_NEXUS_API_URL || "http://localhost:8000";
const OPERATOR_TOKEN = process.env.NEXT_PUBLIC_OPERATOR_TOKEN || "mock_operator_jwt_token_123";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  if (OPERATOR_TOKEN) {
    config.headers.Authorization = `Bearer ${OPERATOR_TOKEN}`;
  }
  return config;
});

export const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

export const approveAction = async (actionId: string, payload: Record<string, any> = {}) => {
  const res = await apiClient.post(`/v1/actions/${actionId}/approve`, payload);
  return res.data;
};
