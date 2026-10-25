// Use `type` only when a complex type like Union (|), Intersection (&), or Tuple is actually needed.

// export interface ThreadPublic {
//   thread_id: string;
// }

// export interface Message {
//   thread_id: string;
//   title: string;
//   content: string;
//   file_path?: string | null; // `?` marks it optional; `null` marks an empty value
// }




export interface ChatPublic {
  thread_id: string;
  title: string;
  created_at: string;
}

export interface ChatRequest {
  message: string;
  file_path?: string | null;
}

export interface ChatUpdate {
  title?: string | null;
}

export type ChatListResponse = {
  chats: ChatPublic[];
};

export type ChatMessageHistory = {
  id: number;
  thread_id: string;
  role: string;
  content: string | any[]; // Matches the backend's Union type exactly
  created_at: string;
};
