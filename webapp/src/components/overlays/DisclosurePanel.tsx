import type { PropsWithChildren } from "react";

export function DisclosurePanel({
  open,
  onToggle,
  label,
  meta,
  children,
}: PropsWithChildren<{
  open: boolean;
  onToggle: () => void;
  label: string;
  meta: string;
}>) {
  return (
    <div className="audit-disclosure">
      <button
        className="audit-toggle"
        type="button"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span>{label}</span>
        <em>{meta}</em>
      </button>
      {open ? <div className="audit-body">{children}</div> : null}
    </div>
  );
}
