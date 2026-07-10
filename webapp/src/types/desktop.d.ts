export type DesktopServiceState = "unknown" | "starting" | "ready" | "error" | "conflict" | "stopped";

export type DesktopRuntimeService = {
  name: string;
  port: number | null;
  state: DesktopServiceState;
  managed: boolean;
  message: string;
};

export type DesktopRuntimeStatus = {
  workspaceRoot: string;
  webUrl: string;
  services: Record<string, DesktopRuntimeService>;
};

export type DesktopTerminalSessionInfo = {
  id: string;
  cwd: string;
  shell: string;
};

export type DesktopTerminalCreateOptions = {
  cols?: number;
  rows?: number;
  cwd?: string;
};

export type DesktopBridge = {
  appInfo: () => Promise<{
    workspaceRoot: string;
    platform: string;
    arch: string;
    node: string;
    electron: string;
    shell: string;
    webUrl: string;
    staticServerPort: number | null;
  }>;
  serviceStatus: () => Promise<DesktopRuntimeStatus>;
  onServiceStatus: (callback: (status: DesktopRuntimeStatus) => void) => () => void;
  checkPorts: (ports: Array<number | string>) => Promise<Array<{ port: number; host: string; listening: boolean }>>;
  openExternal: (url: string) => Promise<boolean>;
  terminal: {
    create: (options?: DesktopTerminalCreateOptions) => Promise<DesktopTerminalSessionInfo>;
    list: () => Promise<DesktopTerminalSessionInfo[]>;
    write: (payload: { id: string; data: string }) => void;
    resize: (payload: { id: string; cols: number; rows: number }) => void;
    dispose: (payload: { id: string }) => void;
    onData: (callback: (payload: { id: string; data: string }) => void) => () => void;
    onExit: (callback: (payload: { id: string; exitCode: number }) => void) => () => void;
  };
};

declare global {
  interface Window {
    coscientist?: DesktopBridge;
  }
}

export {};

