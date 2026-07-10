import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../../lib/api/workbench";
import { queryKeys } from "../../lib/constants/queryKeys";

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
