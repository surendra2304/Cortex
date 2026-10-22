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
  if (typeof window === "undefined") return "";
  return localStorage.getItem("cortex_operator_token") || "";
};

export const apiClient = axios.create({
  baseURL: getBaseUrl(),
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const token = getOperatorToken().replace(/^Bearer\s+/i, "");
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

