import { NavLink } from "react-router-dom";
import { LayoutDashboard, BookOpen, Activity, BarChart3 } from "lucide-react";
import { clsx } from "clsx";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/runbooks", label: "Runbooks", icon: BookOpen, end: false },
  { to: "/stats", label: "MTTR / SLO", icon: BarChart3, end: false },
];

export function Sidebar() {
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-800 bg-surface-1">
      <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3.5">
        <Activity className="h-5 w-5 text-emerald-400" />
        <span className="text-sm font-semibold text-zinc-100">SRE Runbook</span>
      </div>

      <nav className="flex flex-col gap-0.5 p-2 pt-3">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2.5 rounded px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
