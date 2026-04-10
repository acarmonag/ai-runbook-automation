import { Card } from "@/components/ui/Card";
import { MttrDashboard } from "@/components/stats/MttrDashboard";

export function StatsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-lg font-semibold text-zinc-100">MTTR &amp; SLO Dashboard</h1>
      <Card title="Incident Metrics">
        <MttrDashboard />
      </Card>
    </div>
  );
}
