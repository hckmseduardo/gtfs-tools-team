/**
 * CalendarFormModal - Shared component for creating new calendars
 * Used in both Calendars page and Route Creator
 * Includes tabs for Details and Exceptions (like edit modal)
 * Allows adding exceptions before creating the calendar
 */

import { useState, useEffect } from 'react'
import {
  Modal,
  Stack,
  TextInput,
  SimpleGrid,
  Text,
  Switch,
  Group,
  Button,
  Tabs,
  Badge,
  Paper,
  Table,
  ActionIcon,
  Tooltip,
  Code,
  Select,
  LoadingOverlay,
  Alert,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { useForm } from '@mantine/form'
import { useMediaQuery } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'
import {
  IconCalendar,
  IconCalendarEvent,
  IconCalendarPlus,
  IconCalendarMinus,
  IconPlus,
  IconCheck,
  IconEdit,
  IconTrash,
  IconInfoCircle,
} from '@tabler/icons-react'
import { calendarsApi, type CalendarDate } from '../lib/gtfs-api'

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

// Helper function to convert Date to GTFS YYYYMMDD format
const dateToGtfsFormat = (date: Date | null): string => {
  if (!date) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

// Helper function to convert GTFS YYYYMMDD to Date
const gtfsFormatToDate = (gtfsDate: string): Date | null => {
  if (!gtfsDate || gtfsDate.length !== 8) return null
  const year = parseInt(gtfsDate.substring(0, 4))
  const month = parseInt(gtfsDate.substring(4, 6)) - 1
  const day = parseInt(gtfsDate.substring(6, 8))
  return new Date(year, month, day)
}

// Helper to format GTFS date (YYYYMMDD) to readable format
const formatDate = (dateStr: string) => {
  if (!dateStr || dateStr.length !== 8) return dateStr
  return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`
}

// Local exception type (before saving to API)
interface PendingException {
  id: string // temporary local ID
  date: string // YYYYMMDD format
  exception_type: 1 | 2
}

interface CalendarFormModalProps {
  opened: boolean
  onClose: () => void
  feedId: number | null
  onSuccess?: (serviceId: string) => void
  zIndex?: number
}

export function CalendarFormModal({
  opened,
  onClose,
  feedId,
  onSuccess,
  zIndex = 100001,
}: CalendarFormModalProps) {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<string | null>('details')

  // Track if calendar has been created (to switch between local and API exceptions)
  const [createdServiceId, setCreatedServiceId] = useState<string | null>(null)

  // Pending exceptions (local, before calendar is created)
  const [pendingExceptions, setPendingExceptions] = useState<PendingException[]>([])

  // API exceptions (after calendar is created)
  const [apiExceptions, setApiExceptions] = useState<CalendarDate[]>([])
  const [loadingExceptions, setLoadingExceptions] = useState(false)

  // Editing state
  const [editingPendingIndex, setEditingPendingIndex] = useState<number | null>(null)
  const [editingApiException, setEditingApiException] = useState<CalendarDate | null>(null)

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
      service_id: (value) => (!value ? t('calendars.serviceIdRequired', 'Service ID is required') : null),
      start_date: (value) => (!value ? t('calendars.startDateRequired', 'Start date is required') : null),
      end_date: (value) => (!value ? t('calendars.endDateRequired', 'End date is required') : null),
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
        if (!value) return t('calendarDates.dateRequired', 'Date is required')
        return null
      },
    },
  })

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!opened) {
      setActiveTab('details')
      setCreatedServiceId(null)
      setPendingExceptions([])
      setApiExceptions([])
      setEditingPendingIndex(null)
      setEditingApiException(null)
      form.reset()
      exceptionForm.reset()
    }
  }, [opened])

  // Load exceptions from API (after calendar is created)
  const loadApiExceptions = async (serviceId: string) => {
    if (!feedId) return
    setLoadingExceptions(true)
    try {
      const response = await calendarsApi.listExceptions(feedId, serviceId)
      setApiExceptions(response.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('calendarDates.loadError', 'Failed to load exceptions'),
        color: 'red',
      })
    } finally {
      setLoadingExceptions(false)
    }
  }

  // Create calendar with all pending exceptions in a single atomic transaction
  const handleSubmit = async (values: typeof form.values) => {
    if (!feedId) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('calendars.noFeedSelected', 'Please select a feed first'),
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      // Build calendar data with exceptions included for atomic creation
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
        // Include exceptions for atomic creation
        exceptions: pendingExceptions.length > 0
          ? pendingExceptions.map(exc => ({
              date: exc.date,
              exception_type: exc.exception_type,
            }))
          : undefined,
      }

      // Create calendar with exceptions in single atomic transaction
      await calendarsApi.create(feedId, calendarData)

      // Show success message
      if (pendingExceptions.length > 0) {
        notifications.show({
          title: t('common.success', 'Success'),
          message: t('calendars.createSuccessWithExceptions',
            `Calendar created with ${pendingExceptions.length} exceptions`),
          color: 'green',
        })
      } else {
        notifications.show({
          title: t('common.success', 'Success'),
          message: t('calendars.createSuccess', 'Calendar created successfully'),
          color: 'green',
        })
      }

      // Mark as created and load API exceptions
      setCreatedServiceId(values.service_id)
      setPendingExceptions([]) // Clear pending, now using API
      loadApiExceptions(values.service_id)

      // If no exceptions were pending, close the modal
      if (pendingExceptions.length === 0) {
        onSuccess?.(values.service_id)
        handleClose()
      } else {
        // Stay open on exceptions tab to show results
        setActiveTab('exceptions')
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: error?.response?.data?.detail || t('calendars.saveError', 'Failed to save calendar'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  // Handle exception form submit (both pending and API modes)
  const handleExceptionSubmit = async (values: typeof exceptionForm.values) => {
    const dateStr = dateToGtfsFormat(values.date)
    const exceptionType = parseInt(values.exception_type) as 1 | 2

    if (createdServiceId && feedId) {
      // Calendar exists - use API
      try {
        if (editingApiException) {
          await calendarsApi.updateException(feedId, createdServiceId, editingApiException.date, {
            date: dateStr,
            exception_type: exceptionType,
          })
          notifications.show({
            title: t('common.success', 'Success'),
            message: t('calendarDates.updateSuccess', 'Exception updated'),
            color: 'green',
          })
          setEditingApiException(null)
        } else {
          await calendarsApi.createException(feedId, createdServiceId, {
            date: dateStr,
            exception_type: exceptionType,
          })
          notifications.show({
            title: t('common.success', 'Success'),
            message: t('calendarDates.createSuccess', 'Exception added'),
            color: 'green',
          })
        }
        exceptionForm.reset()
        loadApiExceptions(createdServiceId)
      } catch (error: any) {
        let errorMessage = editingApiException
          ? t('calendarDates.updateError', 'Failed to update exception')
          : t('calendarDates.createError', 'Failed to add exception')
        const detail = error?.response?.data?.detail
        if (typeof detail === 'string') {
          errorMessage = detail
        } else if (Array.isArray(detail) && detail.length > 0) {
          errorMessage = detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join(', ')
        }
        notifications.show({
          title: t('common.error', 'Error'),
          message: errorMessage,
          color: 'red',
        })
      }
    } else {
      // Calendar not created yet - use local state
      if (editingPendingIndex !== null) {
        // Update existing pending exception
        setPendingExceptions(prev => {
          const updated = [...prev]
          updated[editingPendingIndex] = {
            ...updated[editingPendingIndex],
            date: dateStr,
            exception_type: exceptionType,
          }
          return updated
        })
        setEditingPendingIndex(null)
      } else {
        // Check for duplicate date
        if (pendingExceptions.some(e => e.date === dateStr)) {
          notifications.show({
            title: t('common.error', 'Error'),
            message: t('calendarDates.duplicateDate', 'An exception for this date already exists'),
            color: 'red',
          })
          return
        }
        // Add new pending exception
        setPendingExceptions(prev => [
          ...prev,
          {
            id: `pending-${Date.now()}`,
            date: dateStr,
            exception_type: exceptionType,
          },
        ])
      }
      exceptionForm.reset()
    }
  }

  // Edit handlers
  const handleEditPending = (index: number) => {
    const exception = pendingExceptions[index]
    setEditingPendingIndex(index)
    setEditingApiException(null)
    exceptionForm.setValues({
      date: gtfsFormatToDate(exception.date),
      exception_type: String(exception.exception_type) as '1' | '2',
    })
  }

  const handleEditApi = (exception: CalendarDate) => {
    setEditingApiException(exception)
    setEditingPendingIndex(null)
    exceptionForm.setValues({
      date: gtfsFormatToDate(exception.date),
      exception_type: String(exception.exception_type) as '1' | '2',
    })
  }

  const handleCancelEdit = () => {
    setEditingPendingIndex(null)
    setEditingApiException(null)
    exceptionForm.reset()
  }

  // Delete handlers
  const handleDeletePending = (index: number) => {
    setPendingExceptions(prev => prev.filter((_, i) => i !== index))
    if (editingPendingIndex === index) {
      setEditingPendingIndex(null)
      exceptionForm.reset()
    }
  }

  const handleDeleteApi = async (exception: CalendarDate) => {
    if (!feedId || !createdServiceId) return

    try {
      await calendarsApi.deleteException(feedId, createdServiceId, exception.date)
      notifications.show({
        title: t('common.success', 'Success'),
        message: t('calendarDates.deleteSuccess', 'Exception deleted'),
        color: 'green',
      })
      loadApiExceptions(createdServiceId)
      if (editingApiException?.date === exception.date) {
        setEditingApiException(null)
        exceptionForm.reset()
      }
    } catch (error) {
      notifications.show({
        title: t('common.error', 'Error'),
        message: t('calendarDates.deleteError', 'Failed to delete exception'),
        color: 'red',
      })
    }
  }

  const handleClose = () => {
    if (createdServiceId) {
      onSuccess?.(createdServiceId)
    }
    form.reset()
    exceptionForm.reset()
    setCreatedServiceId(null)
    setPendingExceptions([])
    setApiExceptions([])
    setActiveTab('details')
    onClose()
  }

  // Determine which exceptions to show
  const exceptions = createdServiceId ? apiExceptions : pendingExceptions
  const isEditing = editingPendingIndex !== null || editingApiException !== null

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={createdServiceId
        ? t('calendars.newCalendar', 'New Calendar') + `: ${createdServiceId}`
        : t('calendars.newCalendar', 'New Calendar')
      }
      size={isMobile ? '100%' : 'lg'}
      fullScreen={isMobile}
      zIndex={zIndex}
    >
      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab
            value="details"
            leftSection={<IconCalendar size={16} />}
            disabled={!!createdServiceId}
          >
            {t('calendars.details', 'Details')}
          </Tabs.Tab>
          <Tabs.Tab
            value="exceptions"
            leftSection={<IconCalendarEvent size={16} />}
          >
            {t('calendarDates.exceptions', 'Exceptions')}
            {exceptions.length > 0 && (
              <Badge size="sm" ml="xs" variant="filled" color={createdServiceId ? undefined : 'orange'}>
                {exceptions.length}
              </Badge>
            )}
          </Tabs.Tab>
        </Tabs.List>

        {/* Details Tab */}
        <Tabs.Panel value="details" pt="md">
          <form onSubmit={form.onSubmit(handleSubmit)}>
            <Stack>
              <TextInput
                label={t('calendars.serviceId', 'Service ID')}
                placeholder="WEEKDAY"
                required
                {...form.getInputProps('service_id')}
              />

              <SimpleGrid cols={isMobile ? 1 : 2}>
                <DatePickerInput
                  label={t('calendars.startDate', 'Start Date')}
                  placeholder={t('calendars.selectDate', 'Select date')}
                  required
                  valueFormat="YYYY-MM-DD"
                  popoverProps={{ zIndex: zIndex + 1 }}
                  {...form.getInputProps('start_date')}
                />
                <DatePickerInput
                  label={t('calendars.endDate', 'End Date')}
                  placeholder={t('calendars.selectDate', 'Select date')}
                  required
                  valueFormat="YYYY-MM-DD"
                  popoverProps={{ zIndex: zIndex + 1 }}
                  {...form.getInputProps('end_date')}
                />
              </SimpleGrid>

              <div>
                <Text size="sm" fw={500} mb="xs">
                  {t('calendars.daysOfService', 'Days of Service')}
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

              {pendingExceptions.length > 0 && (
                <Alert icon={<IconInfoCircle size={16} />} color="blue" variant="light">
                  {t('calendars.pendingExceptions', `${pendingExceptions.length} exception(s) will be created with the calendar`)}
                </Alert>
              )}

              <Group justify="flex-end" mt="md">
                <Button variant="default" onClick={handleClose} disabled={loading}>
                  {t('common.cancel', 'Cancel')}
                </Button>
                <Button type="submit" loading={loading}>
                  {pendingExceptions.length > 0
                    ? t('calendars.createWithExceptions', 'Create with Exceptions')
                    : t('common.create', 'Create')
                  }
                </Button>
              </Group>
            </Stack>
          </form>
        </Tabs.Panel>

        {/* Exceptions Tab */}
        <Tabs.Panel value="exceptions" pt="md">
          <Stack pos="relative">
            <LoadingOverlay visible={loadingExceptions} />

            {!createdServiceId && (
              <Alert icon={<IconInfoCircle size={16} />} color="orange" variant="light" mb="sm">
                {t('calendars.exceptionsBeforeCreate', 'These exceptions will be saved when you create the calendar.')}
              </Alert>
            )}

            {/* Add/Edit Exception Form */}
            <Paper p="md" withBorder>
              <form onSubmit={exceptionForm.onSubmit(handleExceptionSubmit)}>
                {isEditing && (
                  <Text size="sm" fw={500} mb="xs" c="blue">
                    {t('calendarDates.editingException', 'Editing exception')}
                  </Text>
                )}
                <Group align="flex-end" gap="sm" wrap={isMobile ? 'wrap' : 'nowrap'}>
                  <DatePickerInput
                    label={t('calendarDates.date', 'Date')}
                    placeholder={t('calendars.selectDate', 'Select date')}
                    valueFormat="YYYY-MM-DD"
                    style={{ flex: 1, minWidth: isMobile ? '100%' : 150 }}
                    popoverProps={{ zIndex: zIndex + 1 }}
                    {...exceptionForm.getInputProps('date')}
                  />
                  <Select
                    label={t('calendarDates.exceptionType', 'Type')}
                    data={[
                      { value: '1', label: t('calendarDates.serviceAdded', 'Service Added') },
                      { value: '2', label: t('calendarDates.serviceRemoved', 'Service Removed') },
                    ]}
                    style={{ flex: 1, minWidth: isMobile ? '100%' : 180 }}
                    comboboxProps={{ zIndex: zIndex + 1 }}
                    {...exceptionForm.getInputProps('exception_type')}
                  />
                  <Group gap="xs" style={{ minWidth: isMobile ? '100%' : 'auto' }}>
                    {isEditing && (
                      <Button
                        variant="default"
                        onClick={handleCancelEdit}
                      >
                        {t('common.cancel', 'Cancel')}
                      </Button>
                    )}
                    <Button
                      type="submit"
                      leftSection={isEditing ? <IconCheck size={16} /> : <IconPlus size={16} />}
                      color={isEditing ? 'blue' : undefined}
                    >
                      {isEditing ? t('common.update', 'Update') : t('calendarDates.addException', 'Add')}
                    </Button>
                  </Group>
                </Group>
              </form>
            </Paper>

            {/* Exceptions List */}
            {exceptions.length === 0 ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">
                  {t('calendarDates.noExceptions', 'No exceptions defined')}
                </Text>
              </Paper>
            ) : (
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('calendarDates.date', 'Date')}</Table.Th>
                    <Table.Th>{t('calendarDates.type', 'Type')}</Table.Th>
                    <Table.Th style={{ width: 80 }}>{t('common.actions', 'Actions')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {createdServiceId
                    ? // API exceptions (after creation)
                      apiExceptions.map((exception) => (
                        <Table.Tr
                          key={exception.id}
                          style={editingApiException?.id === exception.id ? { backgroundColor: 'var(--mantine-color-blue-light)' } : undefined}
                        >
                          <Table.Td>
                            <Code>{formatDate(exception.date)}</Code>
                          </Table.Td>
                          <Table.Td>
                            {exception.exception_type === 1 ? (
                              <Badge color="green" leftSection={<IconCalendarPlus size={12} />}>
                                {t('calendarDates.serviceAdded', 'Service Added')}
                              </Badge>
                            ) : (
                              <Badge color="red" leftSection={<IconCalendarMinus size={12} />}>
                                {t('calendarDates.serviceRemoved', 'Service Removed')}
                              </Badge>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <Tooltip label={t('common.edit', 'Edit')}>
                                <ActionIcon
                                  color="blue"
                                  variant="subtle"
                                  onClick={() => handleEditApi(exception)}
                                >
                                  <IconEdit size={16} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('common.delete', 'Delete')}>
                                <ActionIcon
                                  color="red"
                                  variant="subtle"
                                  onClick={() => handleDeleteApi(exception)}
                                >
                                  <IconTrash size={16} />
                                </ActionIcon>
                              </Tooltip>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))
                    : // Pending exceptions (before creation)
                      pendingExceptions.map((exception, index) => (
                        <Table.Tr
                          key={exception.id}
                          style={editingPendingIndex === index ? { backgroundColor: 'var(--mantine-color-blue-light)' } : undefined}
                        >
                          <Table.Td>
                            <Group gap="xs">
                              <Code>{formatDate(exception.date)}</Code>
                              <Badge size="xs" color="orange" variant="outline">
                                {t('common.pending', 'pending')}
                              </Badge>
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            {exception.exception_type === 1 ? (
                              <Badge color="green" leftSection={<IconCalendarPlus size={12} />}>
                                {t('calendarDates.serviceAdded', 'Service Added')}
                              </Badge>
                            ) : (
                              <Badge color="red" leftSection={<IconCalendarMinus size={12} />}>
                                {t('calendarDates.serviceRemoved', 'Service Removed')}
                              </Badge>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <Tooltip label={t('common.edit', 'Edit')}>
                                <ActionIcon
                                  color="blue"
                                  variant="subtle"
                                  onClick={() => handleEditPending(index)}
                                >
                                  <IconEdit size={16} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('common.delete', 'Delete')}>
                                <ActionIcon
                                  color="red"
                                  variant="subtle"
                                  onClick={() => handleDeletePending(index)}
                                >
                                  <IconTrash size={16} />
                                </ActionIcon>
                              </Tooltip>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))
                  }
                </Table.Tbody>
              </Table>
            )}

            <Group justify="flex-end" mt="md">
              {!createdServiceId && pendingExceptions.length > 0 && (
                <Button
                  variant="light"
                  onClick={() => setActiveTab('details')}
                >
                  {t('calendars.backToDetails', 'Back to Details')}
                </Button>
              )}
              <Button onClick={handleClose}>
                {createdServiceId ? t('common.done', 'Done') : t('common.cancel', 'Cancel')}
              </Button>
            </Group>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Modal>
  )
}
