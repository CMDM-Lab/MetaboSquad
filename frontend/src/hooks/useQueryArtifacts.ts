import { useQuery } from "@tanstack/react-query";
import { fetchArtifacts } from "@/src/services/artifacts";

export default function useQueryArtifacts(folder: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["artifacts", folder],
    queryFn: () => fetchArtifacts(folder as string),
    enabled: !!folder && enabled,
    staleTime: 5 * 60 * 1000,
  });
}
