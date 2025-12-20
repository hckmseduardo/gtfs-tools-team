import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Container, Center, Loader, Text, Stack, Paper } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useAuthStore } from '../store/authStore'

export default function AuthCallback() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { handleTokensFromUrl, error } = useAuthStore()

  useEffect(() => {
    const processCallback = async () => {
      // Get tokens from URL (sent by backend after OAuth)
      const token = searchParams.get('token')
      const refreshToken = searchParams.get('refresh_token')
      const errorParam = searchParams.get('error')

      // Check for OAuth errors
      if (errorParam) {
        notifications.show({
          title: 'Authentication Error',
          message: decodeURIComponent(errorParam),
          color: 'red',
        })
        navigate('/login', { replace: true })
        return
      }

      // Check if we have at least the access token
      if (!token) {
        notifications.show({
          title: 'Authentication Error',
          message: 'No authentication token received',
          color: 'red',
        })
        navigate('/login', { replace: true })
        return
      }

      try {
        // Store tokens and fetch user info (refresh_token may be empty for portal auth)
        await handleTokensFromUrl(token, refreshToken || '')

        // Success! Redirect to home
        notifications.show({
          title: 'Welcome!',
          message: 'Successfully signed in',
          color: 'green',
        })
        navigate('/', { replace: true })
      } catch (error: any) {
        console.error('Authentication callback error:', error)
        notifications.show({
          title: 'Authentication Failed',
          message: error.response?.data?.detail || 'Failed to complete sign in',
          color: 'red',
        })
        navigate('/login', { replace: true })
      }
    }

    processCallback()
  }, [searchParams, handleTokensFromUrl, navigate])

  return (
    <Container size={420} my={100}>
      <Paper withBorder shadow="md" p={30} radius="md">
        <Stack gap="lg" align="center">
          {error ? (
            <>
              <Text size="lg" fw={500} c="red">
                Authentication Error
              </Text>
              <Text c="dimmed" ta="center">
                {error}
              </Text>
              <Text c="dimmed" size="sm" ta="center">
                Redirecting to login...
              </Text>
            </>
          ) : (
            <>
              <Center>
                <Loader size="lg" />
              </Center>
              <Text size="lg" fw={500}>
                Completing sign in...
              </Text>
              <Text c="dimmed" size="sm" ta="center">
                Please wait while we complete your authentication
              </Text>
            </>
          )}
        </Stack>
      </Paper>
    </Container>
  )
}
