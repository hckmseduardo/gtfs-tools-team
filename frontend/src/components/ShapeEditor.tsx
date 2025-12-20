import { useState, useCallback, useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Polyline, Marker, CircleMarker, Popup, useMapEvents, useMap } from 'react-leaflet'
import { Modal, TextInput, Button, Group, Stack, Select, Text, Badge, ActionIcon, Tooltip, Paper, Divider, Switch, Textarea, NumberInput, SimpleGrid, Code } from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { IconPlus, IconTrash, IconDeviceFloppy, IconX, IconRoute, IconMapPin, IconRoute2, IconWifi, IconWifiOff, IconBus } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { shapesApi, routesApi, routingApi, stopsApi, tripsApi, type ShapeWithPoints, type ShapeBulkCreatePoint, type Route, type TransitMode, type Stop } from '../lib/gtfs-api'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Location type options
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

// Custom icon for shape points
const createPointIcon = (color: string, selected: boolean = false) => {
  const size = selected ? 14 : 10
  return L.divIcon({
    className: 'shape-point-marker',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background-color: ${color};
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

// Custom icon for stops
const createStopIcon = (editMode: boolean) => {
  const size = editMode ? 12 : 10
  const color = editMode ? '#f59e0b' : '#1d4ed8'
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

// Custom icon for waypoints (numbered)
const createWaypointIcon = (number: number) => {
  return L.divIcon({
    className: 'waypoint-marker',
    html: `<div style="
      width: 24px;
      height: 24px;
      background-color: #8b5cf6;
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-size: 12px;
      font-weight: bold;
    ">${number}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

interface ShapeEditorProps {
  center: [number, number]
  zoom: number
  feedId: number
  editMode: boolean
  onShapeUpdated?: () => void
}

interface EditablePoint {
  lat: number
  lon: number
  sequence: number
  isNew?: boolean
}

interface TripShape {
  shape_id: string
  route_id: string
  route_short_name: string
  route_color?: string
}

// Component to handle map clicks for adding points
function MapClickHandler({
  onMapClick,
  onWaypointClick,
  editMode,
  isAddingPoints,
  isWaypointMode
}: {
  onMapClick: (lat: number, lon: number) => void
  onWaypointClick: (lat: number, lon: number) => void
  editMode: boolean
  isAddingPoints: boolean
  isWaypointMode: boolean
}) {
  useMapEvents({
    click: (e) => {
      if (isWaypointMode) {
        onWaypointClick(e.latlng.lat, e.latlng.lng)
      } else if (editMode && isAddingPoints) {
        onMapClick(e.latlng.lat, e.latlng.lng)
      }
    },
  })
  return null
}

// Component to fit map to shape bounds
function FitToBounds({ points, trigger }: { points: EditablePoint[], trigger: string | null }) {
  const map = useMap()

  useEffect(() => {
    if (points.length > 1) {
      const bounds = L.latLngBounds(points.map(p => [p.lat, p.lon]))
      map.fitBounds(bounds, { padding: [50, 50] })
    } else if (points.length === 1) {
      map.setView([points[0].lat, points[0].lon], 15)
    }
  }, [trigger])

  return null
}

// Clickable polyline segment component
function ClickablePolyline({
  positions,
  editMode,
  onSegmentClick,
  color,
  weight,
}: {
  positions: [number, number][]
  editMode: boolean
  onSegmentClick: (segmentIndex: number, latlng: L.LatLng) => void
  color: string
  weight: number
}) {
  const polylineRef = useRef<L.Polyline>(null)
  const map = useMap()

  useEffect(() => {
    const polyline = polylineRef.current
    if (polyline && editMode && map) {
      polyline.on('click', (e: L.LeafletMouseEvent) => {
        // Find which segment was clicked using projected coordinates
        const clickedLatLng = e.latlng
        const clickedPoint = map.latLngToLayerPoint(clickedLatLng)
        let minDist = Infinity
        let closestSegment = 0

        for (let i = 0; i < positions.length - 1; i++) {
          const p1LatLng = L.latLng(positions[i])
          const p2LatLng = L.latLng(positions[i + 1])

          // Convert to projected pixel coordinates
          const p1 = map.latLngToLayerPoint(p1LatLng)
          const p2 = map.latLngToLayerPoint(p2LatLng)

          // Calculate distance from click to line segment in pixel space
          const dist = distanceToSegmentPixels(clickedPoint, p1, p2)
          if (dist < minDist) {
            minDist = dist
            closestSegment = i
          }
        }

        onSegmentClick(closestSegment, clickedLatLng)
        L.DomEvent.stopPropagation(e)
      })

      return () => {
        polyline.off('click')
      }
    }
  }, [editMode, positions, onSegmentClick, map])

  return (
    <Polyline
      ref={polylineRef}
      positions={positions}
      pathOptions={{
        color,
        weight,
        opacity: 0.8,
      }}
    />
  )
}

// Helper function to calculate distance from point to line segment in pixel coordinates
function distanceToSegmentPixels(p: L.Point, v: L.Point, w: L.Point): number {
  const dx = w.x - v.x
  const dy = w.y - v.y
  const l2 = dx * dx + dy * dy

  if (l2 === 0) {
    // Segment is a point
    const pdx = p.x - v.x
    const pdy = p.y - v.y
    return Math.sqrt(pdx * pdx + pdy * pdy)
  }

  // Calculate projection parameter t (0 <= t <= 1)
  let t = ((p.x - v.x) * dx + (p.y - v.y) * dy) / l2
  t = Math.max(0, Math.min(1, t))

  // Find the projection point on the segment
  const projX = v.x + t * dx
  const projY = v.y + t * dy

  // Return distance from p to projection
  const distX = p.x - projX
  const distY = p.y - projY
  return Math.sqrt(distX * distX + distY * distY)
}

export default function ShapeEditor({
  center,
  zoom,
  feedId,
  editMode,
  onShapeUpdated,
}: ShapeEditorProps) {
  const { t } = useTranslation()
  const [shapes, setShapes] = useState<ShapeWithPoints[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [tripShapes, setTripShapes] = useState<TripShape[]>([])
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null)
  const [editablePoints, setEditablePoints] = useState<EditablePoint[]>([])
  const [isAddingPoints, setIsAddingPoints] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [loading, setLoading] = useState(false)
  const [shapesLoading, setShapesLoading] = useState(false)
  const [routesLoading, setRoutesLoading] = useState(false)
  const [createModalOpened, setCreateModalOpened] = useState(false)
  const [selectedPointIndex, setSelectedPointIndex] = useState<number | null>(null)
  const [fitBoundsTrigger, setFitBoundsTrigger] = useState<string | null>(null)

  // Routing state
  const [routingAvailable, setRoutingAvailable] = useState<boolean | null>(null)
  const [isSnapping, setIsSnapping] = useState(false)
  const [isAutoRouting, setIsAutoRouting] = useState(false)
  const [selectedMode, setSelectedMode] = useState<TransitMode>('bus')
  const [waypoints, setWaypoints] = useState<EditablePoint[]>([])
  const [isWaypointMode, setIsWaypointMode] = useState(false)

  // Stops overlay state
  const [showStops, setShowStops] = useState(false)
  const [stops, setStops] = useState<Stop[]>([])
  const [stopsLoading, setStopsLoading] = useState(false)
  const [editingStop, setEditingStop] = useState<Stop | null>(null)
  const [editStopModalOpened, setEditStopModalOpened] = useState(false)

  const createForm = useForm({
    initialValues: {
      shape_id: '',
    },
    validate: {
      shape_id: (value) => (!value ? 'Shape ID is required' : null),
    },
  })

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

  // Check routing service availability on mount
  useEffect(() => {
    routingApi.checkHealth()
      .then(result => setRoutingAvailable(result.available))
      .catch(() => setRoutingAvailable(false))
  }, [])

  // Load stops when toggle is enabled
  useEffect(() => {
    if (showStops && feedId && stops.length === 0) {
      setStopsLoading(true)
      stopsApi.list({ feed_id: feedId, limit: 10000 })
        .then(response => {
          setStops(response.items || [])
        })
        .catch(error => {
          console.error('Failed to load stops:', error)
          notifications.show({
            title: t('common.error'),
            message: t('shapeEditor.loadStopsError'),
            color: 'red',
          })
        })
        .finally(() => setStopsLoading(false))
    }
  }, [showStops, feedId])

  // Load routes and shapes
  useEffect(() => {
    if (feedId) {
      loadRoutes()
      loadShapes()
      loadTripShapes()
    }
  }, [feedId])

  // Load shape points when shape is selected
  useEffect(() => {
    if (selectedShapeId && shapes.length > 0) {
      const shape = shapes.find(s => s.shape_id === selectedShapeId)
      if (shape) {
        setEditablePoints(
          shape.points.map(p => ({
            lat: p.lat,
            lon: p.lon,
            sequence: p.sequence,
          }))
        )
        setHasChanges(false)
        setFitBoundsTrigger(selectedShapeId)
      }
    } else {
      setEditablePoints([])
    }
  }, [selectedShapeId, shapes])

  // Filter shapes when route changes
  // Note: If tripShapes is empty (no route-shape mapping available), show all shapes
  const filteredShapes = selectedRouteId && tripShapes.length > 0
    ? shapes.filter(s => {
        const tripShape = tripShapes.find(ts => ts.shape_id === s.shape_id)
        return tripShape && tripShape.route_id === selectedRouteId
      })
    : shapes

  // Get route info for selected shape
  const selectedShapeRouteInfo = selectedShapeId
    ? tripShapes.find(ts => ts.shape_id === selectedShapeId)
    : null

  const loadRoutes = async () => {
    setRoutesLoading(true)
    try {
      const response = await routesApi.list({ feed_id: feedId, limit: 1000 })
      setRoutes(response.items || [])
    } catch (error) {
      console.error('Failed to load routes:', error)
    } finally {
      setRoutesLoading(false)
    }
  }

  const loadShapes = async () => {
    setShapesLoading(true)
    try {
      const response = await shapesApi.getByShapeId({ feed_id: feedId })
      setShapes(response.items || [])
    } catch (error) {
      console.error('Failed to load shapes:', error)
      notifications.show({
        title: t('common.error'),
        message: t('shapeEditor.loadShapesError'),
        color: 'red',
      })
    } finally {
      setShapesLoading(false)
    }
  }

  const loadTripShapes = async () => {
    try {
      // Get trips with their shape_id and route info
      const response = await tripsApi.listWithRoutes(feedId, { limit: 10000 })
      const trips = response.items || []

      // Build unique shape -> route mapping
      const shapeRouteMap = new Map<string, TripShape>()
      for (const trip of trips) {
        // Use shape_id (the GTFS identifier string)
        const shapeId = trip.shape_id
        if (shapeId && !shapeRouteMap.has(shapeId)) {
          shapeRouteMap.set(shapeId, {
            shape_id: shapeId,
            route_id: trip.route_id || '',  // Use GTFS route_id
            route_short_name: trip.route_short_name || '',
            route_color: trip.route_color,
          })
        }
      }

      setTripShapes(Array.from(shapeRouteMap.values()))
    } catch (error) {
      console.error('Failed to load trip shapes:', error)
    }
  }

  const handleMapClick = useCallback((lat: number, lon: number) => {
    if (!isAddingPoints) return

    setEditablePoints(prev => {
      const newSequence = prev.length > 0 ? Math.max(...prev.map(p => p.sequence)) + 1 : 0
      return [...prev, { lat, lon, sequence: newSequence, isNew: true }]
    })
    setHasChanges(true)
  }, [isAddingPoints])

  const handleWaypointClick = useCallback((lat: number, lon: number) => {
    setWaypoints(prev => [
      ...prev,
      { lat, lon, sequence: prev.length }
    ])
  }, [])

  // Snap shape to road network using Valhalla
  const handleSnapToRoad = async () => {
    if (!selectedShapeId || !routingAvailable || editablePoints.length < 2) return

    setIsSnapping(true)
    try {
      const result = await routingApi.snapToRoad({
        feed_id: feedId,
        shape_id: selectedShapeId,
        mode: selectedMode,
      })

      console.log('Snap-to-road result:', result)

      if (result.success && result.points && result.points.length > 0) {
        const newPoints = result.points.map((p, idx) => ({
          lat: p.lat,
          lon: p.lon,
          sequence: idx,
          isNew: true,
        }))
        console.log('Setting snapped points:', newPoints.length)
        setEditablePoints(newPoints)
        setHasChanges(true)

        const confidenceText = result.confidence
          ? ` (${Math.round(result.confidence * 100)}% confidence)`
          : ''

        notifications.show({
          title: t('shapeEditor.shapeSnapped'),
          message: t('shapeEditor.snapPointsAligned', { count: result.point_count }) + confidenceText,
          color: 'green',
        })
      } else {
        notifications.show({
          title: t('shapeEditor.snapIssue'),
          message: result.message || t('shapeEditor.noSnappedPoints'),
          color: 'orange',
        })
      }
    } catch (error: any) {
      console.error('Snap-to-road error:', error)
      const message = error?.response?.data?.detail || t('shapeEditor.snapFailed')
      notifications.show({
        title: t('shapeEditor.snapFailed'),
        message,
        color: 'red',
      })
    } finally {
      setIsSnapping(false)
    }
  }

  // Generate route from waypoints using Valhalla
  const handleAutoRoute = async () => {
    if (!selectedShapeId || waypoints.length < 2 || !routingAvailable) return

    setIsAutoRouting(true)
    try {
      const result = await routingApi.autoRoute({
        feed_id: feedId,
        shape_id: selectedShapeId,
        waypoints: waypoints.map(w => ({ lat: w.lat, lon: w.lon })),
        mode: selectedMode,
      })

      console.log('Auto-route result:', result)

      if (result.success && result.points && result.points.length > 0) {
        const newPoints = result.points.map((p, idx) => ({
          lat: p.lat,
          lon: p.lon,
          sequence: idx,
          isNew: true,
        }))
        console.log('Setting new editable points:', newPoints.length)
        setEditablePoints(newPoints)
        setHasChanges(true)
        // Keep waypoints visible briefly, then clear
        setTimeout(() => {
          setWaypoints([])
          setIsWaypointMode(false)
        }, 500)

        notifications.show({
          title: t('shapeEditor.routeGenerated'),
          message: t('shapeEditor.routeGeneratedDetails', { points: result.point_count, waypoints: waypoints.length, distance: Math.round(result.distance_meters) }),
          color: 'green',
        })
      } else {
        notifications.show({
          title: t('shapeEditor.routingIssue'),
          message: result.message || t('shapeEditor.noRoutePoints'),
          color: 'orange',
        })
      }
    } catch (error: any) {
      console.error('Auto-route error:', error)
      const message = error?.response?.data?.detail || t('shapeEditor.routingFailed')
      notifications.show({
        title: t('shapeEditor.routingFailed'),
        message,
        color: 'red',
      })
    } finally {
      setIsAutoRouting(false)
    }
  }

  const handlePointDrag = useCallback((index: number, newLat: number, newLon: number) => {
    setEditablePoints(prev => {
      const updated = [...prev]
      updated[index] = { ...updated[index], lat: newLat, lon: newLon }
      return updated
    })
    setHasChanges(true)
  }, [])

  const handleDeletePoint = (index: number) => {
    setEditablePoints(prev => {
      const updated = prev.filter((_, i) => i !== index)
      return updated.map((p, i) => ({ ...p, sequence: i }))
    })
    setSelectedPointIndex(null)
    setHasChanges(true)
  }

  const handleSegmentClick = useCallback((segmentIndex: number, latlng: L.LatLng) => {
    if (!editMode) return

    // Insert a new point after the segment's first point
    setEditablePoints(prev => {
      const updated = [
        ...prev.slice(0, segmentIndex + 1),
        { lat: latlng.lat, lon: latlng.lng, sequence: segmentIndex + 1, isNew: true },
        ...prev.slice(segmentIndex + 1),
      ]
      return updated.map((p, i) => ({ ...p, sequence: i }))
    })
    setHasChanges(true)

    notifications.show({
      title: t('shapeEditor.pointAdded'),
      message: t('shapeEditor.pointInserted', { position: segmentIndex + 2 }),
      color: 'green',
      autoClose: 2000,
    })
  }, [editMode])

  const handleInsertPointAfter = (index: number) => {
    setEditablePoints(prev => {
      const current = prev[index]
      const next = prev[index + 1]

      let newLat = current.lat
      let newLon = current.lon + 0.0001

      if (next) {
        newLat = (current.lat + next.lat) / 2
        newLon = (current.lon + next.lon) / 2
      }

      const updated = [
        ...prev.slice(0, index + 1),
        { lat: newLat, lon: newLon, sequence: index + 1, isNew: true },
        ...prev.slice(index + 1),
      ]

      return updated.map((p, i) => ({ ...p, sequence: i }))
    })
    setHasChanges(true)
  }

  const handleSaveShape = async () => {
    if (!selectedShapeId || editablePoints.length < 2) {
      notifications.show({
        title: t('common.error'),
        message: t('shapeEditor.minPointsError'),
        color: 'red',
      })
      return
    }

    // Validate all points have valid numeric coordinates
    const invalidPoints = editablePoints.filter(
      p => typeof p.lat !== 'number' || typeof p.lon !== 'number' ||
           isNaN(p.lat) || isNaN(p.lon)
    )
    if (invalidPoints.length > 0) {
      notifications.show({
        title: t('common.error'),
        message: t('shapeEditor.invalidCoordinates', { count: invalidPoints.length }),
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      const points: ShapeBulkCreatePoint[] = editablePoints.map((p, index) => ({
        lat: Number(p.lat),
        lon: Number(p.lon),
        sequence: index,
      }))

      await shapesApi.bulkCreate({
        feed_id: feedId,
        shape_id: selectedShapeId,
        points,
      }, true)

      notifications.show({
        title: t('common.success'),
        message: t('shapeEditor.shapeSaved', { id: selectedShapeId }),
        color: 'green',
      })

      setHasChanges(false)
      await loadShapes()

      if (onShapeUpdated) {
        onShapeUpdated()
      }
    } catch (error: any) {
      let errorMessage = 'Failed to save shape'
      const detail = error?.response?.data?.detail
      if (typeof detail === 'string') {
        errorMessage = detail
      } else if (Array.isArray(detail)) {
        // Pydantic validation errors - include field location for debugging
        errorMessage = detail.map((e: any) => {
          const loc = e.loc ? e.loc.join('.') : ''
          const msg = e.msg || e.message || ''
          return loc ? `${loc}: ${msg}` : msg || JSON.stringify(e)
        }).join(', ')
      }
      console.error('Shape save error:', error?.response?.data)
      notifications.show({
        title: t('common.error'),
        message: errorMessage,
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleCreateShape = async (values: typeof createForm.values) => {
    if (shapes.some(s => s.shape_id === values.shape_id)) {
      notifications.show({
        title: t('common.error'),
        message: t('shapeEditor.shapeIdExists'),
        color: 'red',
      })
      return
    }

    const initialPoints: ShapeBulkCreatePoint[] = [
      { lat: center[0], lon: center[1], sequence: 0 }
    ]

    setLoading(true)
    try {
      await shapesApi.bulkCreate({
        feed_id: feedId,
        shape_id: values.shape_id,
        points: initialPoints,
      }, false)

      notifications.show({
        title: t('common.success'),
        message: t('shapeEditor.shapeCreated', { id: values.shape_id }),
        color: 'green',
      })

      setCreateModalOpened(false)
      createForm.reset()
      await loadShapes()
      setSelectedShapeId(values.shape_id)
      setIsAddingPoints(true)

      if (onShapeUpdated) {
        onShapeUpdated()
      }
    } catch (error: any) {
      let errorMessage = error?.response?.data?.detail
      if (typeof errorMessage !== 'string') {
        if (Array.isArray(errorMessage)) {
          errorMessage = errorMessage.map((e: any) => e.msg || e.message || JSON.stringify(e)).join(', ')
        } else {
          errorMessage = t('common.error')
        }
      }
      notifications.show({
        title: t('common.error'),
        message: errorMessage,
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteShape = async () => {
    if (!selectedShapeId) return

    if (!confirm(t('shapeEditor.confirmDeleteMessage', { id: selectedShapeId }))) {
      return
    }

    setLoading(true)
    try {
      await shapesApi.deleteByShapeId(selectedShapeId, feedId)

      notifications.show({
        title: t('common.success'),
        message: t('shapeEditor.shapeDeleted', { id: selectedShapeId }),
        color: 'green',
      })

      setSelectedShapeId(null)
      setEditablePoints([])
      await loadShapes()

      if (onShapeUpdated) {
        onShapeUpdated()
      }
    } catch (error: any) {
      let errorMessage = error?.response?.data?.detail
      if (typeof errorMessage !== 'string') {
        if (Array.isArray(errorMessage)) {
          errorMessage = errorMessage.map((e: any) => e.msg || e.message || JSON.stringify(e)).join(', ')
        } else {
          errorMessage = t('common.error')
        }
      }
      notifications.show({
        title: t('common.error'),
        message: errorMessage,
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleCancelChanges = () => {
    if (hasChanges && !confirm('Discard unsaved changes?')) {
      return
    }

    if (selectedShapeId) {
      const shape = shapes.find(s => s.shape_id === selectedShapeId)
      if (shape) {
        setEditablePoints(
          shape.points.map(p => ({
            lat: p.lat,
            lon: p.lon,
            sequence: p.sequence,
          }))
        )
      }
    }
    setHasChanges(false)
    setIsAddingPoints(false)
    setSelectedPointIndex(null)
  }

  // Stop editing handlers
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

      const response = await api.put(`/stops/${editingStop.id}`, updateData)

      notifications.show({
        title: t('common.success'),
        message: t('stops.updateSuccess', 'Stop updated successfully'),
        color: 'green',
      })

      setEditStopModalOpened(false)
      setEditingStop(null)

      // Refresh stops list
      const stopsResponse = await stopsApi.list({ feed_id: feedId, limit: 10000 })
      setStops(stopsResponse.items || [])
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
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

      await api.put(`/stops/${stop.id}`, updateData)

      notifications.show({
        title: t('common.success'),
        message: t('stops.positionUpdated', 'Stop position updated'),
        color: 'green',
        autoClose: 2000,
      })

      // Update local stops state
      setStops(prev => prev.map(s =>
        s.id === stop.id ? { ...s, stop_lat: newLat, stop_lon: newLon } : s
      ))
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('stops.saveError', 'Failed to update stop position'),
        color: 'red',
      })
    }
  }

  const polylinePositions: [number, number][] = editablePoints.map(p => [p.lat, p.lon])
  const backgroundShapes = shapes.filter(s => s.shape_id !== selectedShapeId)

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

        <MapClickHandler
          onMapClick={handleMapClick}
          onWaypointClick={handleWaypointClick}
          editMode={editMode}
          isAddingPoints={isAddingPoints}
          isWaypointMode={isWaypointMode}
        />

        {editablePoints.length > 0 && (
          <FitToBounds points={editablePoints} trigger={fitBoundsTrigger} />
        )}

        {/* Background shapes */}
        {backgroundShapes.map((shape) => (
          <Polyline
            key={shape.shape_id}
            positions={shape.points.map(p => [p.lat, p.lon] as [number, number])}
            pathOptions={{
              color: '#9ca3af',
              weight: 2,
              opacity: 0.4,
            }}
          />
        ))}

        {/* Stop markers overlay */}
        {showStops && stops.map((stop) => (
          <Marker
            key={`stop-${stop.id}`}
            position={[stop.stop_lat, stop.stop_lon]}
            icon={createStopIcon(editMode)}
            draggable={editMode && !isWaypointMode}
            eventHandlers={{
              click: (e) => {
                if (isWaypointMode) {
                  // Add stop as waypoint when in waypoint mode
                  setWaypoints(prev => [
                    ...prev,
                    { lat: stop.stop_lat, lon: stop.stop_lon, sequence: prev.length }
                  ])
                  L.DomEvent.stopPropagation(e)
                } else if (editMode) {
                  L.DomEvent.stopPropagation(e)
                }
              },
              dragend: (e) => {
                if (editMode && !isWaypointMode) {
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
                  <Text size="xs" c="dimmed">Code: {stop.stop_code}</Text>
                )}
                {stop.stop_desc && (
                  <Text size="xs" c="gray.7">{stop.stop_desc}</Text>
                )}
                <Text size="xs" c="dimmed">
                  {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                </Text>
                {isWaypointMode && (
                  <div style={{ marginTop: 8, fontSize: 11, color: '#7c3aed' }}>
                    Click to add as waypoint
                  </div>
                )}
                {editMode && !isWaypointMode && (
                  <Group gap="xs" mt="xs">
                    <Button size="xs" onClick={() => handleEditStop(stop)}>
                      {t('common.edit', 'Edit')}
                    </Button>
                  </Group>
                )}
              </Stack>
            </Popup>
          </Marker>
        ))}

        {/* Active shape polyline - clickable to insert points */}
        {polylinePositions.length > 1 && (
          <ClickablePolyline
            positions={polylinePositions}
            editMode={editMode}
            onSegmentClick={handleSegmentClick}
            color={editMode ? '#f59e0b' : '#3b82f6'}
            weight={editMode ? 6 : 4}
          />
        )}

        {/* Draggable shape points */}
        {editablePoints.map((point, index) => (
          <Marker
            key={`point-${index}-${point.lat}-${point.lon}`}
            position={[point.lat, point.lon]}
            icon={createPointIcon(
              point.isNew ? '#10b981' : selectedPointIndex === index ? '#ef4444' : '#3b82f6',
              selectedPointIndex === index
            )}
            draggable={editMode}
            eventHandlers={{
              click: (e) => {
                if (editMode) {
                  setSelectedPointIndex(index)
                  L.DomEvent.stopPropagation(e)
                }
              },
              dragend: (e) => {
                const marker = e.target
                const position = marker.getLatLng()
                handlePointDrag(index, position.lat, position.lng)
              },
            }}
          />
        ))}

        {/* Waypoint markers for auto-routing */}
        {isWaypointMode && waypoints.map((wp, index) => (
          <Marker
            key={`waypoint-${index}`}
            position={[wp.lat, wp.lon]}
            icon={createWaypointIcon(index + 1)}
            eventHandlers={{
              click: (e) => {
                // Remove waypoint on click
                setWaypoints(prev => prev.filter((_, i) => i !== index))
                L.DomEvent.stopPropagation(e)
              }
            }}
          />
        ))}
      </MapContainer>

      {/* Compact floating widget */}
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
          maxHeight: 'calc(100vh - 120px)',
          overflowY: 'auto',
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          backdropFilter: 'blur(8px)',
        }}
      >
        <Stack gap={6}>
          {/* Selectors */}
          <Select
            size="xs"
            placeholder="Route"
            data={routes.map(r => ({
              value: r.route_id,
              label: `${r.route_short_name || r.route_id}`,
            }))}
            value={selectedRouteId}
            onChange={(value) => {
              setSelectedRouteId(value)
              setSelectedShapeId(null)
              setEditablePoints([])
            }}
            searchable
            clearable
            disabled={routesLoading}
            styles={{ dropdown: { zIndex: 2000 } }}
            comboboxProps={{ withinPortal: true, zIndex: 2000 }}
          />

          <Select
            size="xs"
            placeholder="Shape"
            data={filteredShapes.map(s => {
              const tripShape = tripShapes.find(ts => ts.shape_id === s.shape_id)
              const routeLabel = tripShape ? ` [${tripShape.route_short_name}]` : ''
              return {
                value: s.shape_id,
                label: `${s.shape_id}${routeLabel}`,
              }
            })}
            value={selectedShapeId}
            onChange={(value) => {
              if (hasChanges && !confirm('Discard changes?')) return
              setSelectedShapeId(value)
              setIsAddingPoints(false)
              setSelectedPointIndex(null)
              setHasChanges(false)
            }}
            searchable
            clearable
            disabled={shapesLoading || (!editMode && filteredShapes.length === 0)}
            styles={{ dropdown: { zIndex: 2000 } }}
            comboboxProps={{ withinPortal: true, zIndex: 2000 }}
          />

          {/* Status badges */}
          <Group gap={4}>
            {editMode && <Badge color="orange" size="xs">Edit</Badge>}
            {selectedShapeId && editablePoints.length > 0 && (
              <Badge size="xs" variant="light">{editablePoints.length}pts</Badge>
            )}
            <Switch
              checked={showStops}
              onChange={(e) => setShowStops(e.currentTarget.checked)}
              size="xs"
              label={<Text size="xs">Stops</Text>}
            />
          </Group>

          {editMode && (
            <>
              {/* Action buttons */}
              <Group gap={4}>
                <ActionIcon
                  size="sm"
                  variant="light"
                  onClick={() => setCreateModalOpened(true)}
                  title="New shape"
                >
                  <IconPlus size={14} />
                </ActionIcon>
                {selectedShapeId && (
                  <>
                    <ActionIcon
                      size="sm"
                      color="red"
                      variant="light"
                      onClick={handleDeleteShape}
                      loading={loading}
                      title="Delete"
                    >
                      <IconTrash size={14} />
                    </ActionIcon>
                    <ActionIcon
                      size="sm"
                      color={isAddingPoints ? 'orange' : 'blue'}
                      variant={isAddingPoints ? 'filled' : 'light'}
                      onClick={() => setIsAddingPoints(!isAddingPoints)}
                      title="Add points"
                    >
                      <IconRoute size={14} />
                    </ActionIcon>
                    {selectedPointIndex !== null && (
                      <>
                        <ActionIcon
                          size="sm"
                          color="green"
                          variant="light"
                          onClick={() => handleInsertPointAfter(selectedPointIndex)}
                          title="Insert"
                        >
                          <IconPlus size={14} />
                        </ActionIcon>
                        <ActionIcon
                          size="sm"
                          color="red"
                          variant="light"
                          onClick={() => handleDeletePoint(selectedPointIndex)}
                          title="Delete point"
                        >
                          <IconTrash size={14} />
                        </ActionIcon>
                      </>
                    )}
                  </>
                )}
              </Group>

              {selectedShapeId && routingAvailable && (
                <>
                  <Select
                    size="xs"
                    value={selectedMode}
                    onChange={(value) => setSelectedMode((value as TransitMode) || 'bus')}
                    data={[
                      { value: 'bus', label: 'Bus' },
                      { value: 'rail', label: 'Rail' },
                      { value: 'tram', label: 'Tram' },
                      { value: 'ferry', label: 'Ferry' },
                    ]}
                    styles={{ dropdown: { zIndex: 2000 } }}
                    comboboxProps={{ withinPortal: true, zIndex: 2000 }}
                  />

                  <Group gap={4}>
                    <ActionIcon
                      size="sm"
                      variant="light"
                      onClick={handleSnapToRoad}
                      loading={isSnapping}
                      disabled={editablePoints.length < 2}
                      title="Snap to roads"
                    >
                      <IconMapPin size={14} />
                    </ActionIcon>
                    <ActionIcon
                      size="sm"
                      color="grape"
                      variant={isWaypointMode ? 'filled' : 'light'}
                      onClick={() => {
                        if (isWaypointMode) {
                          setIsWaypointMode(false)
                          setWaypoints([])
                        } else {
                          setIsWaypointMode(true)
                          setWaypoints([])
                        }
                      }}
                      title="Auto-route"
                    >
                      <IconRoute2 size={14} />
                    </ActionIcon>
                    {isWaypointMode && waypoints.length >= 2 && (
                      <Button
                        size="xs"
                        onClick={handleAutoRoute}
                        loading={isAutoRouting}
                        color="grape"
                        compact
                      >
                        Go ({waypoints.length})
                      </Button>
                    )}
                  </Group>
                </>
              )}

              {hasChanges && (
                <Group gap={4}>
                  <Button
                    size="xs"
                    color="green"
                    onClick={handleSaveShape}
                    loading={loading}
                    fullWidth
                    compact
                  >
                    Save
                  </Button>
                  <ActionIcon
                    size="sm"
                    color="gray"
                    variant="light"
                    onClick={handleCancelChanges}
                    title="Cancel"
                  >
                    <IconX size={14} />
                  </ActionIcon>
                </Group>
              )}
            </>
          )}
        </Stack>
      </Paper>

      {/* Create Shape Modal */}
      <Modal
        opened={createModalOpened}
        onClose={() => {
          setCreateModalOpened(false)
          createForm.reset()
        }}
        title="Create New Shape"
        size="sm"
        zIndex={2000}
      >
        <form onSubmit={createForm.onSubmit(handleCreateShape)}>
          <Stack>
            <TextInput
              label="Shape ID"
              placeholder="SHAPE_001"
              required
              {...createForm.getInputProps('shape_id')}
            />
            <Text size="xs" c="dimmed">
              After creating the shape, click on the map to add points that define the route path.
            </Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => {
                setCreateModalOpened(false)
                createForm.reset()
              }}>
                Cancel
              </Button>
              <Button type="submit" loading={loading}>
                Create Shape
              </Button>
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
        zIndex={2000}
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
              placeholder={t('stops.stopCodePlaceholder', 'Optional code')}
              {...editStopForm.getInputProps('stop_code')}
            />

            <TextInput
              label={t('stops.stopName', 'Stop Name')}
              placeholder={t('stops.stopNamePlaceholder', 'Main Street Station')}
              required
              {...editStopForm.getInputProps('stop_name')}
            />

            <Textarea
              label={t('common.description', 'Description')}
              placeholder={t('common.descriptionPlaceholder', 'Optional description')}
              {...editStopForm.getInputProps('stop_desc')}
              minRows={2}
            />

            <SimpleGrid cols={2}>
              <NumberInput
                label={t('stops.latitude', 'Latitude')}
                placeholder="37.7749"
                required
                decimalScale={8}
                step={0.000001}
                {...editStopForm.getInputProps('stop_lat')}
              />
              <NumberInput
                label={t('stops.longitude', 'Longitude')}
                placeholder="-122.4194"
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

            <TextInput
              label={t('stops.parentStation', 'Parent Station')}
              placeholder={t('stops.parentStationPlaceholder', 'Parent station stop_id')}
              {...editStopForm.getInputProps('parent_station')}
            />

            <TextInput
              label={t('stops.zoneId', 'Zone ID')}
              placeholder="Zone 1"
              {...editStopForm.getInputProps('zone_id')}
            />

            <TextInput
              label={t('stops.stopUrl', 'Stop URL')}
              placeholder="https://example.com/stops/main-street"
              {...editStopForm.getInputProps('stop_url')}
            />

            <Select
              label={t('stops.wheelchairBoarding', 'Wheelchair Boarding')}
              data={WHEELCHAIR_BOARDING}
              {...editStopForm.getInputProps('wheelchair_boarding')}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => {
                setEditStopModalOpened(false)
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
