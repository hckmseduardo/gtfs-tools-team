import { useState, useEffect, useCallback } from 'react'
import {
  Container,
  Title,
  Text,
  Paper,
  Stack,
  Group,
  Select,
  Tabs,
  Table,
  Badge,
  ThemeIcon,
  SimpleGrid,
  Card,
  Loader,
  Alert,
  ActionIcon,
  Tooltip,
  ScrollArea,
  Accordion,
  Code,
  Box,
  Divider,
  Switch,
} from '@mantine/core'
import {
  IconBus,
  IconAlertTriangle,
  IconRoute,
  IconRefresh,
  IconClock,
  IconMapPin,
  IconArrowRight,
  IconInfoCircle,
  IconAlertCircle,
  IconDirections,
  IconCalendar,
  IconPlayerPlay,
  IconPlayerPause,
  IconShape,
  IconMapPinFilled,
} from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { notifications } from '@mantine/notifications'
import { agencyApi } from '../lib/gtfs-api'
import {
  realtimeApi,
  VehiclePosition,
  TripUpdate,
  Alert as RealtimeAlert,
  TripModification,
  RealtimeShape,
  RealtimeStop,
  AllRealtimeResponse,
} from '../lib/realtime-api'

interface Agency {
  id: number
  name: string
  agency_id: string
}

export default function Realtime() {
  const { t } = useTranslation()
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgencyId, setSelectedAgencyId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // Realtime data state
  const [vehicles, setVehicles] = useState<VehiclePosition[]>([])
  const [tripUpdates, setTripUpdates] = useState<TripUpdate[]>([])
  const [alerts, setAlerts] = useState<RealtimeAlert[]>([])
  const [tripModifications, setTripModifications] = useState<TripModification[]>([])
  const [shapes, setShapes] = useState<RealtimeShape[]>([])
  const [stops, setStops] = useState<RealtimeStop[]>([])
  const [errors, setErrors] = useState<{ feed_source_id: number; feed_source_name: string; error: string }[]>([])

  // Load agencies on mount
  useEffect(() => {
    loadAgencies()
  }, [])

  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh || !selectedAgencyId) return

    const interval = setInterval(() => {
      fetchRealtimeData(parseInt(selectedAgencyId))
    }, 10000) // Refresh every 10 seconds

    return () => clearInterval(interval)
  }, [autoRefresh, selectedAgencyId])

  const loadAgencies = async () => {
    try {
      const response = await agencyApi.list({ limit: 100 })
      setAgencies(response.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('errors.unknownError'),
        color: 'red',
      })
    }
  }

  const fetchRealtimeData = useCallback(async (agencyId: number) => {
    setLoading(true)
    try {
      const response: AllRealtimeResponse = await realtimeApi.getAllRealtimeData(agencyId)
      setVehicles(response.vehicles || [])
      setTripUpdates(response.trip_updates || [])
      setAlerts(response.alerts || [])
      setTripModifications(response.trip_modifications || [])
      setShapes(response.shapes || [])
      setStops(response.stops || [])
      setErrors(response.errors || [])
      setLastRefresh(new Date())
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('errors.unknownError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }, [t])

  const handleAgencyChange = (value: string | null) => {
    setSelectedAgencyId(value)
    if (value) {
      fetchRealtimeData(parseInt(value))
    } else {
      // Clear data when no agency selected
      setVehicles([])
      setTripUpdates([])
      setAlerts([])
      setTripModifications([])
      setShapes([])
      setStops([])
      setErrors([])
    }
  }

  const formatDelay = (seconds: number | undefined) => {
    if (seconds === undefined || seconds === null) return '-'
    const absSeconds = Math.abs(seconds)
    const minutes = Math.floor(absSeconds / 60)
    if (seconds === 0) return t('map.stopSchedule.onTime')
    if (seconds > 0) {
      return `+${minutes} min ${t('map.stopSchedule.late')}`
    }
    return `-${minutes} min ${t('map.stopSchedule.early')}`
  }

  const getDelayColor = (delay: number | undefined) => {
    if (delay === undefined || delay === null || delay === 0) return 'green'
    if (delay > 300) return 'red' // > 5 min late
    if (delay > 60) return 'orange' // > 1 min late
    if (delay < -60) return 'blue' // > 1 min early
    return 'green'
  }

  const formatTimestamp = (timestamp: number | undefined) => {
    if (!timestamp) return '-'
    return new Date(timestamp * 1000).toLocaleTimeString()
  }

  const getAlertSeverityColor = (_cause?: string, effect?: string) => {
    if (effect === 'no_service') return 'red'
    if (effect === 'significant_delays' || effect === 'detour') return 'orange'
    if (effect === 'reduced_service') return 'yellow'
    return 'blue'
  }

  const getVehicleStatusBadge = (status?: string) => {
    switch (status) {
      case 'stopped_at':
        return <Badge color="blue">{t('realtime.statusValues.stoppedAt', 'Stopped')}</Badge>
      case 'incoming_at':
        return <Badge color="cyan">{t('realtime.statusValues.incomingAt', 'Arriving')}</Badge>
      case 'in_transit_to':
        return <Badge color="green">{t('realtime.statusValues.inTransitTo', 'In Transit')}</Badge>
      default:
        return <Badge color="gray">{t('common.status')}</Badge>
    }
  }

  return (
    <Container size="xl">
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={1}>{t('realtime.title', 'GTFS Realtime Explorer')}</Title>
            <Text c="dimmed" mt="xs">
              {t('realtime.description', 'Explore real-time transit data: vehicle positions, trip updates, alerts, and detours')}
            </Text>
          </div>
          <Group>
            {lastRefresh && (
              <Text size="sm" c="dimmed">
                {t('realtime.lastRefresh', 'Last refresh')}: {lastRefresh.toLocaleTimeString()}
              </Text>
            )}
          </Group>
        </Group>

        {/* Agency Selection and Controls */}
        <Paper withBorder p="md" radius="md">
          <Group justify="space-between">
            <Group>
              <Select
                label={t('map.selectAgency')}
                placeholder={t('agencies.title')}
                data={agencies.map((a) => ({ value: String(a.id), label: a.name }))}
                value={selectedAgencyId}
                onChange={handleAgencyChange}
                searchable
                clearable
                style={{ minWidth: 250 }}
              />
              <Tooltip label={t('common.refresh')}>
                <ActionIcon
                  variant="light"
                  size="lg"
                  onClick={() => selectedAgencyId && fetchRealtimeData(parseInt(selectedAgencyId))}
                  disabled={!selectedAgencyId || loading}
                  mt={24}
                >
                  <IconRefresh size={20} className={loading ? 'spin' : ''} />
                </ActionIcon>
              </Tooltip>
            </Group>
            <Group mt={24}>
              <Switch
                label={t('realtime.autoRefresh', 'Auto-refresh (10s)')}
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.currentTarget.checked)}
                disabled={!selectedAgencyId}
                thumbIcon={autoRefresh ? <IconPlayerPlay size={12} /> : <IconPlayerPause size={12} />}
              />
            </Group>
          </Group>
        </Paper>

        {/* Errors Display */}
        {errors.length > 0 && (
          <Alert icon={<IconAlertCircle size={16} />} color="red" title={t('realtime.feedErrors', 'Feed Errors')}>
            <Stack gap="xs">
              {errors.map((error, index) => (
                <Text key={index} size="sm">
                  <strong>{error.feed_source_name}:</strong> {error.error}
                </Text>
              ))}
            </Stack>
          </Alert>
        )}

        {/* Summary Cards */}
        {selectedAgencyId && (
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="md">
            <Card withBorder padding="md" radius="md">
              <Group justify="space-between">
                <div>
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {t('realtime.vehicles', 'Vehicles')}
                  </Text>
                  <Title order={2}>{vehicles.length}</Title>
                </div>
                <ThemeIcon size="xl" radius="md" variant="light" color="blue">
                  <IconBus size={28} />
                </ThemeIcon>
              </Group>
            </Card>
            <Card withBorder padding="md" radius="md">
              <Group justify="space-between">
                <div>
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {t('realtime.tripUpdates', 'Trip Updates')}
                  </Text>
                  <Title order={2}>{tripUpdates.length}</Title>
                </div>
                <ThemeIcon size="xl" radius="md" variant="light" color="orange">
                  <IconClock size={28} />
                </ThemeIcon>
              </Group>
            </Card>
            <Card withBorder padding="md" radius="md">
              <Group justify="space-between">
                <div>
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {t('realtime.alerts', 'Alerts')}
                  </Text>
                  <Title order={2}>{alerts.length}</Title>
                </div>
                <ThemeIcon size="xl" radius="md" variant="light" color="red">
                  <IconAlertTriangle size={28} />
                </ThemeIcon>
              </Group>
            </Card>
            <Card withBorder padding="md" radius="md">
              <Group justify="space-between">
                <div>
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {t('realtime.tripModifications', 'Detours')}
                  </Text>
                  <Title order={2}>{tripModifications.length}</Title>
                </div>
                <ThemeIcon size="xl" radius="md" variant="light" color="grape">
                  <IconDirections size={28} />
                </ThemeIcon>
              </Group>
            </Card>
            <Card withBorder padding="md" radius="md">
              <Group justify="space-between">
                <div>
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {t('realtime.shapes', 'RT Shapes')}
                  </Text>
                  <Title order={2}>{shapes.length}</Title>
                </div>
                <ThemeIcon size="xl" radius="md" variant="light" color="cyan">
                  <IconShape size={28} />
                </ThemeIcon>
              </Group>
            </Card>
            <Card withBorder padding="md" radius="md">
              <Group justify="space-between">
                <div>
                  <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                    {t('realtime.rtStops', 'RT Stops')}
                  </Text>
                  <Title order={2}>{stops.length}</Title>
                </div>
                <ThemeIcon size="xl" radius="md" variant="light" color="teal">
                  <IconMapPinFilled size={28} />
                </ThemeIcon>
              </Group>
            </Card>
          </SimpleGrid>
        )}

        {/* Main Content Tabs */}
        {selectedAgencyId && (
          <Paper withBorder p="md" radius="md">
            <Tabs defaultValue="vehicles">
              <Tabs.List>
                <Tabs.Tab value="vehicles" leftSection={<IconBus size={16} />}>
                  {t('realtime.vehicles', 'Vehicles')}
                  {vehicles.length > 0 && <Badge ml="xs" size="sm">{vehicles.length}</Badge>}
                </Tabs.Tab>
                <Tabs.Tab value="tripUpdates" leftSection={<IconClock size={16} />}>
                  {t('realtime.tripUpdates', 'Trip Updates')}
                  {tripUpdates.length > 0 && <Badge ml="xs" size="sm">{tripUpdates.length}</Badge>}
                </Tabs.Tab>
                <Tabs.Tab value="alerts" leftSection={<IconAlertTriangle size={16} />}>
                  {t('realtime.alerts', 'Alerts')}
                  {alerts.length > 0 && <Badge ml="xs" size="sm" color="red">{alerts.length}</Badge>}
                </Tabs.Tab>
                <Tabs.Tab value="tripModifications" leftSection={<IconDirections size={16} />}>
                  {t('realtime.tripModifications', 'Trip Modifications')}
                  {tripModifications.length > 0 && <Badge ml="xs" size="sm" color="grape">{tripModifications.length}</Badge>}
                </Tabs.Tab>
                <Tabs.Tab value="shapes" leftSection={<IconShape size={16} />}>
                  {t('realtime.shapes', 'RT Shapes')}
                  {shapes.length > 0 && <Badge ml="xs" size="sm" color="cyan">{shapes.length}</Badge>}
                </Tabs.Tab>
                <Tabs.Tab value="stops" leftSection={<IconMapPinFilled size={16} />}>
                  {t('realtime.rtStops', 'RT Stops')}
                  {stops.length > 0 && <Badge ml="xs" size="sm" color="teal">{stops.length}</Badge>}
                </Tabs.Tab>
              </Tabs.List>

              {/* Vehicles Tab */}
              <Tabs.Panel value="vehicles" pt="md">
                {loading ? (
                  <Group justify="center" p="xl">
                    <Loader />
                  </Group>
                ) : vehicles.length === 0 ? (
                  <Alert icon={<IconInfoCircle size={16} />} color="gray">
                    {t('realtime.noVehicles', 'No vehicle positions available')}
                  </Alert>
                ) : (
                  <ScrollArea>
                    <Table striped highlightOnHover>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>{t('realtime.vehicleId', 'Vehicle')}</Table.Th>
                          <Table.Th>{t('realtime.route', 'Route')}</Table.Th>
                          <Table.Th>{t('realtime.trip', 'Trip')}</Table.Th>
                          <Table.Th>{t('realtime.position', 'Position')}</Table.Th>
                          <Table.Th>{t('realtime.speed', 'Speed')}</Table.Th>
                          <Table.Th>{t('realtime.status', 'Status')}</Table.Th>
                          <Table.Th>{t('realtime.occupancy', 'Occupancy')}</Table.Th>
                          <Table.Th>{t('realtime.lastUpdate', 'Last Update')}</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {vehicles.map((vehicle) => (
                          <Table.Tr key={vehicle.id}>
                            <Table.Td>
                              <Group gap="xs">
                                <IconBus size={16} />
                                <Text fw={500}>{vehicle.vehicle_label || vehicle.vehicle_id}</Text>
                              </Group>
                            </Table.Td>
                            <Table.Td>
                              {vehicle.route_id ? (
                                <Badge color="blue" variant="light">{vehicle.route_id}</Badge>
                              ) : '-'}
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm">{vehicle.trip_id || '-'}</Text>
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm" c="dimmed">
                                {vehicle.latitude?.toFixed(5)}, {vehicle.longitude?.toFixed(5)}
                              </Text>
                            </Table.Td>
                            <Table.Td>
                              {vehicle.speed !== undefined ? `${(vehicle.speed * 3.6).toFixed(1)} km/h` : '-'}
                            </Table.Td>
                            <Table.Td>{getVehicleStatusBadge(vehicle.current_status)}</Table.Td>
                            <Table.Td>
                              {vehicle.occupancy_status ? (
                                <Badge color="gray" variant="light">
                                  {vehicle.occupancy_status.replace(/_/g, ' ')}
                                </Badge>
                              ) : '-'}
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm">{formatTimestamp(vehicle.timestamp)}</Text>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </ScrollArea>
                )}
              </Tabs.Panel>

              {/* Trip Updates Tab */}
              <Tabs.Panel value="tripUpdates" pt="md">
                {loading ? (
                  <Group justify="center" p="xl">
                    <Loader />
                  </Group>
                ) : tripUpdates.length === 0 ? (
                  <Alert icon={<IconInfoCircle size={16} />} color="gray">
                    {t('realtime.noTripUpdates', 'No trip updates available')}
                  </Alert>
                ) : (
                  <Accordion>
                    {tripUpdates.map((update) => (
                      <Accordion.Item key={update.id} value={update.id}>
                        <Accordion.Control>
                          <Group justify="space-between">
                            <Group>
                              <IconRoute size={16} />
                              <Text fw={500}>{update.trip_id}</Text>
                              {update.route_id && (
                                <Badge color="blue" variant="light">{update.route_id}</Badge>
                              )}
                            </Group>
                            <Badge color={getDelayColor(update.delay)} variant="filled">
                              {formatDelay(update.delay)}
                            </Badge>
                          </Group>
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Stack gap="md">
                            <SimpleGrid cols={3}>
                              <div>
                                <Text size="xs" c="dimmed">{t('realtime.vehicle', 'Vehicle')}</Text>
                                <Text>{update.vehicle_label || update.vehicle_id || '-'}</Text>
                              </div>
                              <div>
                                <Text size="xs" c="dimmed">{t('realtime.startTime', 'Start Time')}</Text>
                                <Text>{update.start_time || '-'}</Text>
                              </div>
                              <div>
                                <Text size="xs" c="dimmed">{t('realtime.scheduleRelationship', 'Schedule')}</Text>
                                <Badge variant="light">
                                  {update.schedule_relationship || 'scheduled'}
                                </Badge>
                              </div>
                            </SimpleGrid>

                            {update.stop_time_updates && update.stop_time_updates.length > 0 && (
                              <>
                                <Divider label={t('realtime.stopTimeUpdates', 'Stop Time Updates')} />
                                <ScrollArea>
                                  <Table striped>
                                    <Table.Thead>
                                      <Table.Tr>
                                        <Table.Th>{t('realtime.sequence', 'Seq')}</Table.Th>
                                        <Table.Th>{t('realtime.stopId', 'Stop ID')}</Table.Th>
                                        <Table.Th>{t('realtime.arrivalDelay', 'Arrival Delay')}</Table.Th>
                                        <Table.Th>{t('realtime.departureDelay', 'Departure Delay')}</Table.Th>
                                      </Table.Tr>
                                    </Table.Thead>
                                    <Table.Tbody>
                                      {update.stop_time_updates.map((stu, idx) => (
                                        <Table.Tr key={idx}>
                                          <Table.Td>{stu.stop_sequence || '-'}</Table.Td>
                                          <Table.Td>{stu.stop_id || '-'}</Table.Td>
                                          <Table.Td>
                                            <Badge size="sm" color={getDelayColor(stu.arrival_delay)}>
                                              {formatDelay(stu.arrival_delay)}
                                            </Badge>
                                          </Table.Td>
                                          <Table.Td>
                                            <Badge size="sm" color={getDelayColor(stu.departure_delay)}>
                                              {formatDelay(stu.departure_delay)}
                                            </Badge>
                                          </Table.Td>
                                        </Table.Tr>
                                      ))}
                                    </Table.Tbody>
                                  </Table>
                                </ScrollArea>
                              </>
                            )}
                          </Stack>
                        </Accordion.Panel>
                      </Accordion.Item>
                    ))}
                  </Accordion>
                )}
              </Tabs.Panel>

              {/* Alerts Tab */}
              <Tabs.Panel value="alerts" pt="md">
                {loading ? (
                  <Group justify="center" p="xl">
                    <Loader />
                  </Group>
                ) : alerts.length === 0 ? (
                  <Alert icon={<IconInfoCircle size={16} />} color="gray">
                    {t('realtime.noAlerts', 'No active service alerts')}
                  </Alert>
                ) : (
                  <Stack gap="md">
                    {alerts.map((alert) => (
                      <Paper key={alert.id} withBorder p="md" radius="md">
                        <Stack gap="sm">
                          <Group justify="space-between">
                            <Group>
                              <ThemeIcon color={getAlertSeverityColor(alert.cause, alert.effect)} variant="light">
                                <IconAlertTriangle size={16} />
                              </ThemeIcon>
                              <Title order={5}>
                                {alert.header_text?.en || alert.header_text?.['en-US'] || t('realtime.serviceAlert', 'Service Alert')}
                              </Title>
                            </Group>
                            <Group gap="xs">
                              {alert.cause && (
                                <Badge color="gray" variant="light">
                                  {alert.cause.replace(/_/g, ' ')}
                                </Badge>
                              )}
                              {alert.effect && (
                                <Badge color={getAlertSeverityColor(alert.cause, alert.effect)} variant="filled">
                                  {alert.effect.replace(/_/g, ' ')}
                                </Badge>
                              )}
                            </Group>
                          </Group>

                          {(alert.description_text?.en || alert.description_text?.['en-US']) && (
                            <Text size="sm">
                              {alert.description_text?.en || alert.description_text?.['en-US']}
                            </Text>
                          )}

                          {alert.informed_entities && alert.informed_entities.length > 0 && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">{t('realtime.affectedEntities', 'Affected Entities')}:</Text>
                              <Group gap="xs">
                                {alert.informed_entities.map((entity, idx) => (
                                  <Badge key={idx} variant="outline" size="sm">
                                    {entity.route_id && `Route: ${entity.route_id}`}
                                    {entity.stop_id && `Stop: ${entity.stop_id}`}
                                    {entity.trip_id && `Trip: ${entity.trip_id}`}
                                    {entity.agency_id && `Agency: ${entity.agency_id}`}
                                  </Badge>
                                ))}
                              </Group>
                            </Box>
                          )}

                          {alert.active_periods && alert.active_periods.length > 0 && (
                            <Text size="xs" c="dimmed">
                              <IconCalendar size={12} style={{ verticalAlign: 'middle' }} />{' '}
                              {t('realtime.activePeriod', 'Active')}: {' '}
                              {alert.active_periods.map((period, idx) => (
                                <span key={idx}>
                                  {period.start ? formatTimestamp(period.start) : t('realtime.now', 'now')}
                                  {' - '}
                                  {period.end ? formatTimestamp(period.end) : t('realtime.indefinite', 'indefinite')}
                                </span>
                              ))}
                            </Text>
                          )}
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Tabs.Panel>

              {/* Trip Modifications Tab */}
              <Tabs.Panel value="tripModifications" pt="md">
                {loading ? (
                  <Group justify="center" p="xl">
                    <Loader />
                  </Group>
                ) : tripModifications.length === 0 ? (
                  <Alert icon={<IconInfoCircle size={16} />} color="gray">
                    {t('realtime.noTripModifications', 'No trip modifications (detours) active')}
                  </Alert>
                ) : (
                  <Stack gap="md">
                    {tripModifications.map((mod) => (
                      <Paper key={mod.id} withBorder p="md" radius="md">
                        <Stack gap="sm">
                          <Group justify="space-between">
                            <Group>
                              <ThemeIcon color="grape" variant="light">
                                <IconDirections size={16} />
                              </ThemeIcon>
                              <Title order={5}>
                                {t('realtime.detour', 'Detour')}: {mod.modification_id}
                              </Title>
                            </Group>
                            <Group gap="xs">
                              {mod.route_id && (
                                <Badge color="blue" variant="light">
                                  {t('realtime.route', 'Route')}: {mod.route_id}
                                </Badge>
                              )}
                              {mod.trip_id && (
                                <Badge color="orange" variant="light">
                                  {t('realtime.trip', 'Trip')}: {mod.trip_id}
                                </Badge>
                              )}
                            </Group>
                          </Group>

                          {/* Selected Trips */}
                          {mod.selected_trips && mod.selected_trips.length > 0 && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">{t('realtime.selectedTrips', 'Selected Trips')}:</Text>
                              {mod.selected_trips.map((st, idx) => (
                                <Box key={idx} mb="xs">
                                  {st.trip_ids && st.trip_ids.length > 0 && (
                                    <Group gap="xs" wrap="wrap">
                                      {st.trip_ids.map((tripId, tidx) => (
                                        <Badge key={tidx} variant="outline" size="sm">{tripId}</Badge>
                                      ))}
                                    </Group>
                                  )}
                                  {st.shape_id && (
                                    <Text size="xs" c="dimmed">Shape: {st.shape_id}</Text>
                                  )}
                                </Box>
                              ))}
                            </Box>
                          )}

                          {/* Service Dates */}
                          {mod.service_dates && mod.service_dates.length > 0 && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">{t('realtime.serviceDates', 'Service Dates')}:</Text>
                              <Group gap="xs">
                                {mod.service_dates.map((date, idx) => (
                                  <Badge key={idx} variant="light" color="teal" size="sm">
                                    <IconCalendar size={10} style={{ marginRight: 4 }} />
                                    {date}
                                  </Badge>
                                ))}
                              </Group>
                            </Box>
                          )}

                          {/* Affected Stops */}
                          {mod.affected_stop_ids && mod.affected_stop_ids.length > 0 && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">{t('realtime.affectedStops', 'Affected Stops')}:</Text>
                              <Group gap="xs">
                                {mod.affected_stop_ids.map((stopId, idx) => (
                                  <Badge key={idx} variant="outline" color="red" size="sm">
                                    <IconMapPin size={10} style={{ marginRight: 4 }} />
                                    {stopId}
                                  </Badge>
                                ))}
                              </Group>
                            </Box>
                          )}

                          {/* Replacement Stops */}
                          {mod.replacement_stops && mod.replacement_stops.length > 0 && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">{t('realtime.replacementStops', 'Replacement Stops')}:</Text>
                              <Group gap="xs">
                                {mod.replacement_stops.map((stop, idx) => (
                                  <Badge key={idx} variant="filled" color="green" size="sm">
                                    <IconMapPin size={10} style={{ marginRight: 4 }} />
                                    {stop.stop_id}
                                    {stop.travel_time && ` (+${Math.floor(stop.travel_time / 60)}min)`}
                                  </Badge>
                                ))}
                              </Group>
                            </Box>
                          )}

                          {/* Modifications Details */}
                          {mod.modifications && mod.modifications.length > 0 && (
                            <Accordion variant="contained" radius="sm">
                              <Accordion.Item value="details">
                                <Accordion.Control>
                                  <Text size="sm">{t('realtime.modificationDetails', 'Modification Details')}</Text>
                                </Accordion.Control>
                                <Accordion.Panel>
                                  {mod.modifications.map((detail, idx) => (
                                    <Paper key={idx} p="sm" mb="xs" withBorder>
                                      <Stack gap="xs">
                                        {detail.start_stop && (
                                          <Group gap="xs">
                                            <Text size="xs" c="dimmed">{t('realtime.startStop', 'Start')}:</Text>
                                            <Badge size="sm" variant="light">
                                              {detail.start_stop.stop_id || `Seq: ${detail.start_stop.stop_sequence}`}
                                            </Badge>
                                          </Group>
                                        )}
                                        {detail.end_stop && (
                                          <Group gap="xs">
                                            <Text size="xs" c="dimmed">{t('realtime.endStop', 'End')}:</Text>
                                            <Badge size="sm" variant="light">
                                              {detail.end_stop.stop_id || `Seq: ${detail.end_stop.stop_sequence}`}
                                            </Badge>
                                          </Group>
                                        )}
                                        {detail.propagated_delay !== undefined && (
                                          <Group gap="xs">
                                            <Text size="xs" c="dimmed">{t('realtime.propagatedDelay', 'Delay')}:</Text>
                                            <Badge size="sm" color={getDelayColor(detail.propagated_delay)}>
                                              {formatDelay(detail.propagated_delay)}
                                            </Badge>
                                          </Group>
                                        )}
                                        {detail.replacement_stops && detail.replacement_stops.length > 0 && (
                                          <Box>
                                            <Text size="xs" c="dimmed">{t('realtime.replacementStops', 'Replacement Stops')}:</Text>
                                            <Group gap="xs" mt="xs">
                                              {detail.replacement_stops.map((rs, ridx) => (
                                                <Badge key={ridx} size="sm" color="green" variant="filled">
                                                  {rs.stop_id}
                                                </Badge>
                                              ))}
                                            </Group>
                                          </Box>
                                        )}
                                        {detail.service_alert_id && (
                                          <Text size="xs" c="dimmed">
                                            {t('realtime.linkedAlert', 'Linked Alert')}: {detail.service_alert_id}
                                          </Text>
                                        )}
                                      </Stack>
                                    </Paper>
                                  ))}
                                </Accordion.Panel>
                              </Accordion.Item>
                            </Accordion>
                          )}
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Tabs.Panel>

              {/* RT Shapes Tab */}
              <Tabs.Panel value="shapes" pt="md">
                {loading ? (
                  <Group justify="center" p="xl">
                    <Loader />
                  </Group>
                ) : shapes.length === 0 ? (
                  <Alert icon={<IconInfoCircle size={16} />} color="gray">
                    {t('realtime.noShapes', 'No real-time shapes (detour paths) available')}
                  </Alert>
                ) : (
                  <Stack gap="md">
                    {shapes.map((shape) => (
                      <Paper key={shape.id} withBorder p="md" radius="md">
                        <Stack gap="sm">
                          <Group justify="space-between">
                            <Group>
                              <ThemeIcon color="cyan" variant="light">
                                <IconShape size={16} />
                              </ThemeIcon>
                              <Title order={5}>
                                {t('realtime.detourShape', 'Detour Shape')}: {shape.shape_id}
                              </Title>
                            </Group>
                            <Group gap="xs">
                              {shape.route_id && (
                                <Badge color="blue" variant="light">
                                  {t('realtime.route', 'Route')}: {shape.route_id}
                                </Badge>
                              )}
                              {shape.modification_id && (
                                <Badge color="grape" variant="light">
                                  {t('realtime.modification', 'Modification')}: {shape.modification_id}
                                </Badge>
                              )}
                            </Group>
                          </Group>

                          {/* Shape Points Summary */}
                          {shape.shape_points && shape.shape_points.length > 0 && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">
                                {t('realtime.shapePoints', 'Shape Points')}: {shape.shape_points.length}
                              </Text>
                              <Group gap="xs">
                                <Badge variant="outline" size="sm">
                                  {t('realtime.start', 'Start')}: {shape.shape_points[0]?.lat?.toFixed(5)}, {shape.shape_points[0]?.lon?.toFixed(5)}
                                </Badge>
                                <IconArrowRight size={12} />
                                <Badge variant="outline" size="sm">
                                  {t('realtime.end', 'End')}: {shape.shape_points[shape.shape_points.length - 1]?.lat?.toFixed(5)}, {shape.shape_points[shape.shape_points.length - 1]?.lon?.toFixed(5)}
                                </Badge>
                              </Group>
                            </Box>
                          )}

                          {/* Encoded Polyline */}
                          {shape.encoded_polyline && (
                            <Box>
                              <Text size="xs" c="dimmed" mb="xs">{t('realtime.encodedPolyline', 'Encoded Polyline')}:</Text>
                              <Code block style={{ maxHeight: 100, overflow: 'auto' }}>
                                {shape.encoded_polyline}
                              </Code>
                            </Box>
                          )}

                          {/* Timestamp */}
                          {shape.timestamp && (
                            <Text size="xs" c="dimmed">
                              <IconClock size={12} style={{ verticalAlign: 'middle' }} />{' '}
                              {t('realtime.lastUpdate', 'Last Update')}: {formatTimestamp(shape.timestamp)}
                            </Text>
                          )}
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Tabs.Panel>

              {/* RT Stops Tab */}
              <Tabs.Panel value="stops" pt="md">
                {loading ? (
                  <Group justify="center" p="xl">
                    <Loader />
                  </Group>
                ) : stops.length === 0 ? (
                  <Alert icon={<IconInfoCircle size={16} />} color="gray">
                    {t('realtime.noRtStops', 'No real-time stops (temporary/replacement stops) available')}
                  </Alert>
                ) : (
                  <ScrollArea>
                    <Table striped highlightOnHover>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>{t('realtime.stopId', 'Stop ID')}</Table.Th>
                          <Table.Th>{t('realtime.stopName', 'Stop Name')}</Table.Th>
                          <Table.Th>{t('realtime.position', 'Position')}</Table.Th>
                          <Table.Th>{t('realtime.stopCode', 'Code')}</Table.Th>
                          <Table.Th>{t('realtime.modification', 'Modification')}</Table.Th>
                          <Table.Th>{t('realtime.route', 'Route')}</Table.Th>
                          <Table.Th>{t('realtime.accessibility', 'Accessibility')}</Table.Th>
                          <Table.Th>{t('realtime.lastUpdate', 'Last Update')}</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {stops.map((stop) => (
                          <Table.Tr key={stop.id}>
                            <Table.Td>
                              <Group gap="xs">
                                <IconMapPinFilled size={16} color="teal" />
                                <Text fw={500}>{stop.stop_id}</Text>
                              </Group>
                            </Table.Td>
                            <Table.Td>
                              <Text>{stop.stop_name || '-'}</Text>
                              {stop.stop_desc && (
                                <Text size="xs" c="dimmed">{stop.stop_desc}</Text>
                              )}
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm" c="dimmed">
                                {stop.stop_lat?.toFixed(5)}, {stop.stop_lon?.toFixed(5)}
                              </Text>
                            </Table.Td>
                            <Table.Td>
                              {stop.stop_code ? (
                                <Badge variant="light">{stop.stop_code}</Badge>
                              ) : '-'}
                            </Table.Td>
                            <Table.Td>
                              {stop.modification_id ? (
                                <Badge color="grape" variant="light">{stop.modification_id}</Badge>
                              ) : '-'}
                            </Table.Td>
                            <Table.Td>
                              {stop.route_id ? (
                                <Badge color="blue" variant="light">{stop.route_id}</Badge>
                              ) : '-'}
                            </Table.Td>
                            <Table.Td>
                              {stop.wheelchair_boarding === 1 ? (
                                <Badge color="green" variant="light">{t('realtime.accessible', 'Accessible')}</Badge>
                              ) : stop.wheelchair_boarding === 2 ? (
                                <Badge color="red" variant="light">{t('realtime.notAccessible', 'Not Accessible')}</Badge>
                              ) : (
                                <Badge color="gray" variant="light">{t('common.unknown', 'Unknown')}</Badge>
                              )}
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm">{formatTimestamp(stop.timestamp)}</Text>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </ScrollArea>
                )}
              </Tabs.Panel>
            </Tabs>
          </Paper>
        )}

        {/* No Agency Selected State */}
        {!selectedAgencyId && (
          <Paper withBorder p="xl" radius="md">
            <Stack align="center" gap="md">
              <ThemeIcon size={60} radius="xl" color="gray" variant="light">
                <IconBus size={30} />
              </ThemeIcon>
              <Title order={3}>{t('realtime.selectAgencyPrompt', 'Select an Agency')}</Title>
              <Text c="dimmed" ta="center" maw={400}>
                {t('realtime.selectAgencyDescription', 'Choose an agency from the dropdown above to view real-time GTFS data including vehicle positions, trip updates, service alerts, and detours.')}
              </Text>
            </Stack>
          </Paper>
        )}
      </Stack>

      {/* CSS for spin animation */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin {
          animation: spin 1s linear infinite;
        }
      `}</style>
    </Container>
  )
}
