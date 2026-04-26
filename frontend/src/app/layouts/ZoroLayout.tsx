import { Outlet, Link, useLocation } from "react-router";
import { useState } from "react";
import {
  LayoutDashboard,
  Upload,
  Users,
  ClipboardCheck,
  MessageSquare,
  Gamepad2,
  Settings,
  ChevronLeft,
  ChevronRight,
  Bell,
  User
} from "lucide-react";

const navigation = [
  { name: "Dashboard Overview", href: "/dashboard", icon: LayoutDashboard },
  { name: "Syllabus Upload", href: "/syllabus", icon: Upload },
  { name: "Student Enrollment", href: "/enrollment", icon: Users },
  { name: "Attendance Records", href: "/attendance", icon: ClipboardCheck },
  { name: "Query & Transcripts", href: "/queries", icon: MessageSquare },
  { name: "Settings", href: "/settings", icon: Settings },
];

export default function ZoroLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  return (
    <div className="flex h-screen bg-[#0A0F1E] text-white overflow-hidden">
      {/* Sidebar */}
      <div
        className={`${
          collapsed ? "w-20" : "w-64"
        } bg-[#0A0F1E] border-r border-white/10 flex flex-col transition-all duration-300`}
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-center border-b border-white/10 px-4">
          {!collapsed && (
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-[#1E6BFF] to-[#00D4FF] rounded-lg flex items-center justify-center">
                <span className="text-xl font-bold">Z</span>
              </div>
              <span className="font-semibold">ZORO</span>
            </div>
          )}
          {collapsed && (
            <div className="w-10 h-10 bg-gradient-to-br from-[#1E6BFF] to-[#00D4FF] rounded-lg flex items-center justify-center">
              <span className="text-xl font-bold">Z</span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                to={item.href}
                className={`
                  flex items-center gap-3 px-3 py-3 rounded-lg transition-all
                  ${isActive
                    ? "bg-[#1E6BFF]/20 text-[#00D4FF] border-l-4 border-[#1E6BFF]"
                    : "text-[#8A9BB5] hover:bg-white/5 hover:text-white border-l-4 border-transparent"
                  }
                `}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {!collapsed && <span className="text-sm">{item.name}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Collapse Toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="h-12 flex items-center justify-center border-t border-white/10 hover:bg-white/5 transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5 text-[#8A9BB5]" />
          ) : (
            <ChevronLeft className="w-5 h-5 text-[#8A9BB5]" />
          )}
        </button>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <div className="h-16 bg-[#131827] border-b border-white/10 flex items-center justify-between px-6">
          <h1 className="text-xl">ZORO Control Center</h1>
          <div className="flex items-center gap-4">
            <div className="text-sm text-[#8A9BB5]">
              {new Date().toLocaleDateString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
              })}
            </div>
            <button className="relative p-2 hover:bg-white/5 rounded-lg transition-colors">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-[#00D4FF] rounded-full"></span>
            </button>
            <button className="w-8 h-8 bg-gradient-to-br from-[#1E6BFF] to-[#00D4FF] rounded-full flex items-center justify-center">
              <User className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Page Content */}
        <div className="flex-1 overflow-auto bg-[#0f1420] p-6">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
