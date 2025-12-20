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
  Textarea,
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
  IconMapPin,
  IconWheelchair,
  IconWheelchairOff,
  IconQuestionMark,
  IconBuilding,
  IconDoor,
  IconCircle,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
  IconClock,
  IconCopy,
  IconSearch,
  IconFilter,
  IconX,
} from '@tabler/icons-react'
import { stopsApi, agencyApi, stopTimesApi, type Stop, type Agency, type StopTime } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { useTranslation } from 'react-i18next'

const LOCATION_TYPE_ICONS = {
  '0': IconCircle,
  '1': IconBuilding,
  '2': IconDoor,
  '3': IconCircle,
  '4': IconCircle,
}

const WHEELCHAIR_BOARDING_ICONS = {
  '0': IconQuestionMark,
  '1': IconWheelchair,
  '2': IconWheelchairOff,
}

export default function Stops() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [stops, setStops] = useState<Stop[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingStop, setEditingStop] = useState<Stop | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [expandedStopId, setExpandedStopId] = useState<string | null>(null)
  const pageSize = 50

  // Filter state
  const [searchQuery, setSearchQuery] = useState('')
  const [locationTypeFilter, setLocationTypeFilter] = useState<string | null>(null)
  const [wheelchairFilter, setWheelchairFilter] = useState<string | null>(null)

  // Schedule modal state
  const [scheduleModalOpened, { open: openScheduleModal, close: closeScheduleModal }] = useDisclosure(false)
  const [scheduleStop, setScheduleStop] = useState<Stop | null>(null)
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [stopTimes, setStopTimes] = useState<StopTime[]>([])
  const [stopTimesTotal, setStopTimesTotal] = useState(0)

  // Parent station options (stations for dropdown)
  const [stationOptions, setStationOptions] = useState<{ value: string; label: string }[]>([])
  const [loadingStations, setLoadingStations] = useState(false)

  const form = useForm({
    initialValues: {
      stop_id: '',
      stop_code: '',
      stop_name: '',
      tts_stop_name: '',
      stop_desc: '',
      stop_lat: 0,
      stop_lon: 0,
      zone_id: '',
      stop_url: '',
      location_type: '0',
      parent_station: '',
      stop_timezone: '',
      wheelchair_boarding: '0',
      level_id: '',
      platform_code: '',
    },
    validate: {
      stop_id: (value) => (!value ? t('stops.stopIdRequired') : null),
      stop_name: (value) => (!value ? t('stops.stopNameRequired') : null),
      stop_lat: (value) => {
        const lat = Number(value)
        if (isNaN(lat)) return t('stops.invalidLatitude')
        if (lat < -90 || lat > 90) return t('stops.latitudeRange')
        return null
      },
      stop_lon: (value) => {
        const lon = Number(value)
        if (isNaN(lon)) return t('stops.invalidLongitude')
        if (lon < -180 || lon > 180) return t('stops.longitudeRange')
        return null
      },
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadStops()
    }
  }, [selectedAgency, selectedFeed, page, searchQuery, locationTypeFilter, wheelchairFilter])

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

  const loadStops = async () => {
    if (!selectedFeed) {
      setStops([])
      setTotal(0)
      return
    }

    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const params: {
        skip: number
        limit: number
        search?: string
        wheelchair_accessible?: boolean
        location_type?: number
      } = {
        skip: (page - 1) * pageSize,
        limit: pageSize,
      }

      if (searchQuery) {
        params.search = searchQuery
      }

      if (wheelchairFilter === '1') {
        params.wheelchair_accessible = true
      } else if (wheelchairFilter === '2') {
        params.wheelchair_accessible = false
      }

      if (locationTypeFilter) {
        params.location_type = parseInt(locationTypeFilter)
      }

      const response = await stopsApi.list(feed_id, params)

      // Apply client-side location type filter if backend doesn't support it
      let filteredStops = response.items || []
      if (locationTypeFilter && !params.location_type) {
        const locType = parseInt(locationTypeFilter)
        filteredStops = filteredStops.filter((s: Stop) => s.location_type === locType)
      }

      setStops(filteredStops)
      setTotal(response.total || 0)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('stops.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  // Load stations for parent_station dropdown
  const loadStations = async () => {
    if (!selectedFeed) {
      setStationOptions([])
      return
    }

    setLoadingStations(true)
    try {
      const feed_id = parseInt(selectedFeed)
      // Load all stops (not just stations) so user can select any stop as parent
      // In GTFS, parent_station can reference any stop with location_type 1 (station)
      // but we show all stops for flexibility
      const response = await stopsApi.list(feed_id, { skip: 0, limit: 10000 })
      const options = (response.items || []).map((s: Stop) => ({
        value: s.stop_id,
        label: `${s.stop_name} (${s.stop_id})${s.location_type === 1 ? ' - Station' : ''}`,
      }))
      setStationOptions(options)
    } catch (error) {
      console.error('Failed to load stations:', error)
      setStationOptions([])
    } finally {
      setLoadingStations(false)
    }
  }

  const handleCreate = () => {
    setEditingStop(null)
    form.reset()
    loadStations()
    open()
  }

  const handleEdit = (stop: Stop) => {
    setEditingStop(stop)
    form.setValues({
      stop_id: stop.stop_id,
      stop_code: stop.stop_code || '',
      stop_name: stop.stop_name,
      tts_stop_name: stop.tts_stop_name || '',
      stop_desc: stop.stop_desc || '',
      stop_lat: stop.stop_lat,
      stop_lon: stop.stop_lon,
      zone_id: stop.zone_id || '',
      stop_url: stop.stop_url || '',
      location_type: String(stop.location_type ?? 0),
      parent_station: stop.parent_station || '',
      stop_timezone: stop.stop_timezone || '',
      wheelchair_boarding: String(stop.wheelchair_boarding ?? 0),
      level_id: stop.level_id || '',
      platform_code: stop.platform_code || '',
    })
    loadStations()
    open()
  }

  const handleDelete = (stop: Stop) => {
    if (!selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: 'Please select a feed first',
        color: 'red',
      })
      return
    }

    modals.openConfirmModal({
      title: t('stops.deleteStop'),
      children: (
        <Text size="sm">
          {t('stops.deleteConfirm', { name: stop.stop_name })}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          const feed_id = parseInt(selectedFeed!)
          await stopsApi.delete(feed_id, stop.stop_id)
          notifications.show({
            title: t('common.success'),
            message: t('stops.deleteSuccess'),
            color: 'green',
          })
          loadStops()
        } catch (error) {
          notifications.show({
            title: t('common.error'),
            message: t('stops.deleteError'),
            color: 'red',
          })
        }
      },
    })
  }

  const handleCopy = (stop: Stop) => {
    modals.open({
      title: t('stops.copyStop'),
      children: (
        <Stack>
          <Text size="sm">
            {t('stops.copyDescription', { name: stop.stop_name })}
          </Text>
          <TextInput
            label={t('stops.newStopId')}
            placeholder={t('stops.newStopIdPlaceholder')}
            required
            id="copy-stop-id"
            defaultValue={`${stop.stop_id}_copy`}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => modals.closeAll()}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={async () => {
                const input = document.getElementById('copy-stop-id') as HTMLInputElement
                const newStopId = input?.value
                if (!newStopId) {
                  notifications.show({
                    title: t('common.error'),
                    message: t('stops.stopIdRequired'),
                    color: 'red',
                  })
                  return
                }
                try {
                  const stopData = {
                    agency_id: stop.agency_id,
                    stop_id: newStopId,
                    stop_code: stop.stop_code || undefined,
                    stop_name: stop.stop_name,
                    tts_stop_name: stop.tts_stop_name || undefined,
                    stop_desc: stop.stop_desc || undefined,
                    stop_lat: Number(stop.stop_lat),
                    stop_lon: Number(stop.stop_lon),
                    zone_id: stop.zone_id || undefined,
                    stop_url: stop.stop_url || undefined,
                    location_type: stop.location_type ?? 0,
                    parent_station: stop.parent_station || undefined,
                    stop_timezone: stop.stop_timezone || undefined,
                    wheelchair_boarding: stop.wheelchair_boarding ?? 0,
                    level_id: stop.level_id || undefined,
                    platform_code: stop.platform_code || undefined,
                  }
                  await stopsApi.create(stopData)
                  notifications.show({
                    title: t('common.success'),
                    message: t('stops.copySuccess'),
                    color: 'green',
                  })
                  modals.closeAll()
                  loadStops()
                } catch (error: any) {
                  const detail = error?.response?.data?.detail
                  let errorMessage = t('stops.copyError')
                  if (typeof detail === 'string') {
                    errorMessage = detail
                  } else if (Array.isArray(detail) && detail.length > 0) {
                    errorMessage = detail.map((d: any) => d.msg || d).join(', ')
                  }
                  notifications.show({
                    title: t('common.error'),
                    message: errorMessage,
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
    if (!selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: 'Please select a feed first',
        color: 'red',
      })
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const stopData = {
        agency_id: selectedAgency,
        stop_id: values.stop_id,
        stop_code: values.stop_code || undefined,
        stop_name: values.stop_name,
        tts_stop_name: values.tts_stop_name || undefined,
        stop_desc: values.stop_desc || undefined,
        stop_lat: Number(values.stop_lat),
        stop_lon: Number(values.stop_lon),
        zone_id: values.zone_id || undefined,
        stop_url: values.stop_url || undefined,
        location_type: parseInt(values.location_type),
        parent_station: values.parent_station || undefined,
        stop_timezone: values.stop_timezone || undefined,
        wheelchair_boarding: parseInt(values.wheelchair_boarding),
        level_id: values.level_id || undefined,
        platform_code: values.platform_code || undefined,
      }

      if (editingStop) {
        await stopsApi.update(feed_id, editingStop.stop_id, stopData)
        notifications.show({
          title: t('common.success'),
          message: t('stops.updateSuccess'),
          color: 'green',
        })
      } else {
        await stopsApi.create(feed_id, stopData)
        notifications.show({
          title: t('common.success'),
          message: t('stops.createSuccess'),
          color: 'green',
        })
      }

      close()
      loadStops()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('stops.saveError'),
        color: 'red',
      })
    }
  }

  // Get translated location type options for dropdowns
  const getLocationTypeOptions = () => [
    { value: '0', label: t('stops.locationTypes.0') },
    { value: '1', label: t('stops.locationTypes.1') },
    { value: '2', label: t('stops.locationTypes.2') },
    { value: '3', label: t('stops.locationTypes.3') },
    { value: '4', label: t('stops.locationTypes.4') },
  ]

  // Get translated wheelchair boarding options for dropdowns
  const getWheelchairBoardingOptions = () => [
    { value: '0', label: t('stops.wheelchairBoardingTypes.0') },
    { value: '1', label: t('stops.wheelchairBoardingTypes.1') },
    { value: '2', label: t('stops.wheelchairBoardingTypes.2') },
  ]

  const getLocationTypeLabel = (type: number | undefined) => {
    const key = String(type ?? 0)
    return t(`stops.locationTypes.${key}`, { defaultValue: t('stops.locationTypes.0') })
  }

  const getWheelchairLabel = (boarding: number | undefined) => {
    const key = String(boarding ?? 0)
    return t(`stops.wheelchairBoardingTypes.${key}`, { defaultValue: t('stops.wheelchairBoardingTypes.0') })
  }

  const handleViewSchedule = async (stop: Stop) => {
    setScheduleStop(stop)
    setStopTimes([])
    setStopTimesTotal(0)
    openScheduleModal()
    setScheduleLoading(true)
    try {
      const response = await stopTimesApi.listForStop(stop.feed_id, stop.stop_id, 100)
      setStopTimes(response.items || [])
      setStopTimesTotal(response.total || 0)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('map.stopSchedule.loadError'),
        color: 'red',
      })
    } finally {
      setScheduleLoading(false)
    }
  }

  // Mobile Stop Card Component
  const StopCard = ({ stop }: { stop: Stop }) => {
    const isExpanded = expandedStopId === stop.stop_id

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedStopId(isExpanded ? null : stop.stop_id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Group gap="xs" wrap="nowrap">
                  <IconMapPin size={16} style={{ flexShrink: 0 }} />
                  <Text fw={600} size="sm" truncate>
                    {stop.stop_name}
                  </Text>
                </Group>
                <Text size="xs" c="dimmed" truncate>
                  {stop.stop_id}
                </Text>
              </Box>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                {stop.wheelchair_boarding === 1 && (
                  <IconWheelchair size={16} color="green" />
                )}
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              {stop.stop_desc && (
                <Text size="sm" c="dimmed">
                  {stop.stop_desc}
                </Text>
              )}

              {stop.stop_code && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('stops.stopCode')}:</Text>
                  <Code fz="xs">{stop.stop_code}</Code>
                </Group>
              )}

              <Box>
                <Text size="xs" c="dimmed" mb={2}>{t('stops.coordinates')}</Text>
                <Code fz="xs">
                  {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                </Code>
              </Box>

              <Group gap="xs">
                <Badge variant="light" size="sm">
                  {getLocationTypeLabel(stop.location_type)}
                </Badge>
                <Badge
                  variant="light"
                  size="sm"
                  color={stop.wheelchair_boarding === 1 ? 'green' : stop.wheelchair_boarding === 2 ? 'red' : 'gray'}
                >
                  {getWheelchairLabel(stop.wheelchair_boarding)}
                </Badge>
              </Group>

              {stop.zone_id && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('stops.zoneId')}:</Text>
                  <Badge variant="outline" size="sm">{stop.zone_id}</Badge>
                </Group>
              )}

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleViewSchedule(stop)}
                  leftSection={<IconClock size={16} />}
                  fullWidth
                >
                  {t('map.stopSchedule.viewSchedule')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleEdit(stop)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="blue"
                  onClick={() => handleCopy(stop)}
                  leftSection={<IconCopy size={16} />}
                  fullWidth
                >
                  {t('common.copy')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="red"
                  onClick={() => handleDelete(stop)}
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
                <Title order={3}>{t('stops.title')}</Title>
                <Text c="dimmed" size="xs">
                  {t('stops.description')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadStops} loading={loading}>
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
              <Title order={2}>{t('stops.title')}</Title>
              <Text c="dimmed" size="sm">
                {t('stops.description')}
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleCreate} disabled={!selectedFeed}>
              {t('stops.newStop')}
            </Button>
          </Group>
        )}

        {/* Filters */}
        <Paper shadow="xs" p={isMobile ? 'sm' : 'md'}>
          <Stack gap="sm">
            <SimpleGrid cols={isMobile ? 1 : 2}>
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
            </SimpleGrid>

            {/* Search and Filters */}
            <Divider label={<Group gap="xs"><IconFilter size={14} />{t('common.filters')}</Group>} labelPosition="left" />

            <SimpleGrid cols={isMobile ? 1 : 3}>
              <TextInput
                placeholder={t('common.search')}
                leftSection={<IconSearch size={16} />}
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  setPage(1)
                }}
                rightSection={
                  searchQuery && (
                    <ActionIcon size="sm" variant="subtle" onClick={() => { setSearchQuery(''); setPage(1) }}>
                      <IconX size={14} />
                    </ActionIcon>
                  )
                }
                size={isMobile ? 'sm' : 'md'}
              />
              <Select
                placeholder={t('stops.locationType')}
                data={[
                  { value: '', label: t('common.all') },
                  ...getLocationTypeOptions()
                ]}
                value={locationTypeFilter || ''}
                onChange={(value) => {
                  setLocationTypeFilter(value || null)
                  setPage(1)
                }}
                clearable
                size={isMobile ? 'sm' : 'md'}
              />
              <Select
                placeholder={t('stops.wheelchairBoarding')}
                data={[
                  { value: '', label: t('common.all') },
                  ...getWheelchairBoardingOptions()
                ]}
                value={wheelchairFilter || ''}
                onChange={(value) => {
                  setWheelchairFilter(value || null)
                  setPage(1)
                }}
                clearable
                size={isMobile ? 'sm' : 'md'}
              />
            </SimpleGrid>

            {/* Active Filters Summary */}
            {(searchQuery || locationTypeFilter || wheelchairFilter) && (
              <Group gap="xs">
                <Text size="xs" c="dimmed">{t('common.activeFilters')}:</Text>
                {searchQuery && (
                  <Badge
                    size="sm"
                    variant="light"
                    rightSection={
                      <ActionIcon size="xs" variant="transparent" onClick={() => { setSearchQuery(''); setPage(1) }}>
                        <IconX size={10} />
                      </ActionIcon>
                    }
                  >
                    {t('common.search')}: {searchQuery}
                  </Badge>
                )}
                {locationTypeFilter && (
                  <Badge
                    size="sm"
                    variant="light"
                    rightSection={
                      <ActionIcon size="xs" variant="transparent" onClick={() => { setLocationTypeFilter(null); setPage(1) }}>
                        <IconX size={10} />
                      </ActionIcon>
                    }
                  >
                    {getLocationTypeLabel(parseInt(locationTypeFilter))}
                  </Badge>
                )}
                {wheelchairFilter && (
                  <Badge
                    size="sm"
                    variant="light"
                    rightSection={
                      <ActionIcon size="xs" variant="transparent" onClick={() => { setWheelchairFilter(null); setPage(1) }}>
                        <IconX size={10} />
                      </ActionIcon>
                    }
                  >
                    {getWheelchairLabel(parseInt(wheelchairFilter))}
                  </Badge>
                )}
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => {
                    setSearchQuery('')
                    setLocationTypeFilter(null)
                    setWheelchairFilter(null)
                    setPage(1)
                  }}
                >
                  {t('common.clearAll')}
                </Button>
              </Group>
            )}
          </Stack>
        </Paper>

        {/* Stops List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {stops.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">{t('stops.noStops')}</Text>
              </Paper>
            ) : (
              <>
                {stops.map((stop) => (
                  <StopCard key={`${stop.feed_id}:${stop.stop_id}`} stop={stop} />
                ))}
                <Group justify="space-between" mt="sm">
                  <Text size="xs" c="dimmed">
                    {stops.length} / {total}
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

            {stops.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">
                {t('stops.noStops')}
              </Text>
            ) : (
              <>
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('stops.stopId')}</Table.Th>
                      <Table.Th>{t('stops.stopCode')}</Table.Th>
                      <Table.Th>{t('stops.stopName')}</Table.Th>
                      <Table.Th>{t('stops.coordinates')}</Table.Th>
                      <Table.Th>{t('stops.locationType')}</Table.Th>
                      <Table.Th>{t('stops.accessibility')}</Table.Th>
                      <Table.Th>{t('common.actions')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {stops.map((stop) => (
                      <Table.Tr key={`${stop.feed_id}:${stop.stop_id}`}>
                        <Table.Td>
                          <Code>{stop.stop_id}</Code>
                        </Table.Td>
                        <Table.Td>
                          {stop.stop_code ? <Code fz="xs">{stop.stop_code}</Code> : '-'}
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <IconMapPin size={16} />
                            <div>
                              <Text size="sm" fw={500}>
                                {stop.stop_name}
                              </Text>
                              {stop.stop_desc && (
                                <Text size="xs" c="dimmed" lineClamp={1}>
                                  {stop.stop_desc}
                                </Text>
                              )}
                            </div>
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          <Tooltip label={`Lat: ${stop.stop_lat}, Lon: ${stop.stop_lon}`}>
                            <Code fz="xs">
                              {Number(stop.stop_lat).toFixed(6)}, {Number(stop.stop_lon).toFixed(6)}
                            </Code>
                          </Tooltip>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{getLocationTypeLabel(stop.location_type)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Tooltip label={getWheelchairLabel(stop.wheelchair_boarding)}>
                            <div>
                              {stop.wheelchair_boarding === 1 ? (
                                <IconWheelchair size={16} color="green" />
                              ) : stop.wheelchair_boarding === 2 ? (
                                <IconWheelchairOff size={16} color="red" />
                              ) : (
                                <IconQuestionMark size={16} color="gray" />
                              )}
                            </div>
                          </Tooltip>
                        </Table.Td>
                        <Table.Td>
                          <Menu shadow="md" width={200}>
                            <Menu.Target>
                              <ActionIcon variant="subtle">
                                <IconDots size={16} />
                              </ActionIcon>
                            </Menu.Target>
                            <Menu.Dropdown>
                              <Menu.Item leftSection={<IconClock size={14} />} onClick={() => handleViewSchedule(stop)}>
                                {t('map.stopSchedule.viewSchedule')}
                              </Menu.Item>
                              <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => handleEdit(stop)}>
                                {t('common.edit')}
                              </Menu.Item>
                              <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => handleCopy(stop)}>
                                {t('common.copy')}
                              </Menu.Item>
                              <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={() => handleDelete(stop)}>
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
                    {t('common.showing')} {stops.length} / {total}
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
        title={editingStop ? t('stops.editStop') : t('stops.newStop')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <TextInput
              label={t('stops.stopId')}
              placeholder="STOP001"
              required
              {...form.getInputProps('stop_id')}
              disabled={!!editingStop}
            />

            <TextInput
              label={t('stops.stopCode')}
              placeholder={t('stops.stopCodePlaceholder')}
              {...form.getInputProps('stop_code')}
            />

            <TextInput
              label={t('stops.stopName')}
              placeholder={t('stops.stopNamePlaceholder')}
              required
              {...form.getInputProps('stop_name')}
            />

            <TextInput
              label={t('stops.ttsStopName')}
              placeholder={t('stops.ttsStopNamePlaceholder')}
              {...form.getInputProps('tts_stop_name')}
            />

            <Textarea
              label={t('common.description')}
              placeholder={t('common.descriptionPlaceholder')}
              {...form.getInputProps('stop_desc')}
              minRows={2}
            />

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <NumberInput
                label={t('stops.latitude')}
                placeholder="37.7749"
                required
                decimalScale={8}
                step={0.000001}
                {...form.getInputProps('stop_lat')}
              />

              <NumberInput
                label={t('stops.longitude')}
                placeholder="-122.4194"
                required
                decimalScale={8}
                step={0.000001}
                {...form.getInputProps('stop_lon')}
              />
            </SimpleGrid>

            <Select
              label={t('stops.locationType')}
              data={getLocationTypeOptions()}
              {...form.getInputProps('location_type')}
            />

            <Select
              label={t('stops.parentStation')}
              placeholder={t('stops.parentStationPlaceholder')}
              data={stationOptions}
              searchable
              clearable
              nothingFoundMessage={t('stops.noStops')}
              disabled={loadingStations}
              {...form.getInputProps('parent_station')}
            />

            <TextInput
              label={t('stops.zoneId')}
              placeholder="Zone 1"
              {...form.getInputProps('zone_id')}
            />

            <TextInput
              label={t('stops.stopUrl')}
              placeholder="https://example.com/stops/main-street"
              {...form.getInputProps('stop_url')}
            />

            <TextInput
              label={t('stops.stopTimezone')}
              placeholder="America/New_York"
              {...form.getInputProps('stop_timezone')}
            />

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <TextInput
                label={t('stops.levelId')}
                placeholder={t('stops.levelIdPlaceholder')}
                {...form.getInputProps('level_id')}
              />

              <TextInput
                label={t('stops.platformCode')}
                placeholder={t('stops.platformCodePlaceholder')}
                {...form.getInputProps('platform_code')}
              />
            </SimpleGrid>

            <Select
              label={t('stops.wheelchairBoarding')}
              data={getWheelchairBoardingOptions()}
              {...form.getInputProps('wheelchair_boarding')}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button type="submit">{editingStop ? t('common.update') : t('common.create')}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Schedule Modal */}
      <Modal
        opened={scheduleModalOpened}
        onClose={closeScheduleModal}
        title={
          <Group gap="xs">
            <IconClock size={20} />
            <Text fw={600}>{t('map.stopSchedule.title')}: {scheduleStop?.stop_name}</Text>
          </Group>
        }
        size={isMobile ? '100%' : 'xl'}
        fullScreen={isMobile}
      >
        <Stack gap="md" pos="relative">
          <LoadingOverlay visible={scheduleLoading} />

          {scheduleStop && (
            <Paper p="sm" withBorder>
              <Group gap="sm">
                <IconMapPin size={16} />
                <Box>
                  <Text size="sm" fw={500}>{scheduleStop.stop_name}</Text>
                  <Text size="xs" c="dimmed">{scheduleStop.stop_id}</Text>
                </Box>
                {scheduleStop.stop_code && (
                  <Badge variant="outline" size="sm">{scheduleStop.stop_code}</Badge>
                )}
              </Group>
            </Paper>
          )}

          {stopTimes.length === 0 && !scheduleLoading ? (
            <Paper p="xl" withBorder>
              <Text c="dimmed" ta="center">{t('map.stopSchedule.noSchedule')}</Text>
            </Paper>
          ) : (
            <>
              <Text size="sm" c="dimmed">
                {t('common.showing')} {stopTimes.length} / {stopTimesTotal}
              </Text>

              {isMobile ? (
                <Stack gap="sm">
                  {stopTimes.map((st) => (
                    <Card key={st.id} shadow="sm" padding="sm" radius="md" withBorder>
                      <Stack gap="xs">
                        <Group justify="space-between">
                          <Group gap="xs">
                            {st.route_color && (
                              <Badge
                                variant="filled"
                                size="sm"
                                style={{
                                  backgroundColor: `#${st.route_color}`,
                                  color: st.route_color && parseInt(st.route_color, 16) > 0x7FFFFF ? '#000' : '#fff'
                                }}
                              >
                                {st.route_short_name || st.gtfs_route_id}
                              </Badge>
                            )}
                            {!st.route_color && st.route_short_name && (
                              <Badge variant="light" size="sm">{st.route_short_name}</Badge>
                            )}
                          </Group>
                          <Badge variant="outline" size="sm">#{st.stop_sequence}</Badge>
                        </Group>

                        {(st.trip_headsign || st.route_long_name) && (
                          <Text size="sm" c="dimmed">
                            {t('map.stopSchedule.headsign')}: {st.trip_headsign || st.route_long_name}
                          </Text>
                        )}

                        <SimpleGrid cols={2}>
                          <Box>
                            <Text size="xs" c="dimmed">{t('map.stopSchedule.arrival')}</Text>
                            <Text size="sm" fw={500}>{st.arrival_time}</Text>
                          </Box>
                          <Box>
                            <Text size="xs" c="dimmed">{t('map.stopSchedule.departure')}</Text>
                            <Text size="sm" fw={500}>{st.departure_time}</Text>
                          </Box>
                        </SimpleGrid>

                        <Text size="xs" c="dimmed">
                          {t('map.stopSchedule.trip')}: {st.gtfs_trip_id || st.trip_id}
                        </Text>
                      </Stack>
                    </Card>
                  ))}
                </Stack>
              ) : (
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('map.stopSchedule.route')}</Table.Th>
                      <Table.Th>{t('map.stopSchedule.headsign')}</Table.Th>
                      <Table.Th>{t('map.stopSchedule.arrival')}</Table.Th>
                      <Table.Th>{t('map.stopSchedule.departure')}</Table.Th>
                      <Table.Th>{t('stopTimes.stopSequence')}</Table.Th>
                      <Table.Th>{t('map.stopSchedule.trip')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {stopTimes.map((st) => (
                      <Table.Tr key={st.id}>
                        <Table.Td>
                          {st.route_color ? (
                            <Badge
                              variant="filled"
                              size="sm"
                              style={{
                                backgroundColor: `#${st.route_color}`,
                                color: st.route_color && parseInt(st.route_color, 16) > 0x7FFFFF ? '#000' : '#fff'
                              }}
                            >
                              {st.route_short_name || st.gtfs_route_id || '-'}
                            </Badge>
                          ) : (
                            <Badge variant="light" size="sm">
                              {st.route_short_name || st.gtfs_route_id || '-'}
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm" lineClamp={1}>
                            {st.trip_headsign || st.route_long_name || '-'}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Code>{st.arrival_time}</Code>
                        </Table.Td>
                        <Table.Td>
                          <Code>{st.departure_time}</Code>
                        </Table.Td>
                        <Table.Td>
                          <Badge variant="outline" size="sm">#{st.stop_sequence}</Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {st.gtfs_trip_id || st.trip_id}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}

              {stopTimesTotal > stopTimes.length && (
                <Text size="sm" c="dimmed" ta="center">
                  {t('map.stopSchedule.showMore')} ({stopTimesTotal - stopTimes.length} more)
                </Text>
              )}
            </>
          )}

          <Group justify="flex-end">
            <Button variant="default" onClick={closeScheduleModal}>
              {t('common.close')}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Container>
  )
}
