import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

axios.interceptors.request.use((config) => {
  const token = localStorage.getItem("hy_token");
  if (token && config.url?.startsWith(API)) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

axios.interceptors.response.use(null, (error) => {
  if (error?.response?.status === 401 && !error.config?.url?.includes("/auth/login")) {
    localStorage.removeItem("hy_token");
    window.dispatchEvent(new Event("hy-logout"));
  }
  return Promise.reject(error);
});

export const loginApi = (password) => axios.post(`${API}/auth/login`, { password }).then((r) => r.data);
export const authMe = () => axios.get(`${API}/auth/me`).then((r) => r.data);
export const switchRoleApi = (role) => axios.post(`${API}/auth/switch-role`, { role }).then((r) => r.data);
export const getRates = () => axios.get(`${API}/settings/rates`).then((r) => r.data);
export const saveRatesApi = (rates) => axios.put(`${API}/settings/rates`, rates).then((r) => r.data);
export const getSchemaApi = (table) => axios.get(`${API}/schema/${table}`).then((r) => r.data);

export const getHealth = () => axios.get(`${API}/health`).then((r) => r.data);
export const verifyAirtable = () => axios.get(`${API}/airtable/verify`).then((r) => r.data);
export const listRecords = (table) => axios.get(`${API}/tables/${table}`).then((r) => r.data.records);
export const createRecordApi = (table, fields) => axios.post(`${API}/tables/${table}`, { fields }).then((r) => r.data);
export const updateRecordApi = (table, id, fields) =>
  axios.patch(`${API}/tables/${table}/${id}`, { fields }).then((r) => r.data);
export const deleteRecordApi = (table, id) => axios.delete(`${API}/tables/${table}/${id}`).then((r) => r.data);

export const apiErrorMessage = (e) => {
  const detail = e?.response?.data?.detail;
  if (detail?.message) return detail.message;
  if (typeof detail === "string") return detail;
  return "Something went wrong talking to Airtable. Try Refresh.";
};
