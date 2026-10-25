/** The single source of truth for this project's chat-related React Query keys. */
// The data's identity key. React Query uses it to decide which cache "drawer" this data is stored in.


export const chatQueryKeys = {
  list: () => ["chatList"] as const,
  history: (threadId: string) => ["chatHistory", threadId] as const,
};
