import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { HomePage } from "../pages/home/HomePage";
import { LoginPage } from "../pages/login/LoginPage";
import { ProjectsPage } from "../pages/projects/ProjectsPage";
import { ProjectDetailPage } from "../pages/projects/ProjectDetailPage";
import { WorkflowsPage } from "../pages/workflows/WorkflowsPage";
import { ToolsPage } from "../pages/tools/ToolsPage";
import { DataPage } from "../pages/data/DataPage";
import { ProjectKnowledgePage } from "../pages/project-chat/ProjectKnowledgePage";
import { WorkspacePage } from "../pages/workspace/WorkspacePage";
import { OutputsPage } from "../pages/outputs/OutputsPage";
import { AdminPage } from "../pages/admin/AdminPage";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import LatticeResearchApp from "../lattice/LatticeResearchApp";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/lattice",
    element: (
      <ProtectedRoute>
        <LatticeResearchApp />
      </ProtectedRoute>
    ),
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/home" replace /> },
      { path: "home", element: <HomePage /> },
      { path: "workflows", element: <WorkflowsPage /> },
      { path: "tools", element: <ToolsPage /> },
      { path: "data", element: <DataPage /> },
      { path: "project-chat", element: <ProjectKnowledgePage /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "projects/:projectId", element: <ProjectDetailPage /> },
      { path: "projects/:projectId/papers", element: <ProjectDetailPage /> },
      { path: "projects/:projectId/hypotheses", element: <ProjectDetailPage /> },
      { path: "projects/:projectId/experiments", element: <ProjectDetailPage /> },
      { path: "projects/:projectId/reports", element: <ProjectDetailPage /> },
      { path: "library", element: <Navigate to="/data" replace /> },
      { path: "library/papers", element: <Navigate to="/data?view=papers" replace /> },
      { path: "library/references", element: <Navigate to="/data?view=references" replace /> },
      { path: "workspace", element: <WorkspacePage /> },
      { path: "workspace/:projectId", element: <WorkspacePage /> },
      { path: "outputs", element: <OutputsPage /> },
      {
        path: "admin",
        element: (
          <ProtectedRoute role="admin">
            <AdminPage />
          </ProtectedRoute>
        ),
      },
      { path: "settings", element: <Navigate to="/admin" replace /> },
    ],
  },
]);
