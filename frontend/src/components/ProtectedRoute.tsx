import { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Center, Loader, Container, Text, Stack } from '@mantine/core'
import { useAuthStore } from '../store/authStore'
import { useSSO } from '../hooks/useSSO'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, checkAuth } = useAuthStore()
  const { isAuthenticating } = useSSO()
  const location = useLocation()

  useEffect(() => {
    // Check authentication status on mount
    checkAuth()
  }, [checkAuth])

  // Show loading while SSO token is being exchanged
  if (isAuthenticating) {
    return (
      <Container size="lg" py="xl">
        <Center h="50vh">
          <Stack align="center" gap="md">
            <Loader size="xl" />
            <Text c="dimmed">Authenticating via SSO...</Text>
          </Stack>
        </Center>
      </Container>
    )
  }

  if (isLoading) {
    return (
      <Container size="lg" py="xl">
        <Center h="50vh">
          <Loader size="xl" />
        </Center>
      </Container>
    )
  }

  if (!isAuthenticated) {
    // Redirect to login, but save the location they were trying to access
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
