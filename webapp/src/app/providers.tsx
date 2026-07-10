import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useState } from "react";
import { AuthProvider } from "../features/auth/auth-context";
import { WorkbenchProvider } from "../features/runs/workbench-context";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WorkbenchProvider>{children}</WorkbenchProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
