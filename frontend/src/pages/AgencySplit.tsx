import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Paper,
  Stack,
  Select,
  MultiSelect,
  TextInput,
  Textarea,
  Button,
  Alert,
  Group,
  Text,
  Switch,
  LoadingOverlay,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconAlertCircle, IconGitBranch } from '@tabler/icons-react'
import { useNavigate } from 'react-router-dom'
import { agencyOperationsApi } from '../lib/agency-operations-api'
import { agencyApi } from '../lib/gtfs-api'
import { feedApi } from '../lib/feed-api'
import { routesApi } from '../lib/gtfs-api'

interface Agency {
  id: number
  name: string
}

interface Feed {
  id: number
  name: string
  agency_id: number
}

interface Route {
  id: number
  route_id: string
  route_short_name: string
  route_long_name: string
}

export default function AgencySplit() {
  const navigate = useNavigate()
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [loading, setLoading] = useState(false)

  const [selectedAgencyId, setSelectedAgencyId] = useState<string | null>(null)
  const [selectedFeedId, setSelectedFeedId] = useState<string | null>(null)
  const [selectedRouteIds, setSelectedRouteIds] = useState<string[]>([])
  const [newAgencyName, setNewAgencyName] = useState('')
  const [newAgencyDescription, setNewAgencyDescription] = useState('')
  const [newFeedName, setNewFeedName] = useState('Initial Feed')
  const [copyUsers, setCopyUsers] = useState(false)
  const [removeFromSource, setRemoveFromSource] = useState(false)

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgencyId) {
      loadFeeds(Number(selectedAgencyId))
    } else {
      setFeeds([])
      setSelectedFeedId(null)
    }
  }, [selectedAgencyId])

  useEffect(() => {
    if (selectedFeedId) {
      loadRoutes(Number(selectedFeedId))
      // Set the new feed name to the selected feed's name
      const selectedFeed = feeds.find(f => f.id.toString() === selectedFeedId)
      if (selectedFeed) {
        setNewFeedName(selectedFeed.name)
      }
    } else {
      setRoutes([])
      setSelectedRouteIds([])
      setNewFeedName('Initial Feed')
    }
  }, [selectedFeedId, feeds])

  const loadAgencies = async () => {
    try {
      const response = await agencyApi.list({ limit: 1000 })
      setAgencies(response.items || [])
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load agencies',
        color: 'red',
      })
    }
  }

  const loadFeeds = async (agencyId: number) => {
    try {
      const response = await feedApi.list({ agency_id: agencyId })
      setFeeds(response.feeds)
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load feeds',
        color: 'red',
      })
    }
  }

  const loadRoutes = async (feedId: number) => {
    try {
      const response = await routesApi.list(feedId, { limit: 10000 })
      setRoutes(response.items || [])
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load routes',
        color: 'red',
      })
    }
  }

  const handleSplit = async () => {
    if (!selectedAgencyId || !selectedFeedId || selectedRouteIds.length === 0) {
      notifications.show({
        title: 'Validation Error',
        message: 'Please select agency, feed, and at least one route',
        color: 'red',
      })
      return
    }

    if (!newAgencyName.trim()) {
      notifications.show({
        title: 'Validation Error',
        message: 'Please enter a name for the new agency',
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      const response = await agencyOperationsApi.executeSplit(Number(selectedAgencyId), {
        feed_id: Number(selectedFeedId),
        route_ids: selectedRouteIds,
        new_agency_name: newAgencyName,
        new_agency_description: newAgencyDescription,
        new_feed_name: newFeedName,
        copy_users: copyUsers,
        remove_from_source: removeFromSource,
      })

      notifications.show({
        title: 'Split Started',
        message: response.message,
        color: 'blue',
      })

      navigate('/tasks')
    } catch (error: any) {
      notifications.show({
        title: 'Split Failed',
        message: error.response?.data?.detail || 'Failed to start split',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const agencyOptions = agencies.map((agency) => ({
    value: agency.id.toString(),
    label: agency.name,
  }))

  const feedOptions = feeds.map((feed) => ({
    value: feed.id.toString(),
    label: feed.name,
  }))

  const routeOptions = routes.map((route) => ({
    value: route.route_id,
    label: `${route.route_short_name || route.route_id} - ${route.route_long_name}`,
  }))

  return (
    <Container size="lg">
      <Stack gap="md">
        <Title order={2}>Split Agency</Title>

        <Paper p="md" withBorder>
          <LoadingOverlay visible={loading} />

          <Stack gap="md">
            <Alert icon={<IconAlertCircle />} title="Important" color="blue">
              Splitting an agency creates a new agency with selected routes and their dependencies.
              You can optionally remove the routes from the source agency.
            </Alert>

            <Select
              label="Source Agency"
              description="Select the agency to split from"
              placeholder="Select agency"
              data={agencyOptions}
              value={selectedAgencyId}
              onChange={setSelectedAgencyId}
              searchable
              required
            />

            {selectedAgencyId && (
              <Select
                label="Source Feed"
                description="Select the feed containing routes to split"
                placeholder="Select feed"
                data={feedOptions}
                value={selectedFeedId}
                onChange={setSelectedFeedId}
                searchable
                required
              />
            )}

            {selectedFeedId && (
              <MultiSelect
                label="Routes to Split"
                description="Select one or more routes to move to new agency"
                placeholder="Select routes"
                data={routeOptions}
                value={selectedRouteIds}
                onChange={setSelectedRouteIds}
                searchable
                required
              />
            )}

            <TextInput
              label="New Agency Name"
              description="Name for the new agency"
              placeholder="e.g., Express Transit"
              value={newAgencyName}
              onChange={(e) => setNewAgencyName(e.target.value)}
              required
            />

            <Textarea
              label="New Agency Description"
              description="Optional description"
              placeholder="Express bus routes"
              value={newAgencyDescription}
              onChange={(e) => setNewAgencyDescription(e.target.value)}
              minRows={2}
            />

            <TextInput
              label="New Feed Name"
              description="Name for the initial feed in new agency"
              value={newFeedName}
              onChange={(e) => setNewFeedName(e.target.value)}
              required
            />

            <Switch
              label="Copy Users"
              description="Copy users from source agency to new agency"
              checked={copyUsers}
              onChange={(e) => setCopyUsers(e.currentTarget.checked)}
            />

            <Switch
              label="Remove from Source"
              description="Remove selected routes from source agency after split"
              checked={removeFromSource}
              onChange={(e) => setRemoveFromSource(e.currentTarget.checked)}
              color="red"
            />

            {selectedRouteIds.length > 0 && (
              <Alert icon={<IconAlertCircle />} title="Split Preview" color="blue">
                <Text size="sm">
                  You are about to create a new agency "<strong>{newAgencyName || '(not set)'}</strong>" with{' '}
                  <strong>{selectedRouteIds.length}</strong> route{selectedRouteIds.length !== 1 ? 's' : ''}.
                </Text>
                <Text size="sm" mt="xs">
                  The system will automatically copy all associated trips, stops, calendars, and shapes.
                </Text>
                {removeFromSource && (
                  <Text size="sm" mt="xs" c="red">
                    <strong>Warning:</strong> These routes will be removed from the source agency.
                  </Text>
                )}
              </Alert>
            )}

            <Group justify="flex-end">
              <Button variant="default" onClick={() => navigate(-1)}>
                Cancel
              </Button>
              <Button
                leftSection={<IconGitBranch size={16} />}
                onClick={handleSplit}
                loading={loading}
                disabled={!selectedAgencyId || !selectedFeedId || selectedRouteIds.length === 0 || !newAgencyName}
              >
                Execute Split
              </Button>
            </Group>
          </Stack>
        </Paper>
      </Stack>
    </Container>
  )
}
