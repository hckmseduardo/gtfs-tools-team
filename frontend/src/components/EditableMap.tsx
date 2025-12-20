import { useState, useCallback, useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMapEvents, Polyline } from 'react-leaflet'
import { Modal, TextInput, Textarea, Button, Group, Stack, NumberInput, Select, Text, SimpleGrid, Code, Switch, Badge, Loader } from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'
import { stopsApi, shapesApi, geocodingApi, type ShapeWithPoints } from '../lib/gtfs-api'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix for default marker icons in Leaflet with Webpack
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
})

// Location type options matching the stops section
const LOCATION_TYPES = [
  { value: '0', label: 'Stop / Platform' },
  { value: '1', label: 'Station' },
  { value: '2', label: 'Entrance/Exit' },
  { value: '3', label: 'Generic Node' },
  { value: '4', label: 'Boarding Area' },
]

const WHEELCHAIR_BOARDING = [
  { value: '0', label: 'No information' },
  { value: '1', label: 'Accessible' },
  { value: '2', label: 'Not accessible' },
]

interface Stop {
  feed_id: number
  agency_id: number
  stop_id: string
  stop_code?: string
  stop_name: string
  stop_desc?: string
  stop_lat: number
  stop_lon: number
  zone_id?: string
  stop_url?: string
  location_type?: number
  parent_station?: string
  wheelchair_boarding?: number
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

interface EditableMapProps {
  center: [number, number]
  zoom: number
  stops: Stop[]
  onStopCreated?: (stop: Stop) => void
  onStopUpdated?: (stop: Stop) => void
  onStopDeleted?: (feedId: number, stopId: string) => void
  agencyId: number | null
  feedId: number | null
  editMode: boolean
}

// Create custom icon for stops (enables dragging with visual feedback)
const createStopIcon = (editMode: boolean) => {
  const size = editMode ? 16 : 12
  const color = editMode ? '#f59e0b' : '#3b82f6'
  return L.divIcon({
    className: 'stop-marker',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background-color: ${color};
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
      cursor: ${editMode ? 'move' : 'pointer'};
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

// Component to handle map clicks for creating stops
function MapClickHandler({
  onMapClick,
  editMode
}: {
  onMapClick: (lat: number, lon: number) => void
  editMode: boolean
}) {
  useMapEvents({
    click: (e) => {
      if (editMode) {
        onMapClick(e.latlng.lat, e.latlng.lng)
      }
    },
  })
  return null
}

export default function EditableMap({
  center,
  zoom,
  stops,
  onStopCreated,
  onStopUpdated,
  onStopDeleted,
  agencyId,
  feedId,
  editMode,
}: EditableMapProps) {
  const { t } = useTranslation()
  const [newStopPosition, setNewStopPosition] = useState<[number, number] | null>(null)
  const [editingStop, setEditingStop] = useState<Stop | null>(null)
  const [createModalOpened, setCreateModalOpened] = useState(false)
  const [editModalOpened, setEditModalOpened] = useState(false)
  const [geocodingLoading, setGeocodingLoading] = useState(false)

  // Shapes overlay state
  const [showShapes, setShowShapes] = useState(false)
  const [shapes, setShapes] = useState<ShapeWithPoints[]>([])
  const [shapesLoading, setShapesLoading] = useState(false)

  // Load shapes when toggle is enabled
  useEffect(() => {
    if (showShapes && feedId && shapes.length === 0) {
      setShapesLoading(true)
      shapesApi.getByShapeId({ feed_id: feedId })
        .then(response => {
          setShapes(response.items || [])
        })
        .catch(error => {
          console.error('Failed to load shapes:', error)
          notifications.show({
            title: t('common.error'),
            message: t('shapeEditor.loadShapesError', 'Failed to load shapes'),
            color: 'red',
          })
        })
        .finally(() => setShapesLoading(false))
    }
  }, [showShapes, feedId])

  // Create form with all fields from stops section
  const createForm = useForm({
    initialValues: {
      stop_id: '',
      stop_code: '',
      stop_name: '',
      stop_desc: '',
      zone_id: '',
      stop_url: '',
      location_type: '0',
      parent_station: '',
      wheelchair_boarding: '0',
    },
    validate: {
      stop_id: (value) => (!value ? t('stops.stopIdRequired', 'Stop ID is required') : null),
      stop_name: (value) => (!value ? t('stops.stopNameRequired', 'Stop name is required') : null),
    },
  })

  // Edit form with all fields from stops section
  const editForm = useForm({
    initialValues: {
      stop_code: '',
      stop_name: '',
      stop_desc: '',
      stop_lat: 0,
      stop_lon: 0,
      zone_id: '',
      stop_url: '',
      location_type: '0',
      parent_station: '',
      wheelchair_boarding: '0',
    },
    validate: {
      stop_name: (value) => (!value ? t('stops.stopNameRequired', 'Stop name is required') : null),
      stop_lat: (value) => {
        const lat = Number(value)
        if (isNaN(lat)) return t('stops.invalidLatitude', 'Invalid latitude')
        if (lat < -90 || lat > 90) return t('stops.latitudeRange', 'Latitude must be between -90 and 90')
        return null
      },
      stop_lon: (value) => {
        const lon = Number(value)
        if (isNaN(lon)) return t('stops.invalidLongitude', 'Invalid longitude')
        if (lon < -180 || lon > 180) return t('stops.longitudeRange', 'Longitude must be between -180 and 180')
        return null
      },
    },
  })

  const handleMapClick = useCallback(async (lat: number, lon: number) => {
    setNewStopPosition([lat, lon])
    createForm.reset()
    setCreateModalOpened(true)

    // Fetch address suggestion via geocoding
    try {
      setGeocodingLoading(true)
      const result = await geocodingApi.reverseGeocode({ lat, lon })
      if (result.suggested_stop_name) {
        createForm.setFieldValue('stop_name', result.suggested_stop_name)
      }
    } catch (error) {
      console.warn('Geocoding failed:', error)
    } finally {
      setGeocodingLoading(false)
    }
  }, [createForm])

  const handleCreateStop = async (values: typeof createForm.values) => {
    if (!newStopPosition || !agencyId || !feedId) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('stops.selectAgencyAndFeed', 'Please select an agency and feed first'),
        color: 'red',
      })
      return
    }

    try {
      const stopData = {
        agency_id: agencyId,
        feed_id: feedId,
        stop_id: values.stop_id,
        stop_code: values.stop_code || undefined,
        stop_name: values.stop_name,
        stop_desc: values.stop_desc || undefined,
        stop_lat: newStopPosition[0],
        stop_lon: newStopPosition[1],
        zone_id: values.zone_id || undefined,
        stop_url: values.stop_url || undefined,
        location_type: parseInt(values.location_type),
        parent_station: values.parent_station || undefined,
        wheelchair_boarding: parseInt(values.wheelchair_boarding),
      }

      const response = await stopsApi.create(feedId!, stopData)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('stops.createSuccess', 'Stop created successfully'),
        color: 'green',
      })

      setCreateModalOpened(false)
      setNewStopPosition(null)

      if (onStopCreated) {
        onStopCreated(response)
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('stops.saveError', 'Failed to create stop'),
        color: 'red',
      })
    }
  }

  const handleEditStop = (stop: Stop) => {
    setEditingStop(stop)
    editForm.setValues({
      stop_code: stop.stop_code || '',
      stop_name: stop.stop_name,
      stop_desc: stop.stop_desc || '',
      stop_lat: stop.stop_lat,
      stop_lon: stop.stop_lon,
      zone_id: stop.zone_id || '',
      stop_url: stop.stop_url || '',
      location_type: String(stop.location_type ?? 0),
      parent_station: stop.parent_station || '',
      wheelchair_boarding: String(stop.wheelchair_boarding ?? 0),
    })
    setEditModalOpened(true)
  }

  const handleUpdateStop = async (values: typeof editForm.values) => {
    if (!editingStop) return

    try {
      const updateData = {
        stop_code: values.stop_code || undefined,
        stop_name: values.stop_name,
        stop_desc: values.stop_desc || undefined,
        stop_lat: Number(values.stop_lat),
        stop_lon: Number(values.stop_lon),
        zone_id: values.zone_id || undefined,
        stop_url: values.stop_url || undefined,
        location_type: parseInt(values.location_type),
        parent_station: values.parent_station || undefined,
        wheelchair_boarding: parseInt(values.wheelchair_boarding),
      }

      const response = await stopsApi.update(editingStop.feed_id, editingStop.stop_id, updateData)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('stops.updateSuccess', 'Stop updated successfully'),
        color: 'green',
      })

      setEditModalOpened(false)
      setEditingStop(null)

      if (onStopUpdated) {
        onStopUpdated(response)
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('stops.saveError', 'Failed to update stop'),
        color: 'red',
      })
    }
  }

  // Handle drag and drop - update stop position
  const handleStopDrag = async (stop: Stop, newLat: number, newLon: number) => {
    try {
      const updateData = {
        stop_lat: newLat,
        stop_lon: newLon,
      }

      const response = await stopsApi.update(stop.feed_id, stop.stop_id, updateData)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('stops.positionUpdated', 'Stop position updated'),
        color: 'green',
      })

      if (onStopUpdated) {
        onStopUpdated(response)
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('stops.saveError', 'Failed to update stop position'),
        color: 'red',
      })
    }
  }

  const handleDeleteStop = async (stop: Stop) => {
    const confirmMessage = t('stops.deleteConfirm', { name: stop.stop_name }) || `Are you sure you want to delete stop "${stop.stop_name}"?`
    if (!confirm(confirmMessage)) {
      return
    }

    try {
      await stopsApi.delete(stop.feed_id, stop.stop_id)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('stops.deleteSuccess', 'Stop deleted successfully'),
        color: 'green',
      })

      if (onStopDeleted) {
        onStopDeleted(stop.feed_id, stop.stop_id)
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('stops.deleteError', 'Failed to delete stop'),
        color: 'red',
      })
    }
  }

  return (
    <>
      <MapContainer
        center={center}
        zoom={zoom}
        style={{ height: '100%', width: '100%' }}
        zoomControl={true}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Map click handler for creating stops */}
        <MapClickHandler onMapClick={handleMapClick} editMode={editMode} />

        {/* Shapes overlay */}
        {showShapes && shapes.map((shape) => (
          <Polyline
            key={shape.shape_id}
            positions={shape.points.map(p => [p.lat, p.lon] as [number, number])}
            pathOptions={{
              color: '#3b82f6',
              weight: 3,
              opacity: 0.6,
            }}
          >
            <Popup>
              <div>
                <Text fw={600} size="sm">{shape.shape_id}</Text>
                <Text size="xs" c="dimmed">{shape.total_points} points</Text>
              </div>
            </Popup>
          </Polyline>
        ))}

        {/* Temporary marker for new stop position */}
        {newStopPosition && editMode && (
          <Marker position={newStopPosition}>
            <Popup>
              <Text size="sm">{t('stops.clickToCreate', 'Click "Create" to add stop here')}</Text>
            </Popup>
          </Marker>
        )}

        {/* Existing stops with drag support */}
        {stops.map((stop) => (
          <Marker
            key={stop.id}
            position={[Number(stop.stop_lat), Number(stop.stop_lon)]}
            icon={createStopIcon(editMode)}
            draggable={editMode}
            eventHandlers={{
              click: (e) => {
                if (editMode) {
                  L.DomEvent.stopPropagation(e)
                }
              },
              dblclick: (e) => {
                if (editMode) {
                  L.DomEvent.stopPropagation(e)
                  handleDeleteStop(stop)
                }
              },
              dragend: (e) => {
                if (editMode) {
                  const marker = e.target
                  const position = marker.getLatLng()
                  handleStopDrag(stop, position.lat, position.lng)
                }
              },
            }}
          >
            <Popup>
              <Stack gap="xs" style={{ minWidth: 200 }}>
                <div>
                  <Text fw={600} size="sm">{stop.stop_name}</Text>
                  <Code fz="xs">{stop.stop_id}</Code>
                </div>
                {stop.stop_code && (
                  <Text size="xs" c="dimmed">{t('stops.stopCode', 'Code')}: {stop.stop_code}</Text>
                )}
                {stop.stop_desc && (
                  <Text size="xs" c="gray.7">{stop.stop_desc}</Text>
                )}
                <Text size="xs" c="dimmed">
                  {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                </Text>
                {editMode && (
                  <>
                    <Group gap="xs" mt="xs">
                      <Button size="xs" onClick={() => handleEditStop(stop)}>
                        {t('common.edit', 'Edit')}
                      </Button>
                    </Group>
                    <Text size="xs" c="dimmed" fs="italic" mt={4}>
                      {t('stops.doubleClickToDelete', 'Double-click marker to delete')}
                    </Text>
                  </>
                )}
              </Stack>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* Floating control panel for shapes overlay */}
      {feedId && (
        <div
          style={{
            position: 'absolute',
            top: 10,
            right: 10,
            zIndex: 1000,
          }}
        >
          <Stack gap="xs">
            <Badge
              style={{ padding: '8px 12px', cursor: 'pointer', userSelect: 'none' }}
              onClick={() => setShowShapes(!showShapes)}
            >
              <Group gap="xs">
                <Switch
                  checked={showShapes}
                  onChange={(e) => setShowShapes(e.currentTarget.checked)}
                  size="sm"
                  onClick={(e) => e.stopPropagation()}
                />
                <Text size="sm">
                  Show Shapes
                  {shapesLoading && ' (loading...)'}
                  {showShapes && shapes.length > 0 && ` (${shapes.length})`}
                </Text>
              </Group>
            </Badge>
          </Stack>
        </div>
      )}

      {/* Create Stop Modal - Full form matching stops section */}
      <Modal
        opened={createModalOpened}
        onClose={() => {
          setCreateModalOpened(false)
          setNewStopPosition(null)
        }}
        title={t('stops.newStop', 'Create New Stop')}
        size="lg"
        zIndex={100000}
        overlayProps={{ zIndex: 99990 }}
      >
        <form onSubmit={createForm.onSubmit(handleCreateStop)}>
          <Stack>
            <TextInput
              label={t('stops.stopId', 'Stop ID')}
              placeholder="STOP001"
              required
              {...createForm.getInputProps('stop_id')}
            />

            <TextInput
              label={t('stops.stopCode', 'Stop Code')}
              placeholder={t('stops.stopCodePlaceholder', 'Optional code')}
              {...createForm.getInputProps('stop_code')}
            />

            <TextInput
              label={t('stops.stopName', 'Stop Name')}
              placeholder={geocodingLoading ? t('stops.loadingAddress', 'Loading address...') : t('stops.stopNamePlaceholder', 'Main Street Station')}
              required
              {...createForm.getInputProps('stop_name')}
              rightSection={geocodingLoading ? <Loader size="xs" /> : null}
            />

            <Textarea
              label={t('common.description', 'Description')}
              placeholder={t('common.descriptionPlaceholder', 'Optional description')}
              {...createForm.getInputProps('stop_desc')}
              minRows={2}
            />

            {newStopPosition && (
              <SimpleGrid cols={2}>
                <NumberInput
                  label={t('stops.latitude', 'Latitude')}
                  value={newStopPosition[0]}
                  readOnly
                  decimalScale={8}
                />
                <NumberInput
                  label={t('stops.longitude', 'Longitude')}
                  value={newStopPosition[1]}
                  readOnly
                  decimalScale={8}
                />
              </SimpleGrid>
            )}

            <Select
              label={t('stops.locationType', 'Location Type')}
              data={LOCATION_TYPES}
              {...createForm.getInputProps('location_type')}
            />

            <TextInput
              label={t('stops.parentStation', 'Parent Station')}
              placeholder={t('stops.parentStationPlaceholder', 'Parent station stop_id')}
              {...createForm.getInputProps('parent_station')}
            />

            <TextInput
              label={t('stops.zoneId', 'Zone ID')}
              placeholder="Zone 1"
              {...createForm.getInputProps('zone_id')}
            />

            <TextInput
              label={t('stops.stopUrl', 'Stop URL')}
              placeholder="https://example.com/stops/main-street"
              {...createForm.getInputProps('stop_url')}
            />

            <Select
              label={t('stops.wheelchairBoarding', 'Wheelchair Boarding')}
              data={WHEELCHAIR_BOARDING}
              {...createForm.getInputProps('wheelchair_boarding')}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => {
                setCreateModalOpened(false)
                setNewStopPosition(null)
              }}>
                {t('common.cancel', 'Cancel')}
              </Button>
              <Button type="submit">{t('common.create', 'Create')}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Edit Stop Modal - Full form matching stops section */}
      <Modal
        opened={editModalOpened}
        onClose={() => {
          setEditModalOpened(false)
          setEditingStop(null)
        }}
        title={`${t('stops.editStop', 'Edit Stop')}: ${editingStop?.stop_id}`}
        size="lg"
        zIndex={100000}
        overlayProps={{ zIndex: 99990 }}
      >
        <form onSubmit={editForm.onSubmit(handleUpdateStop)}>
          <Stack>
            <TextInput
              label={t('stops.stopId', 'Stop ID')}
              value={editingStop?.stop_id || ''}
              disabled
            />

            <TextInput
              label={t('stops.stopCode', 'Stop Code')}
              placeholder={t('stops.stopCodePlaceholder', 'Optional code')}
              {...editForm.getInputProps('stop_code')}
            />

            <TextInput
              label={t('stops.stopName', 'Stop Name')}
              placeholder={t('stops.stopNamePlaceholder', 'Main Street Station')}
              required
              {...editForm.getInputProps('stop_name')}
            />

            <Textarea
              label={t('common.description', 'Description')}
              placeholder={t('common.descriptionPlaceholder', 'Optional description')}
              {...editForm.getInputProps('stop_desc')}
              minRows={2}
            />

            <SimpleGrid cols={2}>
              <NumberInput
                label={t('stops.latitude', 'Latitude')}
                placeholder="37.7749"
                required
                decimalScale={8}
                step={0.000001}
                {...editForm.getInputProps('stop_lat')}
              />
              <NumberInput
                label={t('stops.longitude', 'Longitude')}
                placeholder="-122.4194"
                required
                decimalScale={8}
                step={0.000001}
                {...editForm.getInputProps('stop_lon')}
              />
            </SimpleGrid>

            <Select
              label={t('stops.locationType', 'Location Type')}
              data={LOCATION_TYPES}
              {...editForm.getInputProps('location_type')}
            />

            <TextInput
              label={t('stops.parentStation', 'Parent Station')}
              placeholder={t('stops.parentStationPlaceholder', 'Parent station stop_id')}
              {...editForm.getInputProps('parent_station')}
            />

            <TextInput
              label={t('stops.zoneId', 'Zone ID')}
              placeholder="Zone 1"
              {...editForm.getInputProps('zone_id')}
            />

            <TextInput
              label={t('stops.stopUrl', 'Stop URL')}
              placeholder="https://example.com/stops/main-street"
              {...editForm.getInputProps('stop_url')}
            />

            <Select
              label={t('stops.wheelchairBoarding', 'Wheelchair Boarding')}
              data={WHEELCHAIR_BOARDING}
              {...editForm.getInputProps('wheelchair_boarding')}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => {
                setEditModalOpened(false)
                setEditingStop(null)
              }}>
                {t('common.cancel', 'Cancel')}
              </Button>
              <Button type="submit">{t('common.update', 'Update')}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </>
  )
}
