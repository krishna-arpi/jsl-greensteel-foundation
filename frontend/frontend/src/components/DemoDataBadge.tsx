interface DemoDataBadgeProps {
  label?: string;
  className?: string;
}

/**
 * Flags any figure, panel, or section derived from placeholder data.
 * Used pervasively per project requirement: never let a demo value pass
 * as verified without visual disclosure.
 */
export default function DemoDataBadge({ label = "DEMO DATA", className = "" }: DemoDataBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border border-ember-500/40 bg-ember-500/10 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-ember-400 ${className}`}
    >
      <span className="h-1 w-1 rounded-full bg-ember-500" />
      {label}
    </span>
  );
}
