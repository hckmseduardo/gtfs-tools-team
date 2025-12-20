import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Button,
  Paper,
  Table,
  Badge,
  ActionIcon,
  Modal,
  TextInput,
  Select,
  LoadingOverlay,
  Menu,
  Tooltip,
  Code,
  Card,
  Box,
  Collapse,
  UnstyledButton,
  Divider,
  SimpleGrid,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconDots,
  IconWheelchair,
  IconWheelchairOff,
  IconQuestionMark,
  IconBike,
  IconBikeOff,
  IconCar,
  IconCarOff,
  IconArrowRight,
  IconArrowLeft,
  IconCopy,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
} from '@tabler/icons-react'
import {
  tripsApi,
  routesApi,
  calendarsApi,
  agencyApi,
  shapesApi,
  type TripWithDetails,
  type Route,
  type Calendar,
  type Agency,
} from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { useTranslation } from 'react-i18next'

const DIRECTION_OPTIONS = [
  { value: '0', label: 'Outbound', icon: IconArrowRight },
  { value: '1', label: 'Inbound', icon: IconArrowLeft },
]

const WHEELCHAIR_OPTIONS = [
  { value: '0', label: 'No information', icon: IconQuestionMark },
  { value: '1', label: 'Accessible', icon: IconWheelchair },
  { value: '2', label: 'Not accessible', icon: IconWheelchairOff },
]

const BIKES_OPTIONS = [
  { value: '0', label: 'No information', icon: IconQuestionMark },
  { value: '1', label: 'Allowed', icon: IconBike },
  { value: '2', label: 'Not allowed', icon: IconBikeOff },
]

const CARS_OPTIONS = [
  { value: '0', label: 'No information', icon: IconQuestionMark },
  { value: '1', label: 'Allowed', icon: IconCar },
  { value: '2', label: 'Not allowed', icon: IconCarOff },
]

export default function Trips() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [trips, setTrips] = useState<TripWithDetails[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [calendars, setCalendars] = useState<Calendar[]>([])
  const [shapeIds, setShapeIds] = useState<string[]>([])
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingTrip, setEditingTrip] = useState<TripWithDetails | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [expandedTripId, setExpandedTripId] = useState<string | null>(null)
  const pageSize = 50

  const form = useForm({
    initialValues: {
      trip_id: '',
      route_id: '',
      service_id: '',
      trip_headsign: '',
      trip_short_name: '',
      direction_id: '',
      block_id: '',
      shape_id: '',
      wheelchair_accessible: '0',
      bikes_allowed: '0',
      cars_allowed: '0',
    },
    validate: {
      trip_id: (value) => (!value ? t('trips.tripIdRequired') : null),
      route_id: (value) => (!value ? t('trips.routeRequired') : null),
      service_id: (value) => (!value ? t('trips.serviceRequired') : null),
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadRoutes()
    }
  }, [selectedAgency, selectedFeed])

  useEffect(() => {
    if (selectedFeed) {
      loadCalendars()
      loadShapes()
    } else {
      setCalendars([])
      setShapeIds([])
    }
  }, [selectedFeed])

  useEffect(() => {
    if (selectedRoute) {
      loadTrips()
    }
  }, [selectedRoute, page])

  const loadAgencies = async () => {
    try {
      const response = await agencyApi.list()
      setAgencies(response.items || [])
      if (response.items?.length > 0) {
        setSelectedAgency(response.items[0].id)
      }
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('agencies.loadError'),
        color: 'red',
      })
    }
  }

  const loadRoutes = async () => {
    if (!selectedFeed) {
      setRoutes([])
      setSelectedRoute(null)
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const response = await routesApi.list(feed_id, { limit: 1000 })
      setRoutes(response.items || [])
      if (response.items?.length > 0) {
        setSelectedRoute(response.items[0].route_id)
      } else {
        setSelectedRoute(null)
      }
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('routes.loadError'),
        color: 'red',
      })
    }
  }

  const loadCalendars = async () => {
    if (!selectedFeed) {
      setCalendars([])
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const response = await calendarsApi.list(feed_id, { limit: 1000 })
      setCalendars(response.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('calendars.loadError'),
        color: 'red',
      })
    }
  }

  const loadShapes = async () => {
    if (!selectedFeed) {
      setShapeIds([])
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const ids = await shapesApi.listShapeIds(feed_id)
      setShapeIds(ids || [])
    } catch (error) {
      // Shapes are optional, don't show error
      setShapeIds([])
    }
  }

  const loadTrips = async () => {
    if (!selectedFeed || !selectedRoute) {
      setTrips([])
      setTotal(0)
      return
    }

    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const response = await tripsApi.listWithDetails(feed_id, {
        route_id: selectedRoute,
        skip: (page - 1) * pageSize,
        limit: pageSize,
      })
      setTrips(response.items || [])
      setTotal(response.total || 0)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('trips.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = () => {
    if (!selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: 'Please select a feed first',
        color: 'red',
      })
      return
    }

    setEditingTrip(null)
    form.reset()
    if (selectedRoute) {
      form.setFieldValue('route_id', selectedRoute)
    }
    open()
  }

  const handleEdit = (trip: TripWithDetails) => {
    setEditingTrip(trip)
    form.setValues({
      trip_id: trip.trip_id,
      route_id: String(trip.route_id),
      service_id: String(trip.service_id),
      trip_headsign: trip.trip_headsign || '',
      trip_short_name: trip.trip_short_name || '',
      direction_id: trip.direction_id !== null && trip.direction_id !== undefined ? String(trip.direction_id) : '',
      block_id: trip.block_id || '',
      shape_id: trip.shape_id || '',
      wheelchair_accessible: String(trip.wheelchair_accessible ?? 0),
      bikes_allowed: String(trip.bikes_allowed ?? 0),
      cars_allowed: String(trip.cars_allowed ?? 0),
    })
    open()
  }

  const handleDelete = (trip: TripWithDetails) => {
    modals.openConfirmModal({
      title: t('trips.deleteTrip'),
      children: (
        <Text size="sm">
          {t('trips.deleteConfirm', { id: trip.trip_id })}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          await tripsApi.delete(trip.feed_id, trip.trip_id)
          notifications.show({
            title: t('common.success'),
            message: t('trips.deleteSuccess'),
            color: 'green',
          })
          loadTrips()
        } catch (error) {
          notifications.show({
            title: t('common.error'),
            message: t('trips.deleteError'),
            color: 'red',
          })
        }
      },
    })
  }

  const handleCopy = (trip: TripWithDetails) => {
    modals.open({
      title: t('trips.copyTrip'),
      children: (
        <Stack>
          <Text size="sm">
            {t('trips.copyDescription', { id: trip.trip_id })}
          </Text>
          <TextInput
            label={t('trips.newTripId')}
            placeholder={t('trips.newTripIdPlaceholder')}
            required
            id="copy-trip-id"
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => modals.closeAll()}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={async () => {
                const input = document.getElementById('copy-trip-id') as HTMLInputElement
                const newTripId = input?.value
                if (!newTripId) {
                  notifications.show({
                    title: t('common.error'),
                    message: t('trips.tripIdRequired'),
                    color: 'red',
                  })
                  return
                }
                try {
                  await tripsApi.copy(trip.feed_id, trip.trip_id, newTripId, true)
                  notifications.show({
                    title: t('common.success'),
                    message: t('trips.copySuccess'),
                    color: 'green',
                  })
                  modals.closeAll()
                  loadTrips()
                } catch (error) {
                  notifications.show({
                    title: t('common.error'),
                    message: t('trips.copyError'),
                    color: 'red',
                  })
                }
              }}
            >
              {t('common.copy')}
            </Button>
          </Group>
        </Stack>
      ),
    })
  }

  const handleSubmit = async (values: typeof form.values) => {
    if (!selectedAgency || !selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: 'Please select a feed first',
        color: 'red',
      })
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const tripData = {
        feed_id: feed_id,
        trip_id: values.trip_id,
        route_id: values.route_id,
        service_id: values.service_id,
        trip_headsign: values.trip_headsign || undefined,
        trip_short_name: values.trip_short_name || undefined,
        direction_id: values.direction_id ? parseInt(values.direction_id) : undefined,
        block_id: values.block_id || undefined,
        shape_id: values.shape_id || undefined,
        wheelchair_accessible: parseInt(values.wheelchair_accessible),
        bikes_allowed: parseInt(values.bikes_allowed),
        cars_allowed: parseInt(values.cars_allowed),
      }

      if (editingTrip) {
        await tripsApi.update(feed_id, editingTrip.trip_id, tripData)
        notifications.show({
          title: t('common.success'),
          message: t('trips.updateSuccess'),
          color: 'green',
        })
      } else {
        await tripsApi.create(feed_id, tripData)
        notifications.show({
          title: t('common.success'),
          message: t('trips.createSuccess'),
          color: 'green',
        })
      }

      close()
      loadTrips()
    } catch (error: any) {
      let errorMessage = t('trips.saveError')
      const detail = error?.response?.data?.detail
      if (typeof detail === 'string') {
        errorMessage = detail
      } else if (Array.isArray(detail) && detail.length > 0) {
        // Pydantic validation errors
        errorMessage = detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join(', ')
      }
      notifications.show({
        title: t('common.error'),
        message: errorMessage,
        color: 'red',
      })
    }
  }

  const getDirectionLabel = (directionId: number | undefined) => {
    if (directionId === null || directionId === undefined) return '-'
    return DIRECTION_OPTIONS.find((d) => d.value === String(directionId))?.label || 'Unknown'
  }

  const getServiceName = (serviceId: string) => {
    const calendar = calendars.find((c) => c.service_id === serviceId)
    return calendar?.service_id || `Service ${serviceId}`
  }

  // Mobile Trip Card Component
  const TripCard = ({ trip }: { trip: TripWithDetails }) => {
    const isExpanded = expandedTripId === trip.trip_id

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedTripId(isExpanded ? null : trip.trip_id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Text fw={600} size="sm" truncate>
                  {trip.trip_headsign || trip.trip_id}
                </Text>
                <Text size="xs" c="dimmed" truncate>
                  {trip.trip_id}
                </Text>
              </Box>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Badge size="sm" variant="filled">
                  {trip.stop_count} stops
                </Badge>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              {trip.trip_short_name && (
                <Text size="sm" c="dimmed">
                  {trip.trip_short_name}
                </Text>
              )}

              <Group gap="xs" wrap="wrap">
                {trip.direction_id !== null && trip.direction_id !== undefined && (
                  <Badge variant="light" size="sm" leftSection={
                    trip.direction_id === 0 ? <IconArrowRight size={12} /> : <IconArrowLeft size={12} />
                  }>
                    {getDirectionLabel(trip.direction_id)}
                  </Badge>
                )}
                <Badge variant="outline" size="sm">
                  {getServiceName(trip.service_id)}
                </Badge>
              </Group>

              {trip.first_departure && trip.last_arrival && (
                <Box>
                  <Text size="xs" c="dimmed" mb={2}>{t('trips.times')}</Text>
                  <Code fz="xs">{trip.first_departure} - {trip.last_arrival}</Code>
                </Box>
              )}

              <Group gap="xs">
                <Tooltip label={WHEELCHAIR_OPTIONS.find(w => w.value === String(trip.wheelchair_accessible ?? 0))?.label}>
                  <div>
                    {trip.wheelchair_accessible === 1 ? (
                      <IconWheelchair size={18} color="green" />
                    ) : trip.wheelchair_accessible === 2 ? (
                      <IconWheelchairOff size={18} color="red" />
                    ) : (
                      <IconQuestionMark size={18} color="gray" />
                    )}
                  </div>
                </Tooltip>
                <Tooltip label={BIKES_OPTIONS.find(b => b.value === String(trip.bikes_allowed ?? 0))?.label}>
                  <div>
                    {trip.bikes_allowed === 1 ? (
                      <IconBike size={18} color="green" />
                    ) : trip.bikes_allowed === 2 ? (
                      <IconBikeOff size={18} color="red" />
                    ) : (
                      <IconQuestionMark size={18} color="gray" />
                    )}
                  </div>
                </Tooltip>
              </Group>

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleEdit(trip)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="blue"
                  onClick={() => handleCopy(trip)}
                  leftSection={<IconCopy size={16} />}
                  fullWidth
                >
                  {t('common.copy')}
                </Button>
              </SimpleGrid>

              <Button
                variant="light"
                size="sm"
                color="red"
                onClick={() => handleDelete(trip)}
                leftSection={<IconTrash size={16} />}
                fullWidth
              >
                {t('common.delete')}
              </Button>
            </Stack>
          </Collapse>
        </Stack>
      </Card>
    )
  }

  return (
    <Container size="xl" py={isMobile ? 'sm' : 'xl'} px={isMobile ? 'xs' : 'md'}>
      <Stack gap="lg">
        {/* Header */}
        {isMobile ? (
          <Stack gap="xs">
            <Group justify="space-between" align="flex-start">
              <Box>
                <Title order={3}>{t('trips.title')}</Title>
                <Text c="dimmed" size="xs">
                  {t('trips.description')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadTrips} loading={loading}>
                  <IconRefresh size={18} />
                </ActionIcon>
                <ActionIcon variant="filled" size="lg" onClick={handleCreate} disabled={!selectedFeed}>
                  <IconPlus size={18} />
                </ActionIcon>
              </Group>
            </Group>
          </Stack>
        ) : (
          <Group justify="space-between">
            <div>
              <Title order={2}>{t('trips.title')}</Title>
              <Text c="dimmed" size="sm">
                {t('trips.description')}
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleCreate} disabled={!selectedFeed}>
              {t('trips.newTrip')}
            </Button>
          </Group>
        )}

        {/* Filters */}
        <Paper shadow="xs" p={isMobile ? 'sm' : 'md'}>
          <Stack gap="sm">
            <Select
              label={t('agencies.title')}
              placeholder={t('agencies.selectAgency')}
              data={agencies.map((a) => ({ value: String(a.id), label: a.name }))}
              value={selectedAgency ? String(selectedAgency) : null}
              onChange={(value) => setSelectedAgency(value ? parseInt(value) : null)}
              size={isMobile ? 'sm' : 'md'}
            />
            <FeedSelector
              label={t('feeds.title')}
              agencyId={selectedAgency}
              value={selectedFeed}
              onChange={setSelectedFeed}
              showAllOption={true}
            />
            <Select
              label={t('routes.title')}
              placeholder={t('routes.selectRoute')}
              data={routes.map((r) => ({
                value: r.route_id,
                label: `${r.route_short_name} - ${r.route_long_name}`,
              }))}
              value={selectedRoute}
              onChange={(value) => setSelectedRoute(value)}
              disabled={!selectedFeed}
              size={isMobile ? 'sm' : 'md'}
            />
          </Stack>
        </Paper>

        {/* Trips List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {trips.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">{t('trips.noTrips')}</Text>
              </Paper>
            ) : (
              <>
                {trips.map((trip) => (
                  <TripCard key={`${trip.feed_id}:${trip.trip_id}`} trip={trip} />
                ))}
                <Group justify="space-between" mt="sm">
                  <Text size="xs" c="dimmed">
                    {trips.length} / {total}
                  </Text>
                  <Group gap="xs">
                    <Button size="xs" variant="default" disabled={page === 1} onClick={() => setPage(page - 1)}>
                      {t('common.previous')}
                    </Button>
                    <Button size="xs" variant="default" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
                      {t('common.next')}
                    </Button>
                  </Group>
                </Group>
              </>
            )}
          </Stack>
        ) : (
          /* Desktop Table */
          <Paper shadow="xs" p="md" pos="relative">
            <LoadingOverlay visible={loading} />

            {trips.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">
                {t('trips.noTrips')}
              </Text>
            ) : (
              <>
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('trips.tripId')}</Table.Th>
                      <Table.Th>{t('trips.headsign')}</Table.Th>
                      <Table.Th>{t('trips.direction')}</Table.Th>
                      <Table.Th>{t('trips.service')}</Table.Th>
                      <Table.Th>{t('trips.stops')}</Table.Th>
                      <Table.Th>{t('trips.times')}</Table.Th>
                      <Table.Th>{t('trips.accessibility')}</Table.Th>
                      <Table.Th>{t('common.actions')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {trips.map((trip) => (
                      <Table.Tr key={`${trip.feed_id}:${trip.trip_id}`}>
                        <Table.Td>
                          <Code>{trip.trip_id}</Code>
                        </Table.Td>
                        <Table.Td>
                          <div>
                            <Text size="sm" fw={500}>
                              {trip.trip_headsign || '-'}
                            </Text>
                            {trip.trip_short_name && (
                              <Text size="xs" c="dimmed">
                                {trip.trip_short_name}
                              </Text>
                            )}
                          </div>
                        </Table.Td>
                        <Table.Td>
                          {trip.direction_id !== null && trip.direction_id !== undefined ? (
                            <Badge size="sm" variant="light" leftSection={
                              trip.direction_id === 0 ? <IconArrowRight size={12} /> : <IconArrowLeft size={12} />
                            }>
                              {getDirectionLabel(trip.direction_id)}
                            </Badge>
                          ) : '-'}
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{getServiceName(trip.service_id)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge size="sm" variant="filled">
                            {trip.stop_count}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          {trip.first_departure && trip.last_arrival ? (
                            <Text size="xs">
                              {trip.first_departure} - {trip.last_arrival}
                            </Text>
                          ) : (
                            <Text size="xs" c="dimmed">-</Text>
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Group gap={4}>
                            <Tooltip label={WHEELCHAIR_OPTIONS.find(w => w.value === String(trip.wheelchair_accessible ?? 0))?.label}>
                              <div>
                                {trip.wheelchair_accessible === 1 ? (
                                  <IconWheelchair size={16} color="green" />
                                ) : trip.wheelchair_accessible === 2 ? (
                                  <IconWheelchairOff size={16} color="red" />
                                ) : (
                                  <IconQuestionMark size={16} color="gray" />
                                )}
                              </div>
                            </Tooltip>
                            <Tooltip label={BIKES_OPTIONS.find(b => b.value === String(trip.bikes_allowed ?? 0))?.label}>
                              <div>
                                {trip.bikes_allowed === 1 ? (
                                  <IconBike size={16} color="green" />
                                ) : trip.bikes_allowed === 2 ? (
                                  <IconBikeOff size={16} color="red" />
                                ) : (
                                  <IconQuestionMark size={16} color="gray" />
                                )}
                              </div>
                            </Tooltip>
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          <Menu shadow="md" width={200}>
                            <Menu.Target>
                              <ActionIcon variant="subtle">
                                <IconDots size={16} />
                              </ActionIcon>
                            </Menu.Target>
                            <Menu.Dropdown>
                              <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => handleEdit(trip)}>
                                {t('common.edit')}
                              </Menu.Item>
                              <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => handleCopy(trip)}>
                                {t('common.copy')}
                              </Menu.Item>
                              <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={() => handleDelete(trip)}>
                                {t('common.delete')}
                              </Menu.Item>
                            </Menu.Dropdown>
                          </Menu>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>

                <Group justify="space-between" mt="md">
                  <Text size="sm" c="dimmed">
                    {t('common.showing')} {trips.length} / {total}
                  </Text>
                  <Group>
                    <Button size="xs" variant="default" disabled={page === 1} onClick={() => setPage(page - 1)}>
                      {t('common.previous')}
                    </Button>
                    <Text size="sm">{t('common.page')} {page}</Text>
                    <Button size="xs" variant="default" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
                      {t('common.next')}
                    </Button>
                  </Group>
                </Group>
              </>
            )}
          </Paper>
        )}
      </Stack>

      {/* Create/Edit Modal */}
      <Modal
        opened={opened}
        onClose={close}
        title={editingTrip ? t('trips.editTrip') : t('trips.newTrip')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <TextInput
              label={t('trips.tripId')}
              placeholder="TRIP001"
              required
              {...form.getInputProps('trip_id')}
              disabled={!!editingTrip}
            />

            <Select
              label={t('routes.title')}
              placeholder={t('routes.selectRoute')}
              required
              data={routes.map((r) => ({
                value: r.route_id,
                label: `${r.route_short_name} - ${r.route_long_name}`,
              }))}
              {...form.getInputProps('route_id')}
              disabled={!!editingTrip}
            />

            <Select
              label={t('trips.service')}
              placeholder={t('trips.selectService')}
              required
              data={calendars.map((c) => ({
                value: c.service_id,
                label: `${c.service_id} (${c.start_date} - ${c.end_date})`,
              }))}
              {...form.getInputProps('service_id')}
            />

            <TextInput
              label={t('trips.headsign')}
              placeholder={t('trips.headsignPlaceholder')}
              {...form.getInputProps('trip_headsign')}
            />

            <TextInput
              label={t('trips.shortName')}
              placeholder={t('trips.shortNamePlaceholder')}
              {...form.getInputProps('trip_short_name')}
            />

            <Select
              label={t('trips.direction')}
              placeholder={t('trips.selectDirection')}
              data={DIRECTION_OPTIONS.map((d) => ({ value: d.value, label: d.label }))}
              {...form.getInputProps('direction_id')}
              clearable
            />

            <TextInput
              label={t('trips.blockId')}
              placeholder={t('trips.blockIdPlaceholder')}
              {...form.getInputProps('block_id')}
            />

            <Select
              label={t('trips.shapeId')}
              placeholder={t('trips.selectShape')}
              data={shapeIds.map((id) => ({ value: id, label: id }))}
              {...form.getInputProps('shape_id')}
              clearable
              searchable
            />

            <Select
              label={t('trips.wheelchairAccessible')}
              data={WHEELCHAIR_OPTIONS.map((w) => ({ value: w.value, label: w.label }))}
              {...form.getInputProps('wheelchair_accessible')}
            />

            <Select
              label={t('trips.bikesAllowed')}
              data={BIKES_OPTIONS.map((b) => ({ value: b.value, label: b.label }))}
              {...form.getInputProps('bikes_allowed')}
            />

            <Select
              label={t('trips.carsAllowed')}
              data={CARS_OPTIONS.map((c) => ({ value: c.value, label: c.label }))}
              {...form.getInputProps('cars_allowed')}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button type="submit">{editingTrip ? t('common.update') : t('common.create')}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Container>
  )
}
