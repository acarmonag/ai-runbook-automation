import { IncidentFeed } from "@/components/incidents/IncidentFeed";
import { AlertSimulator } from "@/components/simulator/AlertSimulator";
import { HealthPanel } from "@/components/health/HealthPanel";
import { Card } from "@/components/ui/Card";

export function DashboardPage() {
  return (
    <div className="flex gap-4">
      {/* Main feed */}
      <div className="flex-1 min-w-0">
        <Card title="Incidents">
          <IncidentFeed />
        </Card>
      </div>

      {/* Right sidebar */}
      <div className="flex w-64 shrink-0 flex-col gap-4">
        <AlertSimulator />
        <HealthPanel />
      </div>
    </div>
  );
}
