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
  Code,
  Switch,
  Card,
  Box,
  Collapse,
  UnstyledButton,
  Divider,
  SimpleGrid,
  Tabs,
  Tooltip,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { useForm } from '@mantine/form'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconDots,
  IconCalendar,
  IconCheck,
  IconX,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
  IconCalendarEvent,
  IconCalendarPlus,
  IconCalendarMinus,
} from '@tabler/icons-react'
import { calendarsApi, agencyApi, type Calendar, type Agency, type CalendarDate } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { CalendarFormModal } from '../components/CalendarFormModal'
import { useTranslation } from 'react-i18next'

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

// Helper functions to convert between Date and GTFS YYYYMMDD format
const dateToGtfsFormat = (date: Date | null): string => {
  if (!date) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

const gtfsFormatToDate = (gtfsDate: string): Date | null => {
  if (!gtfsDate || gtfsDate.length !== 8) return null
  const year = parseInt(gtfsDate.substring(0, 4))
  const month = parseInt(gtfsDate.substring(4, 6)) - 1
  const day = parseInt(gtfsDate.substring(6, 8))
  return new Date(year, month, day)
}

export default function Calendars() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [calendars, setCalendars] = useState<Calendar[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)  // For edit modal
  const [createModalOpened, { open: openCreateModal, close: closeCreateModal }] = useDisclosure(false)
  const [editingCalendar, setEditingCalendar] = useState<Calendar | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [expandedCalendarId, setExpandedCalendarId] = useState<string | null>(null)
  const pageSize = 50

  // Calendar dates (exceptions) state
  const [exceptions, setExceptions] = useState<CalendarDate[]>([])
  const [loadingExceptions, setLoadingExceptions] = useState(false)
  const [activeTab, setActiveTab] = useState<string | null>('details')
  const [editingException, setEditingException] = useState<CalendarDate | null>(null)

  const form = useForm({
    initialValues: {
      service_id: '',
      start_date: null as Date | null,
      end_date: null as Date | null,
      monday: true,
      tuesday: true,
      wednesday: true,
      thursday: true,
      friday: true,
      saturday: false,
      sunday: false,
    },
    validate: {
      service_id: (value) => (!value ? t('calendars.serviceIdRequired') : null),
      start_date: (value) => (!value ? t('calendars.startDateRequired') : null),
      end_date: (value) => (!value ? t('calendars.endDateRequired') : null),
    },
  })

  // Form for adding new exceptions
  const exceptionForm = useForm({
    initialValues: {
      date: null as Date | null,
      exception_type: '1' as '1' | '2',
    },
    validate: {
      date: (value) => {
        if (!value) return t('calendarDates.dateRequired')
        return null
      },
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadCalendars()
    }
  }, [selectedAgency, selectedFeed, page])

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

  const loadCalendars = async () => {
    if (!selectedFeed) {
      setCalendars([])
      setTotal(0)
      return
    }

    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const response = await calendarsApi.list(feed_id, {
        skip: (page - 1) * pageSize,
        limit: pageSize,
      })
      setCalendars(response.items || [])
      setTotal(response.total || 0)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('calendars.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  // Load exceptions when editing a calendar
  const loadExceptions = async (feed_id: number, service_id: string) => {
    setLoadingExceptions(true)
    try {
      const response = await calendarsApi.listExceptions(feed_id, service_id)
      setExceptions(response.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('calendarDates.loadError'),
        color: 'red',
      })
    } finally {
      setLoadingExceptions(false)
    }
  }

  const handleExceptionSubmit = async (values: typeof exceptionForm.values) => {
    if (!editingCalendar) return

    try {
      const dateStr = dateToGtfsFormat(values.date)
      if (editingException) {
        // Update existing exception
        await calendarsApi.updateException(editingCalendar.feed_id, editingCalendar.service_id, editingException.date, {
          date: dateStr,
          exception_type: parseInt(values.exception_type) as 1 | 2,
        })
        notifications.show({
          title: t('common.success'),
          message: t('calendarDates.updateSuccess'),
          color: 'green',
        })
        setEditingException(null)
      } else {
        // Create new exception
        await calendarsApi.createException(editingCalendar.feed_id, editingCalendar.service_id, {
          date: dateStr,
          exception_type: parseInt(values.exception_type) as 1 | 2,
        })
        notifications.show({
          title: t('common.success'),
          message: t('calendarDates.createSuccess'),
          color: 'green',
        })
      }
      exceptionForm.reset()
      loadExceptions(editingCalendar.feed_id, editingCalendar.service_id)
    } catch (error: any) {
      // Handle FastAPI validation errors (detail can be an array of objects)
      let errorMessage = editingException ? t('calendarDates.updateError') : t('calendarDates.createError')
      const detail = error?.response?.data?.detail
      if (typeof detail === 'string') {
        errorMessage = detail
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMessage = detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join(', ')
      }
      notifications.show({
        title: t('common.error'),
        message: errorMessage,
        color: 'red',
      })
    }
  }

  const handleEditException = (exception: CalendarDate) => {
    setEditingException(exception)
    exceptionForm.setValues({
      date: gtfsFormatToDate(exception.date),
      exception_type: String(exception.exception_type) as '1' | '2',
    })
  }

  const handleCancelEditException = () => {
    setEditingException(null)
    exceptionForm.reset()
  }

  const handleDeleteException = (exception: CalendarDate) => {
    if (!editingCalendar) return

    modals.openConfirmModal({
      title: t('calendarDates.deleteException'),
      children: (
        <Text size="sm">
          {t('calendarDates.deleteConfirm', { date: formatDate(exception.date) })}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          await calendarsApi.deleteException(editingCalendar.feed_id, editingCalendar.service_id, exception.date)
          notifications.show({
            title: t('common.success'),
            message: t('calendarDates.deleteSuccess'),
            color: 'green',
          })
          loadExceptions(editingCalendar.feed_id, editingCalendar.service_id)
        } catch (error) {
          notifications.show({
            title: t('common.error'),
            message: t('calendarDates.deleteError'),
            color: 'red',
          })
        }
      },
    })
  }

  // Helper to format GTFS date (YYYYMMDD) to readable format
  const formatDate = (dateStr: string) => {
    if (!dateStr || dateStr.length !== 8) return dateStr
    return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`
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

    openCreateModal()
  }

  const handleEdit = (calendar: Calendar) => {
    setEditingCalendar(calendar)
    setActiveTab('details')
    form.setValues({
      service_id: calendar.service_id,
      start_date: gtfsFormatToDate(calendar.start_date),
      end_date: gtfsFormatToDate(calendar.end_date),
      monday: calendar.monday,
      tuesday: calendar.tuesday,
      wednesday: calendar.wednesday,
      thursday: calendar.thursday,
      friday: calendar.friday,
      saturday: calendar.saturday,
      sunday: calendar.sunday,
    })
    exceptionForm.reset()
    loadExceptions(calendar.feed_id, calendar.service_id)
    open()
  }

  const handleDelete = (calendar: Calendar) => {
    modals.openConfirmModal({
      title: t('calendars.deleteCalendar'),
      children: (
        <Text size="sm">
          {t('calendars.deleteConfirm', { id: calendar.service_id })}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          await calendarsApi.delete(calendar.feed_id, calendar.service_id)
          notifications.show({
            title: t('common.success'),
            message: t('calendars.deleteSuccess'),
            color: 'green',
          })
          loadCalendars()
        } catch (error) {
          notifications.show({
            title: t('common.error'),
            message: t('calendars.deleteError'),
            color: 'red',
          })
        }
      },
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
      const calendarData = {
        service_id: values.service_id,
        start_date: dateToGtfsFormat(values.start_date),
        end_date: dateToGtfsFormat(values.end_date),
        monday: values.monday,
        tuesday: values.tuesday,
        wednesday: values.wednesday,
        thursday: values.thursday,
        friday: values.friday,
        saturday: values.saturday,
        sunday: values.sunday,
      }

      if (editingCalendar) {
        await calendarsApi.update(feed_id, editingCalendar.service_id, calendarData)
        notifications.show({
          title: t('common.success'),
          message: t('calendars.updateSuccess'),
          color: 'green',
        })
      } else {
        await calendarsApi.create(feed_id, calendarData)
        notifications.show({
          title: t('common.success'),
          message: t('calendars.createSuccess'),
          color: 'green',
        })
      }

      close()
      loadCalendars()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('calendars.saveError'),
        color: 'red',
      })
    }
  }

  const renderDayBadge = (active: boolean, day: string) => {
    const dayKey = day.toLowerCase()
    const dayLabel = t(`calendars.days.${dayKey}`, day.slice(0, 3))
    return active ? (
      <Badge color="green" size="sm" variant="light" leftSection={<IconCheck size={12} />}>
        {dayLabel.slice(0, 3)}
      </Badge>
    ) : (
      <Badge color="gray" size="sm" variant="light" leftSection={<IconX size={12} />}>
        {dayLabel.slice(0, 3)}
      </Badge>
    )
  }

  const countActiveDays = (calendar: Calendar) => {
    return [
      calendar.monday,
      calendar.tuesday,
      calendar.wednesday,
      calendar.thursday,
      calendar.friday,
      calendar.saturday,
      calendar.sunday,
    ].filter(Boolean).length
  }

  // Mobile Calendar Card Component
  const CalendarCard = ({ calendar }: { calendar: Calendar }) => {
    const isExpanded = expandedCalendarId === calendar.service_id
    const activeDays = countActiveDays(calendar)

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedCalendarId(isExpanded ? null : calendar.service_id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                <IconCalendar size={18} style={{ flexShrink: 0 }} />
                <Box style={{ minWidth: 0 }}>
                  <Text fw={600} size="sm" truncate>
                    {calendar.service_id}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {calendar.start_date} - {calendar.end_date}
                  </Text>
                </Box>
              </Group>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Badge size="sm" variant="filled">
                  {activeDays} {t('calendars.daysActive')}
                </Badge>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              <Group gap={4} wrap="wrap" justify="center">
                {renderDayBadge(calendar.monday, 'Monday')}
                {renderDayBadge(calendar.tuesday, 'Tuesday')}
                {renderDayBadge(calendar.wednesday, 'Wednesday')}
                {renderDayBadge(calendar.thursday, 'Thursday')}
                {renderDayBadge(calendar.friday, 'Friday')}
                {renderDayBadge(calendar.saturday, 'Saturday')}
                {renderDayBadge(calendar.sunday, 'Sunday')}
              </Group>

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleEdit(calendar)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="red"
                  onClick={() => handleDelete(calendar)}
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
                <Title order={3}>{t('calendars.title')}</Title>
                <Text c="dimmed" size="xs">
                  {t('calendars.description')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadCalendars} loading={loading}>
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
              <Title order={2}>{t('calendars.title')}</Title>
              <Text c="dimmed" size="sm">
                {t('calendars.description')}
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleCreate} disabled={!selectedFeed}>
              {t('calendars.newCalendar')}
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
          </Stack>
        </Paper>

        {/* Calendars List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {calendars.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">{t('calendars.noCalendars')}</Text>
              </Paper>
            ) : (
              <>
                {calendars.map((calendar) => (
                  <CalendarCard key={`${calendar.feed_id}:${calendar.service_id}`} calendar={calendar} />
                ))}
                <Group justify="space-between" mt="sm">
                  <Text size="xs" c="dimmed">
                    {calendars.length} / {total}
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

            {calendars.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">
                {t('calendars.noCalendars')}
              </Text>
            ) : (
              <>
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('calendars.serviceId')}</Table.Th>
                      <Table.Th>{t('calendars.dateRange')}</Table.Th>
                      <Table.Th>{t('calendars.daysOfWeek')}</Table.Th>
                      <Table.Th>{t('common.actions')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {calendars.map((calendar) => (
                      <Table.Tr key={`${calendar.feed_id}:${calendar.service_id}`}>
                        <Table.Td>
                          <Group gap="xs">
                            <IconCalendar size={16} />
                            <Code>{calendar.service_id}</Code>
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {calendar.start_date} → {calendar.end_date}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap={4}>
                            {renderDayBadge(calendar.monday, 'Monday')}
                            {renderDayBadge(calendar.tuesday, 'Tuesday')}
                            {renderDayBadge(calendar.wednesday, 'Wednesday')}
                            {renderDayBadge(calendar.thursday, 'Thursday')}
                            {renderDayBadge(calendar.friday, 'Friday')}
                            {renderDayBadge(calendar.saturday, 'Saturday')}
                            {renderDayBadge(calendar.sunday, 'Sunday')}
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
                              <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => handleEdit(calendar)}>
                                {t('common.edit')}
                              </Menu.Item>
                              <Menu.Item leftSection={<IconTrash size={14} />} color="red" onClick={() => handleDelete(calendar)}>
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
                    {t('common.showing')} {calendars.length} / {total}
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

      {/* Edit Modal (only for editing existing calendars) */}
      <Modal
        opened={opened && editingCalendar !== null}
        onClose={close}
        title={t('calendars.editCalendar')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        {editingCalendar && (
          <Tabs value={activeTab} onChange={setActiveTab}>
            <Tabs.List>
              <Tabs.Tab value="details" leftSection={<IconCalendar size={16} />}>
                {t('calendars.details')}
              </Tabs.Tab>
              <Tabs.Tab value="exceptions" leftSection={<IconCalendarEvent size={16} />}>
                {t('calendarDates.exceptions')}
                {exceptions.length > 0 && (
                  <Badge size="sm" ml="xs" variant="filled">
                    {exceptions.length}
                  </Badge>
                )}
              </Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="details" pt="md">
              <form onSubmit={form.onSubmit(handleSubmit)}>
                <Stack>
                  <TextInput
                    label={t('calendars.serviceId')}
                    placeholder="WEEKDAY"
                    required
                    {...form.getInputProps('service_id')}
                    disabled={!!editingCalendar}
                  />

                  <SimpleGrid cols={isMobile ? 1 : 2}>
                    <DatePickerInput
                      label={t('calendars.startDate')}
                      placeholder={t('calendars.selectDate')}
                      required
                      valueFormat="YYYY-MM-DD"
                      {...form.getInputProps('start_date')}
                    />
                    <DatePickerInput
                      label={t('calendars.endDate')}
                      placeholder={t('calendars.selectDate')}
                      required
                      valueFormat="YYYY-MM-DD"
                      {...form.getInputProps('end_date')}
                    />
                  </SimpleGrid>

                  <div>
                    <Text size="sm" fw={500} mb="xs">
                      {t('calendars.daysOfService')}
                    </Text>
                    <Stack gap="xs">
                      {WEEKDAYS.map((day) => (
                        <Switch
                          key={day}
                          label={t(`calendars.days.${day}`, day.charAt(0).toUpperCase() + day.slice(1))}
                          {...form.getInputProps(day, { type: 'checkbox' })}
                        />
                      ))}
                    </Stack>
                  </div>

                  <Group justify="flex-end" mt="md">
                    <Button variant="default" onClick={close}>
                      {t('common.cancel')}
                    </Button>
                    <Button type="submit">{t('common.update')}</Button>
                  </Group>
                </Stack>
              </form>
            </Tabs.Panel>

            <Tabs.Panel value="exceptions" pt="md">
              <Stack pos="relative">
                <LoadingOverlay visible={loadingExceptions} />

                {/* Add/Edit Exception Form */}
                <Paper p="md" withBorder>
                  <form onSubmit={exceptionForm.onSubmit(handleExceptionSubmit)}>
                    {editingException && (
                      <Text size="sm" fw={500} mb="xs" c="blue">
                        {t('calendarDates.editingException', { date: formatDate(editingException.date) })}
                      </Text>
                    )}
                    <Group align="flex-end" gap="sm" wrap={isMobile ? 'wrap' : 'nowrap'}>
                      <DatePickerInput
                        label={t('calendarDates.date')}
                        placeholder={t('calendars.selectDate')}
                        valueFormat="YYYY-MM-DD"
                        style={{ flex: 1, minWidth: isMobile ? '100%' : 150 }}
                        {...exceptionForm.getInputProps('date')}
                      />
                      <Select
                        label={t('calendarDates.exceptionType')}
                        data={[
                          { value: '1', label: t('calendarDates.serviceAdded') },
                          { value: '2', label: t('calendarDates.serviceRemoved') },
                        ]}
                        style={{ flex: 1, minWidth: isMobile ? '100%' : 180 }}
                        {...exceptionForm.getInputProps('exception_type')}
                      />
                      <Group gap="xs" style={{ minWidth: isMobile ? '100%' : 'auto' }}>
                        {editingException && (
                          <Button
                            variant="default"
                            onClick={handleCancelEditException}
                          >
                            {t('common.cancel')}
                          </Button>
                        )}
                        <Button
                          type="submit"
                          leftSection={editingException ? <IconCheck size={16} /> : <IconPlus size={16} />}
                          color={editingException ? 'blue' : undefined}
                        >
                          {editingException ? t('common.update') : t('calendarDates.addException')}
                        </Button>
                      </Group>
                    </Group>
                  </form>
                </Paper>

                {/* Exceptions List */}
                {exceptions.length === 0 ? (
                  <Paper p="xl" withBorder>
                    <Text c="dimmed" ta="center">
                      {t('calendarDates.noExceptions')}
                    </Text>
                  </Paper>
                ) : (
                  <Table striped highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t('calendarDates.date')}</Table.Th>
                        <Table.Th>{t('calendarDates.type')}</Table.Th>
                        <Table.Th style={{ width: 80 }}>{t('common.actions')}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {exceptions.map((exception) => (
                        <Table.Tr key={exception.id} style={editingException?.id === exception.id ? { backgroundColor: 'var(--mantine-color-blue-light)' } : undefined}>
                          <Table.Td>
                            <Code>{formatDate(exception.date)}</Code>
                          </Table.Td>
                          <Table.Td>
                            {exception.exception_type === 1 ? (
                              <Badge color="green" leftSection={<IconCalendarPlus size={12} />}>
                                {t('calendarDates.serviceAdded')}
                              </Badge>
                            ) : (
                              <Badge color="red" leftSection={<IconCalendarMinus size={12} />}>
                                {t('calendarDates.serviceRemoved')}
                              </Badge>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <Tooltip label={t('common.edit')}>
                                <ActionIcon
                                  color="blue"
                                  variant="subtle"
                                  onClick={() => handleEditException(exception)}
                                >
                                  <IconEdit size={16} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('common.delete')}>
                                <ActionIcon
                                  color="red"
                                  variant="subtle"
                                  onClick={() => handleDeleteException(exception)}
                                >
                                  <IconTrash size={16} />
                                </ActionIcon>
                              </Tooltip>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}

                <Group justify="flex-end" mt="md">
                  <Button variant="default" onClick={close}>
                    {t('common.close')}
                  </Button>
                </Group>
              </Stack>
            </Tabs.Panel>
          </Tabs>
        )}
      </Modal>

      {/* Create Calendar Modal (using shared component) */}
      <CalendarFormModal
        opened={createModalOpened}
        onClose={closeCreateModal}
        feedId={selectedFeed ? parseInt(selectedFeed) : null}
        onSuccess={() => {
          loadCalendars()
        }}
      />
    </Container>
  )
}
