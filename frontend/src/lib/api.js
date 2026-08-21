import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

axios.interceptors.request.use((config) => {
  const token = localStorage.getItem("hy_token");
  if (token && config.url?.startsWith(API)) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

axios.interceptors.response.use(null, (error) => {
  const url = error.config?.url || "";
  if (error?.response?.status === 401 && !url.includes("/auth/login") && !url.includes("/auth/change-password")) {
    localStorage.removeItem("hy_token");
    window.dispatchEvent(new Event("hy-logout"));
  }
  return Promise.reject(error);
});

export const loginApi = (payload) => axios.post(`${API}/auth/login`, payload).then((r) => r.data);
export const changePasswordApi = (current_password, new_password) =>
  axios.post(`${API}/auth/change-password`, { current_password, new_password }).then((r) => r.data);
export const gpsConsentApi = () => axios.post(`${API}/auth/consent`).then((r) => r.data);
export const authMe = () => axios.get(`${API}/auth/me`).then((r) => r.data);
export const switchRoleApi = (role) => axios.post(`${API}/auth/switch-role`, { role }).then((r) => r.data);
export const getRates = () => axios.get(`${API}/settings/rates`).then((r) => r.data);
export const saveRatesApi = (rates) => axios.put(`${API}/settings/rates`, rates).then((r) => r.data);
export const saveScopeApi = (payload) => axios.post(`${API}/scopes`, payload).then((r) => r.data);
export const listScopesApi = (leadId) => axios.get(`${API}/scopes`, { params: leadId ? { lead_id: leadId } : {} }).then((r) => r.data.scopes);
export const getScopeApi = (id) => axios.get(`${API}/scopes/${id}`).then((r) => r.data);
export const patchScopeVideoApi = (id, video) => axios.patch(`${API}/scopes/${id}/video`, video).then((r) => r.data);
export const getScopeAccessApi = () => axios.get(`${API}/scopes/access`).then((r) => r.data);
export const getScopePricingValuesApi = () => axios.get(`${API}/scopes/pricing-values`).then((r) => r.data);
export const listCalcAccessApi = () => axios.get(`${API}/users/calculator-access`).then((r) => r.data.access);
export const setCalcAccessApi = (userId, mode) => axios.put(`${API}/users/${userId}/calculator-access`, { mode }).then((r) => r.data);
export const removeCalcAccessApi = (userId) => axios.delete(`${API}/users/${userId}/calculator-access`).then((r) => r.data);

export const getBusinessApi = () => axios.get(`${API}/settings/business`).then((r) => r.data);
export const saveBusinessApi = (b) => axios.put(`${API}/settings/business`, b).then((r) => r.data);
export const getSquareStatusApi = () => axios.get(`${API}/square/status`).then((r) => r.data);
export const sendSquareInvoiceApi = (payload) => axios.post(`${API}/square/invoice`, payload).then((r) => r.data);
export const listSquareInvoicesApi = () => axios.get(`${API}/square/invoices`).then((r) => r.data.invoices);
export const getSchemaApi = (table) => axios.get(`${API}/schema/${table}`).then((r) => r.data);

export const getHealth = () => axios.get(`${API}/health`).then((r) => r.data);
export const verifyAirtable = () => axios.get(`${API}/airtable/verify`).then((r) => r.data);
export const listRecords = (table) => axios.get(`${API}/tables/${table}`).then((r) => r.data.records);
export const createRecordApi = (table, fields) => axios.post(`${API}/tables/${table}`, { fields }).then((r) => r.data);
export const updateRecordApi = (table, id, fields) =>
  axios.patch(`${API}/tables/${table}/${id}`, { fields }).then((r) => r.data);
export const deleteRecordApi = (table, id) => axios.delete(`${API}/tables/${table}/${id}`).then((r) => r.data);

export const listUsersApi = () => axios.get(`${API}/users`).then((r) => r.data.users);
export const createUserApi = (u) => axios.post(`${API}/users`, u).then((r) => r.data);
export const patchUserApi = (id, u) => axios.patch(`${API}/users/${id}`, u).then((r) => r.data);
export const deleteUserApi = (id) => axios.delete(`${API}/users/${id}`).then((r) => r.data);
export const listTrucksApi = () => axios.get(`${API}/trucks`).then((r) => r.data.trucks);
export const createTruckApi = (t) => axios.post(`${API}/trucks`, t).then((r) => r.data);
export const patchTruckApi = (id, t) => axios.patch(`${API}/trucks/${id}`, t).then((r) => r.data);
export const deleteTruckApi = (id) => axios.delete(`${API}/trucks/${id}`).then((r) => r.data);
export const calendarJobsApi = (month) => axios.get(`${API}/calendar/jobs`, { params: { month } }).then((r) => r.data);
export const timelogStatusApi = () => axios.get(`${API}/timelog/status`).then((r) => r.data);
export const teamStatusApi = () => axios.get(`${API}/team/status`).then((r) => r.data);
export const getUserProfileApi = (id) => axios.get(`${API}/users/${id}/profile`).then((r) => r.data);
export const saveUserProfileApi = (id, profile) => axios.put(`${API}/users/${id}/profile`, profile).then((r) => r.data);
export const listAssignmentsApi = (params = {}) => axios.get(`${API}/assignments`, { params }).then((r) => r.data.assignments);
export const createAssignmentApi = (a) => axios.post(`${API}/assignments`, a).then((r) => r.data);
export const updateAssignmentApi = (id, a) => axios.patch(`${API}/assignments/${id}`, a).then((r) => r.data);
export const dispatchBoardApi = (date) => axios.get(`${API}/dispatch/board`, { params: date ? { date } : {} }).then((r) => r.data);
export const jobChecklistsApi = (id) => axios.get(`${API}/assignments/${id}/checklists`).then((r) => r.data);
export const toggleChecklistItemApi = (id, listKey, idx, done) => axios.post(`${API}/assignments/${id}/checklists/${listKey}/items/${idx}`, { done }).then((r) => r.data);
export const jobTimelineApi = (id) => axios.get(`${API}/assignments/${id}/timeline`).then((r) => r.data);
export const fleetApi = () => axios.get(`${API}/fleet`).then((r) => r.data);
export const truckInspectionsApi = (id) => axios.get(`${API}/trucks/${id}/inspections`).then((r) => r.data);
export const createInspectionApi = (id, payload) => axios.post(`${API}/trucks/${id}/inspections`, payload).then((r) => r.data);
export const truckLogsApi = (id) => axios.get(`${API}/trucks/${id}/logs`).then((r) => r.data);
export const addTruckLogApi = (id, payload) => axios.post(`${API}/trucks/${id}/logs`, payload).then((r) => r.data);
export const deleteTruckLogApi = (logId) => axios.delete(`${API}/truck-logs/${logId}`).then((r) => r.data);
export const truckDamageApi = (id) => axios.get(`${API}/trucks/${id}/damage`).then((r) => r.data);
export const reportDamageApi = (id, payload) => axios.post(`${API}/trucks/${id}/damage`, payload).then((r) => r.data);
export const patchDamageApi = (damageId, resolved) => axios.patch(`${API}/truck-damage/${damageId}`, { resolved }).then((r) => r.data);
export const uploadTruckPhotoApi = (truckId, file, kind, refId) => {
  const fd = new FormData();
  fd.append("file", file);
  return axios.post(`${API}/trucks/${truckId}/photos`, fd, { params: { kind, ref_id: refId || "" } }).then((r) => r.data);
};
export const truckPhotoUrl = (id) => `${API}/truck-photos/${id}?auth=${localStorage.getItem("hy_token")}`;
export const deleteAssignmentApi = (id) => axios.delete(`${API}/assignments/${id}`).then((r) => r.data);
export const myJobsApi = () => axios.get(`${API}/crew/my-jobs`).then((r) => r.data.jobs);
export const setJobStatusApi = (id, status, notes, delay_factors) =>
  axios.post(`${API}/crew/jobs/${id}/status`, { status, notes, delay_factors }).then((r) => r.data);
export const uploadJobPhotoApi = (id, file) => {
  const fd = new FormData();
  fd.append("file", file);
  return axios.post(`${API}/crew/jobs/${id}/photos`, fd).then((r) => r.data);
};
export const listJobPhotosApi = (id) => axios.get(`${API}/jobs/${id}/photos`).then((r) => r.data.photos);
export const photoUrl = (id) => `${API}/photos/${id}?auth=${localStorage.getItem("hy_token")}`;
export const clockInApi = (coords) => axios.post(`${API}/crew/clock-in`, coords || {}).then((r) => r.data);
export const clockOutApi = (coords) => axios.post(`${API}/crew/clock-out`, coords || {}).then((r) => r.data);
export const gpsPingApi = (coords) => axios.post(`${API}/crew/ping`, coords).then((r) => r.data);
export const myTimeApi = () => axios.get(`${API}/crew/my-time`).then((r) => r.data);
export const myAvailabilityApi = () => axios.get(`${API}/crew/availability`).then((r) => r.data.availability);
export const setAvailabilityApi = (date, available) =>
  axios.post(`${API}/crew/availability`, { date, available }).then((r) => r.data);
export const listTimeclockApi = (params = {}) => axios.get(`${API}/timeclock`, { params }).then((r) => r.data.entries);
export const patchTimeEntryApi = (id, p) => axios.patch(`${API}/timeclock/${id}`, p).then((r) => r.data);
export const timesheetCsvUrl = (start, end) =>
  `${API}/timeclock/export?start=${start}&end=${end}&auth=${localStorage.getItem("hy_token")}`;
export const gpsLiveApi = () => axios.get(`${API}/gps/live`).then((r) => r.data.crew);
export const listNotificationsApi = () => axios.get(`${API}/notifications`).then((r) => r.data);
export const readAllNotificationsApi = () => axios.post(`${API}/notifications/read-all`).then((r) => r.data);
export const getCrewRatesApi = () => axios.get(`${API}/settings/crew-rates`).then((r) => r.data);
export const saveCrewRatesApi = (rates) => axios.put(`${API}/settings/crew-rates`, rates).then((r) => r.data);
export const laborReportApi = (params = {}) => axios.get(`${API}/reports/labor`, { params }).then((r) => r.data);
export const getIntegrationsApi = () => axios.get(`${API}/settings/integrations`).then((r) => r.data);
export const saveIntegrationsApi = (payload) => axios.put(`${API}/settings/integrations`, payload).then((r) => r.data);
export const squareSyncStatusApi = () => axios.get(`${API}/square/sync-status`).then((r) => r.data);
export const listJobsApi = () => axios.get(`${API}/jobs`).then((r) => r.data.jobs);
export const patchJobApi = (id, payload) => axios.patch(`${API}/jobs/${id}`, payload).then((r) => r.data);
export const crewActiveJobApi = () => axios.get(`${API}/crew/active-job`).then((r) => r.data);
export const sendTrackingLinkApi = (jobId) => axios.post(`${API}/crew/jobs/${jobId}/tracking-link`).then((r) => r.data);
export const sendReviewRequestApi = (jobId, payload) => axios.post(`${API}/crew/jobs/${jobId}/review-request`, payload).then((r) => r.data);
export const listReviewRequestsApi = () => axios.get(`${API}/review-requests`).then((r) => r.data.requests);
export const patchReviewRequestApi = (id, p) => axios.patch(`${API}/review-requests/${id}`, p).then((r) => r.data);
export const marketingOverviewApi = (start, end) => axios.get(`${API}/marketing/overview`, { params: { start, end } }).then((r) => r.data);
export const listAdSpendApi = () => axios.get(`${API}/marketing/ad-spend`).then((r) => r.data.entries);
export const addAdSpendApi = (p) => axios.post(`${API}/marketing/ad-spend`, p).then((r) => r.data);
export const deleteAdSpendApi = (id) => axios.delete(`${API}/marketing/ad-spend/${id}`).then((r) => r.data);
export const getMktThresholdsApi = () => axios.get(`${API}/marketing/thresholds`).then((r) => r.data);
export const saveMktThresholdsApi = (p) => axios.put(`${API}/marketing/thresholds`, p).then((r) => r.data);
export const marketingMarginApi = (start, end) => axios.get(`${API}/marketing/margin`, { params: { start, end } }).then((r) => r.data);
export const setLeadMetaApi = (leadId, p) => axios.post(`${API}/lead-meta/${leadId}`, p).then((r) => r.data);
export const setTaskAudienceApi = (id, audience, title = "") => axios.post(`${API}/tasks/${id}/audience`, { audience, title }).then((r) => r.data);
export const teamNotificationsApi = () => axios.get(`${API}/team-notifications`).then((r) => r.data.items);
export const saveQuoteBreakdownApi = (leadId, breakdown) => axios.put(`${API}/quotes/${leadId}`, { breakdown }).then((r) => r.data);
export const getQuoteBreakdownApi = (leadId) => axios.get(`${API}/quotes/${leadId}`).then((r) => r.data);
export const trackApi = (token) => axios.get(`${API}/track/${token}`).then((r) => r.data);
export const portalDetailsApi = (token, payload) => axios.post(`${API}/track/${token}/details`, payload).then((r) => r.data);
export const portalUploadApi = (token, file, kind) => {
  const fd = new FormData();
  fd.append("file", file);
  return axios.post(`${API}/track/${token}/uploads`, fd, { params: { kind } }).then((r) => r.data);
};
export const portalUploadUrl = (token, id) => `${API}/track/${token}/uploads/${id}`;
export const portalTipApi = (token, payload) => axios.post(`${API}/track/${token}/tip`, payload).then((r) => r.data);
export const portalReviewApi = (token, payload) => axios.post(`${API}/track/${token}/review`, payload).then((r) => r.data);
export const jobPortalUploadsApi = (jobId) => axios.get(`${API}/jobs/${jobId}/portal-uploads`).then((r) => r.data);
export const opsBriefApi = (refresh) => axios.get(`${API}/ai/ops-brief`, { params: refresh ? { refresh: 1 } : {} }).then((r) => r.data);

export const teamMembersApi = () => axios.get(`${API}/team/members`).then((r) => r.data);
export const memberDetailApi = (id) => axios.get(`${API}/team/members/${id}`).then((r) => r.data);
export const saveMyProfileApi = (p) => axios.put(`${API}/profile`, p).then((r) => r.data);
export const moderateProfileApi = (id, p) => axios.put(`${API}/team/members/${id}/moderate`, p).then((r) => r.data);
export const savePinsApi = (badge_ids) => axios.put(`${API}/profile/pins`, { badge_ids }).then((r) => r.data);
export const uploadProfilePhotoApi = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return axios.post(`${API}/profile/photo`, fd).then((r) => r.data);
};
export const profilePhotoUrl = (id, v) =>
  `${API}/profile-photos/${id}?auth=${localStorage.getItem("hy_token")}${v ? `&v=${v}` : ""}`;
export const deleteProfilePhotoApi = (id) => axios.delete(`${API}/team/members/${id}/photo`).then((r) => r.data);
export const listBadgesApi = () => axios.get(`${API}/badges`).then((r) => r.data.badges);
export const createBadgeApi = (b) => axios.post(`${API}/badges`, b).then((r) => r.data);
export const patchBadgeApi = (id, b) => axios.patch(`${API}/badges/${id}`, b).then((r) => r.data);
export const awardBadgeApi = (id, user_id) => axios.post(`${API}/badges/${id}/award`, { user_id }).then((r) => r.data);
export const revokeBadgeApi = (id, userId) => axios.delete(`${API}/badges/${id}/award/${userId}`).then((r) => r.data);
export const listCreditsApi = (params = {}) => axios.get(`${API}/credits`, { params }).then((r) => r.data.credits);
export const addCreditApi = (c) => axios.post(`${API}/credits`, c).then((r) => r.data);
export const deleteCreditApi = (id) => axios.delete(`${API}/credits/${id}`).then((r) => r.data);
export const creditPromptsApi = () => axios.get(`${API}/credit-prompts`).then((r) => r.data.prompts);
export const resolvePromptApi = (id, approve) =>
  axios.post(`${API}/credit-prompts/${encodeURIComponent(id)}/resolve`, { approve }).then((r) => r.data);
export const leaderboardApi = (month) =>
  axios.get(`${API}/leaderboard`, { params: month ? { month } : {} }).then((r) => r.data);
export const hallOfFameApi = () => axios.get(`${API}/hall-of-fame`).then((r) => r.data.entries);
export const listChallengesApi = () => axios.get(`${API}/challenges`).then((r) => r.data);
export const createChallengeApi = (c) => axios.post(`${API}/challenges`, c).then((r) => r.data);
export const patchChallengeApi = (id, c) => axios.patch(`${API}/challenges/${id}`, c).then((r) => r.data);
export const deleteChallengeApi = (id) => axios.delete(`${API}/challenges/${id}`).then((r) => r.data);
export const verifyChallengeApi = (id, user_id, value) =>
  axios.post(`${API}/challenges/${id}/verify`, { user_id, value }).then((r) => r.data);
export const awardChallengeApi = (id, winners) =>
  axios.post(`${API}/challenges/${id}/award`, { winners }).then((r) => r.data);
export const crewComparisonApi = () => axios.get(`${API}/admin/crew-comparison`).then((r) => r.data.rows);
export const auditLogApi = (limit = 200) => axios.get(`${API}/audit`, { params: { limit } }).then((r) => r.data.entries);

export const attributionApi = (leadId) => axios.get(`${API}/commissions/attribution/${leadId}`).then((r) => r.data);
export const saveAttributionApi = (leadId, p) => axios.put(`${API}/commissions/attribution/${leadId}`, p).then((r) => r.data);
export const commissionRatesApi = () => axios.get(`${API}/commissions/rates`).then((r) => r.data);
export const saveCommissionRatesApi = (p) => axios.put(`${API}/commissions/rates`, p).then((r) => r.data);
export const commissionsReportApi = (params = {}) => axios.get(`${API}/commissions/report`, { params }).then((r) => r.data);
export const availabilityOverviewApi = (start, end) =>
  axios.get(`${API}/availability/overview`, { params: { start, end } }).then((r) => r.data);
export const ownerSetAvailabilityApi = (user_id, date, available) =>
  axios.post(`${API}/availability/set`, { user_id, date, available }).then((r) => r.data);
export const profileTaskApi = () => axios.get(`${API}/profile-task`).then((r) => r.data);
export const profileTaskDoneApi = () => axios.post(`${API}/profile-task/done`).then((r) => r.data);
export const alertsApi = () => axios.get(`${API}/alerts`).then((r) => r.data);
export const alertsUnreadApi = () => axios.get(`${API}/alerts/unread-count`).then((r) => r.data.unread);
export const markAlertsReadApi = () => axios.post(`${API}/alerts/read`).then((r) => r.data);
export const webhookInfoApi = () => axios.get(`${API}/alerts/webhook-info`).then((r) => r.data);
export const gmailStatusApi = () => axios.get(`${API}/gmail/status`).then((r) => r.data);
export const gmailConnectApi = (id) => axios.get(`${API}/gmail/connect/${id}`).then((r) => r.data);
export const gmailDisconnectApi = (id) => axios.post(`${API}/gmail/disconnect/${id}`).then((r) => r.data);
export const gmailMessagesApi = (id, params = {}) => axios.get(`${API}/gmail/${id}/messages`, { params }).then((r) => r.data);
export const gmailMessageApi = (id, msgId) => axios.get(`${API}/gmail/${id}/messages/${msgId}`).then((r) => r.data);
export const gmailReplyApi = (id, msgId, body) => axios.post(`${API}/gmail/${id}/messages/${msgId}/reply`, { body }).then((r) => r.data);
export const gmailModifyApi = (id, msgId, action) => axios.post(`${API}/gmail/${id}/messages/${msgId}/modify`, { action }).then((r) => r.data);
export const capiStatusApi = () => axios.get(`${API}/meta/capi-status`).then((r) => r.data);
export const metaStatusApi = () => axios.get(`${API}/meta/status`).then((r) => r.data);
export const metaConnectApi = () => axios.get(`${API}/meta/connect`).then((r) => r.data);
export const metaDisconnectApi = () => axios.post(`${API}/meta/disconnect`).then((r) => r.data);
export const metaFeedApi = () => axios.get(`${API}/meta/feed`).then((r) => r.data);
export const metaRefreshApi = () => axios.post(`${API}/meta/refresh`).then((r) => r.data);

export const apiErrorMessage = (e) => {
  const detail = e?.response?.data?.detail;
  if (detail?.message) return detail.message;
  if (typeof detail === "string") return detail;
  return "Something went wrong talking to Airtable. Try Refresh.";
};
