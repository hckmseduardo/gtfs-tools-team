import { useEffect, useState, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useSSO() {
  const [searchParams, setSearchParams] = useSearchParams()
  const ssoToken = searchParams.get('sso_token')

  // Initialize isAuthenticating to true if there's a token
  // This prevents the race condition where redirect happens before useEffect runs
  const [isAuthenticating, setIsAuthenticating] = useState(!!ssoToken)
  const exchangeStartedRef = useRef(false)

  useEffect(() => {
    if (ssoToken && !exchangeStartedRef.current) {
      exchangeStartedRef.current = true

      // Exchange SSO token for team JWT via team's SSO endpoint
      exchangeToken(ssoToken)
        .then((data) => {
          // Store the tokens (matching authStore format)
          localStorage.setItem('access_token', data.access_token)
          if (data.refresh_token) {
            localStorage.setItem('refresh_token', data.refresh_token)
          }

          // Remove sso_token from URL
          searchParams.delete('sso_token')
          setSearchParams(searchParams, { replace: true })

          // Reload to apply auth
          window.location.reload()
        })
        .catch((error) => {
          console.error('SSO token exchange failed:', error)
          // Remove invalid token from URL
          searchParams.delete('sso_token')
          setSearchParams(searchParams, { replace: true })
          setIsAuthenticating(false)
        })
    }
  }, [ssoToken, searchParams, setSearchParams])

  return { isAuthenticating }
}

async function exchangeToken(ssoToken: string) {
  // Call team's SSO endpoint to exchange cross-domain token for team JWT
  // The team API will verify the token using CROSS_DOMAIN_SECRET,
  // create/sync the user, and return team-valid JWT tokens
  const apiUrl = import.meta.env.VITE_API_URL || '/api/v1'
  const response = await fetch(`${apiUrl}/auth/sso?token=${ssoToken}`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Token exchange failed' }))
    throw new Error(error.detail || 'Token exchange failed')
  }

  return response.json()
}
