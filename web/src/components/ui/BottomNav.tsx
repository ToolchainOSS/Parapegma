import { Link, useLocation } from "react-router";
import { NAV_ITEMS, isNavItemActive } from "../../config/nav";

export function BottomNav() {
  const { pathname } = useLocation();
  const items = NAV_ITEMS.filter((item) => !item.adminOnly);

  return (
    <nav aria-label="Main navigation" data-testid="bottom-nav" className="fixed bottom-0 inset-x-0 z-50 bg-surface border-t border-divider" style={{ height: "calc(var(--bottomnav-h) + env(safe-area-inset-bottom, 0px))", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
      <div className="flex items-center justify-around h-[var(--bottomnav-h)]">
        {items.map((item) => {
          const active = isNavItemActive(item, pathname);
          const Icon = item.Icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              className={`flex flex-col items-center justify-center gap-0.5 min-w-[var(--tap)] h-[var(--tap)] text-[11px] transition-colors ${active
                  ? "text-primary font-medium"
                  : "text-text-muted"
                }`}
            >
              <Icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
