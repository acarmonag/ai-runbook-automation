import { Routes, Route } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { ApprovalNotificationBar } from "@/components/layout/ApprovalNotificationBar";
import { DashboardPage } from "@/pages/DashboardPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { RunbooksPage } from "@/pages/RunbooksPage";
import { StatsPage } from "@/pages/StatsPage";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden bg-surface text-zinc-100">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <ApprovalNotificationBar />
        <main className="flex-1 overflow-y-auto p-4">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
            <Route path="/runbooks" element={<RunbooksPage />} />
            <Route path="/stats" element={<StatsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
