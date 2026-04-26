import { Link, useLocation } from "react-router";
import { LucideIcon } from "lucide-react";
import { cn } from "./ui/utils";

interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
}

interface DashboardSidebarProps {
  navItems: NavItem[];
  title: string;
  subtitle: string;
}

export default function DashboardSidebar({ navItems, title, subtitle }: DashboardSidebarProps) {
  const location = useLocation();

  return (
    <div className="flex h-screen w-64 flex-col bg-sidebar text-sidebar-foreground">
      <div className="p-6 border-b border-sidebar-border">
        <h1 className="text-xl mb-1">{title}</h1>
        <p className="text-sm text-sidebar-foreground/60">{subtitle}</p>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const isActive = location.pathname === item.href || 
            (item.href !== "/" && location.pathname.startsWith(item.href));
          
          return (
            <Link
              key={item.href}
              to={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
                isActive
                  ? "bg-sidebar-primary text-sidebar-primary-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="h-5 w-5" />
              <span>{item.title}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
