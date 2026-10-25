import { useQuery } from "@tanstack/react-query";
import { getList } from "@/src/services/post";
import { chatQueryKeys } from "@/src/queryKeys/chat";

export default function useQueryChatList() {
  return useQuery({
    queryKey: chatQueryKeys.list(), // The query's identity key: ["chatList"]
    queryFn: getList, // The function responsible for fetching the data: getList
  });
}
