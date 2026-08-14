import { createContext, useContext } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getMe } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const queryClient = useQueryClient()

  const { data: user, isLoading, error } = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    // A 401 simply means "signed out" — retrying it just delays the login page.
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const signOut = async () => {
    await fetch('/api/auth/logout', { method: 'POST', redirect: 'manual' })
    queryClient.clear()
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider
      value={{ user: user ?? null, isLoading, error, signOut, isAdmin: !!user?.is_admin }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
