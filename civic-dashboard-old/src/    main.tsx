import React from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";

import "./index.css";

import AppLayout from "./components/layout/AppLayout";

import DashboardPage from "./pages/dashboard/DashboardPage";
import ComplaintsPage from "./pages/complaints/ComplaintsPage";
import AnalyticsPage from "./pages/analytics/AnalyticsPage";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>

          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />

            <Route
              path="/dashboard"
              element={<DashboardPage />}
            />

            <Route
              path="/complaints"
              element={<ComplaintsPage />}
            />

            <Route
              path="/analytics"
              element={<AnalyticsPage />}
            />
          </Route>

        </Routes>
      </BrowserRouter>

      <Toaster position="top-right" />
    </QueryClientProvider>
  </React.StrictMode>
);