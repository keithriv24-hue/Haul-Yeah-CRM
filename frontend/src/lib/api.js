import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const getHealth = () => axios.get(`${API}/health`).then((r) => r.data);
export const verifyAirtable = () => axios.get(`${API}/airtable/verify`).then((r) => r.data);
export const listRecords = (table) => axios.get(`${API}/tables/${table}`).then((r) => r.data.records);
export const createRecordApi = (table, fields) => axios.post(`${API}/tables/${table}`, { fields }).then((r) => r.data);
export const updateRecordApi = (table, id, fields) =>
  axios.patch(`${API}/tables/${table}/${id}`, { fields }).then((r) => r.data);

export const apiErrorMessage = (e) => {
  const detail = e?.response?.data?.detail;
  if (detail?.message) return detail.message;
  if (typeof detail === "string") return detail;
  return "Something went wrong talking to Airtable. Try Refresh.";
};
