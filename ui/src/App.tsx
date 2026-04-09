import { Routes, Route } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { DashboardPage } from "@/pages/DashboardPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { RunbooksPage } from "@/pages/RunbooksPage";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden bg-surface text-zinc-100">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-4">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
            <Route path="/runbooks" element={<RunbooksPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
