import type { ReactNode } from "react";

interface PanelProps {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export default function Panel({ title, eyebrow, action, children, className = "" }: PanelProps) {
  return (
    <section className={`rounded border border-base-600 bg-base-700 shadow-panel ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between border-b border-base-600 px-4 py-3">
          <div>
            {eyebrow && <p className="text-[11px] text-ink-400">{eyebrow}</p>}
            {title && <h2 className="text-sm font-medium text-ink-100">{title}</h2>}
          </div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}
