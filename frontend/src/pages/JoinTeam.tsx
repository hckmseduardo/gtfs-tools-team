import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Container,
  Paper,
  Title,
  Text,
  Button,
  Stack,
  Center,
  Loader,
  Alert,
  Badge,
  Group,
  Divider,
} from '@mantine/core'
import { IconUserPlus, IconAlertCircle, IconCheck, IconLogin } from '@tabler/icons-react'
import { teamsApi, TeamInvitationPublic } from '../lib/teams-api'

// Portal URL for authentication - matches the main domain
const PORTAL_DOMAIN = import.meta.env.VITE_PORTAL_DOMAIN || 'app.gtfs-tools.com'
const PORTAL_URL = `https://${PORTAL_DOMAIN}`

export default function JoinTeam() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // Get token from URL - this could be either:
  // 1. An invitation token (first visit) - comes as ?token=...
  // 2. A portal SSO token (callback from portal auth) - comes as ?sso_token=...
  const invitationUrlToken = searchParams.get('token')
  const ssoToken = searchParams.get('sso_token')

  // Check if this is a callback from portal login (we stored invitation token before redirect)
  const storedInvitationToken = localStorage.getItem('pending_invitation_token')

  // If we have a stored invitation token and an SSO token, this is an auth callback
  const isAuthCallback = !!storedInvitationToken && !!ssoToken
  const invitationToken = isAuthCallback ? storedInvitationToken : invitationUrlToken
  const portalToken = isAuthCallback ? ssoToken : null

  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)

  // Fetch invitation details (only if we're NOT in an auth callback)
  const {
    data: invitation,
    isLoading: loadingInvitation,
    error: invitationError,
  } = useQuery({
    queryKey: ['invitation', invitationToken],
    queryFn: async () => {
      if (!invitationToken) throw new Error('No invitation token provided')
      return teamsApi.getInvitationByToken(invitationToken)
    },
    enabled: !!invitationToken && !portalToken, // Don't fetch if we're processing SSO
    retry: false,
  })

  // Accept invitation mutation - now passes user details
  const acceptMutation = useMutation({
    mutationFn: (data: { token: string; userId: string; userEmail: string; userName: string }) =>
      teamsApi.acceptInvitation(data.token, data.userId, data.userName, data.userEmail),
    onSuccess: (response) => {
      setSuccess(true)
      // Store user info for the session
      const member = response.member
      if (member) {
        localStorage.setItem('user_id', String(member.id))
        localStorage.setItem('user_name', member.full_name || '')
        localStorage.setItem('user_email', member.email)
      }
      // Redirect to dashboard after 2 seconds
      setTimeout(() => {
        navigate('/')
      }, 2000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to accept invitation')
      setIsProcessing(false)
    },
  })

  // Handle SSO callback - user returned from portal login
  useEffect(() => {
    const processSSO = async () => {
      if (!portalToken || !invitationToken) return

      setIsProcessing(true)
      try {
        // Exchange portal token for user info
        const response = await teamsApi.exchangeSSOToken(portalToken)
        const user = response.user

        // Clear the stored invitation token
        localStorage.removeItem('pending_invitation_token')

        // Accept the invitation with the authenticated user's details
        acceptMutation.mutate({
          token: invitationToken,
          userId: String(user.id),
          userEmail: user.email,
          userName: user.display_name || user.email.split('@')[0],
        })
      } catch (err: any) {
        localStorage.removeItem('pending_invitation_token')
        setError(err.response?.data?.detail || 'Failed to authenticate. Please try again.')
        setIsProcessing(false)
      }
    }

    processSSO()
  }, [portalToken, invitationToken])

  // Handle login button click - redirect to portal for authentication
  const handleLogin = () => {
    // Store the invitation token before redirecting to portal
    if (invitationToken) {
      localStorage.setItem('pending_invitation_token', invitationToken)
    }

    // Build callback URL - portal will redirect back here with portal token
    const callbackUrl = window.location.href.split('?')[0] // Remove any existing query params

    // Redirect to portal login - it will append token= to the callback URL
    window.location.href = `${PORTAL_URL}/api/auth/login?redirect_url=${encodeURIComponent(callbackUrl)}`
  }

  // Success state
  if (success) {
    return (
      <Container size="xs" my={100}>
        <Paper withBorder shadow="md" p={30} radius="md">
          <Stack align="center" gap="lg">
            <Center
              style={{
                width: 64,
                height: 64,
                borderRadius: '50%',
                backgroundColor: 'var(--mantine-color-green-1)',
              }}
            >
              <IconCheck size={32} color="var(--mantine-color-green-6)" />
            </Center>
            <Title order={2} ta="center">
              Welcome to the Team!
            </Title>
            <Text c="dimmed" ta="center">
              Your account has been linked successfully. Redirecting you to the dashboard...
            </Text>
            <Loader size="sm" />
          </Stack>
        </Paper>
      </Container>
    )
  }

  // Processing state (SSO callback or accepting invitation)
  if (isProcessing || (portalToken && invitationToken)) {
    return (
      <Container size="xs" my={100}>
        <Paper withBorder shadow="md" p={30} radius="md">
          <Stack align="center" gap="lg">
            <Loader size="lg" />
            <Title order={2} ta="center">
              Joining Team...
            </Title>
            <Text c="dimmed" ta="center">
              Please wait while we set up your account.
            </Text>
          </Stack>
        </Paper>
      </Container>
    )
  }

  // Loading invitation state
  if (loadingInvitation) {
    return (
      <Container size="xs" my={100}>
        <Paper withBorder shadow="md" p={30} radius="md">
          <Stack align="center" gap="lg">
            <Loader size="lg" />
            <Text c="dimmed">Loading invitation...</Text>
          </Stack>
        </Paper>
      </Container>
    )
  }

  return (
    <Container size="xs" my={100}>
      <Paper withBorder shadow="md" p={30} radius="md">
        <Stack gap="lg">
          {/* Header */}
          <Stack align="center" gap="xs">
            <Center
              style={{
                width: 64,
                height: 64,
                borderRadius: '50%',
                backgroundColor: 'var(--mantine-color-blue-1)',
              }}
            >
              <IconUserPlus size={32} color="var(--mantine-color-blue-6)" />
            </Center>
            <Title order={2} ta="center">
              Join the Team
            </Title>
            {invitation && (
              <Text c="dimmed" ta="center">
                You've been invited to join{' '}
                <Text component="span" fw={600}>
                  {invitation.team_name}
                </Text>
              </Text>
            )}
          </Stack>

          {/* Error display */}
          {(error || invitationError) && (
            <Alert color="red" icon={<IconAlertCircle />}>
              {error || (invitationError as any)?.response?.data?.detail || 'Invalid or expired invitation'}
            </Alert>
          )}

          {/* No token */}
          {!invitationToken ? (
            <Alert color="yellow" icon={<IconAlertCircle />}>
              No invitation token found. Please use the link from your invitation email.
            </Alert>
          ) : invitation ? (
            <>
              {/* Invitation details */}
              <Paper p="md" bg="gray.0" radius="md">
                <Stack gap="sm">
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      Invited email:
                    </Text>
                    <Text size="sm" fw={500}>
                      {invitation.email}
                    </Text>
                  </Group>
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      Role:
                    </Text>
                    <Badge color="blue" variant="light">
                      {invitation.role}
                    </Badge>
                  </Group>
                  {invitation.invited_by_name && (
                    <Group justify="space-between">
                      <Text size="sm" c="dimmed">
                        Invited by:
                      </Text>
                      <Text size="sm">{invitation.invited_by_name}</Text>
                    </Group>
                  )}
                </Stack>
              </Paper>

              {/* Login button - always show this for team invitations */}
              <Button
                fullWidth
                size="lg"
                leftSection={<IconLogin size={20} />}
                onClick={handleLogin}
              >
                Sign in with Microsoft
              </Button>
              <Divider label="or" />
              <Text size="sm" c="dimmed" ta="center">
                Don't have an account? Sign in with Microsoft to create one automatically.
              </Text>
            </>
          ) : !invitationError ? (
            <Alert color="yellow" icon={<IconAlertCircle />}>
              Loading invitation details...
            </Alert>
          ) : null}

          {/* Footer */}
          <Divider />
          <Text size="xs" c="dimmed" ta="center">
            By joining, you agree to collaborate respectfully with your team members.
          </Text>
        </Stack>
      </Paper>
    </Container>
  )
}
