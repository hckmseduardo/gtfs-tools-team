import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline, useMap, Marker, useMapEvents, Tooltip as LeafletTooltip } from 'react-leaflet'
import {
  Container,
  Title,
  Text,
  Stack,
  Paper,
  Badge,
  Group,
  Switch,
  SegmentedControl,
  LoadingOverlay,
  ActionIcon,
  Tooltip,
  Select,
  Alert,
  Collapse,
  Box,
  Drawer,
  Button,
  Divider,
  ScrollArea,
  Table,
  Loader,
  Center,
  ThemeIcon,
  Modal,
  Checkbox,
  TextInput,
  Textarea,
  NumberInput,
  SimpleGrid,
  Code,
  ColorInput,
} from '@mantine/core'
import {
  IconBus,
  IconMapPin,
  IconFocus2,
  IconRoute,
  IconDatabase,
  IconLivePhoto,
  IconAlertCircle,
  IconSettings,
  IconX,
  IconChevronDown,
  IconChevronUp,
  IconEye,
  IconEyeOff,
  IconClock,
  IconSearch,
  IconCheck,
  IconCalendar,
  IconPlus,
  IconTrash,
  IconWorld,
  IconWand,
  IconPencil,
} from '@tabler/icons-react'
import { useMediaQuery, useDisclosure } from '@mantine/hooks'
import { useForm } from '@mantine/form'
import { agencyApi, stopTimesApi, routingApi, stopsApi, routesApi, tripsApi, shapesApi, calendarsApi, geocodingApi, type Agency, type StopTime, type SearchResultItem } from '../lib/gtfs-api'
import { realtimeApi, type VehiclePosition, type TripUpdate, type Alert as RealtimeAlert, type StopTimeUpdate, type TripModification } from '../lib/realtime-api'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'
import { api } from '../lib/api'
import { LatLngBounds, DivIcon } from 'leaflet'
import L from 'leaflet'
import FeedSelector from '../components/FeedSelector'
import { FinalExport } from '../components/RouteCreator/FinalExport'
import { CalendarFormModal } from '../components/CalendarFormModal'
import { MultiSelect } from '@mantine/core'
import 'leaflet/dist/leaflet.css'

// Add CSS for smooth vehicle marker transitions and popup z-index fix
const vehicleMarkerStyles = `
  .leaflet-marker-icon.vehicle-marker,
  .leaflet-marker-pane .vehicle-marker {
    transition: transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1) !important;
    will-change: transform;
  }
  .vehicle-marker > div {
    transition: transform 0.3s ease-out;
  }
  /* Ensure Leaflet popups appear above header elements */
  .leaflet-popup-pane {
    z-index: 2500 !important;
  }
  .leaflet-popup {
    z-index: 2500 !important;
  }
`
// Inject styles once
if (typeof document !== 'undefined' && !document.getElementById('vehicle-marker-styles')) {
  const style = document.createElement('style')
  style.id = 'vehicle-marker-styles'
  style.textContent = vehicleMarkerStyles
  document.head.appendChild(style)
}

// Stop editing constants
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

// Component to handle map clicks for creating stops
function MapClickHandler({
  onMapClick,
  enabled
}: {
  onMapClick: (lat: number, lon: number) => void
  enabled: boolean
}) {
  useMapEvents({
    click: (e) => {
      if (enabled) {
        onMapClick(e.latlng.lat, e.latlng.lng)
      }
    },
  })
  return null
}

// Create custom draggable icon for stops in edit mode
const createDraggableStopIcon = (isAffected: boolean = false) => {
  const size = 16
  const color = isAffected ? '#ef4444' : '#f59e0b'
  const borderColor = isAffected ? '#fbbf24' : '#ffffff'

  return L.divIcon({
    className: 'draggable-stop-marker',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background-color: ${color};
      border: 3px solid ${borderColor};
      border-radius: 50%;
      box-shadow: 0 3px 6px rgba(0,0,0,0.4);
      cursor: move;
      transition: transform 0.2s;
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

// Route Creator shape point icon
const createRouteCreatorPointIcon = (index: number) => {
  // Small, blank square slightly smaller than the 6px route stroke
  const size = 6
  return L.divIcon({
    className: 'route-creator-point',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background: transparent;
      border: 1.5px solid #0369a1;
      border-radius: 1px;
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

// Route Creator in-memory stop icon (draggable)
const createRcNewStopIcon = (label: string) => {
  const size = 20
  return L.divIcon({
    className: 'rc-new-stop-marker',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background-color: #0ea5e9;
      border: 3px solid #0369a1;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-size: 10px;
      font-weight: bold;
      cursor: move;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    ">${label}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

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

interface Route {
  feed_id: number
  route_id: string
  route_short_name: string
  route_long_name: string
  route_type: number
  route_color?: string
  route_text_color?: string
  shape_id?: string
}

interface ShapePoint {
  lat: number
  lon: number
  sequence: number
}

interface RouteShape {
  shape_id: string
  points: ShapePoint[]
  total_points: number
}

interface Trip {
  feed_id: number
  trip_id: string
  route_id: string
  trip_headsign?: string
  trip_short_name?: string
  shape_id?: string
  service_id: string
}

// Route Creator types (in-memory only)
interface RCSelectedStop {
  stop_id: string
  stop_code?: string
  stop_name: string
  lat: number
  lon: number
  isNew: boolean
  pass: number
  sequence?: number
}

interface RCNewStop extends RCSelectedStop {
  isNew: true
}

interface RouteCreatorPosition {
  top: number
  left: number | null
  right: number | null
}

const getDefaultRouteCreatorPosition = (isMobile: boolean): RouteCreatorPosition => ({
  // Nudge away from map controls (zoom/satellite) but keep within map
  top: isMobile ? 100 : 90,
  left: isMobile ? 16 : 72,
  right: null,
})

// Stop Popup Content Component - loads and displays schedule inline
interface StopPopupContentProps {
  stop: Stop
  isAffected: boolean
  isMobile: boolean
  realtimeEnabled: boolean
  tripUpdates: TripUpdate[]
  tripByGtfsId: Map<string, Trip>
  routeByGtfsId: Map<string, Route>
  feedId?: number | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t: any
}

function StopPopupContent({
  stop,
  isAffected,
  isMobile,
  realtimeEnabled,
  tripUpdates,
  tripByGtfsId: _tripByGtfsId,
  routeByGtfsId: _routeByGtfsId,
  feedId,
  t
}: StopPopupContentProps) {
  const [scheduleData, setScheduleData] = useState<StopTime[]>([])
  const [scheduleLoading, setScheduleLoading] = useState(true)
  const [scheduleError, setScheduleError] = useState<string | null>(null)

  // Format time string (HH:MM:SS) to display format
  const formatTime = (time: string | undefined): string => {
    if (!time) return '--:--'
    const parts = time.split(':')
    if (parts.length >= 2) {
      const hours = parseInt(parts[0], 10)
      const mins = parts[1]
      const displayHours = hours >= 24 ? hours - 24 : hours
      return `${displayHours.toString().padStart(2, '0')}:${mins}`
    }
    return time
  }

  // Format delay in seconds to human readable
  const formatDelay = (seconds: number | undefined): { text: string; color: string } => {
    if (seconds === undefined || seconds === null) return { text: '', color: 'gray' }
    const absSeconds = Math.abs(seconds)
    const mins = Math.round(absSeconds / 60)
    if (absSeconds < 60) {
      return { text: t('map.stopSchedule.onTime'), color: 'green' }
    } else if (seconds < 0) {
      return { text: `${mins}m ${t('map.stopSchedule.early')}`, color: 'blue' }
    } else {
      return { text: `+${mins}m`, color: seconds > 300 ? 'red' : 'yellow' }
    }
  }

  // Format POSIX timestamp to time string
  const formatPosixTime = (timestamp: number | undefined): string => {
    if (!timestamp) return '--:--'
    const date = new Date(timestamp * 1000)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  // Get real-time updates for this stop
  const getRealtimeUpdatesForStop = useCallback((): { tripId: string; update: StopTimeUpdate; tripUpdate: TripUpdate }[] => {
    if (!realtimeEnabled || !stop.stop_id) return []
    const updates: { tripId: string; update: StopTimeUpdate; tripUpdate: TripUpdate }[] = []
    tripUpdates.forEach(tripUpdate => {
      if (tripUpdate.stop_time_updates) {
        tripUpdate.stop_time_updates.forEach(stu => {
          if (stu.stop_id === stop.stop_id) {
            updates.push({ tripId: tripUpdate.trip_id, update: stu, tripUpdate })
          }
        })
      }
    })
    return updates
  }, [realtimeEnabled, tripUpdates, stop.stop_id])

  // Load schedule when component mounts
  useEffect(() => {
    const loadSchedule = async () => {
      setScheduleLoading(true)
      setScheduleError(null)
      try {
        // Load stop times using composite keys
        console.log('Loading schedules for stop', stop.stop_id, 'with feed_id:', stop.feed_id)
        const result = await stopTimesApi.listForStop(
          stop.feed_id,
          stop.stop_id,
          50 // Limit to 50 for popup
        )
        console.log('Loaded schedules:', result.items?.length, 'items')

        // Deduplicate items based on route, headsign and time
        // This handles cases where the same trip might be returned multiple times or 
        // different trips have identical user-facing details
        const uniqueItems = result.items?.filter((item, index, self) =>
          index === self.findIndex((t) => (
            t.route_short_name === item.route_short_name &&
            t.trip_headsign === item.trip_headsign &&
            t.arrival_time === item.arrival_time
          ))
        ) || []

        setScheduleData(uniqueItems)
      } catch (error: any) {
        console.error('Failed to load schedule:', error)
        setScheduleError(error.message || t('map.stopSchedule.loadError'))
        setScheduleData([])
      } finally {
        setScheduleLoading(false)
      }
    }
    loadSchedule()
  }, [stop.id, feedId, t])

  const rtUpdates = getRealtimeUpdatesForStop()

  return (
    <div style={{ minWidth: isMobile ? '260px' : '320px', maxWidth: isMobile ? '300px' : '380px' }}>
      {/* Header */}
      <Group gap="xs" mb={6} wrap="nowrap">
        <ThemeIcon size="sm" color="blue" variant="light" style={{ flexShrink: 0 }}>
          <IconMapPin size={14} />
        </ThemeIcon>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Text fw={600} size="sm" lineClamp={1}>{stop.stop_name}</Text>
          <Text size="xs" c="dimmed">
            {stop.stop_id} · {Number(stop.stop_lat).toFixed(5)}, {Number(stop.stop_lon).toFixed(5)}
          </Text>
        </div>
      </Group>

      {isAffected && (
        <Badge color="red" size="xs" mb={8} fullWidth>
          {t('map.tripModifications.affectedStop', 'Affected by Detour')}
        </Badge>
      )}

      {stop.stop_desc && (
        <Text size="xs" c="gray.6" mb={8}>{stop.stop_desc}</Text>
      )}

      <Divider mb={8} label={
        <Group gap={4}>
          <IconClock size={12} />
          <Text size="xs">{t('map.stopSchedule.title', 'Schedule')}</Text>
        </Group>
      } labelPosition="center" />

      {/* Schedule Content */}
      {scheduleLoading ? (
        <Center py="sm">
          <Group gap="xs">
            <Loader size="xs" />
            <Text size="xs" c="dimmed">{t('map.stopSchedule.loadingSchedule', 'Loading...')}</Text>
          </Group>
        </Center>
      ) : scheduleError ? (
        <Alert color="red" icon={<IconAlertCircle size={14} />} p="xs">
          <Text size="xs">{scheduleError}</Text>
        </Alert>
      ) : scheduleData.length === 0 ? (
        <Text size="xs" c="dimmed" ta="center" py="xs">
          {t('map.stopSchedule.noSchedule', 'No schedule available')}
        </Text>
      ) : (
        <Stack gap="xs">
          {/* Real-time indicator */}
          {realtimeEnabled && rtUpdates.length > 0 && (
            <Group gap="xs">
              <IconLivePhoto size={12} color="green" />
              <Text size="xs" fw={500} c="green.7">
                {rtUpdates.length} {t('map.stopSchedule.liveUpdates', 'live updates')}
              </Text>
            </Group>
          )}

          {/* Schedule table */}
          <ScrollArea.Autosize mah={220}>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th style={{ padding: '4px 8px' }}>{t('map.stopSchedule.route', 'Route')}</Table.Th>
                  <Table.Th style={{ padding: '4px 8px' }}>{t('map.stopSchedule.headsign', 'To')}</Table.Th>
                  <Table.Th style={{ padding: '4px 8px' }}>{t('map.stopSchedule.arrival', 'Arr')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {scheduleData.slice(0, 20).map((st, idx) => {
                  const rtUpdate = rtUpdates.find(u => u.tripId === st.gtfs_trip_id)
                  const hasRtUpdate = rtUpdate !== undefined
                  const arrivalDelay = rtUpdate ? formatDelay(rtUpdate.update.arrival_delay) : null

                  return (
                    <Table.Tr key={idx}>
                      <Table.Td style={{ padding: '4px 8px' }}>
                        {st.route_color ? (
                          <Badge
                            size="xs"
                            style={{ backgroundColor: st.route_color.startsWith('#') ? st.route_color : `#${st.route_color}` }}
                          >
                            {st.route_short_name || '-'}
                          </Badge>
                        ) : (
                          <Text size="xs" fw={500}>{st.route_short_name || '-'}</Text>
                        )}
                      </Table.Td>
                      <Table.Td style={{ padding: '4px 8px', maxWidth: 120 }}>
                        <Text size="xs" lineClamp={1}>{st.trip_headsign || st.stop_headsign || '-'}</Text>
                      </Table.Td>
                      <Table.Td style={{ padding: '4px 8px' }}>
                        {hasRtUpdate && rtUpdate?.update.arrival_time ? (
                          <Group gap={4} wrap="nowrap">
                            <Text size="xs" fw={500}>
                              {formatPosixTime(rtUpdate.update.arrival_time)}
                            </Text>
                            <Badge size="xs" color={arrivalDelay?.color || 'green'} variant="light">
                              {arrivalDelay?.text || t('map.stopSchedule.onTime')}
                            </Badge>
                          </Group>
                        ) : (
                          <Text size="xs" fw={500}>
                            {formatTime(st.arrival_time)}
                          </Text>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>

          {scheduleData.length > 20 && (
            <Text size="xs" c="dimmed" ta="center">
              +{scheduleData.length - 20} {t('map.stopSchedule.more', 'more')}
            </Text>
          )}
        </Stack>
      )}
    </div>
  )
}

// Component to handle map center updates
function MapCenterUpdater({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap()
  useEffect(() => {
    map.setView(center, zoom)
  }, [center, zoom, map])
  return null
}

// Component to fit map bounds to all stops
function FitBoundsToStops({ stops, shouldFit }: { stops: Stop[]; shouldFit: boolean }) {
  const map = useMap()

  useEffect(() => {
    if (shouldFit && stops.length > 0) {
      const bounds = new LatLngBounds(
        stops.map(stop => [Number(stop.stop_lat), Number(stop.stop_lon)])
      )
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 })
    }
  }, [stops, shouldFit, map])

  return null
}

// Component to fly map to a specific location
function FlyToLocation({ target, onComplete }: {
  target: { lat: number; lon: number; zoom?: number } | null
  onComplete: () => void
}) {
  const map = useMap()

  useEffect(() => {
    if (target) {
      map.flyTo([target.lat, target.lon], target.zoom || 16, { duration: 1.5 })
      onComplete()
    }
  }, [target, map, onComplete])

  return null
}

// Map search box component
function MapSearchBox({
  onSelectLocation,
  isMobile
}: {
  onSelectLocation: (lat: number, lon: number, zoom?: number) => void
  isMobile: boolean
}) {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Debounced search
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    if (searchQuery.trim().length < 3) {
      setSearchResults([])
      setShowResults(false)
      return
    }

    searchTimeoutRef.current = setTimeout(async () => {
      setIsSearching(true)
      try {
        const response = await geocodingApi.search({ query: searchQuery, limit: 5 })
        setSearchResults(response.results)
        setShowResults(response.results.length > 0)
      } catch (error) {
        console.warn('Search failed:', error)
        setSearchResults([])
      } finally {
        setIsSearching(false)
      }
    }, 300)

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [searchQuery])

  const handleSelectResult = (result: SearchResultItem) => {
    // Calculate appropriate zoom level based on result type
    let zoom = 16
    if (result.type === 'city' || result.type === 'administrative') {
      zoom = 12
    } else if (result.type === 'state' || result.type === 'county') {
      zoom = 9
    } else if (result.type === 'country') {
      zoom = 5
    }

    onSelectLocation(result.lat, result.lon, zoom)
    setSearchQuery('')
    setSearchResults([])
    setShowResults(false)
    inputRef.current?.blur()
  }

  const handleClear = () => {
    setSearchQuery('')
    setSearchResults([])
    setShowResults(false)
  }

  return (
    <Box
      style={{
        position: 'absolute',
        top: isMobile ? 10 : 15,
        right: isMobile ? 10 : 15,
        zIndex: 1500,
        width: isMobile ? 'calc(100% - 20px)' : 320,
        maxWidth: 320,
      }}
    >
      <Paper shadow="md" radius="md" style={{ overflow: 'hidden' }}>
        <TextInput
          ref={inputRef}
          placeholder={t('map.searchPlaceholder', 'Search address or place...')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.currentTarget.value)}
          onFocus={() => searchResults.length > 0 && setShowResults(true)}
          onBlur={() => setTimeout(() => setShowResults(false), 200)}
          leftSection={<IconSearch size={16} />}
          rightSection={
            isSearching ? (
              <Loader size="xs" />
            ) : searchQuery ? (
              <ActionIcon size="sm" variant="subtle" onClick={handleClear}>
                <IconX size={14} />
              </ActionIcon>
            ) : null
          }
          styles={{
            input: {
              border: 'none',
              backgroundColor: 'var(--mantine-color-body)',
            }
          }}
        />

        {showResults && searchResults.length > 0 && (
          <Box
            style={{
              borderTop: '1px solid var(--mantine-color-gray-3)',
              maxHeight: 250,
              overflowY: 'auto',
            }}
          >
            {searchResults.map((result, index) => (
              <Box
                key={result.place_id}
                p="xs"
                style={{
                  cursor: 'pointer',
                  borderBottom: index < searchResults.length - 1 ? '1px solid var(--mantine-color-gray-2)' : 'none',
                  ':hover': { backgroundColor: 'var(--mantine-color-gray-1)' }
                }}
                onMouseDown={() => handleSelectResult(result)}
              >
                <Text size="sm" lineClamp={2}>
                  {result.display_name}
                </Text>
                {result.type && (
                  <Badge size="xs" variant="light" color="gray" mt={4}>
                    {result.type}
                  </Badge>
                )}
              </Box>
            ))}
          </Box>
        )}
      </Paper>
    </Box>
  )
}

export default function MapPage() {
  const isMobile = useMediaQuery('(max-width: 768px)')

  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [stops, setStops] = useState<Stop[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [shapes, setShapes] = useState<RouteShape[]>([])
  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editorMode, setEditorMode] = useState<'stops' | 'shapes'>('stops')

  // Selected vehicle for route highlighting
  const [selectedVehicleId, setSelectedVehicleId] = useState<string | null>(null)

  // Map state
  const [mapCenter, setMapCenter] = useState<[number, number]>([40.7128, -74.006])
  const [mapZoom, setMapZoom] = useState(11)
  const [shouldFitBounds, setShouldFitBounds] = useState(false)

  // Layer visibility
  const [showStops, setShowStops] = useState(true)
  const [showRoutes, setShowRoutes] = useState(true)
  const [showShapes, setShowShapes] = useState(true)
  const [showSatellite, setShowSatellite] = useState(false)

  // Search/fly to location
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lon: number; zoom?: number } | null>(null)

  // Orphan display toggles (show items without trips/routes)
  const [showOrphanStops, setShowOrphanStops] = useState(false)
  const [showOrphanShapes, setShowOrphanShapes] = useState(false)

  // Route selection
  const [routeSelectionOpened, setRouteSelectionOpened] = useState(false)
  const [selectedRouteIds, setSelectedRouteIds] = useState<Set<string>>(new Set())
  const [routeSearchText, setRouteSearchText] = useState('')

  // Shape selection
  const [shapeSelectionOpened, setShapeSelectionOpened] = useState(false)
  const [selectedShapeIds, setSelectedShapeIds] = useState<Set<string>>(new Set())
  const [shapeSearchText, setShapeSearchText] = useState('')

  // Calendar selection
  const [calendarSelectionOpened, setCalendarSelectionOpened] = useState(false)
  const [calendars, setCalendars] = useState<any[]>([])
  const [selectedCalendarIds, setSelectedCalendarIds] = useState<Set<string>>(new Set())
  const [calendarSearchText, setCalendarSearchText] = useState('')

  // Route to stops mapping (for filtering stops by selected routes)
  const [routeToStopsMap, setRouteToStopsMap] = useState<Record<string, string[]>>({})

  // Real-time data state
  const [realtimeEnabled, setRealtimeEnabled] = useState(false)
  const [vehicles, setVehicles] = useState<VehiclePosition[]>([])
  const [tripUpdates, setTripUpdates] = useState<TripUpdate[]>([])
  const [alerts, setAlerts] = useState<RealtimeAlert[]>([])
  const [tripModifications, setTripModifications] = useState<TripModification[]>([])
  const [realtimeShapes, setRealtimeShapes] = useState<import('../lib/realtime-api').RealtimeShape[]>([])
  const [realtimeStops, setRealtimeStops] = useState<import('../lib/realtime-api').RealtimeStop[]>([])
  const [showVehicles, setShowVehicles] = useState(true)
  const [showTripUpdates, setShowTripUpdates] = useState(true)
  const [showAlerts, setShowAlerts] = useState(true)
  const [showTripModifications, setShowTripModifications] = useState(true)
  const [showReplacementShapes, setShowReplacementShapes] = useState(true)
  const [showReplacementStops, setShowReplacementStops] = useState(true)
  const [realtimeLoading, setRealtimeLoading] = useState(false)
  const [realtimeError, setRealtimeError] = useState<string | null>(null)

  // Stop editing state
  const [newStopPosition, setNewStopPosition] = useState<[number, number] | null>(null)
  const [editingStop, setEditingStop] = useState<Stop | null>(null)
  const [createStopModalOpened, setCreateStopModalOpened] = useState(false)
  const [editStopModalOpened, setEditStopModalOpened] = useState(false)
  const [geocodingLoading, setGeocodingLoading] = useState(false)

  // Route Creator (in-memory) state
  const [routeCreatorEnabled, setRouteCreatorEnabled] = useState(false)
  const [rcUseExistingRoute, setRcUseExistingRoute] = useState(false)
  const [rcSelectedExistingRouteId, setRcSelectedExistingRouteId] = useState<string | null>(null)
  const [rcSelectedDirection, setRcSelectedDirection] = useState<string | null>(null)
  const [rcAvailableDirections, setRcAvailableDirections] = useState<{ value: string; label: string }[]>([])
  const [rcLoadingExistingRoute, setRcLoadingExistingRoute] = useState(false)
  const [rcRouteId, setRcRouteId] = useState('')
  const [rcRouteShortName, setRcRouteShortName] = useState('')
  const [rcRouteColor, setRcRouteColor] = useState('#0ea5e9')
  const [rcSelectedStops, setRcSelectedStops] = useState<RCSelectedStop[]>([])
  const [rcNewStops, setRcNewStops] = useState<RCNewStop[]>([])
  const [rcNewStopModalOpened, setRcNewStopModalOpened] = useState(false)
  const [rcEditingStopId, setRcEditingStopId] = useState<string | null>(null)
  const [rcEditingExistingStop, setRcEditingExistingStop] = useState<RCSelectedStop | null>(null) // For editing real stops' sequence
  const [rcPendingStopPosition, setRcPendingStopPosition] = useState<[number, number] | null>(null)
  const [rcShapePoints, setRcShapePoints] = useState<Array<{ lat: number; lon: number }>>([])
  const [rcShapeGenerating, setRcShapeGenerating] = useState(false)
  const [rcAddPointMode, setRcAddPointMode] = useState(false)
  const [rcImproveSegmentMode, setRcImproveSegmentMode] = useState(false)
  const [rcImproveSelection, setRcImproveSelection] = useState<{ start: number | null; end: number | null }>({ start: null, end: null })
  const [rcTrips, setRcTrips] = useState<string[]>([])
  const [rcStopTimesTable, setRcStopTimesTable] = useState<Record<string, string[]>>({})
  const [rcStep, setRcStep] = useState<1 | 2 | 3 | 4 | 5 | 6 | 7>(1)
  const [rcDragIndex, setRcDragIndex] = useState<number | null>(null)
  const [rcDragHoverIndex, setRcDragHoverIndex] = useState<number | null>(null)
  const [rcDrawerPosition, setRcDrawerPosition] = useState<RouteCreatorPosition>(() => getDefaultRouteCreatorPosition(isMobile))
  const [rcHoverTime, setRcHoverTime] = useState<string | null>(null)
  const [rcSelectedServiceIds, setRcSelectedServiceIds] = useState<string[]>([])
  const [rcCalendarModalOpened, { open: openRcCalendarModal, close: closeRcCalendarModal }] = useDisclosure(false)
  const rcDrawerRef = useRef<HTMLDivElement | null>(null)
  const rcDragStateRef = useRef<{
    pointerId: number
    offsetX: number
    offsetY: number
    parentLeft: number
    parentTop: number
    dragging: boolean
  } | null>(null)

  // Shape editing state
  const [editingShapeId, setEditingShapeId] = useState<string | null>(null)
  const [shapeSelectionModalOpened, setShapeSelectionModalOpened] = useState(false)
  const [editingShapePoints, setEditingShapePoints] = useState<Array<{ lat: number; lon: number; sequence: number }>>([])
  const [creatingNewShape, setCreatingNewShape] = useState(false)
  const [newShapePoints, setNewShapePoints] = useState<Array<{ lat: number; lon: number }>>([])
  const [newShapeId, setNewShapeId] = useState('')

  const realtimeIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastSuccessfulFetchRef = useRef<number>(0)
  const isInitialFetchRef = useRef<boolean>(true)
  const MIN_FETCH_INTERVAL = 5500 // Minimum 5.5 seconds between successful API calls to avoid 429 errors

  // Mobile controls state
  const [mobileDrawerOpened, { open: openMobileDrawer, close: closeMobileDrawer }] = useDisclosure(false)
  const [statsExpanded, setStatsExpanded] = useState(false)

  // Translation hook
  const { t } = useTranslation()

  // Stop create form
  const createStopForm = useForm({
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

  // Route Creator - new stop form (in-memory only)
  const rcNewStopForm = useForm({
    initialValues: {
      stop_id: '',
      stop_code: '',
      stop_name: '',
      sequence: '',
    },
    validate: {
      stop_id: (value) => (!value ? 'Stop ID is required' : null),
      stop_name: (value) => (!value ? 'Stop name is required' : null),
    },
  })

  // Stop edit form
  const editStopForm = useForm({
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

  // Route Creator ordering helpers
  const normalizeRcStops = useCallback((list: RCSelectedStop[]) => {
    // Preserve user-defined sequences (including gaps) while keeping a stable, strictly increasing order
    const withIndex = list.map((s, idx) => {
      const numericSeq = Number(s.sequence)
      const sequence = Number.isFinite(numericSeq) ? Math.max(1, Math.floor(numericSeq)) : idx + 1
      return { ...s, _idx: idx, sequence }
    })

    withIndex.sort((a, b) => {
      if (a.sequence === b.sequence) return a._idx - b._idx
      return (a.sequence ?? 0) - (b.sequence ?? 0)
    })

    let lastSeq = 0
    return withIndex.map((s) => {
      const nextSeq = Math.max(s.sequence ?? lastSeq + 1, lastSeq + 1)
      lastSeq = nextSeq
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { _idx, ...rest } = s
      return { ...rest, sequence: nextSeq }
    })
  }, [])

  const rcOrderedStops = useMemo(() => normalizeRcStops(rcSelectedStops), [rcSelectedStops, normalizeRcStops])

  // Helpers for Route Creator suggestions/timeline
  const padTime = useCallback((n: number) => n.toString().padStart(2, '0'), [])
  const padSeq = useCallback((n: number) => n.toString().padStart(3, '0'), [])
  const generateRouteIdSuggestion = useCallback(() => {
    const existing = new Set<string>()
    routes.forEach(r => {
      if (r.route_id) existing.add(r.route_id)
    })
    let idx = 1
    let candidate = `RC_ROUTE_${idx}`
    while (existing.has(candidate)) {
      idx += 1
      candidate = `RC_ROUTE_${idx}`
    }
    return candidate
  }, [routes])
  const rcTimeBlocks = useMemo(() => {
    const blocks: string[] = []
    for (let h = 0; h < 24; h++) {
      for (let m = 0; m < 60; m += 5) {
        blocks.push(`${padTime(h)}:${padTime(m)}`)
      }
    }
    return blocks
  }, [padTime])
  const rcHoursAM = useMemo(() => {
    return Array.from({ length: 12 }, (_, h) => ({
      label: `${padTime(h)}:00`,
      times: Array.from({ length: 12 }, (_x, idx) => `${padTime(h)}:${padTime(idx * 5)}`)
    }))
  }, [padTime])
  const rcHoursPM = useMemo(() => {
    return Array.from({ length: 12 }, (_, h) => ({
      label: `${padTime(h + 12)}:00`,
      times: Array.from({ length: 12 }, (_x, idx) => `${padTime(h + 12)}:${padTime(idx * 5)}`)
    }))
  }, [padTime])

  // Calendar options for Route Creator MultiSelect
  const rcCalendarOptions = useMemo(() => {
    if (!calendars || calendars.length === 0) return []
    return calendars
      .filter((cal: any) => cal.service_id)
      .map((cal: any) => {
        const days = [
          (cal.monday === true || cal.monday === 1) && 'M',
          (cal.tuesday === true || cal.tuesday === 1) && 'T',
          (cal.wednesday === true || cal.wednesday === 1) && 'W',
          (cal.thursday === true || cal.thursday === 1) && 'Th',
          (cal.friday === true || cal.friday === 1) && 'F',
          (cal.saturday === true || cal.saturday === 1) && 'Sa',
          (cal.sunday === true || cal.sunday === 1) && 'Su',
        ].filter(Boolean).join('')
        return {
          value: cal.service_id,
          label: `${cal.service_id}${days ? ` (${days})` : ''}`,
        }
      })
  }, [calendars])

  // Handle fit to view
  const handleFitToView = () => {
    setShouldFitBounds(true)
    setTimeout(() => setShouldFitBounds(false), 100)
  }

  // Shape editing helper - defined early for use in handleMapClick
  const handleAddPointToNewShape = useCallback((lat: number, lon: number) => {
    setNewShapePoints(prev => [...prev, { lat, lon }])
  }, [])

  // Route Creator helper: insert shape point closest to clicked segment
  const insertRCShapePoint = useCallback((lat: number, lon: number) => {
    setRcShapePoints(prev => {
      if (prev.length === 0) return [{ lat, lon }]
      if (prev.length === 1) return [...prev, { lat, lon }]

      const toRadians = (deg: number) => (deg * Math.PI) / 180
      const distanceToSegment = (p: { lat: number; lon: number }, v: { lat: number; lon: number }, w: { lat: number; lon: number }) => {
        const lat1 = toRadians(v.lat)
        const lat2 = toRadians(w.lat)
        const lon1 = toRadians(v.lon)
        const lon2 = toRadians(w.lon)
        const pLat = toRadians(p.lat)
        const pLon = toRadians(p.lon)

        // Rough projection using planar approximation for small distances
        const a = { x: (lon1 - lon2), y: (lat1 - lat2) }
        const b = { x: (lon1 - pLon), y: (lat1 - pLat) }
        const lenSq = a.x * a.x + a.y * a.y || 1e-6
        let t = - (a.x * b.x + a.y * b.y) / lenSq
        t = Math.max(0, Math.min(1, t))
        const proj = { x: lon1 + t * (lon2 - lon1), y: lat1 + t * (lat2 - lat1) }
        const dLat = pLat - proj.y
        const dLon = pLon - proj.x
        return Math.sqrt(dLat * dLat + dLon * dLon)
      }

      let bestIdx = 0
      let bestDist = Number.MAX_VALUE
      for (let i = 0; i < prev.length - 1; i++) {
        const dist = distanceToSegment({ lat, lon }, prev[i], prev[i + 1])
        if (dist < bestDist) {
          bestDist = dist
          bestIdx = i
        }
      }

      const updated = [...prev]
      updated.splice(bestIdx + 1, 0, { lat, lon })
      return updated
    })
  }, [])

  // Helper function to fetch address suggestion via geocoding
  const fetchAddressSuggestion = useCallback(async (lat: number, lon: number): Promise<string | null> => {
    try {
      setGeocodingLoading(true)
      const result = await geocodingApi.reverseGeocode({ lat, lon })
      return result.suggested_stop_name
    } catch (error) {
      console.warn('Geocoding failed:', error)
      return null
    } finally {
      setGeocodingLoading(false)
    }
  }, [])

  // Stop editing handlers
  const handleMapClick = useCallback(async (lat: number, lon: number) => {
    if (routeCreatorEnabled) {
      // Shape step: add point when in add mode
      if (rcStep === 4 && rcAddPointMode) {
        insertRCShapePoint(lat, lon)
        setRcAddPointMode(false)
        return
      }

      // Stops step (or route step): open in-memory stop modal and advance step if needed
      if (rcStep <= 3) {
        if (rcStep < 3) setRcStep(3)
        setRcPendingStopPosition([lat, lon])
        rcNewStopForm.reset()
        // Suggested sequence is the last existing sequence + 1 (not just count + 1)
        const lastSeq = rcOrderedStops.length > 0 ? Math.max(...rcOrderedStops.map(s => s.sequence ?? 0)) : 0
        const seq = lastSeq + 1
        const suggestedRouteId = rcRouteId || generateRouteIdSuggestion()
        const suggestedStop = `${suggestedRouteId}_${padSeq(seq)}`
        rcNewStopForm.setValues({
          stop_id: suggestedStop,
          stop_code: '',
          stop_name: '', // Start empty, will be filled by geocoding
          sequence: String(seq),
        })
        setRcNewStopModalOpened(true)

        // Fetch address suggestion and update form
        const suggestedName = await fetchAddressSuggestion(lat, lon)
        if (suggestedName) {
          rcNewStopForm.setFieldValue('stop_name', suggestedName)
        } else {
          // Fallback to stop ID as name if geocoding fails
          rcNewStopForm.setFieldValue('stop_name', suggestedStop)
        }
        return
      }
    }

    if (editMode && editorMode === 'stops') {
      setNewStopPosition([lat, lon])
      createStopForm.reset()
      setCreateStopModalOpened(true)

      // Fetch address suggestion and update form
      const suggestedName = await fetchAddressSuggestion(lat, lon)
      if (suggestedName) {
        createStopForm.setFieldValue('stop_name', suggestedName)
      }
    } else if (editMode && editorMode === 'shapes' && creatingNewShape) {
      handleAddPointToNewShape(lat, lon)
    }
  }, [routeCreatorEnabled, rcStep, rcAddPointMode, insertRCShapePoint, rcNewStopForm, editMode, editorMode, creatingNewShape, handleAddPointToNewShape, rcRouteId, generateRouteIdSuggestion, padSeq, fetchAddressSuggestion, createStopForm])

  const handleCreateStop = async (values: typeof createStopForm.values) => {
    if (!newStopPosition || !selectedAgency || !selectedFeed) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('stops.selectAgencyAndFeed', 'Please select an agency and feed first'),
        color: 'red',
      })
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const stopData = {
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

      const response = await stopsApi.create(feed_id, stopData)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('stops.createSuccess', 'Stop created successfully'),
        color: 'green',
      })

      setCreateStopModalOpened(false)
      setNewStopPosition(null)
      setStops([...stops, response])
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
    editStopForm.setValues({
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
    setEditStopModalOpened(true)
  }

  const handleUpdateStop = async (values: typeof editStopForm.values) => {
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

      setEditStopModalOpened(false)
      setEditingStop(null)
      setStops(stops.map(s =>
        s.feed_id === editingStop.feed_id && s.stop_id === editingStop.stop_id ? response : s
      ))
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('stops.saveError', 'Failed to update stop'),
        color: 'red',
      })
    }
  }

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

      setStops(stops.map(s =>
        s.feed_id === stop.feed_id && s.stop_id === stop.stop_id ? response : s
      ))
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

      setStops(stops.filter(s =>
        !(s.feed_id === stop.feed_id && s.stop_id === stop.stop_id)
      ))
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('stops.deleteError', 'Failed to delete stop'),
        color: 'red',
      })
    }
  }

  // Route Creator helpers
  const resetRouteCreator = () => {
    setRcUseExistingRoute(false)
    setRcSelectedExistingRouteId(null)
    setRcSelectedDirection(null)
    setRcAvailableDirections([])
    setRcLoadingExistingRoute(false)
    setRcRouteId(generateRouteIdSuggestion())
    setRcRouteShortName('')
    setRcRouteColor('#0ea5e9')
    setRcSelectedStops([])
    setRcNewStops([])
    setRcEditingStopId(null)
    setRcPendingStopPosition(null)
    setRcShapePoints([])
    setRcShapeGenerating(false)
    setRcAddPointMode(false)
    setRcImproveSegmentMode(false)
    setRcImproveSelection({ start: null, end: null })
    setRcTrips([])
    setRcStopTimesTable({})
    setRcSelectedServiceIds([])
    setRcStep(1)
  }

  // Load available directions for a route
  const loadExistingRouteDirections = useCallback(async (routeId: string) => {
    if (!selectedFeed) return

    setRcLoadingExistingRoute(true)
    setRcSelectedDirection(null)
    setRcAvailableDirections([])
    setRcSelectedStops([])

    try {
      const feedId = parseInt(selectedFeed)

      // Get the route details
      const route = routes.find(r => r.route_id === routeId)
      if (route) {
        setRcRouteId(route.route_id)
        setRcRouteShortName(route.route_short_name || '')
        setRcRouteColor(route.route_color ? `#${route.route_color}` : '#0ea5e9')
      }

      // Get ALL trips for this route to find available directions
      const tripsResponse = await tripsApi.list(feedId, { route_id: routeId, limit: 50000 })
      if (tripsResponse.items.length === 0) {
        notifications.show({
          title: t('common.warning', 'Warning'),
          message: t('routeCreator.noTripsForRoute', 'No trips found for this route'),
          color: 'yellow',
        })
        setRcLoadingExistingRoute(false)
        return
      }

      // Find unique directions
      const directionsSet = new Set<number>()
      const directionHeadsigns: Record<number, string> = {}

      for (const trip of tripsResponse.items) {
        const dir = trip.direction_id ?? 0
        directionsSet.add(dir)
        // Use the first headsign found for each direction
        if (!directionHeadsigns[dir] && trip.trip_headsign) {
          directionHeadsigns[dir] = trip.trip_headsign
        }
      }

      const directions = Array.from(directionsSet).sort().map(dir => ({
        value: String(dir),
        label: directionHeadsigns[dir]
          ? `${t('routeCreator.direction', 'Direction')} ${dir} - ${directionHeadsigns[dir]}`
          : `${t('routeCreator.direction', 'Direction')} ${dir}`,
      }))

      setRcAvailableDirections(directions)

      // Auto-select if only one direction
      if (directions.length === 1) {
        setRcSelectedDirection(directions[0].value)
        // Load stops for this direction
        await loadExistingRouteStops(routeId, parseInt(directions[0].value))
      }
    } catch (error) {
      console.error('Error loading route directions:', error)
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('routeCreator.loadRouteError', 'Failed to load route directions'),
        color: 'red',
      })
    } finally {
      setRcLoadingExistingRoute(false)
    }
  }, [selectedFeed, routes, t])

  // Load stops from an existing route + direction (all trips)
  const loadExistingRouteStops = useCallback(async (routeId: string, directionId: number) => {
    if (!selectedFeed) return

    setRcLoadingExistingRoute(true)
    try {
      const feedId = parseInt(selectedFeed)

      // Get ALL trips for this route + direction
      const tripsResponse = await tripsApi.list(feedId, {
        route_id: routeId,
        direction_id: directionId,
        limit: 50000
      })

      if (tripsResponse.items.length === 0) {
        notifications.show({
          title: t('common.warning', 'Warning'),
          message: t('routeCreator.noTripsForDirection', 'No trips found for this direction'),
          color: 'yellow',
        })
        setRcLoadingExistingRoute(false)
        return
      }

      // Collect all stop_times from all trips
      // Use a Map to track: stop_id -> { sequences: number[], count: number }
      const stopSequenceMap = new Map<string, { sequences: number[], count: number }>()

      // Find the trip with the most stops to use as the reference sequence
      let maxStopCount = 0
      let referenceStopTimes: StopTime[] = []

      for (const trip of tripsResponse.items) {
        const stopTimesResponse = await stopTimesApi.listForTrip(feedId, trip.trip_id)
        const tripStopTimes = stopTimesResponse.items

        // Track this as potential reference if it has more stops
        if (tripStopTimes.length > maxStopCount) {
          maxStopCount = tripStopTimes.length
          referenceStopTimes = tripStopTimes
        }

        // Collect all stop occurrences
        for (const st of tripStopTimes) {
          const existing = stopSequenceMap.get(st.stop_id)
          if (existing) {
            existing.sequences.push(st.stop_sequence)
            existing.count++
          } else {
            stopSequenceMap.set(st.stop_id, { sequences: [st.stop_sequence], count: 1 })
          }
        }
      }

      if (referenceStopTimes.length === 0) {
        notifications.show({
          title: t('common.warning', 'Warning'),
          message: t('routeCreator.noStopTimesForRoute', 'No stop times found for this route'),
          color: 'yellow',
        })
        setRcLoadingExistingRoute(false)
        return
      }

      // Sort reference by sequence
      const sortedReference = [...referenceStopTimes].sort((a, b) => a.stop_sequence - b.stop_sequence)

      // Build the ordered stop list from the reference trip
      // But include any additional stops from other trips that aren't in the reference
      const orderedStopIds = sortedReference.map(st => st.stop_id)

      // Add any stops that appear in other trips but not in the reference
      for (const [stopId] of stopSequenceMap) {
        if (!orderedStopIds.includes(stopId)) {
          // Find the best position to insert based on average sequence
          const avgSeq = stopSequenceMap.get(stopId)!.sequences.reduce((a, b) => a + b, 0) /
                         stopSequenceMap.get(stopId)!.sequences.length

          // Find insertion point
          let insertIdx = orderedStopIds.length
          for (let i = 0; i < sortedReference.length; i++) {
            if (sortedReference[i].stop_sequence > avgSeq) {
              insertIdx = i
              break
            }
          }
          orderedStopIds.splice(insertIdx, 0, stopId)
        }
      }

      // Map to RCSelectedStop objects
      const selectedStops: RCSelectedStop[] = orderedStopIds
        .map((stopId, index) => {
          const stop = stops.find(s => s.stop_id === stopId)
          if (!stop) return null
          return {
            stop_id: stopId,
            stop_code: stop.stop_code,
            stop_name: stop.stop_name || stopId,
            lat: parseFloat(String(stop.stop_lat)) || 0,
            lon: parseFloat(String(stop.stop_lon)) || 0,
            isNew: false,
            pass: 1,
            sequence: index + 1,
          }
        })
        .filter((s): s is RCSelectedStop => s !== null)

      setRcSelectedStops(selectedStops)

      notifications.show({
        title: t('common.success', 'Success'),
        message: `Loaded ${selectedStops.length} stops from ${tripsResponse.items.length} trips`,
        color: 'green',
      })
    } catch (error) {
      console.error('Error loading existing route stops:', error)
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('routeCreator.loadRouteError', 'Failed to load stops from route'),
        color: 'red',
      })
    } finally {
      setRcLoadingExistingRoute(false)
    }
  }, [selectedFeed, stops, t])

  const handleToggleRouteCreator = (enabled: boolean) => {
    setRouteCreatorEnabled(enabled)
    if (!enabled) {
      resetRouteCreator()
    } else {
      setRcDrawerPosition(getDefaultRouteCreatorPosition(isMobile))
      setRcRouteId(prev => prev || generateRouteIdSuggestion())
    }
  }

  const handleRcDragStart = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!rcDrawerRef.current) return

    const target = e.target as HTMLElement
    if (target.closest('button, input, textarea, select, [role="textbox"], [contenteditable="true"]')) return

    e.preventDefault()

    const rect = rcDrawerRef.current.getBoundingClientRect()
    const parentRect = rcDrawerRef.current.parentElement?.getBoundingClientRect()
    const parentLeft = parentRect?.left || 0
    const parentTop = parentRect?.top || 0
    const offsetX = e.clientX - rect.left
    const offsetY = e.clientY - rect.top

    // Normalize to parent (map container) coordinates
    setRcDrawerPosition({
      top: rect.top - parentTop,
      left: rect.left - parentLeft,
      right: null,
    })

    rcDragStateRef.current = {
      pointerId: e.pointerId,
      offsetX,
      offsetY,
      parentLeft,
      parentTop,
      dragging: true,
    }

    window.addEventListener('pointermove', handleRcDragMove)
    window.addEventListener('pointerup', handleRcDragEnd)
  }

  const handleRcDragMove = useCallback((e: PointerEvent) => {
    const state = rcDragStateRef.current
    if (!state || !state.dragging || e.pointerId !== state.pointerId) return

    e.preventDefault()
    const newLeft = e.clientX - state.offsetX - state.parentLeft
    const newTop = e.clientY - state.offsetY - state.parentTop
    setRcDrawerPosition({
      top: newTop,
      left: newLeft,
      right: null,
    })
  }, [])

  const handleRcDragEnd = useCallback((e: PointerEvent) => {
    const state = rcDragStateRef.current
    if (!state || e.pointerId !== state.pointerId) return

    rcDragStateRef.current = null
    window.removeEventListener('pointermove', handleRcDragMove)
    window.removeEventListener('pointerup', handleRcDragEnd)
  }, [handleRcDragMove])

  useEffect(() => {
    // Cleanup in case component unmounts while dragging
    return () => {
      window.removeEventListener('pointermove', handleRcDragMove)
      window.removeEventListener('pointerup', handleRcDragEnd)
    }
  }, [handleRcDragEnd, handleRcDragMove])

  const reorderStopSequence = useCallback((stopId: string, newSeq: number) => {
    setRcSelectedStops(prev => {
      const normalized = normalizeRcStops(prev)
      const idx = normalized.findIndex(s => s.stop_id === stopId)
      if (idx === -1) return prev
      const updated = normalized.map(s => ({ ...s }))
      const seq = Math.max(1, Math.floor(newSeq))
      updated[idx].sequence = seq
      updated.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
      for (let i = 1; i < updated.length; i++) {
        if ((updated[i].sequence ?? 0) <= (updated[i - 1].sequence ?? 0)) {
          updated[i].sequence = (updated[i - 1].sequence ?? 0) + 1
        }
      }
      return updated
    })
  }, [normalizeRcStops])

  const handleRouteCreatorStopSelection = useCallback((stopData: Omit<RCSelectedStop, 'pass'>) => {
    if (rcStep < 3) {
      setRcStep(3)
    }

    const normalized = normalizeRcStops(rcSelectedStops)
    const existingIdx = normalized.findIndex(s => s.stop_id === stopData.stop_id)

    // If the stop is already selected, open modal to edit its sequence
    if (existingIdx !== -1) {
      const currentSeq = normalized[existingIdx].sequence ?? (existingIdx + 1)
      setRcEditingExistingStop({ ...normalized[existingIdx] })
      setRcPendingStopPosition([stopData.lat, stopData.lon])
      rcNewStopForm.setValues({
        stop_id: stopData.stop_id,
        stop_code: stopData.stop_code || '',
        stop_name: stopData.stop_name,
        sequence: String(currentSeq),
      })
      setRcNewStopModalOpened(true)
      return
    }

    // Check if this stop_id already exists (for loop detection)
    const existingCount = normalized.filter(s => s.stop_id === stopData.stop_id).length
    if (existingCount > 0) {
      const addSecondPass = window.confirm(
        'Is this a second pass for this stop? Click "OK" to add a loop, or "Cancel" to remove this stop from the selection.'
      )
      if (addSecondPass) {
        const nextSeq = normalized.length + 1
        setRcSelectedStops(normalizeRcStops([...normalized, { ...stopData, pass: existingCount + 1, sequence: nextSeq }]))
      } else {
        setRcSelectedStops(normalizeRcStops(normalized.filter(s => s.stop_id !== stopData.stop_id)))
      }
      return
    }

    // New stop selection - add to list
    const nextSeq = normalized.length + 1
    setRcSelectedStops(normalizeRcStops([...normalized, { ...stopData, pass: 1, sequence: nextSeq }]))
  }, [normalizeRcStops, rcStep, rcSelectedStops, rcNewStopForm])

  const handleRouteCreatorNewStopSubmit = (values: typeof rcNewStopForm.values) => {
    if (!rcPendingStopPosition) return

    const parsedSeq = parseInt(values.sequence || '', 10)
    const desiredSeq = !isNaN(parsedSeq) && parsedSeq > 0 ? parsedSeq : undefined
    const currentNormalized = normalizeRcStops(rcSelectedStops)

    // Handle editing an existing (real) stop - only update sequence
    if (rcEditingExistingStop) {
      const stopId = rcEditingExistingStop.stop_id
      const currentIdx = currentNormalized.findIndex(s => s.stop_id === stopId)
      if (currentIdx === -1) {
        setRcNewStopModalOpened(false)
        setRcPendingStopPosition(null)
        setRcEditingExistingStop(null)
        rcNewStopForm.reset()
        return
      }

      const fallbackSeq = currentNormalized[currentIdx].sequence ?? currentIdx + 1
      const finalSeq = desiredSeq ?? fallbackSeq

      setRcSelectedStops(prev => {
        const normalized = normalizeRcStops(prev)
        const idx = normalized.findIndex(s => s.stop_id === stopId)
        if (idx === -1) return prev

        const editedStop = { ...normalized[idx], sequence: finalSeq }
        const others = normalized.filter((_, i) => i !== idx)

        // Check if desiredSeq conflicts with any other stop's sequence
        const hasConflict = others.some(s => s.sequence === finalSeq)

        // Find insert position
        let insertIdx = others.findIndex(s => (s.sequence ?? 0) >= finalSeq)
        if (insertIdx === -1) insertIdx = others.length

        const updated = [...others]
        updated.splice(insertIdx, 0, editedStop)

        if (!hasConflict) {
          return updated
        }

        // Bump conflicting sequences
        let lastSeq = 0
        return updated.map((s) => {
          if (s.stop_id === stopId) {
            lastSeq = finalSeq
            return s
          }
          const seq = s.sequence! <= lastSeq ? lastSeq + 1 : s.sequence!
          lastSeq = seq
          return { ...s, sequence: seq }
        })
      })

      setRcNewStopModalOpened(false)
      setRcPendingStopPosition(null)
      setRcEditingExistingStop(null)
      rcNewStopForm.reset()
      return
    }

    const duplicateId = rcNewStops.some(s => s.stop_id === values.stop_id) || stops.some(s => s.stop_id === values.stop_id)
    if (!rcEditingStopId && duplicateId) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: 'Stop ID already exists in this session',
        color: 'red',
      })
      return
    }

    const fallbackSeq =
      rcEditingStopId
        ? currentNormalized.find(s => s.stop_id === rcEditingStopId)?.sequence ?? currentNormalized.length + 1
        : currentNormalized.length + 1

    const newStop: RCNewStop = {
      stop_id: values.stop_id,
      stop_code: values.stop_code || undefined,
      stop_name: values.stop_name,
      lat: rcPendingStopPosition[0],
      lon: rcPendingStopPosition[1],
      isNew: true,
      pass: 1,
      sequence: desiredSeq ?? fallbackSeq,
    }

    if (rcEditingStopId) {
      // Update existing in-memory stop
      setRcNewStops(prev => prev.map(s => s.stop_id === rcEditingStopId ? { ...newStop } : s))
      setRcSelectedStops(prev => {
        const normalized = normalizeRcStops(prev)
        const currentIdx = normalized.findIndex(s => s.stop_id === rcEditingStopId)
        if (currentIdx === -1) return prev

        // Update the stop's properties
        const editedStop = { ...normalized[currentIdx], ...newStop, pass: normalized[currentIdx].pass || 1 }
        const others = normalized.filter((_, idx) => idx !== currentIdx)

        if (desiredSeq === undefined) {
          // No sequence change, keep current order and sequences
          return normalized.map((s, idx) => idx === currentIdx ? editedStop : s)
        }

        // Check if desiredSeq conflicts with any other stop's sequence
        const hasConflict = others.some(s => s.sequence === desiredSeq)

        // Find insert position: before the first stop with sequence >= desiredSeq
        let insertIdx = others.findIndex(s => (s.sequence ?? 0) >= desiredSeq)
        if (insertIdx === -1) insertIdx = others.length

        // Insert the edited stop at the right position with desired sequence
        const updated = [...others]
        updated.splice(insertIdx, 0, { ...editedStop, sequence: desiredSeq })

        if (!hasConflict) {
          // No conflict - keep all original sequences, just reordered
          return updated
        }

        // Has conflict - bump only the sequences that would create duplicates
        let lastSeq = 0
        return updated.map((s) => {
          const isEdited = s.stop_id === rcEditingStopId
          if (isEdited) {
            lastSeq = desiredSeq
            return s // already has desiredSeq
          }
          // Bump this stop's sequence only if it would overlap
          const seq = s.sequence! <= lastSeq ? lastSeq + 1 : s.sequence!
          lastSeq = seq
          return { ...s, sequence: seq }
        })
      })
    } else {
      setRcNewStops(prev => [...prev, newStop])
      setRcSelectedStops(prev => normalizeRcStops([...prev, newStop]))
    }

    setRcNewStopModalOpened(false)
    setRcPendingStopPosition(null)
    setRcEditingStopId(null)
    rcNewStopForm.reset()
  }

  const handleRcDeleteInMemoryStop = () => {
    if (!rcEditingStopId) return

    if (confirm(t('routeCreator.deleteConfirm', 'Are you sure you want to delete this stop from the map?'))) {
      setRcNewStops(prev => prev.filter(s => s.stop_id !== rcEditingStopId))
      setRcSelectedStops(prev => prev.filter(s => s.stop_id !== rcEditingStopId))
      setRcNewStopModalOpened(false)
      setRcEditingStopId(null)
      setRcPendingStopPosition(null)
      rcNewStopForm.reset()
    }
  }

  const handleRcRemoveStopFromList = (index: number) => {
    const stopToRemove = rcOrderedStops[index]
    if (!stopToRemove) return

    // Remove from selected list
    const newSelected = rcOrderedStops.filter((_, i) => i !== index)

    // We need to pass the denormalized list to setRcSelectedStops (without _idx, sequence might be recalculated)
    // But normalizeRcStops will handle re-sequencing. 
    // We can just filter the current rcSelectedStops based on the index?
    // Wait, rcOrderedStops is derived. rcSelectedStops is the source of truth.
    // The index in rcOrderedStops might not match rcSelectedStops if sorting changed, but
    // usually we display rcOrderedStops.
    // Let's rely on the stop object identity from rcOrderedStops

    // Find the item in rcSelectedStops that matches the one we want to remove
    // We need to be careful with duplicates (loops).
    // The normalized list has _idx from the original mapping if we preserved it, but here we don't have it easily.
    // However, rcOrderedStops[index] corresponds to the user's view.

    // Let's filter rcSelectedStops. 
    // To do it correctly with duplicates, we need to know exactly which instance to remove.
    // Since rcOrderedStops is derived from rcSelectedStops with a stable sort:
    // "withIndex.map((s, idx) => ...)"
    // The best way is to reconstruct rcSelectedStops from rcOrderedStops minus the removed item.

    const updatedList = newSelected.map(({ pass, sequence, ...rest }) => ({ ...rest, pass, sequence }))
    setRcSelectedStops(updatedList)

    // Check if we should remove from rcNewStops (map)
    if (stopToRemove.isNew) {
      const stillInList = updatedList.some(s => s.stop_id === stopToRemove.stop_id)
      if (!stillInList) {
        setRcNewStops(prev => prev.filter(s => s.stop_id !== stopToRemove.stop_id))
      }
    }
  }

  const handleRcReorderStops = (fromIndex: number, toIndex: number) => {
    setRcSelectedStops(prev => {
      const ordered = normalizeRcStops(prev)
      if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= ordered.length || toIndex >= ordered.length) {
        return prev
      }
      const updated = [...ordered]
      const [moved] = updated.splice(fromIndex, 1)
      updated.splice(toIndex, 0, moved)
      // Re-sequence contiguously after drag
      return updated.map((s, idx) => ({ ...s, sequence: idx + 1 }))
    })
  }

  const handleRCMarkerDrag = (index: number, lat: number, lon: number) => {
    setRcShapePoints(prev => prev.map((p, idx) => idx === index ? { lat, lon } : p))
  }

  const handleRcNewStopDrag = (stopId: string, lat: number, lon: number) => {
    // Update position in rcNewStops
    setRcNewStops(prev => prev.map(s => s.stop_id === stopId ? { ...s, lat, lon } : s))
    // Update position in rcSelectedStops
    setRcSelectedStops(prev => prev.map(s => s.stop_id === stopId ? { ...s, lat, lon } : s))
  }

  const handleRCRemovePoint = (index: number) => {
    setRcShapePoints(prev => prev.filter((_, idx) => idx !== index))
  }

  const handleRCSelectImprovePoint = (index: number) => {
    setRcImproveSelection(prev => {
      if (prev.start === null || (prev.start !== null && prev.end !== null)) {
        return { start: index, end: null }
      }
      if (prev.start === index) return { start: null, end: null }
      return { start: prev.start, end: index }
    })
  }

  const handleRouteCreatorGenerateShape = async () => {
    if (!selectedFeed) {
      notifications.show({ title: t('common.error', 'Error'), message: 'Select a feed first', color: 'red' })
      return
    }
    if (rcOrderedStops.length < 2) {
      notifications.show({ title: t('common.error', 'Error'), message: 'Select at least 2 stops to generate a shape', color: 'red' })
      return
    }

    setRcShapeGenerating(true)
    try {
      const waypoints = rcOrderedStops.map(s => ({ lat: s.lat, lon: s.lon }))
      const result = await routingApi.autoRoute({
        feed_id: parseInt(selectedFeed),
        shape_id: `rc_${Date.now()}`,
        waypoints,
      })

      if (!result?.points || result.points.length === 0) {
        throw new Error(result?.message || 'Routing failed')
      }

      setRcShapePoints(result.points.map(p => ({ lat: p.lat, lon: p.lon })))
      notifications.show({
        title: t('common.success', 'Success'),
        message: 'Shape generated from Valhalla (in-memory)',
        color: 'green',
      })
    } catch (error: any) {
      // Fallback: straight line through selected stops if routing service is down
      setRcShapePoints(rcOrderedStops.map(s => ({ lat: s.lat, lon: s.lon })))
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || error?.message || 'Routing unavailable. Using straight line between stops.',
        color: 'orange',
      })
    } finally {
      setRcShapeGenerating(false)
    }
  }

  const handleImproveSegment = async () => {
    if (!selectedFeed || rcImproveSelection.start === null || rcImproveSelection.end === null) {
      notifications.show({ title: t('common.error', 'Error'), message: 'Select start and end points for the segment', color: 'red' })
      return
    }
    if (rcImproveSelection.end <= rcImproveSelection.start) {
      notifications.show({ title: t('common.error', 'Error'), message: 'End point must come after start point', color: 'red' })
      return
    }

    const startPoint = rcShapePoints[rcImproveSelection.start]
    const endPoint = rcShapePoints[rcImproveSelection.end]
    if (!startPoint || !endPoint) return

    try {
      const result = await routingApi.autoRoute({
        feed_id: parseInt(selectedFeed!),
        shape_id: `rc_segment_${Date.now()}`,
        waypoints: [
          { lat: startPoint.lat, lon: startPoint.lon },
          { lat: endPoint.lat, lon: endPoint.lon },
        ],
      })
      if (!result?.points || result.points.length === 0) {
        throw new Error(result?.message || 'Routing failed')
      }

      const newSegment = result.points.map(p => ({ lat: p.lat, lon: p.lon }))
      setRcShapePoints(prev => {
        const before = prev.slice(0, rcImproveSelection.start + 1)
        const after = prev.slice(rcImproveSelection.end)
        return [...before, ...newSegment.slice(1, -1), ...after]
      })
      notifications.show({
        title: t('common.success', 'Success'),
        message: 'Segment improved (in-memory only)',
        color: 'green',
      })
      setRcImproveSegmentMode(false)
      setRcImproveSelection({ start: null, end: null })
    } catch (error: any) {
      // Fallback: keep the original segment and notify
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || error?.message || 'Routing unavailable. Segment left unchanged.',
        color: 'orange',
      })
    }
  }

  const timeStringToSeconds = (time: string) => {
    const [h, m] = time.split(':').map(Number)
    return h * 3600 + m * 60
  }

  const secondsToTimeString = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    const pad = (n: number) => n.toString().padStart(2, '0')
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`
  }

  const handleTripBlockToggle = (time: string) => {
    setRcTrips(prev => prev.includes(time) ? prev.filter(t => t !== time) : [...prev, time].sort())
  }

  const computeStopTimes = () => {
    if (rcOrderedStops.length === 0 || rcShapePoints.length < 2 || rcTrips.length === 0) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: 'Select stops, generate a shape, and add trips first',
        color: 'red',
      })
      return
    }

    // Precompute cumulative distances along shape
    const toRad = (deg: number) => (deg * Math.PI) / 180
    const haversine = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) => {
      const R = 6371000
      const dLat = toRad(b.lat - a.lat)
      const dLon = toRad(b.lon - a.lon)
      const la1 = toRad(a.lat)
      const la2 = toRad(b.lat)
      const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2
      return 2 * R * Math.asin(Math.sqrt(h))
    }

    const cumulative: number[] = [0]
    for (let i = 1; i < rcShapePoints.length; i++) {
      cumulative[i] = cumulative[i - 1] + haversine(rcShapePoints[i - 1], rcShapePoints[i])
    }

    // Map each stop to nearest shape point distance
    const stopDistances: number[] = []
    rcOrderedStops.forEach((stop, idx) => {
      let bestIdx = 0
      let bestDist = Number.MAX_VALUE
      rcShapePoints.forEach((p, i) => {
        const dist = haversine({ lat: stop.lat, lon: stop.lon }, p)
        if (dist < bestDist) {
          bestDist = dist
          bestIdx = i
        }
      })
      // Ensure monotonic progression along path
      let distanceAlong = cumulative[bestIdx]
      if (idx > 0 && distanceAlong < stopDistances[idx - 1]) {
        distanceAlong = stopDistances[idx - 1]
      }
      stopDistances.push(distanceAlong)
    })

    const avgSpeedMps = 8.33 // ~30 km/h
    const dwellSeconds = 20
    const table: Record<string, string[]> = {}

    rcTrips.forEach(tripTime => {
      const tripSeconds = timeStringToSeconds(tripTime)
      const timesForTrip: string[] = []
      stopDistances.forEach((dist, idx) => {
        const travelSeconds = dist / avgSpeedMps
        const dwell = idx === 0 ? 0 : dwellSeconds * idx
        const t = tripSeconds + travelSeconds + dwell
        timesForTrip.push(secondsToTimeString(t))
      })
      table[tripTime] = timesForTrip
    })

    setRcStopTimesTable(table)
    setRcStep(6)
  }

  const handleStopTimeChange = (tripId: string, stopIdx: number, value: string) => {
    setRcStopTimesTable(prev => {
      const next = { ...prev }
      const arr = [...(next[tripId] || [])]
      arr[stopIdx] = value
      next[tripId] = arr
      return next
    })
  }

  const buildGTFSExportFiles = () => {
    const routeId = rcRouteId || `RC_ROUTE_${Date.now()}`
    const shapeId = `${routeId}_shape`
    const routeColor = (rcRouteColor || '#0ea5e9').replace('#', '')
    const routeShort = rcRouteShortName || routeId

    const routesTxt = `route_id,route_short_name,route_long_name,route_type,route_color\n${routeId},${routeShort},${routeShort},3,${routeColor}\n`

    const stopsTxtLines = ['stop_id,stop_code,stop_name,stop_lat,stop_lon']
    rcNewStops.forEach(stop => {
      stopsTxtLines.push([
        stop.stop_id,
        stop.stop_code || '',
        stop.stop_name,
        stop.lat,
        stop.lon,
      ].join(','))
    })
    const stopsTxt = `${stopsTxtLines.join('\n')}\n`

    const shapesTxtLines = ['shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence']
    rcShapePoints.forEach((p, idx) => {
      shapesTxtLines.push([shapeId, p.lat, p.lon, idx + 1].join(','))
    })
    const shapesTxt = `${shapesTxtLines.join('\n')}\n`

    const tripsTxtLines = ['route_id,service_id,trip_id,shape_id']
    const stopTimesTxtLines = ['trip_id,arrival_time,departure_time,stop_id,stop_sequence']
    const serviceId = 'RC_SERVICE'

    rcTrips.forEach((tripTime, tripIdx) => {
      const tripId = `${routeId}_${tripIdx + 1}`
      tripsTxtLines.push([routeId, serviceId, tripId, shapeId].join(','))

      const times = rcStopTimesTable[tripTime] || []
      rcOrderedStops.forEach((stop, stopIdx) => {
        const timeStr = times[stopIdx] || `${tripTime}:00`
        stopTimesTxtLines.push([tripId, timeStr, timeStr, stop.stop_id, stop.sequence ?? stopIdx + 1].join(','))
      })
    })

    const tripsTxt = `${tripsTxtLines.join('\n')}\n`
    const stopTimesTxt = `${stopTimesTxtLines.join('\n')}\n`

    return {
      routes: routesTxt,
      stops: stopsTxt,
      shapes: shapesTxt,
      trips: tripsTxt,
      stop_times: stopTimesTxt,
    }
  }

  const downloadGTFSFile = (name: string, content: string) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleExportGTFS = () => {
    if (rcTrips.length === 0 || Object.keys(rcStopTimesTable).length === 0) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: 'Generate a schedule first',
        color: 'red',
      })
      return
    }
    const files = buildGTFSExportFiles()
    downloadGTFSFile('routes.txt', files.routes)
    downloadGTFSFile('stops.txt', files.stops)
    downloadGTFSFile('shapes.txt', files.shapes)
    downloadGTFSFile('trips.txt', files.trips)
    downloadGTFSFile('stop_times.txt', files.stop_times)
    notifications.show({
      title: t('common.success', 'Success'),
      message: 'Exported GTFS text files (in-memory data)',
      color: 'green',
    })
  }

  // Shape editing handlers
  const handleStartEditingShape = useCallback((shapeId: string) => {
    const shape = shapes.find(s => s.shape_id === shapeId)
    if (!shape) return

    setEditingShapeId(shapeId)
    setEditingShapePoints(
      shape.points.map((p, idx) => ({
        lat: p.lat,
        lon: p.lon,
        sequence: p.shape_pt_sequence || idx
      }))
    )
    setCreatingNewShape(false)
  }, [shapes])

  const handleStartCreateShape = useCallback(() => {
    setCreatingNewShape(true)
    setNewShapePoints([])
    setEditingShapeId(null)
    setEditingShapePoints([])
    setNewShapeId(`shape_${Date.now()}`)
  }, [])

  const handleAddPointToExistingShape = useCallback((index: number, lat: number, lon: number) => {
    setEditingShapePoints(prev => {
      const newPoints = [...prev]
      // Insert new point after the clicked segment
      newPoints.splice(index + 1, 0, {
        lat,
        lon,
        sequence: index + 0.5 // Temporary sequence, will be renumbered on save
      })
      // Renumber sequences
      return newPoints.map((p, i) => ({ ...p, sequence: i }))
    })
  }, [])

  const handleDeleteShapePoint = useCallback((index: number) => {
    setEditingShapePoints(prev => {
      const newPoints = prev.filter((_, i) => i !== index)
      // Renumber sequences
      return newPoints.map((p, i) => ({ ...p, sequence: i }))
    })
  }, [])

  const handleMoveShapePoint = useCallback((index: number, lat: number, lon: number) => {
    setEditingShapePoints(prev => {
      const newPoints = [...prev]
      newPoints[index] = { ...newPoints[index], lat, lon }
      return newPoints
    })
  }, [])

  const handleSaveShape = async () => {
    if (!selectedFeed || !editingShapeId) return

    try {
      const shapeData = {
        feed_id: parseInt(selectedFeed),
        shape_id: editingShapeId,
        points: editingShapePoints.map((p, idx) => ({
          lat: p.lat,
          lon: p.lon,
          sequence: idx,
        }))
      }

      // Use bulk endpoint with replace_existing=true to update all points
      await shapesApi.bulkCreate(shapeData, true)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('map.shapes.shapeSaved', 'Shape saved successfully'),
        color: 'green',
      })

      // Reload shapes using the correct endpoint
      const shapesResponse = await shapesApi.getByShapeId({ feed_id: parseInt(selectedFeed) })
      setShapes(shapesResponse.items || [])

      setEditingShapeId(null)
      setEditingShapePoints([])
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('map.shapes.saveError', 'Failed to save shape'),
        color: 'red',
      })
    }
  }

  const handleSaveNewShape = async () => {
    if (!selectedFeed || !newShapeId || newShapePoints.length < 2) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('map.shapes.needTwoPoints', 'A shape needs at least 2 points'),
        color: 'red',
      })
      return
    }

    try {
      const shapeData = {
        feed_id: parseInt(selectedFeed),
        shape_id: newShapeId,
        points: newShapePoints.map((p, idx) => ({
          lat: p.lat,
          lon: p.lon,
          sequence: idx,
        }))
      }

      await shapesApi.bulkCreate(shapeData, false)

      notifications.show({
        title: t('common.success', 'Success'),
        message: t('map.shapes.shapeCreated', 'Shape created successfully'),
        color: 'green',
      })

      // Reload shapes using the correct endpoint
      const shapesResponse = await shapesApi.getByShapeId({ feed_id: parseInt(selectedFeed) })
      setShapes(shapesResponse.items || [])

      setCreatingNewShape(false)
      setNewShapePoints([])
      setNewShapeId('')
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('map.shapes.createError', 'Failed to create shape'),
        color: 'red',
      })
    }
  }

  const handleCancelShapeEdit = () => {
    setEditingShapeId(null)
    setEditingShapePoints([])
    setCreatingNewShape(false)
    setNewShapePoints([])
    setNewShapeId('')
  }

  const handleSplitShapeSegment = useCallback((index: number, lat: number, lon: number) => {
    // Split creates two shapes from one
    if (!editingShapeId) return

    const pointsBeforeSplit = editingShapePoints.slice(0, index + 1)
    const pointsAfterSplit = editingShapePoints.slice(index + 1)

    // Add the split point to both shapes
    const splitPoint = { lat, lon, sequence: index }
    pointsBeforeSplit.push(splitPoint)
    pointsAfterSplit.unshift(splitPoint)

    // For now, just show a notification - full implementation would create two shapes
    notifications.show({
      title: t('map.shapes.splitSegment', 'Split Segment'),
      message: t('map.shapes.splitWillCreate', 'This will create two shapes. Feature coming soon.'),
      color: 'blue',
    })
  }, [editingShapeId, editingShapePoints, t])

  // Fetch real-time data - uses refs to avoid dependency changes triggering effect re-runs
  const fetchRealtimeData = useCallback(async () => {
    if (!selectedAgency || !realtimeEnabled) return

    // Check if enough time has passed since last successful call to avoid 429 rate limiting
    const now = Date.now()
    const timeSinceLastFetch = now - lastSuccessfulFetchRef.current
    if (lastSuccessfulFetchRef.current > 0 && timeSinceLastFetch < MIN_FETCH_INTERVAL) {
      console.debug(`Skipping realtime fetch - only ${timeSinceLastFetch}ms since last call (min: ${MIN_FETCH_INTERVAL}ms)`)
      return
    }

    // Don't set loading state on subsequent fetches to prevent UI flicker
    const isInitial = isInitialFetchRef.current
    if (isInitial) {
      setRealtimeLoading(true)
    }
    setRealtimeError(null)

    try {
      const data = await realtimeApi.getAllRealtimeData(selectedAgency)

      // Update last successful fetch timestamp
      lastSuccessfulFetchRef.current = Date.now()
      isInitialFetchRef.current = false

      // Merge vehicles intelligently to preserve references when possible
      const newVehicles = data.vehicles || []
      setVehicles(prevVehicles => {
        // Create a map of previous vehicles for O(1) lookup
        const prevMap = new Map(prevVehicles.map(v => [v.vehicle_id, v]))

        // Check if we need to update at all
        let hasAnyChange = prevVehicles.length !== newVehicles.length

        // Merge: keep old reference if position hasn't changed significantly
        const mergedVehicles = newVehicles.map((newV: VehiclePosition) => {
          const oldV = prevMap.get(newV.vehicle_id)
          if (!oldV) {
            hasAnyChange = true
            return newV
          }

          const latDiff = Math.abs(newV.latitude - oldV.latitude)
          const lonDiff = Math.abs(newV.longitude - oldV.longitude)
          const bearingDiff = Math.abs((newV.bearing || 0) - (oldV.bearing || 0))

          // Only update if moved more than ~5 meters or bearing changed by 10+ degrees
          if (latDiff > 0.00005 || lonDiff > 0.00005 || bearingDiff > 10) {
            hasAnyChange = true
            return newV
          }

          // Keep old reference to prevent re-render
          return oldV
        })

        return hasAnyChange ? mergedVehicles : prevVehicles
      })

      setTripUpdates(data.trip_updates || [])
      setAlerts(data.alerts || [])
      setTripModifications(data.trip_modifications || [])
      setRealtimeShapes(data.shapes || [])
      setRealtimeStops(data.stops || [])

      if (data.errors && data.errors.length > 0) {
        console.warn('Real-time feed errors:', data.errors)
      }
    } catch (error: any) {
      console.error('Failed to fetch real-time data:', error)
      setRealtimeError(error.message || 'Failed to fetch real-time data')
    } finally {
      if (isInitial) {
        setRealtimeLoading(false)
      }
    }
  }, [selectedAgency, realtimeEnabled])

  // Real-time polling effect - 5 second interval with timestamp check to avoid rate limiting
  useEffect(() => {
    if (realtimeEnabled && selectedAgency) {
      // Reset refs when enabling realtime for immediate first fetch
      lastSuccessfulFetchRef.current = 0
      isInitialFetchRef.current = true

      // Initial fetch
      fetchRealtimeData()

      // Set up polling interval (5 seconds, but actual API calls throttled by timestamp check)
      realtimeIntervalRef.current = setInterval(fetchRealtimeData, 5000)

      return () => {
        if (realtimeIntervalRef.current) {
          clearInterval(realtimeIntervalRef.current)
          realtimeIntervalRef.current = null
        }
      }
    } else {
      setVehicles([])
      setTripUpdates([])
      setAlerts([])
      setTripModifications([])
      isInitialFetchRef.current = true
      if (realtimeIntervalRef.current) {
        clearInterval(realtimeIntervalRef.current)
        realtimeIntervalRef.current = null
      }
    }
    // Note: fetchRealtimeData is stable (only depends on selectedAgency and realtimeEnabled)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtimeEnabled, selectedAgency])

  // Create a lookup map from route_id to route object for quick access
  const routeByIdMap = useMemo(() => {
    const map: Record<string, any> = {}
    routes.forEach(route => {
      map[route.route_id] = route
    })
    return map
  }, [routes])

  // Filter trips by selected calendars
  const filteredTrips = useMemo(() => {
    console.log('[Map Filter] filteredTrips calculation:', {
      totalTrips: trips.length,
      calendarsLoaded: calendars.length,
      selectedCalendars: selectedCalendarIds.size,
      tripsWithShapeId: trips.filter(t => t.shape_id).length,
      tripsWithRouteId: trips.filter(t => t.route_id).length,
    })

    // If no calendars are selected or no calendars loaded, show all trips
    if (calendars.length === 0 || selectedCalendarIds.size === 0) {
      console.log('[Map Filter] No calendar filter applied, using all trips')
      return trips
    }

    // Filter trips by service_id matching selected calendar service_ids
    const filtered = trips.filter(trip => {
      return selectedCalendarIds.has(trip.service_id)
    })

    console.log('[Map Filter] Trips filtered by calendar:', {
      before: trips.length,
      after: filtered.length,
      filteredWithShapeId: filtered.filter(t => t.shape_id).length,
    })

    return filtered
  }, [trips, selectedCalendarIds, calendars.length])

  // Create a lookup map from shape_id to route color
  // Uses trips to connect shapes to routes (Route -> Trip -> Shape)
  const shapeColorMap = useMemo(() => {
    const colorMap: Record<string, string> = {}

    // For each trip, map its shape to its route's color
    filteredTrips.forEach(trip => {
      if (trip.shape_id && trip.route_id) {
        const route = routeByIdMap[trip.route_id]
        if (route && route.route_color && !colorMap[trip.shape_id]) {
          // GTFS route_color doesn't include # prefix
          const color = route.route_color.startsWith('#') ? route.route_color : `#${route.route_color}`
          colorMap[trip.shape_id] = color
        }
      }
    })

    return colorMap
  }, [filteredTrips, routeByIdMap])

  // Create a lookup map from shape_id to route_id
  // Primary source: trips (Route -> Trip -> Shape) - standard GTFS
  // Fallback: routes with shape_id (non-standard extension)
  const shapeToRouteMap = useMemo(() => {
    const map: Record<string, Set<string>> = {}
    let tripsWithShape = 0
    let routesWithShape = 0

    // Debug: sample the trips data
    if (filteredTrips.length > 0) {
      const sampleTrip = filteredTrips[0]
      console.log('[Map Filter] Sample trip:', {
        trip_id: sampleTrip.trip_id,
        route_id: sampleTrip.route_id,
        shape_id: sampleTrip.shape_id,
        hasShapeId: !!sampleTrip.shape_id,
        hasRouteId: !!sampleTrip.route_id,
      })
    }

    // First, try to build from trips (standard GTFS relationship)
    filteredTrips.forEach(trip => {
      if (trip.shape_id && trip.route_id) {
        tripsWithShape++
        if (!map[trip.shape_id]) {
          map[trip.shape_id] = new Set()
        }
        map[trip.shape_id].add(trip.route_id)
      }
    })

    // If no trip->shape mappings found, try routes with shape_id (fallback)
    if (Object.keys(map).length === 0) {
      routes.forEach(route => {
        // @ts-ignore - shape_id might not be on Route type but could be in data
        if ((route as any).shape_id) {
          routesWithShape++
          // @ts-ignore
          if (!map[(route as any).shape_id]) {
            // @ts-ignore
            map[(route as any).shape_id] = new Set()
          }
          // @ts-ignore
          map[(route as any).shape_id].add(route.route_id)
        }
      })
    }

    console.log('[Map Filter] shapeToRouteMap:', {
      totalTrips: filteredTrips.length,
      tripsWithShapeAndRoute: tripsWithShape,
      routesWithShapeId: routesWithShape,
      uniqueShapes: Object.keys(map).length,
    })
    return map
  }, [filteredTrips, routes])

  // Flag to track if route-to-shape filtering is available
  const canFilterShapesByRoute = useMemo(() => {
    return Object.keys(shapeToRouteMap).length > 0
  }, [shapeToRouteMap])

  // Get available shapes (shapes that belong to selected routes)
  const availableShapes = useMemo(() => {
    console.log('[Map Filter] availableShapes calculation:', {
      totalShapes: shapes.length,
      selectedRoutesCount: selectedRouteIds.size,
      selectedRouteIds: Array.from(selectedRouteIds).slice(0, 5),
      shapeToRouteMapSize: Object.keys(shapeToRouteMap).length,
      canFilterShapesByRoute,
    })

    // If no routes selected, show no shapes
    if (selectedRouteIds.size === 0) {
      console.log('[Map Filter] No routes selected, showing no shapes')
      return []
    }

    // If the shape-to-route map is empty (trips don't have shape_id),
    // we can't filter shapes by route - return all shapes but warn
    if (!canFilterShapesByRoute) {
      console.warn('[Map Filter] Cannot filter shapes by routes: trips have no shape_id. Showing all shapes.')
      return shapes
    }

    const filtered = shapes.filter(shape => {
      const routeIds = shapeToRouteMap[shape.shape_id]
      if (!routeIds) return false
      // Show shape if any of its routes are selected
      for (const routeId of routeIds) {
        if (selectedRouteIds.has(routeId)) return true
      }
      return false
    })

    console.log('[Map Filter] Filtered shapes by route:', {
      input: shapes.length,
      output: filtered.length,
    })

    return filtered
  }, [shapes, selectedRouteIds, shapeToRouteMap, canFilterShapesByRoute])

  // Compute orphan shapes (shapes not associated with any route via trips)
  const orphanShapes = useMemo(() => {
    if (Object.keys(shapeToRouteMap).length === 0) {
      // No mapping available, can't determine orphans
      return []
    }
    return shapes.filter(shape => !shapeToRouteMap[shape.shape_id])
  }, [shapes, shapeToRouteMap])

  // Filter shapes based on selected shapes
  const filteredShapes = useMemo(() => {
    // Start with shapes from selected routes (filtered by selectedShapeIds)
    let result = availableShapes.filter(shape => selectedShapeIds.has(shape.shape_id))

    // Add orphan shapes if the toggle is enabled
    if (showOrphanShapes && orphanShapes.length > 0) {
      // Avoid duplicates
      const existingIds = new Set(result.map(s => s.shape_id))
      const newOrphans = orphanShapes.filter(s => !existingIds.has(s.shape_id))
      result = [...result, ...newOrphans]
    }

    console.log('[Map Filter] filteredShapes:', {
      availableShapes: availableShapes.length,
      selectedShapeIds: selectedShapeIds.size,
      orphanShapesCount: orphanShapes.length,
      showOrphanShapes,
      result: result.length,
    })
    return result
  }, [availableShapes, selectedShapeIds, showOrphanShapes, orphanShapes])

  // Compute effective selected shapes count (shapes that are both selected AND available)
  const effectiveSelectedShapesCount = useMemo(() => {
    const availableIds = new Set(availableShapes.map(s => s.shape_id))
    let count = 0
    for (const shapeId of selectedShapeIds) {
      if (availableIds.has(shapeId)) count++
    }
    return count
  }, [availableShapes, selectedShapeIds])

  // Compute all stops that are in at least one route (have stop_times)
  const stopsInRoutes = useMemo(() => {
    const stopIds = new Set<string>()
    Object.values(routeToStopsMap).forEach(routeStopIds => {
      routeStopIds.forEach(stopId => stopIds.add(stopId))
    })
    return stopIds
  }, [routeToStopsMap])

  // Compute orphan stops (stops not associated with any trip/route)
  const orphanStops = useMemo(() => {
    if (Object.keys(routeToStopsMap).length === 0) {
      // No mapping available, can't determine orphans
      return []
    }
    return stops.filter(stop => !stopsInRoutes.has(stop.stop_id))
  }, [stops, stopsInRoutes, routeToStopsMap])

  // Filter stops based on selected routes using routeToStopsMap (excludes orphan stops - they're rendered separately)
  const filteredStops = useMemo(() => {
    console.log('[Map Filter] filteredStops calculation:', {
      totalStops: stops.length,
      selectedRoutesCount: selectedRouteIds.size,
      routeToStopsMapSize: Object.keys(routeToStopsMap).length,
    })

    // Start with stops from selected routes
    let result: Stop[] = []

    // If routes are selected, include their stops
    if (selectedRouteIds.size > 0) {
      // If no route-stops mapping is available, show all stops (fallback)
      if (Object.keys(routeToStopsMap).length === 0) {
        console.log('[Map Filter] Route-stops mapping not available, showing all stops as fallback')
        result = [...stops]
      } else {
        // Build set of stop_ids that belong to selected routes
        const selectedStopIds = new Set<string>()
        for (const routeId of selectedRouteIds) {
          const stopIds = routeToStopsMap[routeId]
          if (stopIds) {
            stopIds.forEach(stopId => selectedStopIds.add(stopId))
          }
        }

        // Filter stops by selected stop_ids
        result = stops.filter(stop => selectedStopIds.has(stop.stop_id))
      }
    }

    // Note: Orphan stops are NOT included here - they're rendered separately with their own toggle

    console.log('[Map Filter] Filtered stops:', {
      input: stops.length,
      output: result.length,
    })

    return result
  }, [stops, selectedRouteIds, routeToStopsMap])

  // Default color palette for routes without GTFS colors
  const defaultRouteColors = useMemo(() =>
    ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'],
    []
  )

  // Lookup maps for vehicle popup - quick access to names by ID
  const routeByGtfsId = useMemo(() => {
    const map = new Map<string, Route>()
    routes.forEach(route => {
      map.set(route.route_id, route)
    })
    return map
  }, [routes])

  const stopByGtfsId = useMemo(() => {
    const map = new Map<string, Stop>()
    stops.forEach(stop => {
      map.set(stop.stop_id, stop)
    })
    return map
  }, [stops])

  const tripByGtfsId = useMemo(() => {
    const map = new Map<string, Trip>()
    trips.forEach(trip => {
      map.set(trip.trip_id, trip)
    })
    return map
  }, [trips])

  const shapeByShapeId = useMemo(() => {
    const map = new Map<string, RouteShape>()
    shapes.forEach(shape => {
      map.set(shape.shape_id, shape)
    })
    return map
  }, [shapes])

  // Compute stops affected by trip modifications (detours)
  const affectedStopIds = useMemo(() => {
    const affected = new Set<string>()
    if (showTripModifications && tripModifications.length > 0) {
      tripModifications.forEach(mod => {
        if (mod.affected_stop_ids) {
          mod.affected_stop_ids.forEach(stopId => affected.add(stopId))
        }
        // Also check within modifications array
        mod.modifications?.forEach(m => {
          if (m.start_stop?.stop_id) affected.add(m.start_stop.stop_id)
          if (m.end_stop?.stop_id) affected.add(m.end_stop.stop_id)
        })
      })
    }
    return affected
  }, [tripModifications, showTripModifications])

  // Normalize RC stops with sequence numbers, and map stop_id -> labels
  const rcSelectionLabels = useMemo(() => {
    const map = new Map<string, string>()
    rcOrderedStops.forEach((s) => {
      const label = `${s.sequence}${s.pass > 1 ? `(${s.pass})` : ''}`
      const existing = map.get(s.stop_id)
      map.set(s.stop_id, existing ? `${existing},${label}` : label)
    })
    return map
  }, [rcOrderedStops])

  const rcSortedTrips = useMemo(() => [...rcTrips].sort(), [rcTrips])
  const rcDrawerWidth = useMemo(() => {
    if (isMobile) return '96vw'
    return (rcStep === 5 || rcStep === 6 || rcStep === 7) ? '90vw' : 420
  }, [isMobile, rcStep])
  const rcStopTimesMinWidth = useMemo(() => {
    const base = 160 // sticky stop column
    const perTrip = 70 // tighter cells to fit more trips per row
    const min = 600
    return Math.max(min, base + rcTrips.length * perTrip)
  }, [rcTrips.length])

  // Route Creator step guards
  const canGoToRoute = rcSelectedServiceIds.length > 0
  const canGoToStops = canGoToRoute && ((rcUseExistingRoute && rcSelectedExistingRouteId && (rcSelectedDirection || rcAvailableDirections.length <= 1)) || (!rcUseExistingRoute && (rcRouteId.trim().length > 0 || rcRouteShortName.trim().length > 0)))
  const canGoToShape = rcOrderedStops.length >= 2
  const canGoToSchedule = rcShapePoints.length >= 2 && rcOrderedStops.length >= 2
  const canGoToStopTimes = rcTrips.length > 0 && Object.keys(rcStopTimesTable).length > 0

  // Reset shape-add mode when leaving shape step
  useEffect(() => {
    if (rcStep !== 4 && rcAddPointMode) {
      setRcAddPointMode(false)
    }
  }, [rcStep, rcAddPointMode])

  // Get the highlighted shape for selected vehicle
  const highlightedShape = useMemo(() => {
    if (!selectedVehicleId) return null
    const vehicle = vehicles.find(v => v.vehicle_id === selectedVehicleId)
    if (!vehicle?.trip_id && !vehicle?.route_id) return null

    // First try: get shape from the specific trip
    const trip = vehicle.trip_id ? tripByGtfsId.get(vehicle.trip_id) : null
    if (trip?.shape_id) {
      const shape = shapeByShapeId.get(trip.shape_id)
      if (shape) return shape
    }

    // Fallback: find any trip on the same route that has a shape
    if (vehicle.route_id) {
      for (const t of trips) {
        if (t.route_id === vehicle.route_id && t.shape_id) {
          const shape = shapeByShapeId.get(t.shape_id)
          if (shape) return shape
        }
      }
    }

    return null
  }, [selectedVehicleId, vehicles, tripByGtfsId, shapeByShapeId, trips])

  // Cache for vehicle icons to prevent re-creation on every render
  const vehicleIconCache = useRef<Map<string, DivIcon>>(new Map())

  // Create vehicle icon with bearing - uses cache to prevent blinking
  const getVehicleIcon = useCallback((bearing?: number, routeColor?: string) => {
    // Round bearing to nearest 5 degrees to reduce cache misses
    const roundedBearing = bearing ? Math.round(bearing / 5) * 5 : 0
    const color = routeColor || '#ef4444'
    const cacheKey = `${roundedBearing}-${color}`

    let icon = vehicleIconCache.current.get(cacheKey)
    if (!icon) {
      icon = new DivIcon({
        className: 'vehicle-marker',
        html: `
          <div style="
            transform: rotate(${roundedBearing}deg);
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
          ">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="${color}" stroke="white" stroke-width="1">
              <path d="M12 2L4 14h16L12 2z"/>
              <circle cx="12" cy="16" r="4" fill="${color}"/>
            </svg>
          </div>
        `,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      })
      vehicleIconCache.current.set(cacheKey, icon)
    }
    return icon
  }, [])

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedFeed) {
      loadGTFSDataByFeed(parseInt(selectedFeed))
    } else if (selectedAgency) {
      loadGTFSDataByAgency(selectedAgency)
    } else {
      setStops([])
      setRoutes([])
      setShapes([])
      setTrips([])
      setSelectedRouteIds(new Set())
      setSelectedShapeIds(new Set())
    }
  }, [selectedFeed, selectedAgency])

  // Get available routes (routes that have trips in selected calendars)
  const availableRoutes = useMemo(() => {
    // If no calendars loaded/selected or trips didn't load, show all routes
    if (calendars.length === 0 || selectedCalendarIds.size === 0 || filteredTrips.length === 0) return routes

    const routeIds = new Set<string>()
    filteredTrips.forEach(trip => {
      if (trip.route_id) {
        routeIds.add(trip.route_id)
      }
    })
    return routes.filter(route => routeIds.has(route.route_id))
  }, [routes, filteredTrips, selectedCalendarIds, calendars.length])

  // Compute effective selected routes count (routes that are both selected AND available)
  const effectiveSelectedRoutesCount = useMemo(() => {
    const availableIds = new Set(availableRoutes.map(r => r.route_id))
    let count = 0
    for (const routeId of selectedRouteIds) {
      if (availableIds.has(routeId)) count++
    }
    return count
  }, [availableRoutes, selectedRouteIds])

  // NOTE: We no longer auto-select all routes/shapes when availableRoutes/availableShapes change.
  // This was overwriting user selections. Instead, we select all only on initial data load
  // (in loadGTFSDataByFeed) and let users filter from there.

  // Load calendars function (extracted for reuse)
  const loadCalendars = useCallback(async () => {
    if (!selectedFeed) {
      setCalendars([])
      setSelectedCalendarIds(new Set())
      return
    }

    try {
      // Load calendars from the /calendars/ endpoint (plural)
      // Note: Backend has a max limit of 1000
      const response = await calendarsApi.list(parseInt(selectedFeed), { limit: 1000 })
      const loadedCalendars = response.items || []
      setCalendars(loadedCalendars)
      // Select all calendar service_ids by default
      setSelectedCalendarIds(new Set(loadedCalendars.map((c: any) => c.service_id)))
    } catch (error: any) {
      console.error('Failed to load calendars:', error)
      setCalendars([])
      setSelectedCalendarIds(new Set())
    }
  }, [selectedFeed])

  // Load calendars when feed changes
  useEffect(() => {
    loadCalendars()
  }, [loadCalendars])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
      const activeAgencies = (data.items || []).filter((a: Agency) => a.is_active)
      if (activeAgencies.length > 0) {
        setSelectedAgency(activeAgencies[0].id)
      }
    } catch (error) {
      console.error('Failed to load agencies:', error)
      notifications.show({
        title: 'Error',
        message: 'Failed to load agencies',
        color: 'red',
      })
    }
  }

  const loadGTFSDataByAgency = async (agencyId: number) => {
    // With composite keys, we now require feed selection
    // Clear data and show a message
    setStops([])
    setRoutes([])
    setShapes([])
    setTrips([])
    setSelectedRouteIds(new Set())
    setSelectedShapeIds(new Set())
    if (!selectedFeed) {
      notifications.show({
        title: t('map.feedSelectionRequired', 'Feed Selection Required'),
        message: t('map.selectFeedToViewMap', 'Please select a specific feed to view map data'),
        color: 'yellow',
      })
      return
    }
  }

  const loadGTFSDataByFeed = async (feedId: number) => {
    setLoading(true)
    try {
      const stopsResponse = await stopsApi.list(feedId, { limit: 50000 })
      const stopsData = stopsResponse.items || []
      setStops(stopsData)

      const routesResponse = await routesApi.list(feedId, { limit: 50000 })
      const routesData = routesResponse.items || []
      setRoutes(routesData)

      let shapesData: any[] = []
      try {
        const shapesResponse = await shapesApi.getByShapeId({ feed_id: feedId })
        shapesData = shapesResponse.items || []
        setShapes(shapesData)
      } catch (shapeError) {
        console.error(`Shapes not available for feed ${feedId}:`, shapeError)
        setShapes([])
      }

      // Auto-select all routes and shapes on initial load
      setSelectedRouteIds(new Set(routesData.map((r: any) => r.route_id)))
      setSelectedShapeIds(new Set(shapesData.map((s: any) => s.shape_id)))
      console.log('[Map Filter] Initial selection:', {
        routes: routesData.length,
        shapes: shapesData.length,
      })

      // Load trips for shape filtering (Route -> Trip -> Shape hierarchy)
      try {
        const tripsResponse = await tripsApi.list(feedId, { limit: 50000 })
        const tripsData = tripsResponse.items || []
        console.log('[Map Load] Trips loaded:', {
          loaded: tripsData.length,
          total: tripsResponse.total,
          hasShapeId: tripsData.filter((t: any) => t.shape_id).length,
          hasRouteId: tripsData.filter((t: any) => t.route_id).length,
        })
        setTrips(tripsData)
      } catch (tripError) {
        console.error(`Trips not available for feed ${feedId}:`, tripError)
        setTrips([])
      }

      // Load route-to-stops mapping for filtering stops by routes
      try {
        const routeStopsData = await routesApi.getRouteStopsMap(feedId)
        setRouteToStopsMap(routeStopsData)
        console.log('[Map Filter] Loaded route-stops mapping:', {
          routes: Object.keys(routeStopsData).length,
          totalStopMappings: Object.values(routeStopsData).reduce((sum, arr) => sum + arr.length, 0),
        })
      } catch (routeStopsError) {
        console.error(`Route-stops mapping not available for feed ${feedId}:`, routeStopsError)
        setRouteToStopsMap({})
      }

      // Only auto-center on first load (when map is at default position)
      if (stopsData.length > 0 && mapCenter[0] === 40.7128 && mapCenter[1] === -74.006) {
        const firstStop = stopsData[0]
        setMapCenter([Number(firstStop.stop_lat), Number(firstStop.stop_lon)])
        setMapZoom(12)
      }
    } catch (error: any) {
      let errorMessage = 'Failed to load GTFS data'
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (Array.isArray(detail)) {
          errorMessage = detail.map((err: any) => err.msg).join(', ')
        } else if (typeof detail === 'string') {
          errorMessage = detail
        }
      }
      notifications.show({
        title: 'Error',
        message: errorMessage,
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  // Filter routes for search
  const filteredRoutes = useMemo(() => {
    const baseRoutes = availableRoutes
    if (!routeSearchText) return baseRoutes
    const searchLower = routeSearchText.toLowerCase()
    return baseRoutes.filter(route =>
      route.route_short_name?.toLowerCase().includes(searchLower) ||
      route.route_long_name?.toLowerCase().includes(searchLower) ||
      route.route_id.toLowerCase().includes(searchLower)
    )
  }, [availableRoutes, routeSearchText])

  // Handle route selection toggle
  const handleRouteToggle = (routeId: string) => {
    console.log('[Map Filter] handleRouteToggle called:', routeId)
    setSelectedRouteIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(routeId)) {
        newSet.delete(routeId)
        console.log('[Map Filter] Removed route:', routeId, 'New size:', newSet.size)
      } else {
        newSet.add(routeId)
        console.log('[Map Filter] Added route:', routeId, 'New size:', newSet.size)
      }
      return newSet
    })
  }

  // Select/deselect all routes
  const handleSelectAllRoutes = () => {
    setSelectedRouteIds(new Set(availableRoutes.map(r => r.route_id)))
  }

  const handleDeselectAllRoutes = () => {
    setSelectedRouteIds(new Set())
  }

  // Filter calendars for search
  const filteredCalendars = useMemo(() => {
    if (!calendarSearchText) return calendars
    const searchLower = calendarSearchText.toLowerCase()
    return calendars.filter((calendar: any) =>
      calendar.service_id?.toLowerCase().includes(searchLower)
    )
  }, [calendars, calendarSearchText])

  // Handle calendar selection toggle
  const handleCalendarToggle = (serviceId: string) => {
    setSelectedCalendarIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(serviceId)) {
        newSet.delete(serviceId)
      } else {
        newSet.add(serviceId)
      }
      return newSet
    })
  }

  // Select/deselect all calendars
  const handleSelectAllCalendars = () => {
    setSelectedCalendarIds(new Set(calendars.map((c: any) => c.service_id)))
  }

  const handleDeselectAllCalendars = () => {
    setSelectedCalendarIds(new Set())
  }

  // Filter shapes for search
  const filteredShapesForSelection = useMemo(() => {
    if (!shapeSearchText) return availableShapes
    const searchLower = shapeSearchText.toLowerCase()
    return availableShapes.filter(shape =>
      shape.shape_id.toLowerCase().includes(searchLower)
    )
  }, [availableShapes, shapeSearchText])

  // Handle shape selection toggle
  const handleShapeToggle = (shapeId: string) => {
    setSelectedShapeIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(shapeId)) {
        newSet.delete(shapeId)
      } else {
        newSet.add(shapeId)
      }
      return newSet
    })
  }

  // Select/deselect all shapes
  const handleSelectAllShapes = () => {
    setSelectedShapeIds(new Set(availableShapes.map(s => s.shape_id)))
  }

  const handleDeselectAllShapes = () => {
    setSelectedShapeIds(new Set())
  }

  // Stats badges component (reusable for both mobile and desktop)
  const StatsBadges = () => (
    <Group gap="xs" wrap="wrap">
      {/* Static GTFS Data */}
      <Group gap={4} wrap="nowrap">
        <Badge
          leftSection={showRoutes ? <IconEye size={14} /> : <IconEyeOff size={14} />}
          color="green"
          size={isMobile ? 'sm' : 'md'}
          variant={showRoutes ? 'filled' : 'light'}
          style={{ cursor: 'pointer' }}
          onClick={() => setShowRoutes(!showRoutes)}
        >
          Routes
        </Badge>
        <Badge
          leftSection={<IconBus size={14} />}
          color="green"
          size={isMobile ? 'sm' : 'md'}
          variant={effectiveSelectedRoutesCount > 0 ? 'filled' : 'light'}
          style={{ cursor: 'pointer' }}
          onClick={() => setRouteSelectionOpened(true)}
        >
          {effectiveSelectedRoutesCount}/{availableRoutes.length}
        </Badge>
      </Group>
      <Group gap={4} wrap="nowrap">
        <Badge
          leftSection={showShapes ? <IconEye size={14} /> : <IconEyeOff size={14} />}
          color="teal"
          size={isMobile ? 'sm' : 'md'}
          variant={showShapes ? 'filled' : 'light'}
          style={{ cursor: 'pointer' }}
          onClick={() => setShowShapes(!showShapes)}
        >
          Shapes
        </Badge>
        <Badge
          leftSection={<IconRoute size={14} />}
          color="teal"
          size={isMobile ? 'sm' : 'md'}
          variant={effectiveSelectedShapesCount > 0 ? 'filled' : 'light'}
          style={{ cursor: 'pointer' }}
          onClick={() => setShapeSelectionOpened(true)}
        >
          {effectiveSelectedShapesCount}/{availableShapes.length}
        </Badge>
      </Group>
      <Badge
        leftSection={showStops ? <IconEye size={14} /> : <IconEyeOff size={14} />}
        color="blue"
        size={isMobile ? 'sm' : 'md'}
        variant={showStops ? 'filled' : 'light'}
        style={{ cursor: 'pointer' }}
        onClick={() => setShowStops(!showStops)}
      >
        {filteredStops.length}/{stops.length} Stops
      </Badge>

      {/* Orphan toggles - show data not connected to trips/routes */}
      {orphanStops.length > 0 && (
        <Tooltip label={t('map.orphanStops.tooltip', 'Show stops not used in any trip')}>
          <Badge
            leftSection={showOrphanStops ? <IconEye size={14} /> : <IconEyeOff size={14} />}
            color="orange"
            size={isMobile ? 'sm' : 'md'}
            variant={showOrphanStops ? 'filled' : 'light'}
            style={{ cursor: 'pointer' }}
            onClick={() => setShowOrphanStops(!showOrphanStops)}
          >
            {orphanStops.length} {t('map.orphanStops.label', 'Orphan Stops')}
          </Badge>
        </Tooltip>
      )}
      {orphanShapes.length > 0 && (
        <Tooltip label={t('map.orphanShapes.tooltip', 'Show shapes not used by any route')}>
          <Badge
            leftSection={showOrphanShapes ? <IconEye size={14} /> : <IconEyeOff size={14} />}
            color="orange"
            size={isMobile ? 'sm' : 'md'}
            variant={showOrphanShapes ? 'filled' : 'light'}
            style={{ cursor: 'pointer' }}
            onClick={() => setShowOrphanShapes(!showOrphanShapes)}
          >
            {orphanShapes.length} {t('map.orphanShapes.label', 'Orphan Shapes')}
          </Badge>
        </Tooltip>
      )}

      {/* Feed Info Badge */}
      {selectedFeed ? (
        <Badge leftSection={<IconDatabase size={14} />} color="violet" size={isMobile ? 'sm' : 'md'}>
          Specific Feed
        </Badge>
      ) : (
        <Badge leftSection={<IconDatabase size={14} />} color="gray" size={isMobile ? 'sm' : 'md'}>
          All Feeds
        </Badge>
      )}

      {/* Real-time Toggle */}
      <Badge
        leftSection={<IconLivePhoto size={14} />}
        color="green"
        size={isMobile ? 'sm' : 'md'}
        variant={realtimeEnabled ? 'filled' : 'light'}
        style={{ cursor: 'pointer' }}
        onClick={() => setRealtimeEnabled(!realtimeEnabled)}
        disabled={!selectedAgency}
      >
        {realtimeEnabled ? 'Real-time' : 'Real-time'}
      </Badge>

      {/* GTFS-Realtime Data Layers */}
      {realtimeEnabled && (
        <>
          <Badge
            leftSection={showVehicles ? <IconEye size={14} /> : <IconEyeOff size={14} />}
            color={realtimeLoading ? 'yellow' : 'green'}
            variant={showVehicles ? 'filled' : 'light'}
            size={isMobile ? 'sm' : 'md'}
            style={{ cursor: 'pointer' }}
            onClick={() => setShowVehicles(!showVehicles)}
          >
            {vehicles.length} Vehicles
          </Badge>
          {tripUpdates.length > 0 && (
            <Badge
              leftSection={showTripUpdates ? <IconEye size={14} /> : <IconEyeOff size={14} />}
              color="cyan"
              size={isMobile ? 'sm' : 'md'}
              variant={showTripUpdates ? 'filled' : 'light'}
              style={{ cursor: 'pointer' }}
              onClick={() => setShowTripUpdates(!showTripUpdates)}
            >
              {tripUpdates.length} Trip Updates
            </Badge>
          )}
          {alerts.length > 0 && (
            <Badge
              leftSection={showAlerts ? <IconEye size={14} /> : <IconEyeOff size={14} />}
              color="orange"
              size={isMobile ? 'sm' : 'md'}
              variant={showAlerts ? 'filled' : 'light'}
              style={{ cursor: 'pointer' }}
              onClick={() => setShowAlerts(!showAlerts)}
            >
              {alerts.length} Alerts
            </Badge>
          )}
          {tripModifications.length > 0 && (
            <>
              <Badge
                leftSection={showTripModifications ? <IconEye size={14} /> : <IconEyeOff size={14} />}
                color="red"
                size={isMobile ? 'sm' : 'md'}
                variant={showTripModifications ? 'filled' : 'light'}
                style={{ cursor: 'pointer' }}
                onClick={() => setShowTripModifications(!showTripModifications)}
              >
                {tripModifications.length} Trip Modifications
              </Badge>
              <Badge
                leftSection={showReplacementShapes ? <IconEye size={14} /> : <IconEyeOff size={14} />}
                color="pink"
                size={isMobile ? 'sm' : 'md'}
                variant={showReplacementShapes ? 'filled' : 'light'}
                style={{ cursor: 'pointer' }}
                onClick={() => setShowReplacementShapes(!showReplacementShapes)}
              >
                Replacement Shapes
              </Badge>
              <Badge
                leftSection={showReplacementStops ? <IconEye size={14} /> : <IconEyeOff size={14} />}
                color="grape"
                size={isMobile ? 'sm' : 'md'}
                variant={showReplacementStops ? 'filled' : 'light'}
                style={{ cursor: 'pointer' }}
                onClick={() => setShowReplacementStops(!showReplacementStops)}
              >
                Replacement Stops
              </Badge>
            </>
          )}
        </>
      )}
    </Group>
  )

  // Mobile controls drawer content
  const MobileControlsContent = () => (
    <Stack gap="md" p="md">
      <Group justify="space-between">
        <Title order={4}>Map Controls</Title>
        <ActionIcon variant="subtle" onClick={closeMobileDrawer}>
          <IconX size={18} />
        </ActionIcon>
      </Group>

      <Divider />

      <Stack gap="sm">
        <Text size="sm" fw={500}>Select Agency</Text>
        <Select
          placeholder="Select Agency"
          data={agencies
            .filter(a => a.is_active)
            .map(a => ({ value: a.id.toString(), label: a.name }))}
          value={selectedAgency ? selectedAgency.toString() : null}
          onChange={(value) => {
            setSelectedAgency(value ? parseInt(value) : null)
          }}
          searchable
          clearable
          nothingFoundMessage="No agencies found"
          styles={{ dropdown: { zIndex: 10000 } }}
          disabled={agencies.filter(a => a.is_active).length === 0}
        />
      </Stack>

      <Stack gap="sm">
        <Text size="sm" fw={500}>Select Feed</Text>
        <FeedSelector
          agencyId={selectedAgency}
          value={selectedFeed}
          onChange={setSelectedFeed}
          showAllOption={!editMode}
        />
      </Stack>

      <Divider label="Edit Mode" labelPosition="center" />

      <Switch
        label={t('map.editMode', 'Edit mode')}
        checked={editMode}
        onChange={(e) => setEditMode(e.currentTarget.checked)}
        color="orange"
        disabled={!selectedAgency || !selectedFeed}
      />

      {editMode && (
        <SegmentedControl
          value={editorMode}
          onChange={(value) => setEditorMode(value as 'stops' | 'shapes')}
          data={[
            { label: t('map.editStops', 'Stops'), value: 'stops' },
            { label: t('map.editShapes', 'Shapes'), value: 'shapes' },
          ]}
          fullWidth
        />
      )}

      {!editMode && realtimeEnabled && tripModifications.length > 0 && (
        <Switch
          label={t('map.tripModifications.showDetours', 'Show Detours')}
          checked={showTripModifications}
          onChange={(e) => setShowTripModifications(e.currentTarget.checked)}
          color="red"
        />
      )}

      <Divider label="Actions" labelPosition="center" />

      <Button
        variant="light"
        color="blue"
        leftSection={<IconFocus2 size={16} />}
        onClick={() => {
          handleFitToView()
          closeMobileDrawer()
        }}
        disabled={stops.length === 0}
        fullWidth
      >
        Fit to View
      </Button>

      {selectedAgency && (
        <>
          <Divider label="Statistics" labelPosition="center" />
          <StatsBadges />
        </>
      )}

      {/* Shape editing controls for mobile */}
      {editMode && editorMode === 'shapes' && selectedAgency && (
        <>
          <Divider label={t('map.shapes.editor', 'Shape Editor')} labelPosition="center" />
          <Stack gap="xs">
            <Badge
              leftSection={<IconRoute size={14} />}
              color="orange"
              size="md"
              variant="filled"
              style={{ cursor: 'pointer' }}
              onClick={() => {
                setShapeSelectionModalOpened(true)
                closeMobileDrawer()
              }}
              fullWidth
            >
              {effectiveSelectedShapesCount}/{availableShapes.length} shapes
            </Badge>

            {creatingNewShape ? (
              <Alert color="blue" p="xs">
                <Stack gap={4}>
                  <Text size="xs" fw={600}>
                    {t('map.shapes.creatingNew', 'Creating new shape')}: {newShapeId}
                  </Text>
                  <Text size="xs">
                    {t('map.shapes.clickToAdd', 'Click on map to add points')} ({newShapePoints.length} {t('map.shapes.points', 'points')})
                  </Text>
                  <Group gap="xs" mt={4}>
                    <Button
                      size="xs"
                      color="green"
                      onClick={() => {
                        handleSaveNewShape()
                        closeMobileDrawer()
                      }}
                      disabled={newShapePoints.length < 2}
                      fullWidth
                    >
                      {t('common.save', 'Save')}
                    </Button>
                    <Button
                      size="xs"
                      variant="default"
                      onClick={() => {
                        handleCancelShapeEdit()
                        closeMobileDrawer()
                      }}
                      fullWidth
                    >
                      {t('common.cancel', 'Cancel')}
                    </Button>
                  </Group>
                </Stack>
              </Alert>
            ) : editingShapeId ? (
              <Alert color="orange" p="xs">
                <Stack gap={4}>
                  <Text size="xs" fw={600}>
                    {t('map.shapes.editing', 'Editing')}: {editingShapeId}
                  </Text>
                  <Text size="xs">
                    {editingShapePoints.length} {t('map.shapes.points', 'points')}
                  </Text>
                  <Group gap="xs" mt={4}>
                    <Button
                      size="xs"
                      color="green"
                      onClick={() => {
                        handleSaveShape()
                        closeMobileDrawer()
                      }}
                      fullWidth
                    >
                      {t('common.save', 'Save')}
                    </Button>
                    <Button
                      size="xs"
                      variant="default"
                      onClick={() => {
                        handleCancelShapeEdit()
                        closeMobileDrawer()
                      }}
                      fullWidth
                    >
                      {t('common.cancel', 'Cancel')}
                    </Button>
                  </Group>
                </Stack>
              </Alert>
            ) : (
              <Button
                size="sm"
                color="blue"
                leftSection={<IconPlus size={14} />}
                onClick={() => {
                  handleStartCreateShape()
                  closeMobileDrawer()
                }}
                fullWidth
              >
                {t('map.shapes.createNew', 'Create New Shape')}
              </Button>
            )}

            {!creatingNewShape && !editingShapeId && (
              <Text size="xs" c="dimmed" fs="italic">
                {t('map.shapes.clickShapeToEdit', 'Click on a shape on the map to edit it')}
              </Text>
            )}
          </Stack>
        </>
      )}
    </Stack>
  )

  // Full height: viewport - header (60px) - AppShell padding (32px) - bottom nav on mobile (64px)
  const containerStyle = {
    height: isMobile
      ? 'calc(100dvh - 60px - 32px - 64px)'
      : 'calc(100dvh - 60px - 32px)',
    overflow: 'hidden'
  }

  return (
    <Container size="100%" px={0} style={containerStyle}>
      <Stack gap={0} style={{ height: '100%' }}>

        {/* Header - Different for mobile and desktop */}
        {isMobile ? (
          // Mobile Header - Compact
          <Paper shadow="xs" p="xs" style={{ zIndex: 2000, position: 'relative' }}>
            <Group justify="space-between" wrap="nowrap">
              <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                <Select
                  placeholder="Agency"
                  data={agencies
                    .filter(a => a.is_active)
                    .map(a => ({ value: a.id.toString(), label: a.name }))}
                  value={selectedAgency ? selectedAgency.toString() : null}
                  onChange={(value) => setSelectedAgency(value ? parseInt(value) : null)}
                  size="sm"
                  styles={{
                    root: { flex: 1, minWidth: 0 },
                    dropdown: { zIndex: 3000 }
                  }}
                  disabled={agencies.filter(a => a.is_active).length === 0}
                />
              </Group>

              <Group gap={4} wrap="nowrap">
                {realtimeEnabled && (
                  <Badge
                    size="sm"
                    color={realtimeLoading ? 'yellow' : 'green'}
                    variant="dot"
                    style={{ paddingLeft: 8, paddingRight: 8 }}
                  >
                    {vehicles.length}
                  </Badge>
                )}
                <ActionIcon
                  variant={realtimeEnabled ? 'filled' : 'light'}
                  color="green"
                  size="md"
                  onClick={() => setRealtimeEnabled(!realtimeEnabled)}
                  disabled={!selectedAgency}
                >
                  <IconLivePhoto size={16} />
                </ActionIcon>
                <ActionIcon
                  variant="light"
                  color="blue"
                  size="md"
                  onClick={handleFitToView}
                  disabled={stops.length === 0}
                >
                  <IconFocus2 size={16} />
                </ActionIcon>
                <ActionIcon
                  variant="filled"
                  color="blue"
                  size="md"
                  onClick={openMobileDrawer}
                >
                  <IconSettings size={16} />
                </ActionIcon>
              </Group>
            </Group>

            {/* Collapsible stats for mobile */}
            {selectedAgency && (
              <Box mt="xs">
                <Group
                  gap={4}
                  onClick={() => setStatsExpanded(!statsExpanded)}
                  style={{ cursor: 'pointer' }}
                  wrap="nowrap"
                >
                  <ScrollArea scrollbarSize={4} type="never" style={{ flex: 1 }}>
                    <Group gap={4} wrap="nowrap">
                      <Badge size="xs" color="blue" variant="light">{filteredStops.length}/{stops.length} stops</Badge>
                      <Badge size="xs" color="green" variant="light">{effectiveSelectedRoutesCount}/{availableRoutes.length} routes</Badge>
                      {realtimeEnabled && vehicles.length > 0 && (
                        <Badge size="xs" color="green" variant="dot">{vehicles.length} live</Badge>
                      )}
                    </Group>
                  </ScrollArea>
                  {statsExpanded ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
                </Group>
                <Collapse in={statsExpanded}>
                  <Box mt="xs">
                    <StatsBadges />
                  </Box>
                </Collapse>
              </Box>
            )}

            {realtimeError && (
              <Alert color="red" mt="xs" icon={<IconAlertCircle size={14} />} p="xs">
                <Text size="xs">{realtimeError}</Text>
              </Alert>
            )}
          </Paper>
        ) : (
          // Desktop Header - Full
          <Paper shadow="xs" p="md" style={{ zIndex: 2000, position: 'relative' }}>
            <Group justify="space-between">
              <div>
                <Title order={2}>GTFS Map View</Title>
                <Text size="sm" c="dimmed">
                  Explore routes, stops, and shapes on the map
                </Text>
              </div>
              <Group>
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
                  styles={{ dropdown: { zIndex: 3000 } }}
                  disabled={agencies.filter(a => a.is_active).length === 0}
                />
                <FeedSelector
                  agencyId={selectedAgency}
                  value={selectedFeed}
                  onChange={setSelectedFeed}
                  showAllOption={!editMode}
                  style={{ minWidth: 300 }}
                />
                <Button
                  leftSection={<IconCalendar size={16} />}
                  variant={selectedCalendarIds.size > 0 ? 'filled' : 'light'}
                  color="purple"
                  onClick={() => setCalendarSelectionOpened(true)}
                  disabled={calendars.length === 0}
                >
                  {selectedCalendarIds.size > 0
                    ? `${selectedCalendarIds.size}/${calendars.length} Calendars`
                    : 'Calendars'}
                </Button>
                <Button
                  variant={routeCreatorEnabled ? 'filled' : 'light'}
                  color="teal"
                  onClick={() => handleToggleRouteCreator(!routeCreatorEnabled)}
                >
                  Route Creator
                </Button>
                {!editMode && realtimeEnabled && tripModifications.length > 0 && (
                  <Switch
                    label={
                      <Group gap={4}>
                        <IconRoute size={14} color={showTripModifications ? '#ef4444' : undefined} />
                        <span>{t('map.tripModifications.showDetours', 'Detours')}</span>
                      </Group>
                    }
                    checked={showTripModifications}
                    onChange={(e) => setShowTripModifications(e.currentTarget.checked)}
                    color="red"
                  />
                )}
                <Switch
                  label={t('map.editMode', 'Edit mode')}
                  checked={editMode}
                  onChange={(e) => setEditMode(e.currentTarget.checked)}
                  color="blue"
                />
                <SegmentedControl
                  value={editorMode}
                  onChange={(value) => setEditorMode(value as 'stops' | 'shapes')}
                  data={[
                    { label: t('map.editStops', 'Stops'), value: 'stops' },
                    { label: t('map.editShapes', 'Shapes'), value: 'shapes' },
                  ]}
                  size="sm"
                />
              </Group>
            </Group>
            {selectedAgency && (
              <Group mt="xs" gap="xs">
                <StatsBadges />
              </Group>
            )}


            {realtimeError && (
              <Alert color="red" mt="xs" icon={<IconAlertCircle size={16} />}>
                {realtimeError}
              </Alert>
            )}
          </Paper>
        )}

        {/* Map Container */}
        <div style={{ flex: 1, position: 'relative', height: '100%', width: '100%' }}>
          <LoadingOverlay visible={loading} />

          {/* Route Creator Drawer - anchored inside map area */}
          {routeCreatorEnabled && (
            <Box
              ref={rcDrawerRef}
              style={{
                position: 'absolute',
                top: rcDrawerPosition.top,
                right: rcDrawerPosition.right ?? 'auto',
                left: rcDrawerPosition.left ?? 'auto',
                zIndex: 3600,
                maxWidth: rcDrawerWidth,
                width: rcDrawerWidth,
                pointerEvents: 'auto',
                cursor: 'move',
                touchAction: 'none',
                maxHeight: 'calc(100% - 110px)',
                display: 'flex',
                flexDirection: 'column',
              }}
              onPointerDown={handleRcDragStart}
            >
              <Stack gap="sm" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                <Paper p="md" shadow="md" withBorder>
                  <Group justify="space-between" mb="xs" gap="xs" wrap="wrap">
                    <Text fw={600}>{t('routeCreator.title', 'Route Creator')}</Text>
                    <Group gap={6} wrap="wrap">
                      <Badge color="teal" variant="light">{t('routeCreator.noDbWrites', 'No DB writes')}</Badge>
                      <Button size="xs" variant="subtle" color="red" onClick={() => handleToggleRouteCreator(false)}>
                        {t('common.close', 'Close')}
                      </Button>
                    </Group>
                  </Group>
                  <Group gap="xs" mb="sm" wrap="wrap">
                    {[1, 2, 3, 4, 5, 6, 7].map((n) => {
                      const label = n === 1
                        ? t('routeCreator.steps.calendar', 'Calendar')
                        : n === 2
                          ? t('routeCreator.steps.route', 'Route')
                          : n === 3
                            ? t('routeCreator.steps.stops', 'Stops')
                            : n === 4
                              ? t('routeCreator.steps.shape', 'Shape')
                              : n === 5
                                ? t('routeCreator.steps.schedule', 'Schedule')
                                : n === 6
                                  ? t('routeCreator.steps.stopTimes', 'Stop Times')
                                  : t('routeCreator.steps.export', 'Export')
                      const active = rcStep === n
                      const canGoToExport = rcTrips.length > 0 && Object.keys(rcStopTimesTable).length > 0
                      const enabled = (n === 1)
                        || (n === 2 && canGoToRoute)
                        || (n === 3 && canGoToStops)
                        || (n === 4 && canGoToShape)
                        || (n === 5 && canGoToSchedule)
                        || (n === 6 && canGoToStopTimes)
                        || (n === 7 && canGoToExport)
                      return (
                        <Button
                          key={n}
                          size="xs"
                          variant={active ? 'filled' : 'light'}
                          color={active ? 'blue' : 'gray'}
                          disabled={!enabled}
                          onClick={() => {
                            if (enabled) setRcStep(n as 1 | 2 | 3 | 4 | 5 | 6 | 7)
                          }}
                        >
                          {n}. {label}
                        </Button>
                      )
                    })}
                  </Group>
                  {rcStep === 1 && (
                    <>
                      {/* Calendar Selection - Step 1 */}
                      <Text fw={600} mb="xs">{t('routeCreator.calendarSelection', 'Service Calendars')}</Text>
                      <Text size="sm" c="dimmed" mb="sm">
                        {t('routeCreator.calendarSelectionDesc', 'Select an existing calendar or create a new one. Trips will be created for each selected calendar.')}
                      </Text>
                      <Group align="flex-end" gap="xs">
                        <MultiSelect
                          style={{ flex: 1 }}
                          size="sm"
                          data={rcCalendarOptions}
                          value={rcSelectedServiceIds}
                          onChange={setRcSelectedServiceIds}
                          placeholder={rcCalendarOptions.length > 0 ? t('routeCreator.selectCalendarsPlaceholder', 'Select calendars...') : t('routeCreator.noCalendars', 'No calendars available')}
                          searchable
                          clearable
                          maxDropdownHeight={200}
                          comboboxProps={{ zIndex: 100001 }}
                        />
                        <Tooltip label={t('routeCreator.createCalendar', 'Create new calendar')}>
                          <Button size="sm" variant="light" onClick={openRcCalendarModal} leftSection={<IconPlus size={16} />}>
                            {t('common.new', 'New')}
                          </Button>
                        </Tooltip>
                      </Group>
                      {rcCalendarOptions.length === 0 && selectedFeed && (
                        <Alert color="yellow" icon={<IconAlertCircle size={16} />} mt="xs" p="xs">
                          <Text size="xs">{t('routeCreator.noCalendarsWarning', 'No calendars found in this feed. Create one to continue.')}</Text>
                        </Alert>
                      )}

                      <Group mt="sm" gap="xs">
                        <Button size="sm" color="blue" disabled={!canGoToRoute} onClick={() => setRcStep(2)}>
                          {t('routeCreator.nextRoute', 'Next: Route')}
                        </Button>
                        <Button size="sm" variant="light" color="gray" onClick={resetRouteCreator}>
                          {t('common.reset', 'Reset')}
                        </Button>
                      </Group>
                    </>
                  )}

                  {rcStep === 2 && (
                    <>
                      {/* Route Selection - Step 2 */}
                      <SegmentedControl
                        fullWidth
                        size="sm"
                        value={rcUseExistingRoute ? 'existing' : 'new'}
                        onChange={(value) => {
                          const useExisting = value === 'existing'
                          setRcUseExistingRoute(useExisting)
                          if (!useExisting) {
                            setRcSelectedExistingRouteId(null)
                            setRcSelectedDirection(null)
                            setRcAvailableDirections([])
                            setRcRouteId(generateRouteIdSuggestion())
                            setRcRouteShortName('')
                            setRcRouteColor('#0ea5e9')
                            setRcSelectedStops([])
                          }
                        }}
                        data={[
                          { label: t('routeCreator.newRoute', 'New Route'), value: 'new' },
                          { label: t('routeCreator.existingRoute', 'Existing Route'), value: 'existing' },
                        ]}
                      />

                      {/* Existing route selector */}
                      {rcUseExistingRoute && (
                        <Select
                          label={t('routeCreator.selectRoute', 'Select Route')}
                          placeholder={t('routeCreator.selectRoutePlaceholder', 'Choose a route...')}
                          searchable
                          clearable
                          value={rcSelectedExistingRouteId}
                          onChange={(value) => {
                            setRcSelectedExistingRouteId(value)
                            if (value) {
                              loadExistingRouteDirections(value)
                            } else {
                              setRcSelectedDirection(null)
                              setRcAvailableDirections([])
                              setRcSelectedStops([])
                              setRcRouteId('')
                              setRcRouteShortName('')
                              setRcRouteColor('#0ea5e9')
                            }
                          }}
                          data={routes.map(r => ({
                            value: r.route_id,
                            label: `${r.route_short_name || r.route_id}${r.route_long_name ? ` - ${r.route_long_name}` : ''}`,
                          }))}
                          rightSection={rcLoadingExistingRoute ? <Loader size="xs" /> : null}
                          comboboxProps={{ zIndex: 100001 }}
                        />
                      )}

                      {/* Direction selector - shown after route is selected */}
                      {rcUseExistingRoute && rcSelectedExistingRouteId && rcAvailableDirections.length > 1 && (
                        <Select
                          label={t('routeCreator.selectDirection', 'Select Direction')}
                          placeholder={t('routeCreator.selectDirectionPlaceholder', 'Choose a direction...')}
                          value={rcSelectedDirection}
                          onChange={(value) => {
                            setRcSelectedDirection(value)
                            if (value && rcSelectedExistingRouteId) {
                              loadExistingRouteStops(rcSelectedExistingRouteId, parseInt(value))
                            } else {
                              setRcSelectedStops([])
                            }
                          }}
                          data={rcAvailableDirections}
                          rightSection={rcLoadingExistingRoute ? <Loader size="xs" /> : null}
                          comboboxProps={{ zIndex: 100001 }}
                        />
                      )}

                      {/* Route details - editable for new, read-only display for existing */}
                      {!rcUseExistingRoute && (
                        <SimpleGrid cols={2} spacing="sm">
                          <TextInput
                            label={t('routeCreator.routeId', 'Route ID')}
                            value={rcRouteId}
                            onChange={(e) => setRcRouteId(e.currentTarget.value)}
                            placeholder="RC_ROUTE_1"
                          />
                          <TextInput
                            label={t('routeCreator.shortName', 'Short Name')}
                            value={rcRouteShortName}
                            onChange={(e) => setRcRouteShortName(e.currentTarget.value)}
                            placeholder={t('routeCreator.shortNamePlaceholder', 'Express')}
                          />
                        </SimpleGrid>
                      )}

                      {rcUseExistingRoute && rcSelectedExistingRouteId && (rcSelectedDirection || rcAvailableDirections.length <= 1) && (
                        <Group gap="xs">
                          <Badge color="blue" variant="light" size="lg">
                            {rcRouteShortName || rcRouteId}
                          </Badge>
                          {rcSelectedStops.length > 0 && (
                            <Badge color="green" variant="dot">
                              {t('routeCreator.stopsPreloaded', { count: rcSelectedStops.length }, `${rcSelectedStops.length} stops loaded`)}
                            </Badge>
                          )}
                        </Group>
                      )}

                      <ColorInput
                        label={t('routeCreator.routeColor', 'Route Color')}
                        value={rcRouteColor}
                        onChange={setRcRouteColor}
                        format="hex"
                        swatches={['#0ea5e9', '#10b981', '#f97316', '#ef4444', '#8b5cf6']}
                        disabled={rcUseExistingRoute}
                      />

                      <Group mt="sm" gap="xs">
                        <Button size="sm" variant="default" onClick={() => setRcStep(1)}>
                          {t('common.back', 'Back')}
                        </Button>
                        <Button size="sm" color="blue" disabled={!canGoToStops} onClick={() => setRcStep(3)}>
                          {t('routeCreator.nextStops', 'Next: Stops')}
                        </Button>
                        <Button size="sm" variant="light" color="gray" onClick={resetRouteCreator}>
                          {t('common.reset', 'Reset')}
                        </Button>
                      </Group>
                    </>
                  )}
                </Paper>

                {rcStep === 3 && (

                  <Paper p="md" shadow="sm" withBorder style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <Group justify="space-between" mb="xs">
                      <Text fw={600}>{t('routeCreator.stops.title', 'Stops (map click to add/select)')}</Text>
                      <Badge color="green" variant="dot">
                        {t('routeCreator.stops.selected', { defaultValue: '{{count}} selected', count: rcOrderedStops.length } as any)}
                      </Badge>
                    </Group>
                    <Text size="sm" c="dimmed" mb="xs">
                      {t('routeCreator.stops.instructions', 'Click on map to add a new stop. Click an existing stop to add/remove it from the route. Drag to reorder.')}
                    </Text>

                    <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
                      <Stack gap="xs">
                        {rcOrderedStops.length === 0 && (
                          <Text size="sm" c="dimmed">
                            {t('routeCreator.stops.none', 'No stops selected. Click on the map to add.')}
                          </Text>
                        )}

                        {rcOrderedStops.map((s, idx) => (
                          <Group
                            key={`${s.stop_id}-${idx}`}
                            justify="space-between"
                            align="flex-start"
                            p="xs"
                            style={{
                              border: '1px solid var(--mantine-color-gray-3)',
                              borderRadius: 8,
                              backgroundColor: '#f8fafc',
                            }}
                            draggable
                            onDragStart={() => setRcDragIndex(idx)}
                            onDragOver={(e) => {
                              e.preventDefault()
                              setRcDragHoverIndex(idx)
                            }}
                            onDragLeave={() => setRcDragHoverIndex(null)}
                            onDrop={() => {
                              if (rcDragIndex !== null) handleRcReorderStops(rcDragIndex, idx)
                              setRcDragIndex(null)
                              setRcDragHoverIndex(null)
                            }}
                            onDragEnd={() => {
                              setRcDragIndex(null)
                              setRcDragHoverIndex(null)
                            }}
                            style={{
                              border: rcDragHoverIndex === idx ? '1px dashed #3b82f6' : '1px solid var(--mantine-color-gray-3)',
                              backgroundColor: rcDragHoverIndex === idx ? 'var(--mantine-color-blue-0)' : '#f8fafc',
                              cursor: 'grab',
                            }}
                          >
                            <Group gap="xs">
                              <Badge size="sm" color="teal" variant="filled">#{idx + 1}</Badge>
                              <div>
                                <Text fw={600} size="sm">
                                  {s.stop_name}{' '}
                                  {s.pass > 1 && (
                                    <Badge size="xs" color="orange" variant="light">
                                      {t('routeCreator.stops.loop', { defaultValue: 'loop {{pass}}', pass: s.pass } as any)}
                                    </Badge>
                                  )}
                                </Text>
                                <Text size="xs" c="dimmed">{s.stop_id} • {(parseFloat(String(s.lat)) || 0).toFixed(5)}, {(parseFloat(String(s.lon)) || 0).toFixed(5)}</Text>
                              </div>
                            </Group>
                            <Group gap={4}>
                              <Tooltip label={t('routeCreator.stops.editStop', 'Edit stop')}>
                                <ActionIcon
                                  size="sm"
                                  variant="subtle"
                                  color="blue"
                                  onClick={() => {
                                    // Open edit modal with existing data
                                    setRcEditingStopId(s.stop_id)
                                    setRcPendingStopPosition([s.lat, s.lon])
                                    rcNewStopForm.setValues({
                                      stop_id: s.stop_id,
                                      stop_code: s.stop_code || '',
                                      stop_name: s.stop_name,
                                      sequence: String(s.sequence || idx + 1),
                                    })
                                    setRcNewStopModalOpened(true)
                                  }}
                                >
                                  <IconPencil size={16} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('routeCreator.stops.locateOnMap', 'Locate on map')}>
                                <ActionIcon
                                  size="sm"
                                  variant="subtle"
                                  color="teal"
                                  onClick={() => setFlyTarget({ lat: s.lat, lon: s.lon, zoom: 17 })}
                                >
                                  <IconFocus2 size={16} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('common.remove', 'Remove')}>
                                <ActionIcon
                                  size="sm"
                                  variant="subtle"
                                  color="red"
                                  onClick={() => handleRcRemoveStopFromList(idx)}
                                >
                                  <IconTrash size={16} />
                                </ActionIcon>
                              </Tooltip>
                            </Group>
                          </Group>
                        ))}
                      </Stack>
                    </div>
                    <Group mt="sm" gap="xs" style={{ flexShrink: 0 }}>
                      <Button size="sm" variant="default" onClick={() => setRcStep(2)}>
                        {t('common.back', 'Back')}
                      </Button>
                      <Button size="sm" color="blue" disabled={!canGoToShape} onClick={() => setRcStep(4)}>
                        {t('routeCreator.nextShape', 'Next: Shape')}
                      </Button>
                      <Button size="sm" variant="light" color="gray" onClick={() => { setRcSelectedStops([]); setRcNewStops([]); }}>
                        {t('routeCreator.stops.clear', 'Clear Stops')}
                      </Button>
                    </Group>
                  </Paper>
                )}

                {/* Shape, Schedule, Stop Times cards are below; keep existing layout */}
                {rcStep === 4 && (
                  <Paper p="md" shadow="sm" withBorder>
                    <Group justify="space-between" mb="xs">
                      <Text fw={600}>{t('routeCreator.shape.title', 'Shape Editing')}</Text>
                      <Badge color="blue" variant="dot">
                        {t('routeCreator.shape.points', { defaultValue: '{{count}} pts', count: rcShapePoints.length } as any)}
                      </Badge>
                    </Group>
                    <Text size="sm" c="dimmed" mb="xs">
                      {t('routeCreator.shape.instructions', 'Generate from Valhalla or edit manually. Drag point markers to move. Use Improve Segment to re-route between two points.')}
                    </Text>
                    <Group gap="xs" mb="xs">
                      <Button size="sm" color="teal" onClick={handleRouteCreatorGenerateShape} loading={rcShapeGenerating} disabled={!canGoToShape}>
                        {t('routeCreator.shape.generate', 'Generate Shape')}
                      </Button>
                      <Button size="sm" variant={rcAddPointMode ? 'filled' : 'light'} color="blue" onClick={() => setRcAddPointMode(!rcAddPointMode)}>
                        {rcAddPointMode
                          ? t('routeCreator.shape.addPointActive', 'Click map to add point')
                          : t('routeCreator.shape.addPoint', 'Add Shape Point')}
                      </Button>
                      <Button size="sm" variant={rcImproveSegmentMode ? 'filled' : 'light'} color="orange" onClick={() => {
                        setRcImproveSegmentMode(!rcImproveSegmentMode)
                        setRcImproveSelection({ start: null, end: null })
                      }} disabled={rcShapePoints.length < 2}>
                        {rcImproveSegmentMode
                          ? t('routeCreator.shape.selectImprove', 'Select start & end on map')
                          : t('routeCreator.shape.improve', 'Improve Segment')}
                      </Button>
                      <Button size="sm" variant="light" color="gray" onClick={() => setRcShapePoints([])}>
                        {t('routeCreator.shape.clear', 'Clear Shape')}
                      </Button>
                    </Group>
                    <Text size="xs" c="dimmed" mb="sm">
                      {t('routeCreator.shape.tip', 'Tip: when "Add Shape Point" is active, click the map or shape line to insert a point.')}
                    </Text>
                    <Group gap="xs">
                      <Button size="sm" variant="default" onClick={() => setRcStep(3)}>
                        {t('common.back', 'Back')}
                      </Button>
                      <Button size="sm" color="blue" disabled={!canGoToSchedule} onClick={() => setRcStep(5)}>
                        {t('routeCreator.nextSchedule', 'Next: Schedule')}
                      </Button>
                    </Group>
                  </Paper>
                )}

                {rcStep === 5 && (
                  <Paper p="md" shadow="sm" withBorder style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <Group justify="space-between" align="flex-start" mb="xs">
                      <div>
                        <Text fw={600}>{t('routeCreator.schedule.title', 'Schedule')}</Text>
                        <Text size="sm" c="dimmed">
                          {t('routeCreator.schedule.instructions', 'Click anywhere on the 24h timeline to add/remove departures (leave from stop #1). Hover shows exact time. Hours are grouped in two rows: AM on top, PM on bottom. Each hour has 3 rows x 4 columns of 5-minute slots.')}
                        </Text>
                      </div>
                      <Group gap={6}>
                        <Badge color="grape" variant="dot">
                          {t('routeCreator.schedule.trips', { defaultValue: '{{count}} trips', count: rcTrips.length } as any)}
                        </Badge>
                        <Badge color="gray" variant="light">
                          {rcHoverTime ? `${t('routeCreator.schedule.hover', 'Hover')}: ${rcHoverTime}` : t('routeCreator.schedule.hoverNone', 'Hover timeline')}
                        </Badge>
                      </Group>
                    </Group>

                    <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
                      <Box
                        mt="xs"
                        p="xs"
                        style={{
                          border: '1px solid var(--mantine-color-gray-3)',
                          borderRadius: 8,
                          backgroundColor: 'var(--mantine-color-gray-0)',
                        }}
                      >
                        <Group justify="space-between" align="center" mb="xs">
                          <Text size="sm" fw={600}>{t('routeCreator.schedule.departures', 'Departures')}</Text>
                          <Text size="xs" c="dimmed">
                            {rcSortedTrips.length > 0
                              ? `${t('routeCreator.schedule.selected', 'Selected')}: ${rcSortedTrips.join(', ')}`
                              : t('routeCreator.schedule.noneSelected', 'No departures selected')}
                          </Text>
                        </Group>

                        <Box style={{ width: '100%' }}>
                          {[
                            { label: t('routeCreator.schedule.amRow', 'AM (00:00 - 11:55)'), hours: rcHoursAM },
                            { label: t('routeCreator.schedule.pmRow', 'PM (12:00 - 23:55)'), hours: rcHoursPM },
                          ].map((row) => (
                            <Box key={row.label} mb="xs">
                              <Group gap={6} mb={4}>
                                <Badge size="sm" variant="light" color="gray">{row.label}</Badge>
                              </Group>
                              <Box
                                style={{
                                  display: 'grid',
                                  gridTemplateColumns: 'repeat(12, minmax(30px, 1fr))',
                                  gap: 2,
                                  width: '100%',
                                }}
                              >
                                {row.hours.map((hour) => (
                                  <Box key={hour.label}>
                                    <Text size="xs" fw={600} ta="center" mb={2} style={{ fontSize: 9 }}>{hour.label}</Text>
                                    <Box
                                      style={{
                                        display: 'grid',
                                        gridTemplateColumns: 'repeat(4, 1fr)',
                                        gridTemplateRows: 'repeat(3, 1fr)',
                                        gap: 1,
                                      }}
                                    >
                                      {hour.times.map((time) => {
                                        const selected = rcTrips.includes(time)
                                        const minuteLabel = time.split(':')[1]
                                        return (
                                          <Box
                                            key={time}
                                            onMouseEnter={() => setRcHoverTime(time)}
                                            onMouseLeave={() => setRcHoverTime(null)}
                                            onClick={() => handleTripBlockToggle(time)}
                                            title={time}
                                            style={{
                                              height: 16,
                                              borderRadius: 2,
                                              cursor: 'pointer',
                                              display: 'flex',
                                              alignItems: 'center',
                                              justifyContent: 'center',
                                              backgroundColor: selected ? '#9b5de5' : '#e2e8f0',
                                              color: selected ? '#fff' : '#475569',
                                              border: selected ? '1px solid #7c3aed' : '1px solid #e2e8f0',
                                              boxShadow: selected ? '0 0 0 1px #f3e8ff inset' : undefined,
                                              transition: 'transform 80ms ease, box-shadow 120ms ease',
                                              fontSize: 9,
                                              fontWeight: 600,
                                            }}
                                            onMouseDown={(e) => e.preventDefault()}
                                            onMouseUp={(e) => e.preventDefault()}
                                          >
                                            {minuteLabel}
                                          </Box>
                                        )
                                      })}
                                    </Box>
                                  </Box>
                                ))}
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    </div>

                    <Group gap="xs" mt="md">
                      <Button size="sm" variant="default" onClick={() => setRcStep(4)}>
                        {t('common.back', 'Back')}
                      </Button>
                      <Button size="sm" color="grape" onClick={computeStopTimes} disabled={rcTrips.length === 0 || rcShapePoints.length < 2 || rcOrderedStops.length < 2}>
                        {t('routeCreator.schedule.generate', 'Generate Schedule')}
                      </Button>
                      <Button size="sm" variant="outline" color="green" onClick={handleExportGTFS} disabled={rcTrips.length === 0}>
                        {t('routeCreator.schedule.export', 'Export GTFS txt')}
                      </Button>
                    </Group>
                  </Paper>
                )}

                {rcStep === 6 && (
                  <Paper p="xs" shadow="sm" withBorder style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <Group justify="space-between" mb="xs" align="flex-start">
                      <div>
                        <Text fw={600}>{t('routeCreator.stopTimes.title', 'Stop Times')}</Text>
                        <Text size="xs" c="dimmed">
                          {t('routeCreator.stopTimes.instructions', 'Review and edit departure/arrival times for each stop and trip.')}
                        </Text>
                      </div>
                      <Group gap={8}>
                        <Badge color="grape" variant="dot">
                          {t('routeCreator.schedule.trips', { defaultValue: '{{count}} trips', count: rcTrips.length } as any)}
                        </Badge>
                        <Badge color="gray" variant="light">
                          {rcOrderedStops.length} {t('routeCreator.stopTimes.stops', 'stops')}
                        </Badge>
                      </Group>
                    </Group>

                    {rcTrips.length === 0 || rcOrderedStops.length === 0 ? (
                      <Alert color="yellow" variant="light" mb="md">
                        {t('routeCreator.stopTimes.empty', 'No trips or stops available. Go back to schedule to generate times.')}
                      </Alert>
                    ) : (
                      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                        <Table
                          stickyHeader
                          striped
                          withRowBorders={false}
                          highlightOnHover
                          style={{ tableLayout: 'fixed', minWidth: rcStopTimesMinWidth }}
                        >
                          <Table.Thead>
                            <Table.Tr>
                              <Table.Th
                                style={{
                                  position: 'sticky',
                                  left: 0,
                                  zIndex: 3,
                                  background: 'var(--mantine-color-white)',
                                  padding: '4px 8px',
                                  fontSize: '11px',
                                }}
                              >
                                {t('routeCreator.schedule.stop', 'Stop')}
                              </Table.Th>
                              {rcTrips.map((trip) => (
                                <Table.Th key={trip} style={{ textAlign: 'center', padding: '4px' }}>
                                  <Badge variant="light" color="gray" size="xs" style={{ fontSize: '9px', height: '16px' }}>{trip}</Badge>
                                </Table.Th>
                              ))}
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {rcOrderedStops.map((stop, idx) => (
                              <Table.Tr key={`${stop.stop_id}-${idx}`}>
                                <Table.Td
                                  style={{
                                    position: 'sticky',
                                    left: 0,
                                    zIndex: 2,
                                    background: 'var(--mantine-color-white)',
                                    boxShadow: '8px 0 8px -8px rgba(0,0,0,0.08)',
                                    minWidth: 160,
                                    padding: '2px 8px',
                                  }}
                                >
                                  <Text fw={600} size="xs" style={{ fontSize: '11px' }} lineClamp={1}>{stop.stop_name}</Text>
                                  <Text size="xs" c="dimmed" style={{ fontSize: '9px' }}>{stop.stop_id}</Text>
                                </Table.Td>
                                {rcTrips.map((trip) => (
                                  <Table.Td key={`${trip}-${idx}`} style={{ padding: '2px' }}>
                                    <TextInput
                                      size="xs"
                                      variant="unstyled"
                                      value={(rcStopTimesTable[trip] || [])[idx] || ''}
                                      onChange={(e) => handleStopTimeChange(trip, idx, e.currentTarget.value)}
                                      placeholder="--"
                                      styles={{
                                        input: {
                                          textAlign: 'center',
                                          fontFamily: 'monospace',
                                          fontSize: '11px',
                                          height: '20px',
                                          minHeight: '20px',
                                          padding: 0,
                                          backgroundColor: (rcStopTimesTable[trip] || [])[idx] ? 'transparent' : 'rgba(0,0,0,0.02)',
                                        },
                                      }}
                                    />
                                  </Table.Td>
                                ))}
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      </div>
                    )}

                    <Group gap="xs" mt="xs">
                      <Button size="xs" variant="default" onClick={() => setRcStep(5)}>
                        {t('common.back', 'Back')}
                      </Button>
                      <Button size="xs" variant="light" color="gray" onClick={computeStopTimes} disabled={rcTrips.length === 0}>
                        {t('routeCreator.stopTimes.regenerate', 'Recompute')}
                      </Button>
                      <Button size="xs" variant="outline" color="green" onClick={handleExportGTFS} disabled={rcTrips.length === 0 || rcOrderedStops.length === 0}>
                        {t('routeCreator.schedule.export', 'Export GTFS txt')}
                      </Button>
                      <Button size="xs" color="green" onClick={() => setRcStep(7)} disabled={rcTrips.length === 0 || rcOrderedStops.length === 0}>
                        {t('routeCreator.nextReview', 'Next: Review & Create')}
                      </Button>
                    </Group>
                  </Paper>
                )}

                {/* Step 7: Export to Feed */}
                {rcStep === 7 && (
                  <FinalExport
                    routeId={rcRouteId}
                    routeShortName={rcRouteShortName}
                    routeColor={rcRouteColor}
                    orderedStops={rcOrderedStops}
                    newStops={rcNewStops}
                    shapePoints={rcShapePoints}
                    trips={rcTrips}
                    stopTimesTable={rcStopTimesTable}
                    feedId={selectedFeed ? parseInt(selectedFeed) : null}
                    calendars={calendars}
                    selectedServiceIds={rcSelectedServiceIds}
                    onBack={() => setRcStep(6)}
                    onExportComplete={() => {
                      handleToggleRouteCreator(false)
                      notifications.show({
                        title: t('common.success', 'Success'),
                        message: t('routeCreator.export.taskStarted', 'Export task started. Check Task Manager for progress.'),
                        color: 'green',
                      })
                    }}
                  />
                )}
              </Stack>
            </Box>
          )}

          {/* Always render the main map container */}
          {/* @ts-ignore - react-leaflet v4 type definitions issue */}
          <MapContainer
            center={mapCenter}
            zoom={mapZoom}
            style={{ height: '100%', width: '100%' }}
            zoomControl={!isMobile}
            scrollWheelZoom={true}
          >
            <MapCenterUpdater center={mapCenter} zoom={mapZoom} />
            <FitBoundsToStops stops={stops} shouldFit={shouldFitBounds} />
            <FlyToLocation target={flyTarget} onComplete={() => setFlyTarget(null)} />

            <TileLayer
              attribution={showSatellite
                ? 'Imagery © <a href="https://www.esri.com/">Esri</a>, Earthstar Geographics'
                : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}
              url={showSatellite
                ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"}
            />

            {/* Map click handler for creating stops/shapes in edit mode */}
            <MapClickHandler
              onMapClick={handleMapClick}
              enabled={
                routeCreatorEnabled ||
                (editMode && (editorMode === 'stops' || (editorMode === 'shapes' && creatingNewShape)))
              }
            />

            {/* Stops Layer */}
            {showStops && filteredStops.map((stop) => {
              const isAffected = affectedStopIds.has(stop.stop_id)
              const isEditMode = editMode && editorMode === 'stops'
              const rcLabel = rcSelectionLabels.get(stop.stop_id)
              const isRCSelected = routeCreatorEnabled && !!rcLabel

              // Use Marker with custom icon for edit mode (draggable), CircleMarker otherwise
              if (isEditMode) {
                return (
                  // @ts-ignore - react-leaflet v4 type definitions issue
                  <Marker
                    key={`${stop.feed_id}:${stop.stop_id}`}
                    position={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                    icon={createDraggableStopIcon(isAffected)}
                    draggable={true}
                    eventHandlers={{
                      dragend: (e) => {
                        const marker = e.target
                        const position = marker.getLatLng()
                        handleStopDrag(stop, position.lat, position.lng)
                      },
                      click: () => {
                        if (routeCreatorEnabled) {
                          handleRouteCreatorStopSelection({
                            stop_id: stop.stop_id,
                            stop_code: stop.stop_code || undefined,
                            stop_name: stop.stop_name,
                            lat: Number(stop.stop_lat),
                            lon: Number(stop.stop_lon),
                            isNew: false,
                          })
                        }
                      },
                    }}
                  >
                    <Popup>
                      <div style={{ padding: '4px', minWidth: 200 }}>
                        <Text fw={600} size="sm">{stop.stop_name}</Text>
                        <Code fz="xs">{stop.stop_id}</Code>
                        {stop.stop_code && (
                          <Text size="xs" c="dimmed">Code: {stop.stop_code}</Text>
                        )}
                        {stop.stop_desc && (
                          <Text size="xs" c="gray.7">{stop.stop_desc}</Text>
                        )}
                        <Text size="xs" c="dimmed">
                          {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                        </Text>
                        <Group gap="xs" mt="xs">
                          <Button size="xs" onClick={() => handleEditStop(stop)}>
                            {t('common.edit', 'Edit')}
                          </Button>
                          <Button size="xs" color="red" onClick={() => handleDeleteStop(stop)}>
                            {t('common.delete', 'Delete')}
                          </Button>
                        </Group>
                        <Text size="xs" c="dimmed" fs="italic" mt={4}>
                          💡 Drag marker to move stop
                        </Text>
                      </div>
                    </Popup>
                  </Marker>
                )
              }

              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <CircleMarker
                  key={`${stop.feed_id}:${stop.stop_id}`}
                  center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                  radius={isRCSelected ? (isMobile ? 9 : 10) : isAffected ? (isMobile ? 7 : 8) : (isMobile ? 5 : 6)}
                  pathOptions={{
                    fillColor: isRCSelected ? '#34d399' : isAffected ? '#ef4444' : '#3b82f6',
                    fillOpacity: isRCSelected ? 1 : isAffected ? 1 : 0.8,
                    color: isRCSelected ? '#0ea5e9' : isAffected ? '#fbbf24' : '#ffffff',
                    weight: isRCSelected ? 3 : isAffected ? 3 : 2,
                  }}
                  eventHandlers={{
                    click: (e) => {
                      if (routeCreatorEnabled) {
                        handleRouteCreatorStopSelection({
                          stop_id: stop.stop_id,
                          stop_code: stop.stop_code || undefined,
                          stop_name: stop.stop_name,
                          lat: Number(stop.stop_lat),
                          lon: Number(stop.stop_lon),
                          isNew: false,
                        })
                        const target: any = e.target
                        if (target?.closePopup) target.closePopup()
                      }
                    },
                    mouseover: (e) => {
                      if (routeCreatorEnabled) {
                        const target: any = e.target
                        if (target?.openPopup) target.openPopup()
                      }
                    },
                    mouseout: (e) => {
                      if (routeCreatorEnabled) {
                        const target: any = e.target
                        if (target?.closePopup) target.closePopup()
                      }
                    },
                  }}
                >
                  {routeCreatorEnabled && rcLabel && (
                    <LeafletTooltip direction="top" offset={[0, -4]} permanent>
                      #{rcLabel}
                    </LeafletTooltip>
                  )}
                  <Popup>
                    <StopPopupContent
                      stop={stop}
                      isAffected={isAffected}
                      isMobile={isMobile || false}
                      realtimeEnabled={realtimeEnabled}
                      tripUpdates={tripUpdates}
                      tripByGtfsId={tripByGtfsId}
                      routeByGtfsId={routeByGtfsId}
                      feedId={selectedFeed ? parseInt(selectedFeed) : null}
                      t={t}
                    />
                  </Popup>
                </CircleMarker>
              )
            })}

            {/* Orphan Stops Layer - independent from regular stops toggle, uses orange color */}
            {showOrphanStops && orphanStops.map((stop) => {
              const isEditMode = editMode && editorMode === 'stops'

              // Use Marker with custom icon for edit mode (draggable), CircleMarker otherwise
              if (isEditMode) {
                return (
                  // @ts-ignore - react-leaflet v4 type definitions issue
                  <Marker
                    key={`orphan-${stop.feed_id}:${stop.stop_id}`}
                    position={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                    icon={createDraggableStopIcon(false)}
                    draggable={true}
                    eventHandlers={{
                      dragend: (e) => {
                        const marker = e.target
                        const position = marker.getLatLng()
                        handleStopDrag(stop, position.lat, position.lng)
                      },
                    }}
                  >
                    <Popup>
                      <div style={{ padding: '4px', minWidth: 200 }}>
                        <Text fw={600} size="sm">{stop.stop_name}</Text>
                        <Code fz="xs">{stop.stop_id}</Code>
                        <Badge size="xs" color="orange" mt={4}>Orphan Stop</Badge>
                        {stop.stop_code && (
                          <Text size="xs" c="dimmed">Code: {stop.stop_code}</Text>
                        )}
                        {stop.stop_desc && (
                          <Text size="xs" c="gray.7">{stop.stop_desc}</Text>
                        )}
                        <Text size="xs" c="dimmed">
                          {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                        </Text>
                        <Group gap="xs" mt="xs">
                          <Button size="xs" onClick={() => handleEditStop(stop)}>
                            {t('common.edit', 'Edit')}
                          </Button>
                          <Button size="xs" color="red" onClick={() => handleDeleteStop(stop)}>
                            {t('common.delete', 'Delete')}
                          </Button>
                        </Group>
                        <Text size="xs" c="dimmed" fs="italic" mt={4}>
                          💡 Drag marker to move stop
                        </Text>
                      </div>
                    </Popup>
                  </Marker>
                )
              }

              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <CircleMarker
                  key={`orphan-${stop.feed_id}:${stop.stop_id}`}
                  center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                  radius={isMobile ? 5 : 6}
                  pathOptions={{
                    fillColor: '#f97316', // Orange for orphan stops
                    fillOpacity: 0.9,
                    color: '#ffffff',
                    weight: 2,
                  }}
                >
                  <Popup>
                    <div style={{ padding: '4px', minWidth: 200 }}>
                      <Text fw={600} size="sm">{stop.stop_name}</Text>
                      <Code fz="xs">{stop.stop_id}</Code>
                      <Badge size="xs" color="orange" mt={4}>Orphan Stop</Badge>
                      {stop.stop_code && (
                        <Text size="xs" c="dimmed">Code: {stop.stop_code}</Text>
                      )}
                      {stop.stop_desc && (
                        <Text size="xs" c="gray.7">{stop.stop_desc}</Text>
                      )}
                      <Text size="xs" c="dimmed" mt={4}>
                        {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                      </Text>
                      <Text size="xs" c="orange" fs="italic" mt={4}>
                        This stop is not used in any trip
                      </Text>
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}

            {/* Route Creator - in-memory new stops (draggable) */}
            {routeCreatorEnabled && rcNewStops.map((stop, idx) => {
              const rcLabel = rcSelectionLabels.get(stop.stop_id) || String(rcOrderedStops.findIndex(s => s.stop_id === stop.stop_id) + 1) || '?'
              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <Marker
                  key={`rc-new-${stop.stop_id}-${idx}`}
                  position={[Number(stop.lat), Number(stop.lon)]}
                  icon={createRcNewStopIcon(rcLabel)}
                  draggable={true}
                  eventHandlers={{
                    dragend: (e) => {
                      const marker = e.target
                      const position = marker.getLatLng()
                      handleRcNewStopDrag(stop.stop_id, position.lat, position.lng)
                    },
                    click: () => {
                      // Open edit modal with existing data
                      setRcEditingStopId(stop.stop_id)
                      setRcPendingStopPosition([Number(stop.lat), Number(stop.lon)])
                      const normalizedSeq = rcOrderedStops.find(s => s.stop_id === stop.stop_id)?.sequence
                      rcNewStopForm.setValues({
                        stop_id: stop.stop_id,
                        stop_code: stop.stop_code || '',
                        stop_name: stop.stop_name,
                        sequence: String(normalizedSeq || stop.sequence || rcOrderedStops.findIndex(s => s.stop_id === stop.stop_id) + 1),
                      })
                      setRcNewStopModalOpened(true)
                    },
                  }}
                >
                  <Popup>
                    <Text fw={600} size="sm">{stop.stop_name}</Text>
                    <Code fz="xs">{stop.stop_id}</Code>
                    <Text size="xs" c="dimmed">
                      {Number(stop.lat).toFixed(6)}, {Number(stop.lon).toFixed(6)}
                    </Text>
                    <Text size="xs" c="teal" mt={4}>In-memory stop (drag to move)</Text>
                  </Popup>
                </Marker>
              )
            })}

            {/* Route Creator Shape (in-memory) */}
            {routeCreatorEnabled && rcShapePoints.length > 0 && (
              <>
                <Polyline
                  positions={rcShapePoints.map(p => [p.lat, p.lon] as [number, number])}
                  pathOptions={{
                    color: '#0ea5e9',
                    weight: 6,
                    opacity: 0.8,
                    dashArray: '6 4',
                  }}
                  eventHandlers={{
                    click: (e) => {
                      if (rcAddPointMode) {
                        insertRCShapePoint(e.latlng.lat, e.latlng.lng)
                        setRcAddPointMode(false)
                      }
                    }
                  }}
                />
                {rcImproveSelection.start !== null && rcImproveSelection.end !== null && rcImproveSelection.end > rcImproveSelection.start && (
                  <Polyline
                    positions={rcShapePoints.slice(rcImproveSelection.start, rcImproveSelection.end + 1).map(p => [p.lat, p.lon] as [number, number])}
                    pathOptions={{
                      color: '#f59e0b',
                      weight: 8,
                      opacity: 0.7,
                    }}
                  />
                )}
                {rcShapePoints.map((point, idx) => (
                  // @ts-ignore - react-leaflet v4 type definitions issue
                  <Marker
                    key={`rc-shape-${idx}`}
                    position={[point.lat, point.lon]}
                    icon={createRouteCreatorPointIcon(idx)}
                    draggable
                    eventHandlers={{
                      dragend: (e) => {
                        const pos = e.target.getLatLng()
                        handleRCMarkerDrag(idx, pos.lat, pos.lng)
                      },
                      click: () => {
                        if (rcImproveSegmentMode) {
                          handleRCSelectImprovePoint(idx)
                        }
                      }
                    }}
                  >
                    <LeafletTooltip direction="top" offset={[0, -4]}>
                      Point #{idx + 1}
                    </LeafletTooltip>
                    <Popup>
                      <Text fw={600} size="sm">Shape Point {idx + 1}</Text>
                      <Text size="xs" c="dimmed">
                        {(point.lat ?? 0).toFixed(6)}, {(point.lon ?? 0).toFixed(6)}
                      </Text>
                      <Group gap="xs" mt="xs">
                        <Button size="xs" color="red" variant="light" disabled={rcShapePoints.length <= 2} onClick={() => handleRCRemovePoint(idx)}>
                          Remove
                        </Button>
                        {rcImproveSegmentMode && (
                          <Button
                            size="xs"
                            variant={rcImproveSelection.start === idx || rcImproveSelection.end === idx ? 'filled' : 'outline'}
                            onClick={() => handleRCSelectImprovePoint(idx)}
                          >
                            {rcImproveSelection.start === idx ? 'Start' : rcImproveSelection.end === idx ? 'End' : 'Select'}
                          </Button>
                        )}
                      </Group>
                    </Popup>
                  </Marker>
                ))}
              </>
            )}

            {/* Shapes Layer - only show if both routes and shapes are enabled */}
            {showRoutes && showShapes && filteredShapes.map((shape, index) => {
              if (!shape.points || shape.points.length === 0) {
                return null
              }

              const isShapesEditMode = editMode && editorMode === 'shapes'
              const isEditingThis = editingShapeId === shape.shape_id

              // Use edited points if this shape is being edited
              const positions = isEditingThis && editingShapePoints.length > 0
                ? editingShapePoints.map(p => [p.lat, p.lon] as [number, number])
                : shape.points.map(p => [p.lat, p.lon] as [number, number])

              // Use GTFS route_color if available, otherwise use default color palette
              let color = shapeColorMap[shape.shape_id] || defaultRouteColors[index % defaultRouteColors.length]

              // Highlight editing shape in orange
              if (isEditingThis) {
                color = '#f59e0b'
              }

              return (
                <div key={shape.shape_id}>
                  {/* Shape polyline */}
                  {/* @ts-ignore - react-leaflet v4 type definitions issue */}
                  <Polyline
                    positions={positions}
                    pathOptions={{
                      color: color,
                      weight: isEditingThis ? (isMobile ? 4 : 5) : (isMobile ? 2 : 3),
                      opacity: isEditingThis ? 1 : 0.7,
                    }}
                    eventHandlers={isShapesEditMode && !isEditingThis ? {
                      click: () => handleStartEditingShape(shape.shape_id)
                    } : undefined}
                  >
                    <Popup>
                      <div style={{ padding: '4px', minWidth: 200 }}>
                        <Text fw={600} size="sm">Shape {shape.shape_id}</Text>
                        <Text size="xs" c="dimmed">{isEditingThis ? editingShapePoints.length : shape.total_points} points</Text>
                        {shapeColorMap[shape.shape_id] && (
                          <Badge size="xs" color="gray" mt={4}>GTFS color</Badge>
                        )}
                        {isShapesEditMode && !isEditingThis && (
                          <Button size="xs" mt="xs" fullWidth onClick={() => handleStartEditingShape(shape.shape_id)}>
                            Edit this shape
                          </Button>
                        )}
                      </div>
                    </Popup>
                  </Polyline>

                  {/* Shape waypoint markers - only show when editing */}
                  {isEditingThis && isShapesEditMode && editingShapePoints.map((point, idx) => {
                    const waypointIcon = L.divIcon({
                      className: 'shape-waypoint-marker',
                      html: `<div style="
                        width: 12px;
                        height: 12px;
                        background-color: #f59e0b;
                        border: 2px solid white;
                        border-radius: 50%;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                        cursor: move;
                      "></div>`,
                      iconSize: [12, 12],
                      iconAnchor: [6, 6],
                    })

                    return (
                      // @ts-ignore - react-leaflet v4 type definitions issue
                      <Marker
                        key={`waypoint-${shape.shape_id}-${idx}`}
                        position={[point.lat, point.lon]}
                        icon={waypointIcon}
                        draggable={true}
                        eventHandlers={{
                          dragend: (e) => {
                            const marker = e.target
                            const position = marker.getLatLng()
                            handleMoveShapePoint(idx, position.lat, position.lng)
                          },
                        }}
                      >
                        <Popup>
                          <div style={{ padding: '4px' }}>
                            <Text size="xs" fw={600}>Waypoint {idx + 1}</Text>
                            <Text size="xs" c="dimmed">
                              {(point.lat ?? 0).toFixed(6)}, {(point.lon ?? 0).toFixed(6)}
                            </Text>
                            <Button
                              size="xs"
                              color="red"
                              mt="xs"
                              fullWidth
                              leftSection={<IconTrash size={12} />}
                              onClick={() => handleDeleteShapePoint(idx)}
                              disabled={editingShapePoints.length <= 2}
                            >
                              Delete Point
                            </Button>
                            {editingShapePoints.length <= 2 && (
                              <Text size="xs" c="dimmed" fs="italic" mt={4}>
                                Shape needs at least 2 points
                              </Text>
                            )}
                          </div>
                        </Popup>
                      </Marker>
                    )
                  })}

                  {/* Segment midpoint markers for adding points - only when editing */}
                  {isEditingThis && isShapesEditMode && editingShapePoints.length > 0 && editingShapePoints.map((point, idx) => {
                    if (idx === editingShapePoints.length - 1) return null // No midpoint after last point

                    const nextPoint = editingShapePoints[idx + 1]
                    const midLat = (point.lat + nextPoint.lat) / 2
                    const midLon = (point.lon + nextPoint.lon) / 2

                    const addPointIcon = L.divIcon({
                      className: 'shape-add-point-marker',
                      html: `<div style="
                        width: 16px;
                        height: 16px;
                        background-color: white;
                        border: 2px solid #f59e0b;
                        border-radius: 50%;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 12px;
                        color: #f59e0b;
                        font-weight: bold;
                      ">+</div>`,
                      iconSize: [16, 16],
                      iconAnchor: [8, 8],
                    })

                    return (
                      // @ts-ignore - react-leaflet v4 type definitions issue
                      <Marker
                        key={`add-point-${shape.shape_id}-${idx}`}
                        position={[midLat, midLon]}
                        icon={addPointIcon}
                        eventHandlers={{
                          click: () => handleAddPointToExistingShape(idx, midLat, midLon)
                        }}
                      >
                        <Popup>
                          <Text size="xs">Click to add waypoint</Text>
                        </Popup>
                      </Marker>
                    )
                  })}
                </div>
              )
            })}

            {/* New shape being created */}
            {creatingNewShape && newShapePoints.length > 0 && (
              <>
                {/* Polyline connecting the points */}
                {newShapePoints.length > 1 && (
                  // @ts-ignore - react-leaflet v4 type definitions issue
                  <Polyline
                    positions={newShapePoints.map(p => [p.lat, p.lon] as [number, number])}
                    pathOptions={{
                      color: '#3b82f6',
                      weight: isMobile ? 4 : 5,
                      opacity: 0.8,
                      dashArray: '10, 10',
                    }}
                  />
                )}

                {/* Markers for each point */}
                {newShapePoints.map((point, idx) => {
                  const pointIcon = L.divIcon({
                    className: 'new-shape-point-marker',
                    html: `<div style="
                      width: 14px;
                      height: 14px;
                      background-color: #3b82f6;
                      border: 2px solid white;
                      border-radius: 50%;
                      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                      display: flex;
                      align-items: center;
                      justify-content: center;
                      font-size: 8px;
                      color: white;
                      font-weight: bold;
                    ">${idx + 1}</div>`,
                    iconSize: [14, 14],
                    iconAnchor: [7, 7],
                  })

                  return (
                    // @ts-ignore - react-leaflet v4 type definitions issue
                    <Marker
                      key={`new-point-${idx}`}
                      position={[point.lat, point.lon]}
                      icon={pointIcon}
                    >
                      <Popup>
                        <div style={{ padding: '4px' }}>
                          <Text size="xs" fw={600}>Point {idx + 1}</Text>
                          <Text size="xs" c="dimmed">
                            {(point.lat ?? 0).toFixed(6)}, {(point.lon ?? 0).toFixed(6)}
                          </Text>
                          <Button
                            size="xs"
                            color="red"
                            mt="xs"
                            fullWidth
                            leftSection={<IconTrash size={12} />}
                            onClick={() => {
                              setNewShapePoints(prev => prev.filter((_, i) => i !== idx))
                            }}
                          >
                            Remove Point
                          </Button>
                        </div>
                      </Popup>
                    </Marker>
                  )
                })}
              </>
            )}

            {/* Highlighted Shape for Selected Vehicle */}
            {highlightedShape && highlightedShape.points && highlightedShape.points.length > 0 && (() => {
              const positions = highlightedShape.points.map(p => [p.lat, p.lon] as [number, number])
              const selectedVehicle = vehicles.find(v => v.vehicle_id === selectedVehicleId)
              const route = selectedVehicle?.route_id ? routeByGtfsId.get(selectedVehicle.route_id) : undefined
              const highlightColor = route?.route_color
                ? (route.route_color.startsWith('#') ? route.route_color : `#${route.route_color}`)
                : '#228be6'
              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <Polyline
                  key={`highlight-${highlightedShape.shape_id}`}
                  positions={positions}
                  pathOptions={{
                    color: highlightColor,
                    weight: isMobile ? 5 : 6,
                    opacity: 1,
                  }}
                />
              )
            })()}

            {/* Real-time Vehicle Markers */}
            {realtimeEnabled && showVehicles && vehicles.map((vehicle) => {
              const tripUpdate = tripUpdates.find(tu => tu.trip_id === vehicle.trip_id)
              const delay = tripUpdate?.delay

              // Lookup route, trip, and stop details for enhanced display
              const route = vehicle.route_id ? routeByGtfsId.get(vehicle.route_id) : undefined
              const trip = vehicle.trip_id ? tripByGtfsId.get(vehicle.trip_id) : undefined
              const stop = vehicle.stop_id ? stopByGtfsId.get(vehicle.stop_id) : undefined

              const routeColor = route?.route_color
                ? (route.route_color.startsWith('#') ? route.route_color : `#${route.route_color}`)
                : '#228be6'

              // Format status text
              const statusText = vehicle.current_status === 'stopped_at' ? 'Stopped at' :
                vehicle.current_status === 'incoming_at' ? 'Arriving at' : 'Next stop'

              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <Marker
                  key={`vehicle-${vehicle.vehicle_id}`}
                  position={[vehicle.latitude, vehicle.longitude]}
                  icon={getVehicleIcon(vehicle.bearing, routeColor)}
                  eventHandlers={{
                    popupopen: () => setSelectedVehicleId(vehicle.vehicle_id),
                    popupclose: () => setSelectedVehicleId(null),
                  }}
                >
                  <Popup>
                    <div style={{ minWidth: isMobile ? '220px' : '260px' }}>
                      {/* Compact Header */}
                      <div style={{
                        background: routeColor,
                        padding: '8px 12px',
                        margin: '-14px -14px 10px -14px',
                        borderRadius: '8px 8px 0 0'
                      }}>
                        <Group justify="space-between" align="center" wrap="nowrap" gap={8}>
                          <Group gap={8} wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                            <Text fw={700} size="lg" c="white" style={{ flexShrink: 0 }}>
                              {route?.route_short_name || vehicle.route_id || '—'}
                            </Text>
                            {route?.route_long_name && (
                              <Text size="xs" c="white" style={{ opacity: 0.85 }} lineClamp={1}>
                                {route.route_long_name}
                              </Text>
                            )}
                          </Group>
                          {vehicle.current_status && (
                            <Badge size="xs" variant="white" color="dark" style={{ flexShrink: 0 }}>
                              {vehicle.current_status.replace(/_/g, ' ').toUpperCase()}
                            </Badge>
                          )}
                        </Group>
                      </div>

                      <Stack gap={8}>
                        {/* Vehicle ID */}
                        <Group gap={6}>
                          <IconBus size={14} color="#868e96" style={{ flexShrink: 0 }} />
                          <Text size="xs" c="dimmed">{vehicle.vehicle_label || vehicle.vehicle_id}</Text>
                        </Group>

                        {/* Trip destination - if available */}
                        {(trip?.trip_headsign || trip?.trip_short_name) && (
                          <Group gap={6}>
                            <IconRoute size={14} color="#868e96" style={{ flexShrink: 0 }} />
                            <Text size="sm">{trip.trip_headsign || trip.trip_short_name}</Text>
                          </Group>
                        )}

                        {/* Stop info */}
                        {vehicle.stop_id && (
                          <Group gap={6} align="flex-start">
                            <IconMapPin size={14} color="#228be6" style={{ flexShrink: 0, marginTop: 2 }} />
                            <div>
                              <Text size="xs" c="dimmed">{statusText}</Text>
                              <Text size="sm" fw={500}>{stop?.stop_name || vehicle.stop_id}</Text>
                            </div>
                          </Group>
                        )}

                        {/* Metrics Row */}
                        <Group gap="xs">
                          {vehicle.speed !== undefined && vehicle.speed !== null && (
                            <Badge variant="light" color="blue" size="md">
                              {Math.round(vehicle.speed * 3.6)} km/h
                            </Badge>
                          )}
                          {delay !== undefined && delay !== null && (
                            <Badge
                              variant="light"
                              size="md"
                              color={delay > 300 ? 'red' : delay > 60 ? 'yellow' : 'green'}
                            >
                              {delay > 0 ? '+' : ''}{Math.round(delay / 60)} min
                            </Badge>
                          )}
                          {vehicle.occupancy_status && (
                            <Badge
                              size="md"
                              variant="light"
                              color={
                                vehicle.occupancy_status === 'full' ? 'red' :
                                  vehicle.occupancy_status === 'standing_room_only' ? 'orange' :
                                    vehicle.occupancy_status === 'few_seats_available' ? 'yellow' : 'green'
                              }
                            >
                              {vehicle.occupancy_status.replace(/_/g, ' ')}
                            </Badge>
                          )}
                        </Group>

                        {/* Timestamp */}
                        {vehicle.timestamp && (
                          <Text size="xs" c="dimmed">
                            Updated {new Date(vehicle.timestamp * 1000).toLocaleTimeString()}
                          </Text>
                        )}
                      </Stack>
                    </div>
                  </Popup>
                </Marker>
              )
            })}

            {/* Realtime Replacement Shapes (Detours) */}
            {realtimeEnabled && showReplacementShapes && realtimeShapes.map((rtShape) => {
              if (!rtShape.shape_points || rtShape.shape_points.length === 0) {
                return null
              }

              const positions = rtShape.shape_points.map(p => [p.lat, p.lon] as [number, number])

              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <Polyline
                  key={`rt-shape-${rtShape.shape_id}`}
                  positions={positions}
                  pathOptions={{
                    color: '#ff6b6b',  // Red color for detour shapes
                    weight: isMobile ? 4 : 5,
                    opacity: 0.8,
                    dashArray: '10, 10',  // Dashed line to distinguish from regular shapes
                  }}
                >
                  <Popup>
                    <div style={{ padding: '4px' }}>
                      <Text fw={600} size="sm" c="red">
                        🚧 Detour Shape
                      </Text>
                      <Text size="xs">{rtShape.shape_id}</Text>
                      {rtShape.shape_points && (
                        <Text size="xs" c="dimmed">{rtShape.shape_points.length} points</Text>
                      )}
                      {rtShape.modification_id && (
                        <Badge size="xs" color="red" mt={4}>Trip Modification</Badge>
                      )}
                    </div>
                  </Popup>
                </Polyline>
              )
            })}

            {/* Realtime Replacement Stops (Temporary Stops) */}
            {realtimeEnabled && showReplacementStops && realtimeStops.map((rtStop) => {
              if (!rtStop.stop_lat || !rtStop.stop_lon) {
                return null
              }

              return (
                // @ts-ignore - react-leaflet v4 type definitions issue
                <CircleMarker
                  key={`rt-stop-${rtStop.stop_id}`}
                  center={[rtStop.stop_lat, rtStop.stop_lon]}
                  radius={isMobile ? 8 : 10}
                  pathOptions={{
                    fillColor: '#ff6b6b',  // Red for temporary stops
                    color: '#ffffff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.9,
                  }}
                >
                  <Popup>
                    <div style={{ padding: '4px' }}>
                      <Text fw={600} size="sm" c="red">
                        🚧 Temporary Stop
                      </Text>
                      <Text size="sm">{rtStop.stop_name}</Text>
                      {rtStop.stop_code && (
                        <Badge size="xs" variant="outline" mt={4}>{rtStop.stop_code}</Badge>
                      )}
                      {rtStop.stop_desc && (
                        <Text size="xs" c="dimmed" mt={4}>{rtStop.stop_desc}</Text>
                      )}
                      {rtStop.wheelchair_boarding === 1 && (
                        <Badge size="xs" color="blue" mt={4}>♿ Accessible</Badge>
                      )}
                      {rtStop.modification_id && (
                        <Badge size="xs" color="red" mt={4}>Trip Modification</Badge>
                      )}
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}
          </MapContainer>

          {/* Map search box */}
          <MapSearchBox
            onSelectLocation={(lat, lon, zoom) => setFlyTarget({ lat, lon, zoom })}
            isMobile={isMobile}
          />

          {/* Floating map controls */}
          <Box
            style={{
              position: 'absolute',
              top: isMobile ? 82 : 88, // tuck just under zoom control
              left: isMobile ? 10 : 10, // align with Leaflet zoom left offset
              zIndex: 1400,
              pointerEvents: 'auto',
            }}
          >
            <Stack gap="xs" align="flex-start">
              <Tooltip label="Fit all stops in view">
                <ActionIcon
                  size="lg"
                  variant="filled"
                  color="blue"
                  radius="xl"
                  onClick={handleFitToView}
                  disabled={stops.length === 0}
                >
                  <IconFocus2 size={18} />
                </ActionIcon>
              </Tooltip>
              <Tooltip label={showSatellite ? 'Switch to map view' : 'Switch to satellite view'}>
                <ActionIcon
                  size="lg"
                  variant={showSatellite ? 'filled' : 'light'}
                  color="green"
                  radius="xl"
                  onClick={() => setShowSatellite(!showSatellite)}
                >
                  <IconWorld size={18} />
                </ActionIcon>
              </Tooltip>
            </Stack>
          </Box>

          {/* Floating Shape Editor Widget */}
          {editMode && editorMode === 'shapes' && selectedAgency && !isMobile && (
            <Paper
              shadow="xl"
              p={8}
              radius="md"
              style={{
                position: 'absolute',
                top: 15,
                left: 15,
                zIndex: 1000,
                width: 260,
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                backdropFilter: 'blur(8px)',
              }}
            >
              <Stack gap={6}>
                <Group justify="space-between" wrap="nowrap">
                  <Text fw={600} size="xs">{t('map.shapes.editor', 'Shape Editor')}</Text>
                  <Badge
                    color="orange"
                    size="xs"
                    variant="filled"
                    style={{ cursor: 'pointer' }}
                    onClick={() => setShapeSelectionModalOpened(true)}
                    title="Select shapes"
                  >
                    {effectiveSelectedShapesCount}/{availableShapes.length}
                  </Badge>
                </Group>

                {creatingNewShape ? (
                  <Stack gap={4}>
                    <Text size="xs" fw={600} c="blue">
                      {t('map.shapes.creatingNew', 'Creating')}: {newShapeId}
                    </Text>
                    <Badge size="xs" variant="light">{newShapePoints.length} pts</Badge>
                    <Group gap={4}>
                      <Button
                        size="xs"
                        color="green"
                        onClick={handleSaveNewShape}
                        disabled={newShapePoints.length < 2}
                        fullWidth
                        compact
                      >
                        {t('common.save', 'Save')}
                      </Button>
                      <ActionIcon
                        size="sm"
                        color="gray"
                        variant="light"
                        onClick={handleCancelShapeEdit}
                        title="Cancel"
                      >
                        <IconX size={14} />
                      </ActionIcon>
                    </Group>
                  </Stack>
                ) : editingShapeId ? (
                  <Stack gap={4}>
                    <Text size="xs" fw={600} c="orange">
                      {t('map.shapes.editing', 'Editing')}: {editingShapeId}
                    </Text>
                    <Badge size="xs" variant="light">{editingShapePoints.length} pts</Badge>
                    <Group gap={4}>
                      <Button
                        size="xs"
                        color="green"
                        onClick={handleSaveShape}
                        fullWidth
                        compact
                      >
                        {t('common.save', 'Save')}
                      </Button>
                      <ActionIcon
                        size="sm"
                        color="gray"
                        variant="light"
                        onClick={handleCancelShapeEdit}
                        title="Cancel"
                      >
                        <IconX size={14} />
                      </ActionIcon>
                    </Group>
                  </Stack>
                ) : (
                  <Button
                    size="xs"
                    color="blue"
                    leftSection={<IconPlus size={14} />}
                    onClick={handleStartCreateShape}
                    fullWidth
                  >
                    {t('map.shapes.createNew', 'Create New Shape')}
                  </Button>
                )}
              </Stack>
            </Paper>
          )}

          {/* No data message */}
          {!loading && selectedAgency && stops.length === 0 && (
            <Paper
              shadow="md"
              p={isMobile ? 'md' : 'xl'}
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                zIndex: 1000,
                maxWidth: isMobile ? '90%' : 'auto'
              }}
            >
              <Stack align="center" gap="xs">
                <IconMapPin size={isMobile ? 36 : 48} color="gray" />
                <Text size={isMobile ? 'md' : 'lg'} fw={500} ta="center">No GTFS Data Available</Text>
                <Text size="sm" c="dimmed" ta="center">
                  Import GTFS data for this agency to view it on the map
                </Text>
              </Stack>
            </Paper>
          )}
        </div>

        {/* Mobile Controls Drawer */}
        <Drawer
          opened={mobileDrawerOpened}
          onClose={closeMobileDrawer}
          position="bottom"
          size="auto"
          withCloseButton={false}
          styles={{
            content: {
              borderTopLeftRadius: 16,
              borderTopRightRadius: 16,
            },
            body: {
              paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 80px)',
            }
          }}
        >
          <MobileControlsContent />
        </Drawer>

        {/* Route Selection Modal */}
        <Modal
          opened={routeSelectionOpened}
          onClose={() => setRouteSelectionOpened(false)}
          title={
            <Group gap="xs">
              <IconBus size={20} />
              <Text fw={600}>Select Routes to Display</Text>
            </Group>
          }
          size="lg"
          zIndex={3000}
        >
          <Stack gap="md">
            {/* Search and Actions */}
            <Group>
              <TextInput
                placeholder="Search routes..."
                leftSection={<IconSearch size={16} />}
                value={routeSearchText}
                onChange={(e) => setRouteSearchText(e.currentTarget.value)}
                style={{ flex: 1 }}
              />
              <Button
                variant="light"
                size="sm"
                leftSection={<IconCheck size={16} />}
                onClick={handleSelectAllRoutes}
              >
                All
              </Button>
              <Button
                variant="light"
                size="sm"
                color="gray"
                onClick={handleDeselectAllRoutes}
              >
                None
              </Button>
            </Group>

            <Divider />

            {/* Route List */}
            <ScrollArea.Autosize mah={400}>
              <Stack gap="xs">
                {filteredRoutes.length === 0 ? (
                  <Text size="sm" c="dimmed" ta="center" py="md">
                    No routes found
                  </Text>
                ) : (
                  filteredRoutes.map((route) => {
                    const routeColor = route.route_color
                      ? (route.route_color.startsWith('#') ? route.route_color : `#${route.route_color}`)
                      : '#3b82f6'
                    const isSelected = selectedRouteIds.has(route.route_id)

                    return (
                      <Paper
                        key={route.route_id}
                        p="xs"
                        withBorder
                        style={{
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'var(--mantine-color-blue-0)' : 'transparent',
                          borderColor: isSelected ? 'var(--mantine-color-blue-3)' : undefined,
                        }}
                        onClick={() => handleRouteToggle(route.route_id)}
                      >
                        <Group gap="sm" wrap="nowrap">
                          <Checkbox
                            checked={isSelected}
                            onChange={() => handleRouteToggle(route.route_id)}
                            onClick={(e) => e.stopPropagation()}
                            color="blue"
                          />
                          <div
                            style={{
                              width: 4,
                              height: 28,
                              backgroundColor: routeColor,
                              borderRadius: 2,
                              flexShrink: 0,
                            }}
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Group gap="xs" wrap="nowrap">
                              <Text fw={600} size="sm" style={{ flexShrink: 0 }}>
                                {route.route_short_name || route.route_id}
                              </Text>
                              {route.route_long_name && (
                                <Text size="sm" c="dimmed" lineClamp={1}>
                                  {route.route_long_name}
                                </Text>
                              )}
                            </Group>
                            <Text size="xs" c="dimmed">
                              ID: {route.route_id}
                            </Text>
                          </div>
                        </Group>
                      </Paper>
                    )
                  })
                )}
              </Stack>
            </ScrollArea.Autosize>

            <Divider />

            {/* Summary */}
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                {effectiveSelectedRoutesCount} of {availableRoutes.length} routes selected
              </Text>
              <Button onClick={() => setRouteSelectionOpened(false)}>
                Done
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* Shapes Selection Modal */}
        <Modal
          opened={shapeSelectionOpened}
          onClose={() => setShapeSelectionOpened(false)}
          title={
            <Group gap="xs">
              <IconRoute size={20} />
              <Text fw={600}>Select Shapes to Display</Text>
            </Group>
          }
          size="lg"
          zIndex={3000}
        >
          <Stack gap="md">
            {/* Search and Actions */}
            <Group>
              <TextInput
                placeholder="Search shapes..."
                leftSection={<IconSearch size={16} />}
                value={shapeSearchText}
                onChange={(e) => setShapeSearchText(e.currentTarget.value)}
                style={{ flex: 1 }}
              />
              <Button
                variant="light"
                size="sm"
                leftSection={<IconCheck size={16} />}
                onClick={handleSelectAllShapes}
              >
                All
              </Button>
              <Button
                variant="light"
                size="sm"
                color="gray"
                onClick={handleDeselectAllShapes}
              >
                None
              </Button>
            </Group>

            <Divider />

            {/* Shape List */}
            <ScrollArea.Autosize mah={400}>
              <Stack gap="xs">
                {filteredShapesForSelection.length === 0 ? (
                  <Text size="sm" c="dimmed" ta="center" py="md">
                    No shapes found
                  </Text>
                ) : (
                  filteredShapesForSelection.map((shape) => {
                    const isSelected = selectedShapeIds.has(shape.shape_id)
                    const shapeColor = shapeColorMap[shape.shape_id] || '#3b82f6'

                    return (
                      <Paper
                        key={shape.shape_id}
                        p="xs"
                        withBorder
                        style={{
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'var(--mantine-color-teal-0)' : 'transparent',
                          borderColor: isSelected ? 'var(--mantine-color-teal-3)' : undefined,
                        }}
                        onClick={() => handleShapeToggle(shape.shape_id)}
                      >
                        <Group gap="sm" wrap="nowrap">
                          <Checkbox
                            checked={isSelected}
                            onChange={() => handleShapeToggle(shape.shape_id)}
                            onClick={(e) => e.stopPropagation()}
                            color="teal"
                          />
                          <div
                            style={{
                              width: 4,
                              height: 28,
                              backgroundColor: shapeColor,
                              borderRadius: 2,
                              flexShrink: 0,
                            }}
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Text fw={600} size="sm">
                              {shape.shape_id}
                            </Text>
                            <Text size="xs" c="dimmed">
                              {shape.total_points} points
                            </Text>
                          </div>
                        </Group>
                      </Paper>
                    )
                  })
                )}
              </Stack>
            </ScrollArea.Autosize>

            <Divider />

            {/* Summary */}
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                {effectiveSelectedShapesCount} of {availableShapes.length} shapes selected
              </Text>
              <Button onClick={() => setShapeSelectionOpened(false)}>
                Done
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* Calendar Selection Modal */}
        <Modal
          opened={calendarSelectionOpened}
          onClose={() => setCalendarSelectionOpened(false)}
          title={
            <Group gap="xs">
              <IconCalendar size={20} />
              <Text fw={600}>Select Calendars to Filter</Text>
            </Group>
          }
          size="lg"
          zIndex={3000}
        >
          <Stack gap="md">
            {/* Search and Actions */}
            <Group>
              <TextInput
                placeholder="Search calendars..."
                leftSection={<IconSearch size={16} />}
                value={calendarSearchText}
                onChange={(e) => setCalendarSearchText(e.currentTarget.value)}
                style={{ flex: 1 }}
              />
              <Button
                variant="light"
                size="sm"
                leftSection={<IconCheck size={16} />}
                onClick={handleSelectAllCalendars}
              >
                All
              </Button>
              <Button
                variant="light"
                size="sm"
                color="gray"
                onClick={handleDeselectAllCalendars}
              >
                None
              </Button>
            </Group>

            <Divider />

            {/* Calendar List */}
            <ScrollArea.Autosize mah={400}>
              <Stack gap="xs">
                {filteredCalendars.length === 0 ? (
                  <Text size="sm" c="dimmed" ta="center" py="md">
                    No calendars found
                  </Text>
                ) : (
                  filteredCalendars.map((calendar: any) => {
                    const isSelected = selectedCalendarIds.has(calendar.service_id)

                    return (
                      <Paper
                        key={`${calendar.feed_id}:${calendar.service_id}`}
                        p="xs"
                        withBorder
                        style={{
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'var(--mantine-color-purple-0)' : 'transparent',
                          borderColor: isSelected ? 'var(--mantine-color-purple-3)' : undefined,
                        }}
                        onClick={() => handleCalendarToggle(calendar.service_id)}
                      >
                        <Group gap="sm" wrap="nowrap">
                          <Checkbox
                            checked={isSelected}
                            onChange={() => handleCalendarToggle(calendar.service_id)}
                            onClick={(e) => e.stopPropagation()}
                            color="purple"
                          />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Text fw={600} size="sm">
                              {calendar.service_id}
                            </Text>
                            {calendar.isExceptionBased ? (
                              <Badge size="xs" variant="light" color="orange" mt={4}>
                                Exception-based (calendar_dates only)
                              </Badge>
                            ) : (
                              <>
                                <Group gap="xs" mt={4}>
                                  {calendar.monday && <Badge size="xs" variant="light">Mon</Badge>}
                                  {calendar.tuesday && <Badge size="xs" variant="light">Tue</Badge>}
                                  {calendar.wednesday && <Badge size="xs" variant="light">Wed</Badge>}
                                  {calendar.thursday && <Badge size="xs" variant="light">Thu</Badge>}
                                  {calendar.friday && <Badge size="xs" variant="light">Fri</Badge>}
                                  {calendar.saturday && <Badge size="xs" variant="light" color="blue">Sat</Badge>}
                                  {calendar.sunday && <Badge size="xs" variant="light" color="blue">Sun</Badge>}
                                </Group>
                                {(calendar.start_date || calendar.end_date) && (
                                  <Text size="xs" c="dimmed" mt={4}>
                                    {calendar.start_date && `From: ${calendar.start_date}`}
                                    {calendar.start_date && calendar.end_date && ' • '}
                                    {calendar.end_date && `To: ${calendar.end_date}`}
                                  </Text>
                                )}
                              </>
                            )}
                          </div>
                        </Group>
                      </Paper>
                    )
                  })
                )}
              </Stack>
            </ScrollArea.Autosize>

            <Divider />

            {/* Summary */}
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                {selectedCalendarIds.size} of {calendars.length} calendars selected
              </Text>
              <Button onClick={() => setCalendarSelectionOpened(false)}>
                Done
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* Route Creator Drawer */}
        {false && (
          <Box
            ref={rcDrawerRef}
            style={{
              position: 'absolute',
              top: rcDrawerPosition.top,
              right: rcDrawerPosition.right ?? 'auto',
              left: rcDrawerPosition.left ?? 'auto',
              zIndex: 3600,
              maxWidth: rcDrawerWidth,
              width: rcDrawerWidth,
              pointerEvents: 'auto',
              cursor: 'move',
              touchAction: 'none',
            }}
            onPointerDown={handleRcDragStart}
          >
            <Stack gap="sm">
              <Paper p="md" shadow="md" withBorder>
                <Group justify="space-between" mb="xs">
                  <Text fw={600}>{t('routeCreator.title', 'Route Creator')}</Text>
                  <Group gap={6}>
                    <Badge color="teal" variant="light">{t('routeCreator.noDbWrites', 'No DB writes')}</Badge>
                    <Button size="xs" variant="subtle" color="red" onClick={() => handleToggleRouteCreator(false)}>
                      {t('common.close', 'Close')}
                    </Button>
                  </Group>
                </Group>
                <Group gap="xs" mb="sm">
                  {[1, 2, 3, 4, 5, 6, 7].map((n) => {
                    const label = n === 1
                      ? t('routeCreator.steps.calendar', 'Calendar')
                      : n === 2
                        ? t('routeCreator.steps.route', 'Route')
                        : n === 3
                          ? t('routeCreator.steps.stops', 'Stops')
                          : n === 4
                            ? t('routeCreator.steps.shape', 'Shape')
                            : n === 5
                              ? t('routeCreator.steps.schedule', 'Schedule')
                              : n === 6
                                ? t('routeCreator.steps.stopTimes', 'Stop Times')
                                : t('routeCreator.steps.export', 'Export')
                    const active = rcStep === n
                    const canGoToExport = rcTrips.length > 0 && Object.keys(rcStopTimesTable).length > 0
                    const enabled = (n === 1)
                      || (n === 2 && canGoToRoute)
                      || (n === 3 && canGoToStops)
                      || (n === 4 && canGoToShape)
                      || (n === 5 && canGoToSchedule)
                      || (n === 6 && canGoToStopTimes)
                      || (n === 7 && canGoToExport)
                    return (
                      <Button
                        key={n}
                        size="xs"
                        variant={active ? 'filled' : 'light'}
                        color={active ? 'blue' : 'gray'}
                        disabled={!enabled}
                        onClick={() => {
                          if (enabled) setRcStep(n as 1 | 2 | 3 | 4 | 5 | 6 | 7)
                        }}
                      >
                        {n}. {label}
                      </Button>
                    )
                  })}
                </Group>
                {rcStep === 1 && (
                  <>
                    {/* Calendar Selection - Step 1 */}
                    <Text fw={600} mb="xs">{t('routeCreator.calendarSelection', 'Service Calendars')}</Text>
                    <Text size="sm" c="dimmed" mb="sm">
                      {t('routeCreator.calendarSelectionDesc', 'Select an existing calendar or create a new one. Trips will be created for each selected calendar.')}
                    </Text>
                    <Group align="flex-end" gap="xs">
                      <MultiSelect
                        style={{ flex: 1 }}
                        size="sm"
                        data={rcCalendarOptions}
                        value={rcSelectedServiceIds}
                        onChange={setRcSelectedServiceIds}
                        placeholder={rcCalendarOptions.length > 0 ? t('routeCreator.selectCalendarsPlaceholder', 'Select calendars...') : t('routeCreator.noCalendars', 'No calendars available')}
                        searchable
                        clearable
                        maxDropdownHeight={200}
                        comboboxProps={{ zIndex: 100001 }}
                      />
                      <Tooltip label={t('routeCreator.createCalendar', 'Create new calendar')}>
                        <Button size="sm" variant="light" onClick={openRcCalendarModal} leftSection={<IconPlus size={16} />}>
                          {t('common.new', 'New')}
                        </Button>
                      </Tooltip>
                    </Group>
                    {rcCalendarOptions.length === 0 && selectedFeed && (
                      <Alert color="yellow" icon={<IconAlertCircle size={16} />} mt="xs" p="xs">
                        <Text size="xs">{t('routeCreator.noCalendarsWarning', 'No calendars found in this feed. Create one to continue.')}</Text>
                      </Alert>
                    )}

                    <Group mt="sm" gap="xs">
                      <Button size="sm" color="blue" disabled={!canGoToRoute} onClick={() => setRcStep(2)}>
                        {t('routeCreator.nextRoute', 'Next: Route')}
                      </Button>
                      <Button size="sm" variant="light" color="gray" onClick={resetRouteCreator}>
                        {t('common.reset', 'Reset')}
                      </Button>
                    </Group>
                  </>
                )}

                {rcStep === 2 && (
                  <>
                    {/* Route Selection - Step 2 */}
                    <SimpleGrid cols={2} spacing="sm">
                      <TextInput
                        label={t('routeCreator.routeId', 'Route ID')}
                        value={rcRouteId}
                        onChange={(e) => setRcRouteId(e.currentTarget.value)}
                        placeholder="RC_ROUTE_1"
                      />
                      <TextInput
                        label={t('routeCreator.shortName', 'Short Name')}
                        value={rcRouteShortName}
                        onChange={(e) => setRcRouteShortName(e.currentTarget.value)}
                        placeholder={t('routeCreator.shortNamePlaceholder', 'Express')}
                      />
                    </SimpleGrid>
                    <ColorInput
                      label={t('routeCreator.routeColor', 'Route Color')}
                      value={rcRouteColor}
                      onChange={setRcRouteColor}
                      format="hex"
                      swatches={['#0ea5e9', '#10b981', '#f97316', '#ef4444', '#8b5cf6']}
                    />

                    <Group mt="sm" gap="xs">
                      <Button size="sm" variant="default" onClick={() => setRcStep(1)}>
                        {t('common.back', 'Back')}
                      </Button>
                      <Button size="sm" color="blue" disabled={!canGoToStops} onClick={() => setRcStep(3)}>
                        {t('routeCreator.nextStops', 'Next: Stops')}
                      </Button>
                      <Button size="sm" variant="light" color="gray" onClick={resetRouteCreator}>
                        {t('common.reset', 'Reset')}
                      </Button>
                    </Group>
                  </>
                )}
              </Paper>

              {rcStep === 3 && (
                <Paper p="md" shadow="sm" withBorder style={{ maxHeight: '60vh', display: 'flex', flexDirection: 'column' }}>
                  <Group justify="space-between" mb="xs" gap="xs" wrap="wrap">
                    <Text fw={600}>{t('routeCreator.stops.title', 'Stops (map click to add/select)')}</Text>
                    <Badge color="indigo" variant="dot">
                      {t('routeCreator.stops.count', { defaultValue: '{{count}} selected', count: rcOrderedStops.length } as any)}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed" mb="xs">
                    {t(
                      'routeCreator.stops.instructions',
                      'Click existing stops to select; click map to add in-memory stops. Click last stop again to remove, earlier stop to loop or remove. Drag items below to reorder stop sequence.'
                    )}
                  </Text>
                  <ScrollArea style={{ flex: 1, minHeight: 0 }} type="auto">
                    <Stack gap="xs">
                      {rcOrderedStops.length === 0 && (
                        <Text size="sm" c="dimmed">
                          {t('routeCreator.stops.none', 'No stops selected yet.')}
                        </Text>
                      )}
                      {rcOrderedStops.map((s, idx) => (
                        <Group
                          key={`${s.stop_id}-${idx}`}
                          justify="space-between"
                          draggable
                          onDragStart={(e) => {
                            setRcDragIndex(idx)
                            setRcDragHoverIndex(idx)
                            e.dataTransfer.effectAllowed = 'move'
                            // Some browsers require data to enable drops
                            e.dataTransfer.setData('text/plain', String(idx))
                          }}
                          onDragEnter={(e) => {
                            e.preventDefault()
                            setRcDragHoverIndex(idx)
                          }}
                          onDragOver={(e) => {
                            e.preventDefault()
                            e.dataTransfer.dropEffect = 'move'
                          }}
                          onDrop={(e) => {
                            e.preventDefault()
                            // capture last target index for reorder on drag end
                            setRcDragHoverIndex(idx)
                          }}
                          onDragEnd={() => {
                            if (rcDragIndex !== null && rcDragHoverIndex !== null && rcDragIndex !== rcDragHoverIndex) {
                              handleRcReorderStops(rcDragIndex, rcDragHoverIndex)
                            }
                            setRcDragIndex(null)
                            setRcDragHoverIndex(null)
                          }}
                          style={{
                            border:
                              rcDragHoverIndex === idx
                                ? '1px dashed #0ea5e9'
                                : '1px solid var(--mantine-color-gray-3)',
                            borderRadius: 8,
                            padding: 8,
                            background: 'white',
                            cursor: 'grab',
                          }}
                        >
                          <Group gap="xs">
                            <Badge size="sm" color="teal" variant="filled">#{idx + 1}</Badge>
                            <div>
                              <Text fw={600} size="sm">
                                {s.stop_name}{' '}
                                {s.pass > 1 && (
                                  <Badge size="xs" color="orange" variant="light">
                                    {t('routeCreator.stops.loop', { defaultValue: 'loop {{pass}}', pass: s.pass } as any)}
                                  </Badge>
                                )}
                              </Text>
                              <Text size="xs" c="dimmed">{s.stop_id} • {(parseFloat(String(s.lat)) || 0).toFixed(5)}, {(parseFloat(String(s.lon)) || 0).toFixed(5)}</Text>
                            </div>
                          </Group>
                          <Button size="xs" variant="subtle" color="red" onClick={() => setRcSelectedStops(prev => prev.filter((_, i) => i !== idx))}>
                            {t('common.remove', 'Remove')}
                          </Button>
                        </Group>
                      ))}
                    </Stack>
                  </ScrollArea>
                  <Group mt="sm" gap="xs" style={{ flexShrink: 0 }}>
                    <Button size="sm" variant="default" onClick={() => setRcStep(2)}>
                      {t('common.back', 'Back')}
                    </Button>
                    <Button size="sm" color="blue" disabled={!canGoToShape} onClick={() => setRcStep(4)}>
                      {t('routeCreator.nextShape', 'Next: Shape')}
                    </Button>
                    <Button size="sm" variant="light" color="gray" onClick={() => { setRcSelectedStops([]); setRcNewStops([]); }}>
                      {t('routeCreator.stops.clear', 'Clear Stops')}
                    </Button>
                  </Group>
                </Paper>
              )}

              {rcStep === 4 && (
                <Paper p="md" shadow="sm" withBorder>
                  <Group justify="space-between" mb="xs" gap="xs" wrap="wrap">
                    <Text fw={600}>{t('routeCreator.shape.title', 'Shape Editing')}</Text>
                    <Badge color="blue" variant="dot">
                      {t('routeCreator.shape.points', { defaultValue: '{{count}} pts', count: rcShapePoints.length } as any)}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed" mb="xs">
                    {t('routeCreator.shape.instructions', 'Generate from Valhalla or edit manually. Drag point markers to move. Use Improve Segment to re-route between two points.')}
                  </Text>
                  <Group gap="xs" mb="xs">
                    <Button size="sm" color="teal" onClick={handleRouteCreatorGenerateShape} loading={rcShapeGenerating} disabled={!canGoToShape}>
                      {t('routeCreator.shape.generate', 'Generate Shape')}
                    </Button>
                    <Button size="sm" variant={rcAddPointMode ? 'filled' : 'light'} color="blue" onClick={() => setRcAddPointMode(!rcAddPointMode)}>
                      {rcAddPointMode
                        ? t('routeCreator.shape.addPointActive', 'Click map to add point')
                        : t('routeCreator.shape.addPoint', 'Add Shape Point')}
                    </Button>
                    <Button size="sm" variant={rcImproveSegmentMode ? 'filled' : 'light'} color="orange" onClick={() => {
                      setRcImproveSegmentMode(!rcImproveSegmentMode)
                      setRcImproveSelection({ start: null, end: null })
                    }} disabled={rcShapePoints.length < 2}>
                      {rcImproveSegmentMode
                        ? t('routeCreator.shape.selectImprove', 'Select start & end on map')
                        : t('routeCreator.shape.improve', 'Improve Segment')}
                    </Button>
                    <Button size="sm" variant="light" color="gray" onClick={() => setRcShapePoints([])}>
                      {t('routeCreator.shape.clear', 'Clear Shape')}
                    </Button>
                  </Group>
                  <Text size="xs" c="dimmed" mb="sm">
                    {t('routeCreator.shape.tip', 'Tip: when "Add Shape Point" is active, click the map or shape line to insert a point.')}
                  </Text>
                  <Group gap="xs">
                    <Button size="sm" variant="default" onClick={() => setRcStep(3)}>
                      {t('common.back', 'Back')}
                    </Button>
                    <Button size="sm" color="blue" disabled={!canGoToSchedule} onClick={() => setRcStep(5)}>
                      {t('routeCreator.nextSchedule', 'Next: Schedule')}
                    </Button>
                  </Group>
                </Paper>
              )}

              {rcStep === 5 && (
                <Paper p="md" shadow="sm" withBorder style={{ width: '100%', alignSelf: 'stretch', maxWidth: '100%' }}>
                  <Group justify="space-between" align="flex-start" mb="xs" gap="xs" wrap="wrap">
                    <div>
                      <Text fw={600}>{t('routeCreator.schedule.title', 'Schedule')}</Text>
                      <Text size="sm" c="dimmed">
                        {t('routeCreator.schedule.instructions', 'Click anywhere on the 24h timeline to add/remove departures (leave from stop #1). Hover shows exact time. Hours are grouped in two rows: AM on top, PM on bottom. Each hour has 3 rows x 4 columns of 5-minute slots.')}
                      </Text>
                    </div>
                    <Group gap={6}>
                      <Badge color="grape" variant="dot">
                        {t('routeCreator.schedule.trips', { defaultValue: '{{count}} trips', count: rcTrips.length } as any)}
                      </Badge>
                      <Badge color="gray" variant="light">
                        {rcHoverTime ? `${t('routeCreator.schedule.hover', 'Hover')}: ${rcHoverTime}` : t('routeCreator.schedule.hoverNone', 'Hover timeline')}
                      </Badge>
                    </Group>
                  </Group>

                  <Box
                    mt="sm"
                    p="md"
                    style={{
                      border: '1px solid var(--mantine-color-gray-3)',
                      borderRadius: 12,
                      backgroundColor: 'var(--mantine-color-gray-0)',
                    }}
                  >
                    <Group justify="space-between" align="center" mb="xs">
                      <Text size="sm" fw={600}>{t('routeCreator.schedule.departures', 'Departures')}</Text>
                      <Text size="xs" c="dimmed">
                        {rcSortedTrips.length > 0
                          ? `${t('routeCreator.schedule.selected', 'Selected')}: ${rcSortedTrips.join(', ')}`
                          : t('routeCreator.schedule.noneSelected', 'No departures selected')}
                      </Text>
                    </Group>

                    <Box style={{ width: '100%' }}>
                      {[
                        { label: t('routeCreator.schedule.amRow', 'AM (00:00 - 11:55)'), hours: rcHoursAM },
                        { label: t('routeCreator.schedule.pmRow', 'PM (12:00 - 23:55)'), hours: rcHoursPM },
                      ].map((row) => (
                        <Box key={row.label} mb="md">
                          <Group gap={6} mb={6}>
                            <Badge size="sm" variant="light" color="gray">{row.label}</Badge>
                          </Group>
                          <Box
                            style={{
                              display: 'grid',
                              gridTemplateColumns: 'repeat(12, minmax(40px, 1fr))',
                              gap: 8,
                              width: '100%',
                            }}
                          >
                            {row.hours.map((hour) => (
                              <Box key={hour.label}>
                                <Text size="xs" fw={600} ta="center" mb={6}>{hour.label}</Text>
                                <Box
                                  style={{
                                    display: 'grid',
                                    gridTemplateColumns: 'repeat(4, 1fr)',
                                    gridTemplateRows: 'repeat(3, 1fr)',
                                    gap: 6,
                                  }}
                                >
                                  {hour.times.map((time) => {
                                    const selected = rcTrips.includes(time)
                                    const minuteLabel = time.split(':')[1]
                                    return (
                                      <Box
                                        key={time}
                                        onMouseEnter={() => setRcHoverTime(time)}
                                        onMouseLeave={() => setRcHoverTime(null)}
                                        onClick={() => handleTripBlockToggle(time)}
                                        title={time}
                                        style={{
                                          height: 20,
                                          borderRadius: 5,
                                          cursor: 'pointer',
                                          display: 'flex',
                                          alignItems: 'center',
                                          justifyContent: 'center',
                                          backgroundColor: selected ? '#9b5de5' : '#e2e8f0',
                                          color: selected ? '#fff' : '#475569',
                                          border: selected ? '1px solid #7c3aed' : '1px solid #e2e8f0',
                                          boxShadow: selected ? '0 0 0 1px #f3e8ff inset' : undefined,
                                          transition: 'transform 80ms ease, box-shadow 120ms ease',
                                          fontSize: 11,
                                          fontWeight: 600,
                                        }}
                                        onMouseDown={(e) => e.preventDefault()}
                                        onMouseUp={(e) => e.preventDefault()}
                                      >
                                        {minuteLabel}
                                      </Box>
                                    )
                                  })}
                                </Box>
                              </Box>
                            ))}
                          </Box>
                        </Box>
                      ))}
                    </Box>
                  </Box>

                  <Group gap="xs" mt="md">
                    <Button size="sm" variant="default" onClick={() => setRcStep(4)}>
                      {t('common.back', 'Back')}
                    </Button>
                    <Button size="sm" color="grape" onClick={computeStopTimes} disabled={rcTrips.length === 0 || rcShapePoints.length < 2 || rcOrderedStops.length < 2}>
                      {t('routeCreator.schedule.generate', 'Generate Schedule')}
                    </Button>
                    <Button size="sm" variant="outline" color="green" onClick={handleExportGTFS} disabled={rcTrips.length === 0}>
                      {t('routeCreator.schedule.export', 'Export GTFS txt')}
                    </Button>
                  </Group>

                </Paper>
              )}

              {rcStep === 6 && (
                <Paper p="md" shadow="sm" withBorder style={{ width: '100%', alignSelf: 'stretch', maxWidth: '100%' }}>
                  <Group justify="space-between" mb="xs" align="flex-start" gap="xs" wrap="wrap">
                    <div>
                      <Text fw={600}>{t('routeCreator.stopTimes.title', 'Stop Times')}</Text>
                      <Text size="sm" c="dimmed">
                        {t('routeCreator.stopTimes.instructions', 'Review and edit departure/arrival times for each stop and trip.')}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {t('routeCreator.stopTimes.tips', 'Tip: Use Tab / Shift+Tab to move across cells. Stop names stay pinned while you scroll horizontally.')}
                      </Text>
                    </div>
                    <Group gap={8}>
                      <Badge color="grape" variant="dot">
                        {t('routeCreator.schedule.trips', { defaultValue: '{{count}} trips', count: rcTrips.length } as any)}
                      </Badge>
                      <Badge color="gray" variant="light">
                        {rcOrderedStops.length} {t('routeCreator.stopTimes.stops', 'stops')}
                      </Badge>
                    </Group>
                  </Group>

                  {rcTrips.length === 0 || rcOrderedStops.length === 0 ? (
                    <Alert color="yellow" variant="light" mb="md">
                      {t('routeCreator.stopTimes.empty', 'No trips or stops available. Go back to schedule to generate times.')}
                    </Alert>
                  ) : (
                    <ScrollArea h={360} type="auto" scrollbarSize={10}>
                      <Table
                        stickyHeader
                        striped
                        withRowBorders={false}
                        highlightOnHover
                        style={{ tableLayout: 'fixed', minWidth: rcStopTimesMinWidth }}
                      >
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th
                              style={{
                                position: 'sticky',
                                left: 0,
                                zIndex: 3,
                                background: 'var(--mantine-color-white)',
                              }}
                            >
                              {t('routeCreator.schedule.stop', 'Stop')}
                            </Table.Th>
                            {rcTrips.map((trip) => (
                              <Table.Th key={trip} style={{ textAlign: 'center' }}>
                                <Badge variant="light" color="gray">{trip}</Badge>
                              </Table.Th>
                            ))}
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {rcOrderedStops.map((stop, idx) => (
                            <Table.Tr key={`${stop.stop_id}-${idx}`}>
                              <Table.Td
                                style={{
                                  position: 'sticky',
                                  left: 0,
                                  zIndex: 2,
                                  background: 'var(--mantine-color-white)',
                                  boxShadow: '8px 0 8px -8px rgba(0,0,0,0.08)',
                                  minWidth: 180,
                                }}
                              >
                                <Text fw={600} size="sm">{stop.stop_name}</Text>
                                <Text size="xs" c="dimmed">{stop.stop_id}</Text>
                              </Table.Td>
                              {rcTrips.map((trip) => (
                                <Table.Td key={`${trip}-${idx}`} style={{ padding: '6px' }}>
                                  <TextInput
                                    size="xs"
                                    value={(rcStopTimesTable[trip] || [])[idx] || ''}
                                    onChange={(e) => handleStopTimeChange(trip, idx, e.currentTarget.value)}
                                    placeholder="HH:MM:SS"
                                    styles={{
                                      input: {
                                        textAlign: 'center',
                                        fontFamily: 'monospace',
                                      },
                                    }}
                                  />
                                </Table.Td>
                              ))}
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </ScrollArea>
                  )}

                  <Group gap="xs" mt="md">
                    <Button size="sm" variant="default" onClick={() => setRcStep(5)}>
                      {t('common.back', 'Back')}
                    </Button>
                    <Button size="sm" variant="light" color="gray" onClick={computeStopTimes} disabled={rcTrips.length === 0}>
                      {t('routeCreator.stopTimes.regenerate', 'Recompute')}
                    </Button>
                    <Button size="sm" variant="outline" color="green" onClick={handleExportGTFS} disabled={rcTrips.length === 0 || rcOrderedStops.length === 0}>
                      {t('routeCreator.schedule.export', 'Export GTFS txt')}
                    </Button>
                    <Button size="sm" color="green" onClick={() => setRcStep(7)} disabled={rcTrips.length === 0 || rcOrderedStops.length === 0}>
                      {t('routeCreator.nextReview', 'Next: Review & Create')}
                    </Button>
                  </Group>
                </Paper>
              )}

              {/* Step 7: Export to Feed (Mobile) */}
              {rcStep === 7 && (
                <FinalExport
                  routeId={rcRouteId}
                  routeShortName={rcRouteShortName}
                  routeColor={rcRouteColor}
                  orderedStops={rcOrderedStops}
                  newStops={rcNewStops}
                  shapePoints={rcShapePoints}
                  trips={rcTrips}
                  stopTimesTable={rcStopTimesTable}
                  feedId={selectedFeed ? parseInt(selectedFeed) : null}
                  calendars={calendars}
                  selectedServiceIds={rcSelectedServiceIds}
                  onBack={() => setRcStep(6)}
                  onExportComplete={() => {
                    handleToggleRouteCreator(false)
                    notifications.show({
                      title: t('common.success', 'Success'),
                      message: t('routeCreator.export.taskStarted', 'Export task started. Check Task Manager for progress.'),
                      color: 'green',
                    })
                  }}
                />
              )}
            </Stack>
          </Box>
        )}

        {/* Route Creator: Stop Modal (for both in-memory and existing stops) */}
        <Modal
          opened={rcNewStopModalOpened}
          onClose={() => {
            setRcNewStopModalOpened(false)
            setRcPendingStopPosition(null)
            setRcEditingStopId(null)
            setRcEditingExistingStop(null)
          }}
          title={rcEditingExistingStop ? 'Edit Stop Sequence' : (rcEditingStopId ? 'Edit In-Memory Stop' : 'New Route Creator Stop')}
          size="md"
          zIndex={4100}
          overlayProps={{ zIndex: 4090 }}
        >
          <form onSubmit={rcNewStopForm.onSubmit(handleRouteCreatorNewStopSubmit)}>
            <Stack>
              {rcEditingExistingStop && (
                <Text size="sm" c="dimmed" fs="italic">
                  This is an existing stop. Only the sequence can be modified.
                </Text>
              )}
              <TextInput
                label="Stop ID"
                required
                placeholder="RC_STOP_1"
                {...rcNewStopForm.getInputProps('stop_id')}
                disabled={!!rcEditingStopId || !!rcEditingExistingStop}
              />
              <TextInput
                label="Stop Code"
                placeholder="Optional"
                {...rcNewStopForm.getInputProps('stop_code')}
                disabled={!!rcEditingExistingStop}
              />
              <TextInput
                label="Stop Name"
                required
                placeholder={geocodingLoading ? "Loading address..." : "New Stop"}
                {...rcNewStopForm.getInputProps('stop_name')}
                disabled={!!rcEditingExistingStop}
                rightSection={
                  !rcEditingExistingStop ? (
                    <Tooltip label={t('stops.suggestName', 'Suggest name from location')}>
                      <ActionIcon
                        variant="subtle"
                        loading={geocodingLoading}
                        onClick={async () => {
                          if (rcPendingStopPosition) {
                            const suggestedName = await fetchAddressSuggestion(rcPendingStopPosition[0], rcPendingStopPosition[1])
                            if (suggestedName) {
                              rcNewStopForm.setFieldValue('stop_name', suggestedName)
                            }
                          }
                        }}
                      >
                        <IconWand size={16} />
                      </ActionIcon>
                    </Tooltip>
                  ) : null
                }
              />
              <NumberInput
                label="Sequence"
                placeholder="e.g. 4"
                min={1}
                allowNegative={false}
                allowDecimal={false}
                {...rcNewStopForm.getInputProps('sequence')}
              />
              {rcPendingStopPosition && (
                <SimpleGrid cols={2}>
                  <NumberInput label="Latitude" value={rcPendingStopPosition[0]} readOnly decimalScale={8} />
                  <NumberInput label="Longitude" value={rcPendingStopPosition[1]} readOnly decimalScale={8} />
                </SimpleGrid>
              )}
              <Group justify="space-between" mt="md">
                {rcEditingStopId && (
                  <Button variant="outline" color="red" onClick={handleRcDeleteInMemoryStop}>
                    {t('common.delete', 'Delete')}
                  </Button>
                )}
                <Group gap="xs" style={{ marginLeft: rcEditingStopId ? undefined : 'auto' }}>
                  <Button
                    variant="default"
                    onClick={() => {
                      setRcNewStopModalOpened(false)
                      setRcPendingStopPosition(null)
                      setRcEditingExistingStop(null)
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit">
                    {rcEditingExistingStop ? 'Update Sequence' : (rcEditingStopId ? 'Update Stop' : 'Add Stop')}
                  </Button>
                </Group>
              </Group>
            </Stack>
          </form>
        </Modal>

        {/* Create Stop Modal */}
        <Modal
          opened={createStopModalOpened}
          onClose={() => {
            setCreateStopModalOpened(false)
            setNewStopPosition(null)
          }}
          title={t('stops.newStop', 'Create New Stop')}
          size="lg"
          zIndex={4000}
          overlayProps={{ zIndex: 3990 }}
        >
          <form onSubmit={createStopForm.onSubmit(handleCreateStop)}>
            <Stack>
              <TextInput
                label={t('stops.stopId', 'Stop ID')}
                placeholder="STOP001"
                required
                {...createStopForm.getInputProps('stop_id')}
              />
              <TextInput
                label={t('stops.stopCode', 'Stop Code')}
                {...createStopForm.getInputProps('stop_code')}
              />
              <TextInput
                label={t('stops.stopName', 'Stop Name')}
                required
                placeholder={geocodingLoading ? t('stops.loadingAddress', 'Loading address...') : undefined}
                {...createStopForm.getInputProps('stop_name')}
                rightSection={
                  <Tooltip label={t('stops.suggestName', 'Suggest name from location')}>
                    <ActionIcon
                      variant="subtle"
                      loading={geocodingLoading}
                      onClick={async () => {
                        if (newStopPosition) {
                          const suggestedName = await fetchAddressSuggestion(newStopPosition[0], newStopPosition[1])
                          if (suggestedName) {
                            createStopForm.setFieldValue('stop_name', suggestedName)
                          }
                        }
                      }}
                    >
                      <IconWand size={16} />
                    </ActionIcon>
                  </Tooltip>
                }
              />
              <Textarea
                label={t('common.description', 'Description')}
                {...createStopForm.getInputProps('stop_desc')}
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
                {...createStopForm.getInputProps('location_type')}
              />
              <Select
                label={t('stops.wheelchairBoarding', 'Wheelchair Boarding')}
                data={WHEELCHAIR_BOARDING}
                {...createStopForm.getInputProps('wheelchair_boarding')}
              />
              <Group justify="flex-end" mt="md">
                <Button
                  variant="default"
                  onClick={() => {
                    setCreateStopModalOpened(false)
                    setNewStopPosition(null)
                  }}
                >
                  {t('common.cancel', 'Cancel')}
                </Button>
                <Button type="submit">{t('common.create', 'Create')}</Button>
              </Group>
            </Stack>
          </form>
        </Modal>

        {/* Edit Stop Modal */}
        <Modal
          opened={editStopModalOpened}
          onClose={() => {
            setEditStopModalOpened(false)
            setEditingStop(null)
          }}
          title={`${t('stops.editStop', 'Edit Stop')}: ${editingStop?.stop_id}`}
          size="lg"
          zIndex={4000}
          overlayProps={{ zIndex: 3990 }}
        >
          <form onSubmit={editStopForm.onSubmit(handleUpdateStop)}>
            <Stack>
              <TextInput
                label={t('stops.stopId', 'Stop ID')}
                value={editingStop?.stop_id || ''}
                disabled
              />
              <TextInput
                label={t('stops.stopCode', 'Stop Code')}
                {...editStopForm.getInputProps('stop_code')}
              />
              <TextInput
                label={t('stops.stopName', 'Stop Name')}
                required
                {...editStopForm.getInputProps('stop_name')}
                rightSection={
                  <Tooltip label={t('stops.suggestName', 'Suggest name from location')}>
                    <ActionIcon
                      variant="subtle"
                      loading={geocodingLoading}
                      onClick={async () => {
                        const lat = editStopForm.values.stop_lat
                        const lon = editStopForm.values.stop_lon
                        if (lat && lon) {
                          const suggestedName = await fetchAddressSuggestion(lat, lon)
                          if (suggestedName) {
                            editStopForm.setFieldValue('stop_name', suggestedName)
                          } else {
                            notifications.show({
                              title: t('common.error', 'Error'),
                              message: t('stops.geocodingFailed', 'Could not suggest a name for this location'),
                              color: 'orange',
                            })
                          }
                        }
                      }}
                    >
                      <IconWand size={16} />
                    </ActionIcon>
                  </Tooltip>
                }
              />
              <Textarea
                label={t('common.description', 'Description')}
                {...editStopForm.getInputProps('stop_desc')}
                minRows={2}
              />
              <SimpleGrid cols={2}>
                <NumberInput
                  label={t('stops.latitude', 'Latitude')}
                  required
                  decimalScale={8}
                  step={0.000001}
                  {...editStopForm.getInputProps('stop_lat')}
                />
                <NumberInput
                  label={t('stops.longitude', 'Longitude')}
                  required
                  decimalScale={8}
                  step={0.000001}
                  {...editStopForm.getInputProps('stop_lon')}
                />
              </SimpleGrid>
              <Select
                label={t('stops.locationType', 'Location Type')}
                data={LOCATION_TYPES}
                {...editStopForm.getInputProps('location_type')}
              />
              <Select
                label={t('stops.wheelchairBoarding', 'Wheelchair Boarding')}
                data={WHEELCHAIR_BOARDING}
                {...editStopForm.getInputProps('wheelchair_boarding')}
              />
              <Group justify="flex-end" mt="md">
                <Button
                  variant="default"
                  onClick={() => {
                    setEditStopModalOpened(false)
                    setEditingStop(null)
                  }}
                >
                  {t('common.cancel', 'Cancel')}
                </Button>
                <Button type="submit">{t('common.update', 'Update')}</Button>
              </Group>
            </Stack>
          </form>
        </Modal>

        {/* Route Creator - Calendar Creation Modal */}
        <CalendarFormModal
          opened={rcCalendarModalOpened}
          onClose={closeRcCalendarModal}
          feedId={selectedFeed ? parseInt(selectedFeed) : null}
          zIndex={100002}
          onSuccess={(newServiceId) => {
            // Refresh calendars and auto-select the new one
            loadCalendars()
            setRcSelectedServiceIds(prev => [...prev, newServiceId])
          }}
        />
      </Stack>
    </Container>
  )
}
