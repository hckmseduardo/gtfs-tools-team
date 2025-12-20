import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Button,
  Paper,
  TextInput,
  Textarea,
  Avatar,
  SimpleGrid,
  Badge,
  ActionIcon,
  Divider,
  Box,
  LoadingOverlay,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconEdit, IconTrash, IconPlus, IconTestPipe } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

// Badge options for team customization
const BADGE_OPTIONS = [
  { emoji: '🚌', label: 'Bus' },
  { emoji: '🚇', label: 'Metro' },
  { emoji: '🚊', label: 'Tram' },
  { emoji: '🚈', label: 'Light Rail' },
  { emoji: '🚆', label: 'Train' },
  { emoji: '⛴️', label: 'Ferry' },
  { emoji: '🚡', label: 'Cable Car' },
  { emoji: '🛤️', label: 'Rail' },
  { emoji: '🗺️', label: 'Map' },
  { emoji: '📍', label: 'Location' },
  { emoji: '🎯', label: 'Target' },
  { emoji: '🌐', label: 'Global' },
]

// Helper to get auth headers
const getAuthHeaders = (): HeadersInit => {
  const token = localStorage.getItem('access_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
}

// API functions
const teamSettingsApi = {
  get: async () => {
    const response = await fetch('/api/v1/team/settings', {
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to fetch settings')
    return response.json()
  },
  update: async (data: { name?: string; description?: string; badge?: string }) => {
    const response = await fetch('/api/v1/team/settings', {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify(data)
    })
    if (!response.ok) throw new Error('Failed to update settings')
    return response.json()
  }
}

const webhooksApi = {
  list: async () => {
    const response = await fetch('/api/v1/webhooks', {
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to fetch webhooks')
    return response.json()
  },
  create: async (data: any) => {
    const response = await fetch('/api/v1/webhooks', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data)
    })
    if (!response.ok) throw new Error('Failed to create webhook')
    return response.json()
  },
  delete: async (id: string) => {
    const response = await fetch(`/api/v1/webhooks/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to delete webhook')
  },
  test: async (id: string) => {
    const response = await fetch(`/api/v1/webhooks/${id}/test`, {
      method: 'POST',
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to test webhook')
    return response.json()
  }
}

export default function Settings() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [showCreateWebhook, setShowCreateWebhook] = useState(false)
  const [customBadgeUrl, setCustomBadgeUrl] = useState('')
  const [teamName, setTeamName] = useState('')
  const [teamDescription, setTeamDescription] = useState('')
  const [isEditingTeamInfo, setIsEditingTeamInfo] = useState(false)
  const [newWebhook, setNewWebhook] = useState({
    name: '',
    url: '',
    events: ['feed.imported', 'feed.exported', 'validation.completed'],
    secret: ''
  })

  const { data: teamSettings, isLoading: settingsLoading } = useQuery({
    queryKey: ['team-settings'],
    queryFn: teamSettingsApi.get,
    retry: false,
    meta: {
      onError: () => {
        // Settings API not implemented yet - show placeholder
      }
    }
  })

  const updateTeamSettings = useMutation({
    mutationFn: teamSettingsApi.update,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-settings'] })
      setIsEditingTeamInfo(false)
      notifications.show({
        title: t('common.success'),
        message: t('settings.teamUpdated'),
        color: 'green'
      })
    },
    onError: () => {
      notifications.show({
        title: t('common.error'),
        message: t('settings.updateFailed'),
        color: 'red'
      })
    }
  })

  const { data: webhooks, isLoading: webhooksLoading } = useQuery({
    queryKey: ['webhooks'],
    queryFn: webhooksApi.list,
    retry: false
  })

  const createWebhook = useMutation({
    mutationFn: webhooksApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
      setShowCreateWebhook(false)
      setNewWebhook({ name: '', url: '', events: ['feed.imported', 'feed.exported', 'validation.completed'], secret: '' })
      notifications.show({
        title: t('common.success'),
        message: t('settings.webhookCreated'),
        color: 'green'
      })
    }
  })

  const deleteWebhook = useMutation({
    mutationFn: webhooksApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
      notifications.show({
        title: t('common.success'),
        message: t('settings.webhookDeleted'),
        color: 'green'
      })
    }
  })

  const testWebhook = useMutation({
    mutationFn: webhooksApi.test,
    onSuccess: () => {
      notifications.show({
        title: t('common.success'),
        message: t('settings.webhookTestSent'),
        color: 'green'
      })
    }
  })

  const eventOptions = [
    'feed.imported',
    'feed.exported',
    'feed.updated',
    'validation.completed',
    'validation.failed'
  ]

  const toggleEvent = (event: string) => {
    if (newWebhook.events.includes(event)) {
      setNewWebhook({ ...newWebhook, events: newWebhook.events.filter(e => e !== event) })
    } else {
      setNewWebhook({ ...newWebhook, events: [...newWebhook.events, event] })
    }
  }

  const handleBadgeSelect = (badge: string) => {
    updateTeamSettings.mutate({ badge })
  }

  const handleCustomBadgeSubmit = () => {
    if (customBadgeUrl.trim()) {
      updateTeamSettings.mutate({ badge: customBadgeUrl.trim() })
      setCustomBadgeUrl('')
    }
  }

  const handleClearBadge = () => {
    updateTeamSettings.mutate({ badge: '' })
  }

  const handleEditTeamInfo = () => {
    setTeamName(teamSettings?.name || '')
    setTeamDescription(teamSettings?.description || '')
    setIsEditingTeamInfo(true)
  }

  const handleSaveTeamInfo = () => {
    updateTeamSettings.mutate({
      name: teamName,
      description: teamDescription
    })
  }

  // Get team slug from hostname
  const getTeamSlug = () => {
    const hostname = window.location.hostname
    const parts = hostname.split('.')
    if (parts.length > 1 && parts[0] !== 'localhost') {
      return parts[0]
    }
    return import.meta.env.VITE_TEAM_SLUG || 'Team'
  }

  const teamSlug = getTeamSlug()
  const displayName = teamSettings?.name || teamSlug

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Box>
          <Title order={1}>{t('settings.title')}</Title>
          <Text c="dimmed">{t('settings.description')}</Text>
        </Box>

        {/* Team Profile Section */}
        <Paper withBorder p="lg" pos="relative">
          <LoadingOverlay visible={settingsLoading} />
          <Group justify="space-between" mb="md">
            <Box>
              <Title order={3}>{t('settings.teamProfile')}</Title>
              <Text size="sm" c="dimmed">{t('settings.teamProfileDescription')}</Text>
            </Box>
            {!isEditingTeamInfo && (
              <Button
                variant="subtle"
                leftSection={<IconEdit size={16} />}
                onClick={handleEditTeamInfo}
              >
                {t('common.edit')}
              </Button>
            )}
          </Group>

          <Divider mb="md" />

          {/* Team Name & Description */}
          <Box mb="lg">
            {isEditingTeamInfo ? (
              <Stack gap="md">
                <TextInput
                  label={t('settings.teamName')}
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                  style={{ maxWidth: 400 }}
                />
                <Textarea
                  label={t('settings.teamDescription')}
                  value={teamDescription}
                  onChange={(e) => setTeamDescription(e.target.value)}
                  rows={3}
                  style={{ maxWidth: 500 }}
                  placeholder={t('settings.descriptionPlaceholder')}
                />
                <Group>
                  <Button
                    onClick={handleSaveTeamInfo}
                    loading={updateTeamSettings.isPending}
                  >
                    {t('common.save')}
                  </Button>
                  <Button
                    variant="subtle"
                    onClick={() => setIsEditingTeamInfo(false)}
                  >
                    {t('common.cancel')}
                  </Button>
                </Group>
              </Stack>
            ) : (
              <Group gap="lg" align="flex-start">
                {/* Badge Preview */}
                {teamSettings?.badge ? (
                  teamSettings.badge.startsWith('http') ? (
                    <Avatar
                      src={teamSettings.badge}
                      size={64}
                      radius="md"
                    />
                  ) : (
                    <Avatar size={64} radius="md" color="blue">
                      <Text size="xl">{teamSettings.badge}</Text>
                    </Avatar>
                  )
                ) : (
                  <Avatar size={64} radius="md" color="blue">
                    <Text size="xl" fw={700}>{displayName.charAt(0).toUpperCase()}</Text>
                  </Avatar>
                )}
                <Box>
                  <Title order={4}>{displayName}</Title>
                  <Text c="dimmed" size="sm">{teamSettings?.description || t('settings.noDescription')}</Text>
                </Box>
              </Group>
            )}
          </Box>

          {/* Badge Selection */}
          <Box mb="md">
            <Group justify="space-between" mb="xs">
              <Text fw={500}>{t('settings.teamBadge')}</Text>
              {teamSettings?.badge && (
                <Button
                  variant="subtle"
                  color="red"
                  size="xs"
                  onClick={handleClearBadge}
                >
                  {t('settings.removeBadge')}
                </Button>
              )}
            </Group>

            {/* Predefined Badges */}
            <Text size="sm" c="dimmed" mb="xs">{t('settings.quickSelect')}</Text>
            <SimpleGrid cols={6} spacing="xs" mb="md">
              {BADGE_OPTIONS.map(({ emoji, label }) => (
                <Button
                  key={emoji}
                  variant={teamSettings?.badge === emoji ? 'filled' : 'light'}
                  onClick={() => handleBadgeSelect(emoji)}
                  h={48}
                  p={0}
                  title={label}
                >
                  <Text size="xl">{emoji}</Text>
                </Button>
              ))}
            </SimpleGrid>

            {/* Custom Badge URL */}
            <Text size="sm" c="dimmed" mb="xs">{t('settings.customImageUrl')}</Text>
            <Group>
              <TextInput
                placeholder="https://example.com/badge.png"
                value={customBadgeUrl}
                onChange={(e) => setCustomBadgeUrl(e.target.value)}
                style={{ flex: 1 }}
              />
              <Button
                onClick={handleCustomBadgeSubmit}
                disabled={!customBadgeUrl.trim()}
              >
                {t('common.apply')}
              </Button>
            </Group>
            <Text size="xs" c="dimmed" mt="xs">
              {t('settings.customImageHint')}
            </Text>
          </Box>
        </Paper>

        {/* Webhooks Section */}
        <Paper withBorder p="lg" pos="relative">
          <LoadingOverlay visible={webhooksLoading} />
          <Group justify="space-between" mb="md">
            <Box>
              <Title order={3}>{t('settings.webhooks')}</Title>
              <Text size="sm" c="dimmed">{t('settings.webhooksDescription')}</Text>
            </Box>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => setShowCreateWebhook(true)}
            >
              {t('settings.addWebhook')}
            </Button>
          </Group>

          <Divider mb="md" />

          {/* Create Webhook Form */}
          {showCreateWebhook && (
            <Paper withBorder p="md" mb="md" bg="gray.0">
              <Stack gap="md">
                <TextInput
                  label={t('settings.webhookName')}
                  placeholder="My Webhook"
                  value={newWebhook.name}
                  onChange={(e) => setNewWebhook({ ...newWebhook, name: e.target.value })}
                />
                <TextInput
                  label={t('settings.webhookUrl')}
                  placeholder="https://example.com/webhook"
                  value={newWebhook.url}
                  onChange={(e) => setNewWebhook({ ...newWebhook, url: e.target.value })}
                />
                <TextInput
                  label={t('settings.webhookSecret')}
                  placeholder={t('settings.optional')}
                  value={newWebhook.secret}
                  onChange={(e) => setNewWebhook({ ...newWebhook, secret: e.target.value })}
                />
                <Box>
                  <Text size="sm" fw={500} mb="xs">{t('settings.events')}</Text>
                  <Group gap="xs">
                    {eventOptions.map((event) => (
                      <Badge
                        key={event}
                        variant={newWebhook.events.includes(event) ? 'filled' : 'outline'}
                        style={{ cursor: 'pointer' }}
                        onClick={() => toggleEvent(event)}
                      >
                        {event}
                      </Badge>
                    ))}
                  </Group>
                </Box>
                <Group>
                  <Button
                    onClick={() => createWebhook.mutate(newWebhook)}
                    disabled={!newWebhook.name || !newWebhook.url}
                    loading={createWebhook.isPending}
                  >
                    {t('common.create')}
                  </Button>
                  <Button
                    variant="subtle"
                    onClick={() => setShowCreateWebhook(false)}
                  >
                    {t('common.cancel')}
                  </Button>
                </Group>
              </Stack>
            </Paper>
          )}

          {/* Webhooks List */}
          {!webhooks || webhooks.length === 0 ? (
            <Text c="dimmed" ta="center" py="xl">
              {t('settings.noWebhooks')}
            </Text>
          ) : (
            <Stack gap="sm">
              {webhooks.map((webhook: any) => (
                <Paper key={webhook.id} withBorder p="md">
                  <Group justify="space-between">
                    <Box>
                      <Text fw={500}>{webhook.name}</Text>
                      <Text size="sm" c="dimmed">{webhook.url}</Text>
                      <Group gap="xs" mt="xs">
                        {webhook.events?.map((event: string) => (
                          <Badge key={event} size="xs" variant="light">
                            {event}
                          </Badge>
                        ))}
                      </Group>
                    </Box>
                    <Group gap="xs">
                      <ActionIcon
                        variant="subtle"
                        color="blue"
                        onClick={() => testWebhook.mutate(webhook.id)}
                        loading={testWebhook.isPending}
                        title={t('settings.test')}
                      >
                        <IconTestPipe size={18} />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => deleteWebhook.mutate(webhook.id)}
                        loading={deleteWebhook.isPending}
                        title={t('common.delete')}
                      >
                        <IconTrash size={18} />
                      </ActionIcon>
                    </Group>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}
        </Paper>
      </Stack>
    </Container>
  )
}
