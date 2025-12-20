import { create } from 'zustand'
import { authApi } from '../lib/api'

export interface User {
  id: number
  email: string
  full_name: string
  is_active: boolean
  is_superuser: boolean
  azure_ad_object_id?: string
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isLoading: boolean
  isAuthenticated: boolean
  error: string | null

  // Actions
  setTokens: (accessToken: string, refreshToken: string) => void
  setUser: (user: User) => void
  login: () => void
  handleTokensFromUrl: (token: string, refreshToken: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  isLoading: false,
  isAuthenticated: !!localStorage.getItem('access_token'),
  error: null,

  setTokens: (accessToken: string, refreshToken: string) => {
    localStorage.setItem('access_token', accessToken)
    localStorage.setItem('refresh_token', refreshToken)
    set({ accessToken, refreshToken, isAuthenticated: true })
  },

  setUser: (user: User) => {
    localStorage.setItem('user', JSON.stringify(user))
    set({ user })
  },

  // Redirect to auth based on whether we're on portal or team instance
  login: () => {
    set({ isLoading: true, error: null })

    const hostname = window.location.hostname
    const portalDomain = 'app.gtfs-tools.com'

    // Check if we're on a team subdomain (e.g., testes.app.gtfs-tools.com)
    const isTeamSubdomain = hostname.endsWith(`.${portalDomain}`) && hostname !== portalDomain

    if (isTeamSubdomain) {
      // Team instances: redirect to portal for auth, then portal redirects back with sso_token
      // After auth, portal will redirect to: https://team.domain/?sso_token=xxx
      // The useSSO hook will handle the token exchange
      const portalAuthUrl = `https://${portalDomain}/auth/login`
      const returnUrl = window.location.origin + '/'
      window.location.href = `${portalAuthUrl}?redirect_url=${encodeURIComponent(returnUrl)}`
    } else {
      // Portal domain: use local auth endpoint with Traefik rewrite
      // /api/v1/auth/entra/login gets rewritten to /auth/login on portal-api
      const callbackUrl = `${window.location.origin}/auth/callback`
      window.location.href = `/api/v1/auth/entra/login?redirect_url=${encodeURIComponent(callbackUrl)}`
    }
  },

  // Handle tokens received from URL after OAuth redirect
  handleTokensFromUrl: async (token: string, refreshToken: string) => {
    try {
      set({ isLoading: true, error: null })

      // Store tokens
      get().setTokens(token, refreshToken)

      // Fetch user info
      const userData = await authApi.getCurrentUser()
      get().setUser(userData)

      set({ isLoading: false })
    } catch (error: any) {
      set({
        error: error.response?.data?.detail || 'Failed to complete authentication',
        isLoading: false,
        isAuthenticated: false,
      })
      throw error
    }
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      error: null,
    })
  },

  checkAuth: async () => {
    const accessToken = localStorage.getItem('access_token')
    const storedUser = localStorage.getItem('user')

    if (!accessToken) {
      set({ isAuthenticated: false, user: null })
      return
    }

    try {
      set({ isLoading: true })

      // If we have a stored user, use it temporarily
      if (storedUser) {
        set({ user: JSON.parse(storedUser) })
      }

      // Fetch fresh user data
      const userData = await authApi.getCurrentUser()
      get().setUser(userData)

      set({
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (error) {
      // Token is invalid
      get().logout()
      set({ isLoading: false })
    }
  },

  clearError: () => set({ error: null }),
}))
