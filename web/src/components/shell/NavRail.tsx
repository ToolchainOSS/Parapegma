import { Link, useLocation } from "react-router";
import { useAuth } from "../../auth";
import { NAV_ITEMS, isNavItemActive } from "../../config/nav";

export function NavRail() {
  const { pathname } = useLocation();
  const { role } = useAuth();

  return (
    <nav
      aria-label="Main navigation"
      data-testid="nav-rail"
      className="flex flex-col items-center gap-1 w-[72px] min-h-0 h-full bg-surface border-r border-divider pt-4 pb-[env(safe-area-inset-bottom,0px)]"
    >
      {NAV_ITEMS.filter((item) => !item.adminOnly || role === "admin").map(
        (item) => {
          const active = isNavItemActive(item, pathname);
          const Icon = item.Icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              title={item.label}
              className={`flex flex-col items-center justify-center gap-0.5 w-14 h-14 rounded-[var(--radius-md)] text-[11px] transition-colors ${active
                  ? "text-primary bg-primary/10 font-medium"
                  : "text-text-muted hover:bg-surface-2"
                }`}
            >
              <Icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        },
      )}
    </nav>
  );
}
