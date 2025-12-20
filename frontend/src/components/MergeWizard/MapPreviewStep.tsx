import { useState, useEffect, useMemo } from 'react'
import { Stack, Alert, Text, Group, Badge, Paper, LoadingOverlay } from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap, Polyline } from 'react-leaflet'
import { LatLngBounds } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { AgencyMergeValidationResult } from '../../lib/agency-operations-api'
import { stopsApi, Stop, shapesApi } from '../../lib/gtfs-api'
import { notifications } from '@mantine/notifications'

interface Feed {
  id: number
  agency_id: number
  name: string
  description?: string
}

interface Agency {
  id: number
  name: string
  slug: string
  feeds: Feed[]
}

interface MapPreviewStepProps {
  agencies: Agency[]
  selectedFeedIds: number[]
  validationResult: AgencyMergeValidationResult
}

interface ShapeWithPoints {
  shape_id: string
  points: {
    lat: number
    lon: number
    sequence: number
  }[]
}

// Component to fit map bounds to all stops and shapes
function FitBounds({ stops, shapes, shouldFit }: { stops: Stop[]; shapes: ShapeWithPoints[]; shouldFit: boolean }) {
  const map = useMap()

  useEffect(() => {
    if (shouldFit && (stops.length > 0 || shapes.length > 0)) {
      try {
        const bounds = new LatLngBounds([])

        stops.forEach(stop => bounds.extend([Number(stop.stop_lat), Number(stop.stop_lon)]))
        shapes.forEach(shape =>
          shape.points.forEach(point => bounds.extend([point.lat, point.lon]))
        )

        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 })
        }
      } catch (e) {
        console.error('Error fitting bounds:', e)
      }
    }
  }, [stops, shapes, shouldFit, map])

  return null
}

export default function MapPreviewStep({
  agencies,
  selectedFeedIds,
  validationResult,
}: MapPreviewStepProps) {
  const [loading, setLoading] = useState(false)
  const [stops, setStops] = useState<Stop[]>([])
  const [stopsByFeed, setStopsByFeed] = useState<Record<number, Stop[]>>({})
  const [shapesByFeed, setShapesByFeed] = useState<Record<number, ShapeWithPoints[]>>({})
  const [mapReady, setMapReady] = useState(false)

  // Generate colors for different feeds
  const feedColors = useMemo(() => selectedFeedIds.reduce((acc, feedId, index) => {
    const colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899']
    acc[feedId] = colors[index % colors.length]
    return acc
  }, {} as Record<number, string>), [selectedFeedIds])

  useEffect(() => {
    loadData()
  }, [selectedFeedIds])

  const loadData = async () => {
    if (selectedFeedIds.length === 0) return

    setLoading(true)
    const newStops: Stop[] = []
    const newStopsByFeed: Record<number, Stop[]> = {}
    const newShapesByFeed: Record<number, ShapeWithPoints[]> = {}

    try {
      await Promise.all(selectedFeedIds.map(async (feedId) => {
        try {
          // Load stops (limit to 200 to improve perf with shapes)
          const stopsResponse = await stopsApi.list(feedId, { limit: 200 })
          if (stopsResponse.items) {
            newStops.push(...stopsResponse.items)
            newStopsByFeed[feedId] = stopsResponse.items
          }

          // Load shapes (limit distinct shapes to 20)
          const shapesResponse = await shapesApi.getByShapeId({
            feed_id: feedId,
            limit: 20
          })
          if (shapesResponse.items) {
            // @ts-ignore - API returns items with correct structure but type might not match exactly what we defined locally
            newShapesByFeed[feedId] = shapesResponse.items
          }
        } catch (error) {
          console.error(`Failed to load data for feed ${feedId}`, error)
        }
      }))

      setStops(newStops)
      setStopsByFeed(newStopsByFeed)
      setShapesByFeed(newShapesByFeed)
    } catch (error) {
      console.error('Error loading map data:', error)
      notifications.show({
        title: 'Error loading map data',
        message: 'Could not load data for preview',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const allShapes = Object.values(shapesByFeed).flat()

  return (
    <Stack gap="md">
      <Alert icon={<IconInfoCircle />} title="Merge Preview" color="blue">
        Preview of the feeds to be merged. The map shows a sample of stops and routes from each feed to verify spatial alignment.
      </Alert>

      <Group>
        <Text size="sm" fw={500}>
          Preview Summary:
        </Text>
        <Badge variant="light">{validationResult.total_stops.toLocaleString()} stops</Badge>
        <Badge variant="light">{validationResult.total_routes.toLocaleString()} routes</Badge>
        <Badge variant="light">{validationResult.total_trips.toLocaleString()} trips</Badge>
        <Badge variant="light">{validationResult.total_shapes.toLocaleString()} shapes</Badge>
      </Group>

      <Paper withBorder p={0} style={{ position: 'relative', height: 500, overflow: 'hidden' }}>
        <LoadingOverlay visible={loading} zIndex={1000} overlayProps={{ radius: 'sm', blur: 2 }} />

        <MapContainer
          center={[0, 0]}
          zoom={2}
          style={{ height: '100%', width: '100%' }}
          whenReady={() => setMapReady(true)}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {selectedFeedIds.map(feedId => (
            <FieldLayer
              key={feedId}
              stops={stopsByFeed[feedId] || []}
              shapes={shapesByFeed[feedId] || []}
              color={feedColors[feedId]}
              mapReady={mapReady}
            />
          ))}

          <FitBounds
            stops={stops}
            shapes={allShapes}
            shouldFit={mapReady && !loading && (stops.length > 0 || allShapes.length > 0)}
          />
        </MapContainer>
      </Paper>

      <Group gap="xs">
        <Text size="sm" fw={500}>
          Selected Feeds:
        </Text>
        {selectedFeedIds.map((feedId) => {
          const agency = agencies.find((a) => a.feeds.some((f) => f.id === feedId))
          const feed = agency?.feeds.find((f) => f.id === feedId)
          if (!feed) return null

          return (
            <Badge
              key={feedId}
              variant="dot"
              color={feedColors[feedId]}
            >
              {feed.name}
            </Badge>
          )
        })}
      </Group>
    </Stack>
  )
}

function FieldLayer({ stops, shapes, color, mapReady }: { stops: Stop[], shapes: ShapeWithPoints[], color: string, mapReady: boolean }) {
  if (!mapReady) return null

  return (
    <>
      {shapes.map(shape => (
        <Polyline
          key={`${shape.shape_id}`}
          positions={shape.points.map(p => [p.lat, p.lon])}
          pathOptions={{
            color: color,
            opacity: 0.6,
            weight: 3
          }}
        />
      ))}
      {stops.map(stop => (
        <CircleMarker
          key={`${stop.feed_id}-${stop.stop_id}`}
          center={[stop.stop_lat, stop.stop_lon]}
          radius={3}
          pathOptions={{
            color: color,
            fillColor: color,
            fillOpacity: 0.8,
            weight: 1
          }}
        >
          <Popup>
            <Text size="xs" fw={700}>{stop.stop_name}</Text>
            <Text size="xs" c="dimmed">ID: {stop.stop_id}</Text>
          </Popup>
        </CircleMarker>
      ))}
    </>
  )
}
