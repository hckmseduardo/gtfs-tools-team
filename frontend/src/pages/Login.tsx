import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { Container, Paper, Title, Text, Button, Stack, Center, Loader } from '@mantine/core'
import { IconLogin } from '@tabler/icons-react'
import { useAuthStore } from '../store/authStore'
import { useSSO } from '../hooks/useSSO'

export default function Login() {
  const { isAuthenticated, isLoading, error, login, clearError } = useAuthStore()
  const { isAuthenticating } = useSSO()

  // Show loading while SSO token is being exchanged
  if (isAuthenticating) {
    return (
      <Container size={420} my={100}>
        <Paper withBorder shadow="md" p={30} radius="md">
          <Center py="xl">
            <Stack align="center" gap="md">
              <Loader size="lg" />
              <Text c="dimmed">Authenticating via SSO...</Text>
            </Stack>
          </Center>
        </Paper>
      </Container>
    )
  }

  useEffect(() => {
    // Clear any previous errors when component mounts
    clearError()
  }, [clearError])

  // If already authenticated, redirect to home
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const handleLogin = () => {
    login()
  }

  return (
    <Container size={420} my={100}>
      <Paper withBorder shadow="md" p={30} radius="md">
        <Stack gap="lg">
          <div>
            <Title order={2} ta="center">
              GTFS Tools
            </Title>
            <Text c="dimmed" size="sm" ta="center" mt={5}>
              Multi-agency GTFS data editor
            </Text>
          </div>

          {error && (
            <Paper bg="red.1" p="md" radius="md">
              <Text c="red" size="sm">
                {error}
              </Text>
            </Paper>
          )}

          {isLoading ? (
            <Center py="xl">
              <Loader size="lg" />
            </Center>
          ) : (
            <Button
              fullWidth
              size="lg"
              leftSection={<IconLogin size={20} />}
              onClick={handleLogin}
            >
              Sign in with Microsoft
            </Button>
          )}
        </Stack>
      </Paper>
    </Container>
  )
}
