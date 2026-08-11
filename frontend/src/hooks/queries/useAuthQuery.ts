import { useQuery } from '@tanstack/react-query'
import { authApi } from '../../api/auth'
// Note: User type import removed - not needed for this hook

export function useCurrentUser() {
  const token = localStorage.getItem('fd_access_token')

  return useQuery({
    queryKey: ['user', 'current'],
    queryFn: () => authApi.me(),
    enabled: !!token, // Only fetch if token exists
    staleTime: 1000 * 60 * 30, // 30 minutes
  })
}
