/**
 * FinalExport component for Route Creator
 * Step 6: Review & Create route in GTFS feed
 */

import { useState, useMemo, useEffect } from 'react'
import {
  Paper,
  Stack,
  Group,
  Text,
  Badge,
  Button,
  Modal,
  Alert,
  List,
  ThemeIcon,
  SimpleGrid,
  TextInput,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'
import {
  IconRoute,
  IconMapPin,
  IconTimeline,
  IconBus,
  IconCalendar,
  IconAlertCircle,
  IconAlertTriangle,
  IconCheck,
  IconX,
  IconDatabase,
} from '@tabler/icons-react'
import { routeCreatorApi, type RouteExportPayload, type RouteExportValidation } from '../../lib/route-creator-api'

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

interface RCNewStop {
  stop_id: string
  stop_code: string
  stop_name: string
  lat: number
  lon: number
  sequence: number
}

interface Calendar {
  id: number
  service_id: string
  monday: boolean | number
  tuesday: boolean | number
  wednesday: boolean | number
  thursday: boolean | number
  friday: boolean | number
  saturday: boolean | number
  sunday: boolean | number
  start_date?: string
  end_date?: string
}

interface FinalExportProps {
  // Route data
  routeId: string
  routeShortName: string
  routeColor: string
  // Stops
  orderedStops: RCSelectedStop[]
  newStops: RCNewStop[]
  // Shape
  shapePoints: Array<{ lat: number; lon: number }>
  // Trips & Schedule
  trips: string[]
  stopTimesTable: Record<string, string[]>
  // Feed & Calendars
  feedId: number | null
  calendars: Calendar[]
  selectedServiceIds: string[]  // Now passed from parent (Step 1)
  // Callbacks
  onBack: () => void
  onExportComplete: () => void
}

export function FinalExport({
  routeId,
  routeShortName,
  routeColor,
  orderedStops,
  newStops,
  shapePoints,
  trips,
  stopTimesTable,
  feedId,
  calendars,
  selectedServiceIds,
  onBack,
  onExportComplete,
}: FinalExportProps) {
  const { t } = useTranslation()
  const [confirmModalOpened, { open: openConfirmModal, close: closeConfirmModal }] = useDisclosure(false)
  const [validationModalOpened, { open: openValidationModal, close: closeValidationModal }] = useDisclosure(false)
  const [validating, setValidating] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [validation, setValidation] = useState<RouteExportValidation | null>(null)

  // Editable route fields - initialize from props
  const [editableRouteId, setEditableRouteId] = useState<string>(routeId)
  const [editableRouteShortName, setEditableRouteShortName] = useState<string>(routeShortName)
  const [customShapeId, setCustomShapeId] = useState<string>(`${routeId}_shape`)

  // Calculate summary
  const summary = useMemo(() => {
    const newStopsCount = newStops.length
    const existingStopsCount = orderedStops.filter(s => !s.isNew).length
    const shapePointsCount = shapePoints.length
    const tripsPerCalendar = trips.length
    const totalTrips = tripsPerCalendar * Math.max(selectedServiceIds.length, 1)
    const stopTimesPerTrip = orderedStops.length
    const totalStopTimes = stopTimesPerTrip * totalTrips

    return {
      newStopsCount,
      existingStopsCount,
      shapePointsCount,
      tripsPerCalendar,
      totalTrips,
      stopTimesPerTrip,
      totalStopTimes,
    }
  }, [newStops, orderedStops, shapePoints, trips, selectedServiceIds])

  // Build export payload
  const buildPayload = (): RouteExportPayload | null => {
    if (!feedId) return null
    if (selectedServiceIds.length === 0) return null
    if (!customShapeId.trim()) return null
    if (!editableRouteId.trim()) return null

    const shapeId = customShapeId.trim()
    const color = routeColor.replace('#', '')
    const finalRouteId = editableRouteId.trim()
    const finalRouteShortName = editableRouteShortName.trim() || finalRouteId

    // Build new stops
    const exportNewStops = newStops.map(s => ({
      stop_id: s.stop_id,
      stop_name: s.stop_name,
      stop_lat: s.lat,
      stop_lon: s.lon,
      stop_code: s.stop_code || undefined,
    }))

    // Build shape points
    const exportShapePoints = shapePoints.map((p, idx) => ({
      lat: p.lat,
      lon: p.lon,
      sequence: idx,
    }))

    // Build trips (one per departure time, will be duplicated for each service_id by backend)
    const exportTrips = trips.map((tripTime, idx) => ({
      trip_id: `${finalRouteId}_${idx + 1}`,
      trip_headsign: finalRouteShortName,
      direction_id: 0,
    }))

    // Build stop_times
    const exportStopTimes: RouteExportPayload['stop_times'] = []
    trips.forEach((tripTime, tripIdx) => {
      const tripId = `${finalRouteId}_${tripIdx + 1}`
      const times = stopTimesTable[tripTime] || []

      orderedStops.forEach((stop, stopIdx) => {
        const timeStr = times[stopIdx] || '00:00:00'
        // Ensure time has seconds
        const formattedTime = timeStr.includes(':') && timeStr.split(':').length === 2
          ? `${timeStr}:00`
          : timeStr

        exportStopTimes.push({
          trip_id: tripId,
          stop_id: stop.stop_id,
          stop_sequence: stop.sequence ?? (stopIdx + 1),
          arrival_time: formattedTime,
          departure_time: formattedTime,
        })
      })
    })

    return {
      feed_id: feedId,
      service_ids: selectedServiceIds,  // Already string service_ids from Calendar
      route: {
        route_id: finalRouteId,
        route_short_name: finalRouteShortName,
        route_type: 3, // Bus
        route_color: color,
      },
      new_stops: exportNewStops,
      shape_id: shapeId,
      shape_points: exportShapePoints,
      trips: exportTrips,
      stop_times: exportStopTimes,
    }
  }

  // Validate before export
  const handleValidate = async () => {
    const payload = buildPayload()
    if (!payload) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('routeCreator.export.selectCalendars', 'Please select at least one calendar'),
        color: 'red',
      })
      return
    }

    setValidating(true)
    try {
      const result = await routeCreatorApi.validate(payload)
      setValidation(result)
      openValidationModal()
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error.response?.data?.detail || t('routeCreator.export.validationFailed', 'Validation failed'),
        color: 'red',
      })
    } finally {
      setValidating(false)
    }
  }

  // Export to feed
  const handleExport = async () => {
    const payload = buildPayload()
    if (!payload) return

    setExporting(true)
    try {
      await routeCreatorApi.export(payload)
      closeConfirmModal()
      notifications.show({
        title: t('common.success', 'Success'),
        message: t('routeCreator.export.exportStarted', `Route export started. Creating '${editableRouteId}' with ${summary.totalTrips} trips. Track progress in Task Manager.`, { routeId: editableRouteId, tripCount: summary.totalTrips }),
        color: 'green',
        autoClose: 10000,
      })
      onExportComplete()
    } catch (error: any) {
      const detail = error.response?.data?.detail
      const message = typeof detail === 'object'
        ? detail.message || detail.errors?.join('; ')
        : detail || t('routeCreator.export.exportFailed', 'Export failed')

      notifications.show({
        title: t('common.error', 'Error'),
        message,
        color: 'red',
      })
    } finally {
      setExporting(false)
    }
  }

  const canExport = feedId && selectedServiceIds.length > 0 && trips.length > 0 && orderedStops.length >= 2 && customShapeId.trim().length > 0 && editableRouteId.trim().length > 0

  return (
    <>
      <Paper p="xs" shadow="sm" withBorder style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <Group justify="space-between" mb="xs">
          <Group gap="xs">
            <Text fw={600}>{t('routeCreator.export.title', 'Review & Create')}</Text>
            <Badge color="green" variant="light" size="sm">{t('routeCreator.export.step6', 'Step 6')}</Badge>
          </Group>
        </Group>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <Stack gap="xs">
            {/* Summary - 4 columns horizontal layout */}
            <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
              {/* Route */}
              <Paper p="xs" bg="gray.0" radius="sm" withBorder>
                <Group gap="xs" mb={4}>
                  <ThemeIcon size="sm" color="blue" variant="light">
                    <IconRoute size={14} />
                  </ThemeIcon>
                  <Text fw={600} size="sm">{t('routeCreator.export.routeDetails', 'Route')}</Text>
                </Group>
                <TextInput
                  size="xs"
                  label={t('routeCreator.routeId', 'Route ID')}
                  value={editableRouteId}
                  onChange={(e) => setEditableRouteId(e.currentTarget.value)}
                  placeholder="route_id"
                  error={!editableRouteId.trim()}
                  styles={{ input: { fontSize: 11 }, label: { fontSize: 10 } }}
                  mb={4}
                />
                <TextInput
                  size="xs"
                  label={t('routeCreator.routeShortName', 'Short Name')}
                  value={editableRouteShortName}
                  onChange={(e) => setEditableRouteShortName(e.currentTarget.value)}
                  placeholder="Short name"
                  styles={{ input: { fontSize: 11 }, label: { fontSize: 10 } }}
                  mb={4}
                />
                <Badge size="xs" style={{ backgroundColor: routeColor, color: '#fff' }}>{routeColor}</Badge>
              </Paper>

              {/* Stops */}
              <Paper p="xs" bg="gray.0" radius="sm" withBorder>
                <Group gap="xs" mb={4}>
                  <ThemeIcon size="sm" color="teal" variant="light">
                    <IconMapPin size={14} />
                  </ThemeIcon>
                  <Text fw={600} size="sm">{t('routeCreator.export.stops', 'Stops')}</Text>
                </Group>
                <Text size="xs" c="dimmed">Total: <strong>{orderedStops.length}</strong></Text>
                <Group gap={4} mt={4}>
                  <Badge size="xs" color="green" variant="light">{summary.newStopsCount} new</Badge>
                  <Badge size="xs" color="gray" variant="light">{summary.existingStopsCount} existing</Badge>
                </Group>
              </Paper>

              {/* Shape */}
              <Paper p="xs" bg="gray.0" radius="sm" withBorder>
                <Group gap="xs" mb={4}>
                  <ThemeIcon size="sm" color="violet" variant="light">
                    <IconTimeline size={14} />
                  </ThemeIcon>
                  <Text fw={600} size="sm">{t('routeCreator.export.shape', 'Shape')}</Text>
                </Group>
                <TextInput
                  size="xs"
                  value={customShapeId}
                  onChange={(e) => setCustomShapeId(e.currentTarget.value)}
                  placeholder="shape_id"
                  error={!customShapeId.trim()}
                  styles={{ input: { fontSize: 11 } }}
                />
                <Badge size="xs" color="violet" variant="light" mt={4}>{summary.shapePointsCount} points</Badge>
              </Paper>

              {/* Trips */}
              <Paper p="xs" bg="gray.0" radius="sm" withBorder>
                <Group gap="xs" mb={4}>
                  <ThemeIcon size="sm" color="grape" variant="light">
                    <IconBus size={14} />
                  </ThemeIcon>
                  <Text fw={600} size="sm">{t('routeCreator.export.trips', 'Trips')}</Text>
                </Group>
                <Text size="xs" c="dimmed">Departures: <strong>{trips.length}</strong></Text>
                <Group gap={4} mt={4}>
                  <Badge size="xs" color="grape" variant="light">{summary.totalTrips} trips</Badge>
                  <Badge size="xs" color="orange" variant="light">{summary.totalStopTimes} stop_times</Badge>
                </Group>
              </Paper>
            </SimpleGrid>

            {/* Calendar Selection (read-only - selected in Step 1) */}
            <Paper p="xs" bg="blue.0" radius="sm" withBorder>
              <Group gap="xs" mb={4}>
                <ThemeIcon size="sm" color="blue" variant="light">
                  <IconCalendar size={14} />
                </ThemeIcon>
                <Text fw={600} size="sm">{t('routeCreator.export.serviceCalendars', 'Service Calendars')}</Text>
                <Badge size="xs" variant="light">{selectedServiceIds.length} selected</Badge>
              </Group>
              <Group gap={4} wrap="wrap">
                {selectedServiceIds.map(serviceId => {
                  const cal = calendars.find(c => c.service_id === serviceId)
                  const days = cal ? [
                    (cal.monday === true || cal.monday === 1) && 'M',
                    (cal.tuesday === true || cal.tuesday === 1) && 'T',
                    (cal.wednesday === true || cal.wednesday === 1) && 'W',
                    (cal.thursday === true || cal.thursday === 1) && 'Th',
                    (cal.friday === true || cal.friday === 1) && 'F',
                    (cal.saturday === true || cal.saturday === 1) && 'Sa',
                    (cal.sunday === true || cal.sunday === 1) && 'Su',
                  ].filter(Boolean).join('') : ''
                  return (
                    <Badge key={serviceId} size="sm" variant="light" color="blue">
                      {serviceId}{days ? ` (${days})` : ''}
                    </Badge>
                  )
                })}
              </Group>
              {selectedServiceIds.length > 0 && (
                <Text size="xs" mt={4} c="dimmed">
                  → {summary.totalTrips} trips ({trips.length} × {selectedServiceIds.length} calendars)
                </Text>
              )}
            </Paper>

            {/* Alerts */}
            {!feedId && (
              <Alert color="yellow" icon={<IconAlertCircle size={16} />} p="xs">
                <Text size="xs">{t('routeCreator.export.noFeed', 'No feed selected.')}</Text>
              </Alert>
            )}
            {calendars.length === 0 && feedId && (
              <Alert color="yellow" icon={<IconAlertCircle size={16} />} p="xs">
                <Text size="xs">{t('routeCreator.export.noCalendars', 'No calendars found.')}</Text>
              </Alert>
            )}
          </Stack>
        </div>

        {/* Footer buttons */}
        <Group gap="xs" mt="xs">
          <Button size="xs" variant="default" onClick={onBack}>
            {t('common.back', 'Back')}
          </Button>
          <Button size="xs" color="blue" variant="light" onClick={handleValidate} loading={validating} disabled={!canExport}>
            {t('routeCreator.export.validate', 'Validate')}
          </Button>
          <Button size="xs" color="green" onClick={openConfirmModal} disabled={!canExport} leftSection={<IconDatabase size={14} />}>
            {t('routeCreator.export.createRoute', 'Create')}
          </Button>
        </Group>
      </Paper>

      {/* Validation Results Modal */}
      <Modal
        opened={validationModalOpened}
        onClose={closeValidationModal}
        title={t('routeCreator.export.validationResults', 'Validation Results')}
        size="md"
        zIndex={100001}
      >
        {validation && (
          <Stack gap="md">
            <Group gap="xs">
              {validation.valid ? (
                <>
                  <ThemeIcon color="green" size="lg" radius="xl">
                    <IconCheck size={20} />
                  </ThemeIcon>
                  <Text fw={500} c="green">{t('routeCreator.export.validationPassed', 'Validation Passed')}</Text>
                </>
              ) : (
                <>
                  <ThemeIcon color="red" size="lg" radius="xl">
                    <IconX size={20} />
                  </ThemeIcon>
                  <Text fw={500} c="red">{t('routeCreator.export.validationFailed', 'Validation Failed')}</Text>
                </>
              )}
            </Group>

            {validation.errors.length > 0 && (
              <Alert color="red" icon={<IconAlertCircle size={16} />} title={t('routeCreator.export.errors', 'Errors')}>
                <List size="sm">
                  {validation.errors.map((err, idx) => (
                    <List.Item key={idx}>{err}</List.Item>
                  ))}
                </List>
              </Alert>
            )}

            {validation.warnings.length > 0 && (
              <Alert color="yellow" icon={<IconAlertTriangle size={16} />} title={t('routeCreator.export.warnings', 'Warnings')}>
                <List size="sm">
                  {validation.warnings.map((warn, idx) => (
                    <List.Item key={idx}>{warn}</List.Item>
                  ))}
                </List>
              </Alert>
            )}

            <Paper p="sm" bg="gray.0" radius="sm">
              <Text fw={500} size="sm" mb="xs">{t('routeCreator.export.summary', 'Summary')}</Text>
              <List size="sm" spacing={2}>
                <List.Item><strong>Route:</strong> {validation.summary.route_id} ({validation.summary.route_short_name})</List.Item>
                <List.Item><strong>New stops:</strong> {validation.summary.new_stops_count}</List.Item>
                <List.Item><strong>Shape points:</strong> {validation.summary.shape_points_count}</List.Item>
                <List.Item><strong>Total trips:</strong> {validation.summary.total_trips}</List.Item>
                <List.Item><strong>Total stop times:</strong> {validation.summary.total_stop_times}</List.Item>
              </List>
            </Paper>

            <Group justify="flex-end">
              <Button variant="default" onClick={closeValidationModal}>
                {t('common.close', 'Close')}
              </Button>
              {validation.valid && (
                <Button color="green" onClick={() => { closeValidationModal(); openConfirmModal(); }}>
                  {t('routeCreator.export.proceedToCreate', 'Proceed to Create')}
                </Button>
              )}
            </Group>
          </Stack>
        )}
      </Modal>

      {/* Confirmation Modal */}
      <Modal
        opened={confirmModalOpened}
        onClose={closeConfirmModal}
        title={t('routeCreator.export.confirmCreate', 'Confirm Create Route')}
        size="md"
        zIndex={100001}
      >
        <Stack gap="md">
          <Text>
            {t('routeCreator.export.confirmMessage', 'You are about to add the following to the GTFS feed:')}
          </Text>

          <Paper p="sm" bg="gray.0" radius="sm">
            <List size="sm" spacing={4}>
              <List.Item><strong>1 new route:</strong> {editableRouteId} ({editableRouteShortName || editableRouteId})</List.Item>
              <List.Item><strong>{summary.newStopsCount} new stops</strong></List.Item>
              <List.Item><strong>1 new shape:</strong> {customShapeId} ({summary.shapePointsCount} points)</List.Item>
              <List.Item><strong>{summary.totalTrips} new trips</strong></List.Item>
              <List.Item><strong>{summary.totalStopTimes} new stop_times</strong></List.Item>
            </List>
          </Paper>

          <Alert color="yellow" icon={<IconAlertTriangle size={16} />}>
            {t('routeCreator.export.cannotUndo', 'This will run as a background task. You can track progress in the Task Manager.')}
          </Alert>

          <Group justify="flex-end">
            <Button variant="default" onClick={closeConfirmModal} disabled={exporting}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button color="green" onClick={handleExport} loading={exporting}>
              {exporting ? t('routeCreator.export.creating', 'Creating...') : t('routeCreator.export.startCreate', 'Create Route')}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
