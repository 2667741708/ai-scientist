import { Brain, LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { PrimaryNav } from "../../components/navigation/PrimaryNav";
import { useAuth } from "../../features/auth/auth-context";
import { ResearchChatLauncher } from "../../features/research-chat/ResearchChatDrawer";
import { classNames, copy } from "../../lib/formatters/workbench";
import { useRouteEntranceMotion } from "../../lib/motion/useAnimeEntrance";
import { AppSidePanel } from "./AppSidePanel";

const SIDE_PANEL_STORAGE_KEY = "coscientist.sidePanelOpen";

function readStoredSidePanelState() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SIDE_PANEL_STORAGE_KEY) === "true";
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const workspaceRef = useRef<HTMLElement | null>(null);
  const [sidePanelOpen, setSidePanelOpen] = useState(readStoredSidePanelState);
  const isProjectChatRoute = location.pathname.startsWith("/project-chat");
  useRouteEntranceMotion(workspaceRef, location.pathname);

  useEffect(() => {
    window.localStorage.setItem(SIDE_PANEL_STORAGE_KEY, String(sidePanelOpen));
  }, [sidePanelOpen]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if (!event.ctrlKey || !event.altKey || event.key.toLowerCase() !== "b") return;
      event.preventDefault();
      setSidePanelOpen((open) => !open);
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  const handleSignOut = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

  return (
    <div className={classNames("app-shell", sidePanelOpen && "side-panel-open")}>
      <aside className="nav-rail">
        <div className="brand-block">
          <div className="brand-mark">
            <Brain size={20} />
          </div>
          <div>
            <strong>开放共研</strong>
            <span>{copy.railSubtitle}</span>
          </div>
        </div>
        <PrimaryNav />
        <div className="rail-account-card" aria-label="当前账号">
          <span>{user?.role === "admin" ? "管理员" : "研究员"}</span>
          <strong>{user?.display_name || user?.email}</strong>
          <small>{user?.email}</small>
          <button className="button-ghost" type="button" onClick={handleSignOut}>
            <LogOut size={16} />
            退出
          </button>
        </div>
        <div className="rail-footer">实时文献支撑科研工作台</div>
      </aside>
      <main className="workspace" ref={workspaceRef}>
        <Outlet />
      </main>
      <AppSidePanel
        open={sidePanelOpen}
        onClose={() => setSidePanelOpen(false)}
        onToggle={() => setSidePanelOpen((open) => !open)}
      />
      {isProjectChatRoute ? null : <ResearchChatLauncher />}
    </div>
  );
}
