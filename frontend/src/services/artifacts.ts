import { apiJson } from "@/src/lib/apiClient";
import type { ArtifactsResponse } from "@/src/types/results";

export const fetchArtifacts = (folder: string): Promise<ArtifactsResponse> =>
  apiJson<ArtifactsResponse>(
    `/api/artifacts?folder=${encodeURIComponent(folder)}`,
  );
