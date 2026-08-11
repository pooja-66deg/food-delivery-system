import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      gcTime: 1000 * 60 * 10, // 10 minutes (garbage collection)
      retry: (failureCount, error: any) => {
        // Retry 5xx errors, not 4xx
        if (error?.status >= 400 && error?.status < 500) {
          return false
        }
        return failureCount < 3
      },
      refetchOnWindowFocus: false, // Avoid aggressive refetching on tab focus
    },
    mutations: {
      retry: 1,
    },
  },
})
