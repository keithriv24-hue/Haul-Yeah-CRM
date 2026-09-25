import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AppProvider } from "@/context/AppContext";
import AuthGate, { useAuth } from "@/components/AuthGate";
import ScopeCalculator from "@/pages/ScopeCalculator";
import Script from "@/pages/Script";
import Settings from "@/pages/Settings";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Leads from "@/pages/Leads";
import LeadDetail from "@/pages/LeadDetail";
import Contacts from "@/pages/Contacts";
import Projects from "@/pages/Projects";
import DaySheet from "@/pages/DaySheet";
import Tasks from "@/pages/Tasks";
import Blog from "@/pages/Blog";
import Invoices from "@/pages/Invoices";
import Subscriptions from "@/pages/Subscriptions";
import Partner from "@/pages/Partner";
import Help from "@/pages/Help";
import Crew from "@/pages/Crew";
import CrewJobs from "@/pages/CrewJobs";
import TimeClock from "@/pages/TimeClock";
import DaysOff from "@/pages/DaysOff";
import CrewToday from "@/pages/CrewToday";
import JobsBoard from "@/pages/JobsBoard";
import Dispatch from "@/pages/Dispatch";
import Fleet from "@/pages/Fleet";
import MarketingDashboard from "@/pages/MarketingDashboard";
import Team from "@/pages/Team";
import MemberProfile from "@/pages/MemberProfile";
import Leaderboard from "@/pages/Leaderboard";
import Challenges from "@/pages/Challenges";
import TeamAdmin from "@/pages/TeamAdmin";
import Commissions from "@/pages/Commissions";
import Notifications from "@/pages/Notifications";
import Track from "@/pages/Track";
import QualityAudits from "@/pages/QualityAudits";
import QualityProblems from "@/pages/QualityProblems";
import QualityDocuments from "@/pages/QualityDocuments";
import QualityQuoteAccuracy from "@/pages/QualityQuoteAccuracy";
import { UpdateOverlay } from "@/components/UpdateOverlay";

function RoleRoutes() {
  const { role } = useAuth();
  if (role === "sales") {
    return (
      <Routes>
        <Route element={<Layout />}>
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadDetail />} />
          <Route path="/scope-calculator" element={<ScopeCalculator />} />
          <Route path="/script" element={<Script />} />
          <Route path="/commissions" element={<Commissions />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/team" element={<Team />} />
          <Route path="/team/:id" element={<MemberProfile />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/challenges" element={<Challenges />} />
          <Route path="*" element={<Navigate to="/leads" replace />} />
        </Route>
      </Routes>
    );
  }
  if (role === "crew") {
    return (
      <Routes>
        <Route element={<Layout />}>
          <Route path="/today" element={<CrewToday />} />
          <Route path="/jobs" element={<CrewJobs />} />
          <Route path="/scope-calculator" element={<ScopeCalculator />} />
          <Route path="/clock" element={<TimeClock />} />
          <Route path="/days-off" element={<DaysOff />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/team" element={<Team />} />
          <Route path="/team/:id" element={<MemberProfile />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/challenges" element={<Challenges />} />
          <Route path="*" element={<Navigate to="/today" replace />} />
        </Route>
      </Routes>
    );
  }
  if (role === "marketing") {
    return (
      <Routes>
        <Route element={<Layout />}>
          <Route path="/marketing" element={<MarketingDashboard />} />
          <Route path="/scope-calculator" element={<ScopeCalculator />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/team" element={<Team />} />
          <Route path="/team/:id" element={<MemberProfile />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/challenges" element={<Challenges />} />
          <Route path="*" element={<Navigate to="/marketing" replace />} />
        </Route>
      </Routes>
    );
  }
  if (role === "employee") {
    return (
      <Routes>
        <Route element={<Layout />}>
          <Route path="/projects" element={<Projects />} />
          <Route path="/day-sheet" element={<DaySheet />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/team" element={<Team />} />
          <Route path="/team/:id" element={<MemberProfile />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/challenges" element={<Challenges />} />
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Route>
      </Routes>
    );
  }
  if (role === "quality") {
    return (
      <Routes>
        <Route element={<Layout />}>
          <Route path="/quality/audits" element={<QualityAudits />} />
          <Route path="/quality/problems" element={<QualityProblems />} />
          <Route path="/quality/documents" element={<QualityDocuments />} />
          <Route path="/quality/quote-accuracy" element={<QualityQuoteAccuracy />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="*" element={<Navigate to="/quality/audits" replace />} />
        </Route>
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/leads/:id" element={<LeadDetail />} />
        <Route path="/script" element={<Script />} />
        <Route path="/commissions" element={<Commissions />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/crew" element={<Crew />} />
        <Route path="/dispatch" element={<Dispatch />} />
        <Route path="/fleet" element={<Fleet />} />
        <Route path="/jobs" element={<JobsBoard />} />
        <Route path="/marketing" element={<MarketingDashboard />} />
        <Route path="/day-sheet" element={<DaySheet />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/blog" element={<Blog />} />
        <Route path="/team" element={<Team />} />
        <Route path="/team/:id" element={<MemberProfile />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/challenges" element={<Challenges />} />
        <Route path="/team-admin" element={<TeamAdmin />} />
        <Route path="/invoices" element={<Invoices />} />
        <Route path="/subscriptions" element={<Subscriptions />} />
        <Route path="/partner" element={<Partner />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/scope-calculator" element={<ScopeCalculator />} />
        <Route path="/help" element={<Help />} />
        <Route path="/quality/audits" element={<QualityAudits />} />
        <Route path="/quality/problems" element={<QualityProblems />} />
        <Route path="/quality/documents" element={<QualityDocuments />} />
        <Route path="/quality/quote-accuracy" element={<QualityQuoteAccuracy />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function AuthedApp() {
  return (
    <AuthGate>
      <AppProvider>
        <RoleRoutes />
      </AppProvider>
    </AuthGate>
  );
}

function App() {
  return (
    <>
      <UpdateOverlay />
      <BrowserRouter>
        <Routes>
          <Route path="/track/:token" element={<Track />} />
          <Route path="*" element={<AuthedApp />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-center" richColors />
    </>
  );
}

export default App;
