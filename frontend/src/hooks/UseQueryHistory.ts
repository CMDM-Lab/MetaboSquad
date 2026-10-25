import { useQuery } from "@tanstack/react-query";
import { getHistory } from "../services/post";
import { chatQueryKeys } from "@/src/queryKeys/chat";

export default function useQueryHistory(thread_id: string) {
  return useQuery({
    queryKey: chatQueryKeys.history(thread_id),
    queryFn: () => getHistory(thread_id),
    enabled: !!thread_id, // Only fetches once the URL actually has an ID
  });
}