/** The frontend's single source of truth for the backend address. Hardcoding http://localhost:8000 in any other file is forbidden. */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
