import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { apiErrorMessage, createRecordApi, deleteRecordApi, getBusinessApi, getHealth, getRates, getSchemaApi, listRecords, listSquareInvoicesApi, saveBusinessApi, saveRatesApi, updateRecordApi } from "@/lib/api";
import { DEFAULT_RATES } from "@/lib/pricing";
import { LF } from "@/lib/fields";
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
  const [business, setBusiness] = useState({ reviewLink: "" });
  const [squareInvoices, setSquareInvoices] = useState([]);
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
    getBusinessApi().then(setBusiness).catch(() => {});
  }, [checkHealth]);

  const saveRates = useCallback(async (newRates) => {
    const saved = await saveRatesApi(newRates);
    setRates(saved);
    return saved;
  }, []);

  const saveBusiness = useCallback(async (b) => {
    const saved = await saveBusinessApi(b);
    setBusiness(saved);
    return saved;
  }, []);

  const loadSquareInvoices = useCallback(async () => {
    try {
      const list = await listSquareInvoicesApi();
      setSquareInvoices(list);
      const paidLeadIds = new Set(list.filter((i) => i.status === "PAID" && i.lead_id && i.deposit_synced).map((i) => i.lead_id));
      if (paidLeadIds.size) {
        setData((d) => {
          const leadRecords = d.leads?.records;
          if (!leadRecords) return d;
          return {
            ...d,
            leads: {
              ...d.leads,
              records: leadRecords.map((r) =>
                paidLeadIds.has(r.id) ? { ...r, fields: { ...r.fields, [LF.depositPaid]: true } } : r
              ),
            },
          };
        });
      }
      return list;
    } catch {
      return [];
    }
  }, []);

  const invoicesForLead = useCallback(
    (leadId) => squareInvoices.filter((i) => i.lead_id === leadId),
    [squareInvoices]
  );

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
      value={{ privacy, togglePrivacy, health, checkHealth, loadTable, refreshAll, refreshing, updateRecord, createRecord, deleteRecord, records, tableState, rates, saveRates, business, saveBusiness, schemas, loadSchema, squareInvoices, loadSquareInvoices, invoicesForLead }}
    >
      {children}
    </AppContext.Provider>
  );
};
