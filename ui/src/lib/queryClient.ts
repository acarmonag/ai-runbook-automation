import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
