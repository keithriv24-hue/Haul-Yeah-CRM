import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { apiErrorMessage, createRecordApi, deleteRecordApi, getHealth, getRates, getSchemaApi, listRecords, saveRatesApi, updateRecordApi } from "@/lib/api";
import { DEFAULT_RATES } from "@/lib/pricing";
import { useAuth } from "@/components/AuthGate";

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

export const ALL_TABLES = ["leads", "contacts", "projects", "tasks", "blog", "invoices", "subscriptions"];

export const AppProvider = ({ children }) => {
  const [privacy, setPrivacy] = useState(() => localStorage.getItem("hy_privacy") === "1");
  const [health, setHealth] = useState({ airtable_configured: null });
  const [data, setData] = useState({});
  const [refreshing, setRefreshing] = useState(false);
  const [rates, setRates] = useState(DEFAULT_RATES);
  const [schemas, setSchemas] = useState({});
  const schemaRequested = useRef(new Set());
  const dataRef = useRef(data);
  dataRef.current = data;
  const { role } = useAuth();
  const prevRoleRef = useRef(role);

  useEffect(() => {
    if (prevRoleRef.current !== role) {
      prevRoleRef.current = role;
      setData({});
      setSchemas({});
      schemaRequested.current = new Set();
    }
  }, [role]);

  const togglePrivacy = () => {
    setPrivacy((p) => {
      localStorage.setItem("hy_privacy", p ? "0" : "1");
      return !p;
    });
  };

  const checkHealth = useCallback(async () => {
    try {
      const h = await getHealth();
      setHealth(h);
      return h;
    } catch {
      setHealth({ airtable_configured: false });
      return { airtable_configured: false };
    }
  }, []);

  useEffect(() => {
    checkHealth();
    getRates().then(setRates).catch(() => {});
  }, [checkHealth]);

  const saveRates = useCallback(async (newRates) => {
    const saved = await saveRatesApi(newRates);
    setRates(saved);
    return saved;
  }, []);

  const loadSchema = useCallback(async (table) => {
    if (schemaRequested.current.has(table)) return;
    schemaRequested.current.add(table);
    try {
      const d = await getSchemaApi(table);
      setSchemas((s) => ({ ...s, [table]: d.fields }));
    } catch {
      schemaRequested.current.delete(table);
    }
  }, []);

  const loadTable = useCallback(async (table, force = false) => {
    const existing = dataRef.current[table];
    if (existing?.records && !force) return existing.records;
    if (existing?.loading && !force) return null;
    setData((d) => ({ ...d, [table]: { ...d[table], loading: true, error: null } }));
    try {
      const records = await listRecords(table);
      setData((d) => ({ ...d, [table]: { records, loading: false, error: null } }));
      setHealth((h) => (h.airtable_configured ? h : { ...h, airtable_configured: true }));
      return records;
    } catch (e) {
      const msg = apiErrorMessage(e);
      if (e?.response?.status === 503) setHealth((h) => ({ ...h, airtable_configured: false }));
      setData((d) => ({ ...d, [table]: { ...d[table], loading: false, error: msg } }));
      return null;
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    const h = await checkHealth();
    if (h.airtable_configured) {
      const loaded = Object.keys(dataRef.current).filter((t) => dataRef.current[t]?.records || dataRef.current[t]?.error);
      const tables = loaded.length ? loaded : ["leads"];
      await Promise.all(tables.map((t) => loadTable(t, true)));
      toast.success("Fresh data pulled from Airtable.");
    } else {
      toast.error("Airtable key is not set. Add AIRTABLE_API_KEY in the secrets panel.");
    }
    setRefreshing(false);
  }, [checkHealth, loadTable]);

  const updateRecord = useCallback(async (table, id, fields) => {
    const prevRecords = dataRef.current[table]?.records || [];
    setData((d) => ({
      ...d,
      [table]: {
        ...d[table],
        records: (d[table]?.records || []).map((r) => (r.id === id ? { ...r, fields: { ...r.fields, ...fields } } : r)),
      },
    }));
    try {
      const updated = await updateRecordApi(table, id, fields);
      setData((d) => ({
        ...d,
        [table]: { ...d[table], records: (d[table]?.records || []).map((r) => (r.id === id ? updated : r)) },
      }));
      return updated;
    } catch (e) {
      setData((d) => ({ ...d, [table]: { ...d[table], records: prevRecords } }));
      toast.error(`Save failed — change undone. ${apiErrorMessage(e)}`);
      throw e;
    }
  }, []);

  const createRecord = useCallback(async (table, fields) => {
    const clean = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined && v !== "" && v !== null));
    try {
      const rec = await createRecordApi(table, clean);
      setData((d) => ({ ...d, [table]: { ...d[table], records: [rec, ...(d[table]?.records || [])] } }));
      return rec;
    } catch (e) {
      toast.error(`Could not save. ${apiErrorMessage(e)}`);
      throw e;
    }
  }, []);

  const deleteRecord = useCallback(async (table, id) => {
    const prevRecords = dataRef.current[table]?.records || [];
    setData((d) => ({ ...d, [table]: { ...d[table], records: (d[table]?.records || []).filter((r) => r.id !== id) } }));
    try {
      await deleteRecordApi(table, id);
    } catch (e) {
      setData((d) => ({ ...d, [table]: { ...d[table], records: prevRecords } }));
      toast.error(`Delete failed — record restored. ${apiErrorMessage(e)}`);
      throw e;
    }
  }, []);

  const records = (table) => data[table]?.records || [];
  const tableState = (table) => data[table] || {};

  return (
    <AppContext.Provider
      value={{ privacy, togglePrivacy, health, checkHealth, loadTable, refreshAll, refreshing, updateRecord, createRecord, deleteRecord, records, tableState, rates, saveRates, schemas, loadSchema }}
    >
      {children}
    </AppContext.Provider>
  );
};
