import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AppProvider } from "@/context/AppContext";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Leads from "@/pages/Leads";
import Contacts from "@/pages/Contacts";
import Projects from "@/pages/Projects";
import Tasks from "@/pages/Tasks";
import Blog from "@/pages/Blog";
import Invoices from "@/pages/Invoices";
import Subscriptions from "@/pages/Subscriptions";
import Partner from "@/pages/Partner";
import Help from "@/pages/Help";

function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/leads" element={<Leads />} />
            <Route path="/contacts" element={<Contacts />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/blog" element={<Blog />} />
            <Route path="/invoices" element={<Invoices />} />
            <Route path="/subscriptions" element={<Subscriptions />} />
            <Route path="/partner" element={<Partner />} />
            <Route path="/help" element={<Help />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="top-center" richColors />
    </AppProvider>
  );
}

export default App;
