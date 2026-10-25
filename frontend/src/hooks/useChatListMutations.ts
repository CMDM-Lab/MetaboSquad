"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { deleteChat, updateTitle } from "@/src/services/post";
import { chatQueryKeys } from "@/src/queryKeys/chat";

type UseChatListMutationsOptions = {
  activeThreadId?: string;
};

export function useChatListMutations(options: UseChatListMutationsOptions = {}) {
  const { activeThreadId } = options; // Tracks which conversation the user is currently viewing.
  const queryClient = useQueryClient();
  const router = useRouter();

  const deleteChatMutation = useMutation({
    mutationFn: (threadId: string) => deleteChat(threadId),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.list() });
      if (activeThreadId === deletedId) {
        router.push("/chat");
      }
    },
  });

  const updateTitleMutation = useMutation({
    mutationFn: (payload: { id: string; title: string }) => updateTitle(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.list() });
    },
  });

  return {
    deleteChatMutation,
    updateTitleMutation,
  };
}
