import axios from "axios";

// Default to relative URL in browser to avoid CORS and host mismatch across environments
const getBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_CORTEX_API_URL) {
    return process.env.NEXT_PUBLIC_CORTEX_API_URL;
  }
  if (typeof window !== "undefined") {
    return "";
  }
  return "http://localhost:8000";
};

export const getOperatorToken = () => {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("cortex_operator_token");
    if (stored) return stored;
  }
  return process.env.NEXT_PUBLIC_OPERATOR_TOKEN || "mock_operator_jwt_token_123";
};

export const apiClient = axios.create({
  baseURL: getBaseUrl(),
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const token = getOperatorToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

export const approveAction = async (actionId: string, payload: Record<string, any> = {}) => {
  const res = await apiClient.post(`/v1/actions/${actionId}/approve`, payload);
  return res.data;
};

