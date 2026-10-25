// Connects to the API. Every request goes through apiClient; the host must
// never be hardcoded here.
import { apiJson, ApiError } from "@/src/lib/apiClient";
import { ChatListResponse, ChatMessageHistory, ChatPublic } from "../types/type";

// Creates a new chat and obtains a thread_id.
export const addChat = async (): Promise<ChatPublic> =>
  apiJson<ChatPublic>("/api/chat/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

// Deletes a chat.
export const deleteChat = async (id: string) =>
  apiJson(`/api/chat/${id}`, { method: "DELETE" });

// Renames a chat's title.
export const updateTitle = async ({ id, title }: { id: string; title: string }) =>
  apiJson(`/api/chat/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });

// Fetches the chat list.
export const getList = async (): Promise<ChatListResponse> =>
  apiJson<ChatListResponse>("/api/chat/");

// Fetches a chat's history.
export const getHistory = async (id: string): Promise<ChatMessageHistory[]> =>
  apiJson<ChatMessageHistory[]>(`/api/chat/${id}/history`);

// Uploads a file.
export const uploadFile = async ({ file }: { file: File }) => {
  const formData = new FormData();
  formData.append("file", file);

  // Case-insensitive, and matches the same case-insensitive filename
  // extension check UploadFlie.tsx's local precheck uses (that precheck's
  // own isCsv doesn't additionally compare `file.type`, so the MIME-type
  // half of the check below is a broader net specific to this second
  // layer). When a physician uploads data.CSV (uppercase extension), on
  // Windows with Excel installed the browser commonly reports the MIME
  // type as application/vnd.ms-excel rather than text/csv; if the check
  // here were case-sensitive on top of that, it would reject the file
  // again after it already passed the local precheck, and the plain Error
  // thrown would get mapped by the caller to "cannot connect to server",
  // making the physician think it's a dropped connection rather than a
  // filename-case issue.
  const isImage = file.type.toLowerCase().startsWith("image/");
  const isCsv =
    file.name.toLowerCase().endsWith(".csv") || file.type.toLowerCase() === "text/csv";

  if (!isImage && !isCsv) {
    // Thrown as an ApiError (not a plain Error): the caller uniformly
    // branches on `e instanceof ApiError ? e.detail : t("error.network")`,
    // so a "format problem" is never mistaken for a "dropped connection".
    // Under the normal UI flow this branch should already have been
    // blocked by UploadFlie.tsx's local precheck; this is the defensive
    // second layer.
    throw new ApiError(415, "不支援的檔案類型");
  }

  const endpoint = isImage ? "/api/uploads/image" : "/api/uploads/csv";
  return apiJson<{ message: string; file_path: string }>(endpoint, {
    method: "POST",
    body: formData,
  });
};
