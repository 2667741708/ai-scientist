import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  kicker,
  actions,
}: {
  title: string;
  description?: string;
  kicker?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        {kicker && <span>{kicker}</span>}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  );
}
