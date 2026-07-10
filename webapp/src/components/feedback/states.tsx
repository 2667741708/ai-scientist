import type { PropsWithChildren, ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react";
import { classNames } from "../../lib/formatters/workbench";

export function EmptyState({
  title,
  description,
  className,
  actions,
}: {
  title: string;
  description: string;
  className?: string;
  actions?: ReactNode;
}) {
  return (
    <div className={classNames("state-card", "empty-state-card", className)}>
      <Sparkles size={18} />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {actions ? <div className="state-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

export function LoadingState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="state-card loading-state-card" role="status" aria-busy="true">
      <Loader2 size={18} className="spin" />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  );
}

export function SkeletonState({
  title,
  rows = 3,
}: {
  title: string;
  rows?: number;
}) {
  return (
    <div className="state-card skeleton-state-card" aria-busy="true" aria-label={title}>
      <div className="skeleton-icon" />
      <div className="skeleton-stack">
        {Array.from({ length: rows }).map((_, index) => (
          <span className="skeleton-line" key={index} />
        ))}
      </div>
    </div>
  );
}

export function SuccessState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="state-card success-state-card" role="status">
      <CheckCircle2 size={18} />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  );
}

export function ErrorState({
  title,
  description,
  children,
}: PropsWithChildren<{ title: string; description: string }>) {
  return (
    <div className="state-card error-state-card" role="alert">
      <AlertTriangle size={18} />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {children}
      </div>
    </div>
  );
}

export function StatusBanner({
  tone = "neutral",
  children,
}: PropsWithChildren<{ tone?: "neutral" | "warning" | "ok" | "error" }>) {
  const role = tone === "error" ? "alert" : tone === "ok" || tone === "warning" ? "status" : undefined;
  return (
    <div className={classNames("status-banner", tone)} role={role}>
      {children}
    </div>
  );
}
