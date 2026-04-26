import { Outlet } from "react-router";
import DashboardSidebar from "../components/DashboardSidebar";
import {
  LayoutDashboard,
  Mic,
  Phone,
  TrendingUp,
  FileText,
  Settings,
} from "lucide-react";

export default function ClientLayout() {
  const navItems = [
    { title: "Dashboard", href: "/client", icon: LayoutDashboard },
    { title: "AI Voice Demo", href: "/client/demo", icon: Mic },
    { title: "Call Logs", href: "/client/call-logs", icon: Phone },
    { title: "Leads", href: "/client/leads", icon: TrendingUp },
    { title: "Transcripts", href: "/client/transcripts", icon: FileText },
    { title: "Settings", href: "/client/settings", icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-background">
      <DashboardSidebar
        navItems={navItems}
        title="Zoro"
        subtitle="Voice Agent"
      />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
