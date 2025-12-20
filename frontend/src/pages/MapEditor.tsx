import { useState, useEffect } from 'react'
import { Container, Title, Text, Stack, Paper, Group, LoadingOverlay, Select, Badge, Button, SegmentedControl } from '@mantine/core'
import { IconMapPin, IconDatabase, IconEdit, IconEye, IconRoute } from '@tabler/icons-react'
import { agencyApi, type Agency } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { api } from '../lib/api'
import FeedSelector from '../components/FeedSelector'
import EditableMap from '../components/EditableMap'
import ShapeEditor from '../components/ShapeEditor'

type EditorMode = 'stops' | 'shapes'
type SetEditorModeFn = (mode: EditorMode) => void

interface MapEditorProps {
  forceEditMode?: boolean
  editorModeOverride?: EditorMode
  onEditorModeChange?: SetEditorModeFn
}

interface Stop {
  id: number
  stop_id: string
  stop_name: string
  stop_lat: number
  stop_lon: number
  stop_desc?: string
  location_type?: number
}

export default function MapEditor({ forceEditMode, editorModeOverride, onEditorModeChange }: MapEditorProps) {
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [stops, setStops] = useState<Stop[]>([])
  const [loading, setLoading] = useState(false)
  const [editMode, setEditMode] = useState(forceEditMode ?? false)
  const [editorMode, setEditorMode] = useState<EditorMode>(editorModeOverride || 'stops')
  const activeEditMode = forceEditMode ?? editMode

  // Map state
  const [mapCenter, setMapCenter] = useState<[number, number]>([40.7128, -74.006])
  const [mapZoom, setMapZoom] = useState(11)

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (forceEditMode !== undefined) {
      setEditMode(forceEditMode)
    }
  }, [forceEditMode])

  useEffect(() => {
    if (editorModeOverride) {
      setEditorMode(editorModeOverride)
    }
  }, [editorModeOverride])

  useEffect(() => {
    if (selectedFeed) {
      loadStopsByFeed(parseInt(selectedFeed))
    } else if (selectedAgency) {
      loadStopsByAgency(selectedAgency)
    } else {
      setStops([])
    }
  }, [selectedFeed, selectedAgency])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
      const activeAgencies = (data.items || []).filter((a: Agency) => a.is_active)
      if (activeAgencies.length > 0) {
        setSelectedAgency(activeAgencies[0].id)
      }
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load agencies',
        color: 'red',
      })
    }
  }

  const loadStopsByAgency = async (agencyId: number) => {
    setLoading(true)
    try {
      const response = await api.get(`/stops/?agency_id=${agencyId}&limit=10000`)
      const stopsData = response.data.items || []
      setStops(stopsData)

      if (stopsData.length > 0) {
        const firstStop = stopsData[0]
        setMapCenter([Number(firstStop.stop_lat), Number(firstStop.stop_lon)])
        setMapZoom(12)
      }
    } catch (error: any) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load stops',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const loadStopsByFeed = async (feedId: number) => {
    setLoading(true)
    try {
      const response = await api.get(`/stops/?feed_id=${feedId}&limit=10000`)
      const stopsData = response.data.items || []
      setStops(stopsData)

      if (stopsData.length > 0) {
        const firstStop = stopsData[0]
        setMapCenter([Number(firstStop.stop_lat), Number(firstStop.stop_lon)])
        setMapZoom(12)
      }
    } catch (error: any) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load stops',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleStopCreated = (newStop: Stop) => {
    setStops([...stops, newStop])
  }

  const handleStopUpdated = (updatedStop: Stop) => {
    setStops(stops.map(s => s.id === updatedStop.id ? updatedStop : s))
  }

  const handleStopDeleted = (stopId: number) => {
    setStops(stops.filter(s => s.id !== stopId))
  }

  const getEditorDescription = () => {
    if (!activeEditMode) {
      return editorMode === 'stops'
        ? 'Enable edit mode to modify stops'
        : 'Enable edit mode to modify shapes'
    }
    return editorMode === 'stops'
      ? 'Click on the map to create stops, or click existing stops to edit them'
      : 'Select a shape to edit or create a new one'
  }

  return (
    <Container size="100%" px={0} style={{ height: 'calc(100vh - 60px)' }}>
      <Stack gap={0} style={{ height: '100%' }}>
        {/* Header */}
        <Paper shadow="xs" p="md" style={{ zIndex: 2000, position: 'relative' }}>
          <Group justify="space-between">
            <div>
              <Title order={2}>Interactive Map Editor</Title>
              <Text size="sm" c="dimmed">
                {getEditorDescription()}
              </Text>
            </div>
            <Group>
              <SegmentedControl
                value={editorMode}
                onChange={(value) => {
                  const mode = value as EditorMode
                  setEditorMode(mode)
                  onEditorModeChange?.(mode)
                }}
                data={[
                  { value: 'stops', label: 'Stops' },
                  { value: 'shapes', label: 'Shapes' },
                ]}
                disabled={activeEditMode}
              />
              <Select
                placeholder="Select Agency"
                data={agencies
                  .filter(a => a.is_active)
                  .map(a => ({ value: a.id.toString(), label: a.name }))}
                value={selectedAgency ? selectedAgency.toString() : null}
                onChange={(value) => setSelectedAgency(value ? parseInt(value) : null)}
                searchable
                clearable
                nothingFoundMessage="No agencies found"
                style={{ minWidth: 250 }}
                styles={{
                  dropdown: {
                    zIndex: 3000,
                  }
              }}
                disabled={agencies.filter(a => a.is_active).length === 0 || activeEditMode}
              />
              <FeedSelector
                agencyId={selectedAgency}
                value={selectedFeed}
                onChange={setSelectedFeed}
                showAllOption={editorMode === 'stops'}
                style={{ minWidth: 300 }}
                disabled={activeEditMode}
              />
            <Button
              leftSection={activeEditMode ? <IconEye size={18} /> : <IconEdit size={18} />}
              color={activeEditMode ? 'red' : 'blue'}
              variant={activeEditMode ? 'filled' : 'light'}
              onClick={() => {
                if (forceEditMode) return
                setEditMode(!activeEditMode)
              }}
              disabled={!selectedAgency || !selectedFeed || forceEditMode}
            >
              {activeEditMode ? 'Exit Edit Mode' : 'Enter Edit Mode'}
            </Button>
          </Group>
        </Group>
        {selectedAgency && (
          <Group mt="xs" gap="xs">
            {editorMode === 'stops' ? (
              <Badge leftSection={<IconMapPin size={14} />} color={activeEditMode ? 'orange' : 'blue'}>
                {stops.length} Stops {activeEditMode && '(Editable)'}
              </Badge>
            ) : (
              <Badge leftSection={<IconRoute size={14} />} color={activeEditMode ? 'orange' : 'green'}>
                Shape Editor {activeEditMode && '(Active)'}
              </Badge>
            )}
            {selectedFeed ? (
              <Badge leftSection={<IconDatabase size={14} />} color="violet">
                Specific Feed
              </Badge>
            ) : (
              <Badge leftSection={<IconDatabase size={14} />} color="gray">
                All Active Feeds
              </Badge>
            )}
            {activeEditMode && (
              <Badge color="orange" variant="filled">
                Edit Mode Active
              </Badge>
            )}
          </Group>
        )}
        </Paper>

        {/* Map Container */}
        <div style={{ flex: 1, position: 'relative' }}>
          <LoadingOverlay visible={loading} />
          {selectedAgency && selectedFeed ? (
            editorMode === 'stops' ? (
              <EditableMap
                center={mapCenter}
                zoom={mapZoom}
                stops={stops}
                onStopCreated={handleStopCreated}
                onStopUpdated={handleStopUpdated}
                onStopDeleted={handleStopDeleted}
                agencyId={selectedAgency}
                feedId={selectedFeed ? parseInt(selectedFeed) : null}
                editMode={activeEditMode}
              />
            ) : (
              <ShapeEditor
                center={mapCenter}
                zoom={mapZoom}
                feedId={parseInt(selectedFeed)}
                editMode={activeEditMode}
              />
            )
          ) : (
            <Paper
              shadow="md"
              p="xl"
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                zIndex: 1000,
                textAlign: 'center'
              }}
            >
              <Stack align="center" gap="xs">
                {editorMode === 'stops' ? (
                  <IconMapPin size={48} color="gray" />
                ) : (
                  <IconRoute size={48} color="gray" />
                )}
                <Text size="lg" fw={500}>Select Agency and Feed</Text>
                <Text size="sm" c="dimmed">
                  {!selectedAgency
                    ? 'Please select an agency to begin'
                    : 'Please select a specific feed to enable editing'}
                </Text>
              </Stack>
            </Paper>
          )}
        </div>
      </Stack>
    </Container>
  )
}
