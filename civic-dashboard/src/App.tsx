import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import AppLayout from "./components/layout/AppLayout";

import DashboardPage from "./pages/dashboard/DashboardPage";
import ComplaintsPage from "./pages/complaints/ComplaintsPage";
import AnalyticsPage from "./pages/analytics/AnalyticsPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>

          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />

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

            <Route
              path="*"
              element={<Navigate to="/dashboard" replace />}
            />

          </Route>

        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}