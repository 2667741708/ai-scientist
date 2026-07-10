import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingState, StatusBanner } from "../../components/feedback/states";
import { useAuth } from "./auth-context";
import type { AccountRole } from "../../types/workbench";

export function ProtectedRoute({
  children,
  role,
}: PropsWithChildren<{
  role?: AccountRole;
}>) {
  const { loading, isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (loading) {
    return <LoadingState title="正在验证登录状态" description="正在确认当前账号和工作区权限。" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ redirectTo: location.pathname + location.search }} />;
  }

  if (role && user?.role !== role) {
    return (
      <div className="page-stack">
        <StatusBanner tone="warning">当前账号没有访问该控制面的权限，请联系管理员授予角色。</StatusBanner>
      </div>
    );
  }

  return <>{children}</>;
}
