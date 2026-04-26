import { Outlet } from "react-router";
import DashboardSidebar from "../components/DashboardSidebar";
import {
  LayoutDashboard,
  Users,
  FileText,
  Settings,
  Phone,
  UserCog,
  VideoIcon,
  Link as LinkIcon,
} from "lucide-react";

export default function AdminLayout() {
  const navItems = [
    { title: "Dashboard", href: "/admin", icon: LayoutDashboard },
    { title: "User Requests", href: "/admin/user-requests", icon: FileText },
    { title: "Clients", href: "/admin/clients", icon: Users },
    { title: "Demo Sessions", href: "/admin/demo-sessions", icon: VideoIcon },
    { title: "AI Configuration", href: "/admin/ai-config", icon: UserCog },
    { title: "Call History", href: "/admin/call-history", icon: Phone },
    { title: "Generate Demo Access", href: "/admin/generate-demo", icon: LinkIcon },
    { title: "Settings", href: "/admin/settings", icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-background">
      <DashboardSidebar
        navItems={navItems}
        title="Zoro"
        subtitle="Admin Panel"
      />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
