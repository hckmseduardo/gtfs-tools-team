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
  NumberInput,
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
  IconClock,
  IconMapPin,
  IconArrowUp,
  IconArrowDown,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
} from '@tabler/icons-react'
import { agencyApi, tripsApi, stopsApi, stopTimesApi, type Agency, type TripWithDetails } from '../lib/gtfs-api'
import { api } from '../lib/api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { useTranslation } from 'react-i18next'

interface Stop {
  feed_id: number
  stop_id: string
  stop_name: string
  stop_lat: number
  stop_lon: number
}

interface StopTime {
  feed_id: number
  trip_id: string
  stop_id: string
  stop_sequence: number
  arrival_time: string
  departure_time: string
  stop_headsign?: string
  pickup_type: number
  drop_off_type: number
  stop_name?: string
  stop_code?: string
}

export default function StopTimes() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')

  // Create translated pickup/dropoff options
  const getPickupDropOffOptions = () => [
    { value: '0', label: t('stopTimes.pickupTypes.0') },
    { value: '1', label: t('stopTimes.pickupTypes.1') },
    { value: '2', label: t('stopTimes.pickupTypes.2') },
    { value: '3', label: t('stopTimes.pickupTypes.3') },
  ]

  const getPickupLabel = (type: number) => t(`stopTimes.pickupTypes.${type}`) || t('common.noData')
  const getDropOffLabel = (type: number) => t(`stopTimes.dropOffTypes.${type}`) || t('common.noData')
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [trips, setTrips] = useState<TripWithDetails[]>([])
  const [stops, setStops] = useState<Stop[]>([])
  const [stopTimes, setStopTimes] = useState<StopTime[]>([])
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [selectedTrip, setSelectedTrip] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingStopTime, setEditingStopTime] = useState<StopTime | null>(null)
  const [expandedStopTimeId, setExpandedStopTimeId] = useState<string | null>(null)

  const form = useForm({
    initialValues: {
      stop_id: '',
      stop_sequence: 0,
      arrival_time: '',
      departure_time: '',
      stop_headsign: '',
      pickup_type: '0',
      drop_off_type: '0',
    },
    validate: {
      stop_id: (value) => (!value ? t('stopTimes.stopRequired') : null),
      arrival_time: (value) => {
        if (!value) return t('stopTimes.arrivalRequired')
        if (!/^\d{1,2}:\d{2}:\d{2}$/.test(value)) return t('stopTimes.timeFormat')
        return null
      },
      departure_time: (value) => {
        if (!value) return t('stopTimes.departureRequired')
        if (!/^\d{1,2}:\d{2}:\d{2}$/.test(value)) return t('stopTimes.timeFormat')
        return null
      },
      stop_sequence: (value) => (value < 0 ? t('stopTimes.sequenceRange') : null),
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadTrips()
      loadStops()
    }
  }, [selectedAgency, selectedFeed])

  useEffect(() => {
    if (selectedTrip) {
      loadStopTimes()
    }
  }, [selectedTrip])

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

  const loadTrips = async () => {
    if (!selectedFeed) {
      setTrips([])
      setSelectedTrip(null)
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const response = await tripsApi.list(feed_id, { limit: 1000 })
      setTrips(response.items || [])
      if (response.items?.length > 0) {
        setSelectedTrip(response.items[0].trip_id)
      } else {
        setSelectedTrip(null)
      }
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('trips.loadError'),
        color: 'red',
      })
    }
  }

  const loadStops = async () => {
    if (!selectedFeed) {
      setStops([])
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const response = await stopsApi.list(feed_id, { limit: 10000 })
      setStops(response.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('stops.loadError'),
        color: 'red',
      })
    }
  }

  const loadStopTimes = async () => {
    if (!selectedFeed || !selectedTrip) {
      setStopTimes([])
      return
    }

    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const response = await stopTimesApi.listForTrip(feed_id, selectedTrip)
      setStopTimes(response.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('stopTimes.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = () => {
    if (!selectedFeed || !selectedTrip) {
      notifications.show({
        title: t('common.error'),
        message: t('stopTimes.selectTrip'),
        color: 'red',
      })
      return
    }

    setEditingStopTime(null)
    form.reset()
    if (stopTimes.length > 0) {
      const maxSequence = Math.max(...stopTimes.map(st => st.stop_sequence))
      form.setFieldValue('stop_sequence', maxSequence + 1)
    }
    open()
  }

  const handleEdit = (stopTime: StopTime) => {
    setEditingStopTime(stopTime)
    form.setValues({
      stop_id: stopTime.stop_id,
      stop_sequence: stopTime.stop_sequence,
      arrival_time: stopTime.arrival_time,
      departure_time: stopTime.departure_time,
      stop_headsign: stopTime.stop_headsign || '',
      pickup_type: String(stopTime.pickup_type),
      drop_off_type: String(stopTime.drop_off_type),
    })
    open()
  }

  const handleDelete = (stopTime: StopTime) => {
    modals.openConfirmModal({
      title: t('stopTimes.deleteStopTime'),
      children: (
        <Text size="sm">
          {t('stopTimes.deleteConfirm')}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          await stopTimesApi.delete(stopTime.feed_id, stopTime.trip_id, stopTime.stop_sequence)
          notifications.show({
            title: t('common.success'),
            message: t('stopTimes.deleteSuccess'),
            color: 'green',
          })
          loadStopTimes()
        } catch (error) {
          notifications.show({
            title: t('common.error'),
            message: t('stopTimes.deleteError'),
            color: 'red',
          })
        }
      },
    })
  }

  const handleMoveUp = async (stopTime: StopTime) => {
    try {
      const currentIndex = stopTimes.findIndex(st =>
        st.feed_id === stopTime.feed_id &&
        st.trip_id === stopTime.trip_id &&
        st.stop_sequence === stopTime.stop_sequence
      )
      if (currentIndex > 0) {
        const previousStopTime = stopTimes[currentIndex - 1]
        await stopTimesApi.update(stopTime.feed_id, stopTime.trip_id, stopTime.stop_sequence, {
          stop_sequence: previousStopTime.stop_sequence
        })
        await stopTimesApi.update(previousStopTime.feed_id, previousStopTime.trip_id, previousStopTime.stop_sequence, {
          stop_sequence: stopTime.stop_sequence
        })
        notifications.show({
          title: t('common.success'),
          message: t('stopTimes.sequenceUpdated'),
          color: 'green',
        })
        loadStopTimes()
      }
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('stopTimes.sequenceError'),
        color: 'red',
      })
    }
  }

  const handleMoveDown = async (stopTime: StopTime) => {
    try {
      const currentIndex = stopTimes.findIndex(st =>
        st.feed_id === stopTime.feed_id &&
        st.trip_id === stopTime.trip_id &&
        st.stop_sequence === stopTime.stop_sequence
      )
      if (currentIndex < stopTimes.length - 1) {
        const nextStopTime = stopTimes[currentIndex + 1]
        await stopTimesApi.update(stopTime.feed_id, stopTime.trip_id, stopTime.stop_sequence, {
          stop_sequence: nextStopTime.stop_sequence
        })
        await stopTimesApi.update(nextStopTime.feed_id, nextStopTime.trip_id, nextStopTime.stop_sequence, {
          stop_sequence: stopTime.stop_sequence
        })
        notifications.show({
          title: t('common.success'),
          message: t('stopTimes.sequenceUpdated'),
          color: 'green',
        })
        loadStopTimes()
      }
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('stopTimes.sequenceError'),
        color: 'red',
      })
    }
  }

  const handleSubmit = async (values: typeof form.values) => {
    if (!selectedFeed || !selectedTrip) {
      notifications.show({
        title: t('common.error'),
        message: t('stopTimes.selectTrip'),
        color: 'red',
      })
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const stopTimeData = {
        stop_id: values.stop_id,
        stop_sequence: values.stop_sequence,
        arrival_time: values.arrival_time,
        departure_time: values.departure_time,
        stop_headsign: values.stop_headsign || undefined,
        pickup_type: parseInt(values.pickup_type),
        drop_off_type: parseInt(values.drop_off_type),
      }

      if (editingStopTime) {
        await stopTimesApi.update(feed_id, selectedTrip, editingStopTime.stop_sequence, stopTimeData)
        notifications.show({
          title: t('common.success'),
          message: t('stopTimes.updateSuccess'),
          color: 'green',
        })
      } else {
        await stopTimesApi.create(feed_id, selectedTrip, stopTimeData)
        notifications.show({
          title: t('common.success'),
          message: t('stopTimes.createSuccess'),
          color: 'green',
        })
      }

      close()
      loadStopTimes()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('stopTimes.saveError'),
        color: 'red',
      })
    }
  }

  const getSelectedTripInfo = () => {
    const trip = trips.find(t => t.trip_id === selectedTrip)
    return trip ? `${trip.trip_id} - ${trip.trip_headsign || t('trips.noHeadsign')}` : t('trips.noTripSelected')
  }

  // Mobile StopTime Card Component
  const StopTimeCard = ({ stopTime, index }: { stopTime: StopTime; index: number }) => {
    const stopTimeKey = `${stopTime.feed_id}:${stopTime.trip_id}:${stopTime.stop_sequence}`
    const isExpanded = expandedStopTimeId === stopTimeKey

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedStopTimeId(isExpanded ? null : stopTimeKey)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                <Badge size="lg" variant="filled" style={{ flexShrink: 0 }}>
                  {stopTime.stop_sequence}
                </Badge>
                <Box style={{ minWidth: 0 }}>
                  <Text fw={600} size="sm" truncate>
                    {stopTime.stop_name}
                  </Text>
                  <Group gap={4}>
                    <Code fz="xs">{stopTime.arrival_time}</Code>
                    <Text size="xs" c="dimmed">-</Text>
                    <Code fz="xs">{stopTime.departure_time}</Code>
                  </Group>
                </Box>
              </Group>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              {stopTime.stop_code && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('stops.stopCode')}:</Text>
                  <Code fz="xs">{stopTime.stop_code}</Code>
                </Group>
              )}

              {stopTime.stop_headsign && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('stopTimes.headsign')}:</Text>
                  <Text size="sm">{stopTime.stop_headsign}</Text>
                </Group>
              )}

              <Group gap="xs">
                <Badge size="xs" color="blue">
                  P: {getPickupLabel(stopTime.pickup_type)}
                </Badge>
                <Badge size="xs" color="teal">
                  D: {getDropOffLabel(stopTime.drop_off_type)}
                </Badge>
              </Group>

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleMoveUp(stopTime)}
                  leftSection={<IconArrowUp size={16} />}
                  disabled={index === 0}
                  fullWidth
                >
                  {t('stopTimes.moveUp')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleMoveDown(stopTime)}
                  leftSection={<IconArrowDown size={16} />}
                  disabled={index === stopTimes.length - 1}
                  fullWidth
                >
                  {t('stopTimes.moveDown')}
                </Button>
              </SimpleGrid>

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleEdit(stopTime)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="red"
                  onClick={() => handleDelete(stopTime)}
                  leftSection={<IconTrash size={16} />}
                  fullWidth
                >
                  {t('common.delete')}
                </Button>
              </SimpleGrid>
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
                <Title order={3}>{t('stopTimes.title')}</Title>
                <Text c="dimmed" size="xs">
                  {t('stopTimes.description')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadStopTimes} loading={loading}>
                  <IconRefresh size={18} />
                </ActionIcon>
                <ActionIcon variant="filled" size="lg" onClick={handleCreate} disabled={!selectedTrip}>
                  <IconPlus size={18} />
                </ActionIcon>
              </Group>
            </Group>
          </Stack>
        ) : (
          <Group justify="space-between">
            <div>
              <Title order={2}>{t('stopTimes.title')}</Title>
              <Text c="dimmed" size="sm">
                {t('stopTimes.description')}
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleCreate} disabled={!selectedTrip}>
              {t('stopTimes.newStopTime')}
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
              label={t('trips.title')}
              placeholder={t('trips.selectTrip')}
              data={trips.map((trip) => ({
                value: trip.trip_id,
                label: `${trip.trip_id} - ${trip.trip_headsign || t('trips.noHeadsign')}`,
              }))}
              value={selectedTrip}
              onChange={(value) => setSelectedTrip(value)}
              disabled={!selectedFeed}
              searchable
              size={isMobile ? 'sm' : 'md'}
            />
          </Stack>
        </Paper>

        {/* Selected Trip Info */}
        {selectedTrip && (
          <Group gap="xs" wrap="wrap">
            <Badge leftSection={<IconClock size={14} />} color="blue">
              {getSelectedTripInfo()}
            </Badge>
            <Badge leftSection={<IconMapPin size={14} />} color="green">
              {stopTimes.length} {t('stopTimes.stops')}
            </Badge>
          </Group>
        )}

        {/* StopTimes List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {stopTimes.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">
                  {selectedTrip ? t('stopTimes.noStopTimes') : t('stopTimes.selectTrip')}
                </Text>
              </Paper>
            ) : (
              stopTimes.map((stopTime, index) => (
                <StopTimeCard key={`${stopTime.feed_id}:${stopTime.trip_id}:${stopTime.stop_sequence}`} stopTime={stopTime} index={index} />
              ))
            )}
          </Stack>
        ) : (
          /* Desktop Table */
          <Paper shadow="xs" p="md" pos="relative">
            <LoadingOverlay visible={loading} />

            {stopTimes.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">
                {selectedTrip ? t('stopTimes.noStopTimes') : t('stopTimes.selectTrip')}
              </Text>
            ) : (
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('stopTimes.sequence')}</Table.Th>
                    <Table.Th>{t('stops.title')}</Table.Th>
                    <Table.Th>{t('stopTimes.arrival')}</Table.Th>
                    <Table.Th>{t('stopTimes.departure')}</Table.Th>
                    <Table.Th>{t('stopTimes.headsign')}</Table.Th>
                    <Table.Th>{t('stopTimes.pickupDropoff')}</Table.Th>
                    <Table.Th>{t('common.actions')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {stopTimes.map((stopTime, index) => (
                    <Table.Tr key={`${stopTime.feed_id}:${stopTime.trip_id}:${stopTime.stop_sequence}`}>
                      <Table.Td>
                        <Group gap="xs">
                          <Badge size="lg" variant="filled">
                            {stopTime.stop_sequence}
                          </Badge>
                          <div>
                            <Tooltip label={t('stopTimes.moveUp')}>
                              <ActionIcon size="sm" variant="subtle" disabled={index === 0} onClick={() => handleMoveUp(stopTime)}>
                                <IconArrowUp size={14} />
                              </ActionIcon>
                            </Tooltip>
                            <Tooltip label={t('stopTimes.moveDown')}>
                              <ActionIcon size="sm" variant="subtle" disabled={index === stopTimes.length - 1} onClick={() => handleMoveDown(stopTime)}>
                                <IconArrowDown size={14} />
                              </ActionIcon>
                            </Tooltip>
                          </div>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <div>
                          <Text size="sm" fw={500}>{stopTime.stop_name}</Text>
                          {stopTime.stop_code && <Code>{stopTime.stop_code}</Code>}
                        </div>
                      </Table.Td>
                      <Table.Td><Code>{stopTime.arrival_time}</Code></Table.Td>
                      <Table.Td><Code>{stopTime.departure_time}</Code></Table.Td>
                      <Table.Td>
                        <Text size="sm" c={stopTime.stop_headsign ? undefined : "dimmed"}>
                          {stopTime.stop_headsign || '-'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4}>
                          <Badge size="xs" color="blue">
                            P: {getPickupLabel(stopTime.pickup_type)}
                          </Badge>
                          <Badge size="xs" color="teal">
                            D: {getDropOffLabel(stopTime.drop_off_type)}
                          </Badge>
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
                            <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => handleEdit(stopTime)}>
                              {t('common.edit')}
                            </Menu.Item>
                            <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={() => handleDelete(stopTime)}>
                              {t('common.delete')}
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
        )}
      </Stack>

      {/* Create/Edit Modal */}
      <Modal
        opened={opened}
        onClose={close}
        title={editingStopTime ? t('stopTimes.editStopTime') : t('stopTimes.newStopTime')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <Select
              label={t('stops.title')}
              placeholder={t('stops.selectStop')}
              required
              searchable
              data={stops.map((s) => ({
                value: s.stop_id,
                label: `${s.stop_name} (${s.stop_id})`,
              }))}
              {...form.getInputProps('stop_id')}
            />

            <NumberInput
              label={t('stopTimes.sequence')}
              placeholder="0"
              required
              min={0}
              {...form.getInputProps('stop_sequence')}
            />

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <TextInput
                label={t('stopTimes.arrival')}
                placeholder="08:30:00"
                required
                {...form.getInputProps('arrival_time')}
              />
              <TextInput
                label={t('stopTimes.departure')}
                placeholder="08:31:00"
                required
                {...form.getInputProps('departure_time')}
              />
            </SimpleGrid>

            <TextInput
              label={t('stopTimes.headsign')}
              placeholder={t('stopTimes.headsignPlaceholder')}
              {...form.getInputProps('stop_headsign')}
            />

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <Select
                label={t('stopTimes.pickupType')}
                data={getPickupDropOffOptions()}
                {...form.getInputProps('pickup_type')}
              />
              <Select
                label={t('stopTimes.dropoffType')}
                data={getPickupDropOffOptions()}
                {...form.getInputProps('drop_off_type')}
              />
            </SimpleGrid>

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button type="submit">{editingStopTime ? t('common.update') : t('common.create')}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Container>
  )
}
