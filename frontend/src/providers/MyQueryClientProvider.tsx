"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { QueryClient } from "@tanstack/react-query";

// Creates a QueryClient instance responsible for managing the whole application's cache and API request state.
const queryClient = new QueryClient();

export default function MyQueryClientProvider({ children }: Readonly<{ children: React.ReactNode; }>) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

