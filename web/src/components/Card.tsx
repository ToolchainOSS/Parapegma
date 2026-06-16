import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className = "", onClick }: CardProps) {
  const interactive = onClick !== undefined;
  return (
    <div
      className={`bg-surface border border-border rounded-[var(--radius-lg)] shadow-[var(--shadow-sm)] ${interactive
          ? "cursor-pointer transition-[transform,box-shadow,border-color] duration-200 ease-[var(--ease-out)] hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)] hover:border-text-subtle/30 active:translate-y-0"
          : ""
        } ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "" }: CardProps) {
  return (
    <div className={`px-6 pt-5 pb-4 border-b border-divider ${className}`}>
      {children}
    </div>
  );
}

export function CardContent({ children, className = "" }: CardProps) {
  return <div className={`px-6 py-5 ${className}`}>{children}</div>;
}
