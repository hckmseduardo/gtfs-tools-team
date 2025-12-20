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
  Textarea,
  Switch,
  LoadingOverlay,
  Menu,
  rem,
  Select,
  PasswordInput,
  Checkbox,
  Tooltip,
  Card,
  SimpleGrid,
  Box,
  Divider,
  ScrollArea,
  Collapse,
  UnstyledButton,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconDots,
  IconBuilding,
  IconCloudDownload,
  IconPlayerPlay,
  IconDownload,
  IconHistory,
  IconCheck,
  IconX,
  IconRefresh,
  IconChevronDown,
  IconChevronUp,
  IconMail,
  IconWorld,
  IconPhone,
  IconClock,
  IconLanguage,
  IconCurrencyDollar,
  IconId,
} from '@tabler/icons-react'
import {
  agencyApi,
  feedSourcesApi,
  type Agency,
  type FeedSource,
  type FeedSourceCheckLog,
  type FeedSourceType,
  type CheckFrequency,
} from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import { useTranslation } from 'react-i18next'

// Common IANA timezones for transit agencies (flat list for Mantine Select)
const timezoneOptions = [
  // North America
  { value: 'America/New_York', label: 'America/New_York (Eastern)' },
  { value: 'America/Chicago', label: 'America/Chicago (Central)' },
  { value: 'America/Denver', label: 'America/Denver (Mountain)' },
  { value: 'America/Los_Angeles', label: 'America/Los_Angeles (Pacific)' },
  { value: 'America/Anchorage', label: 'America/Anchorage (Alaska)' },
  { value: 'America/Phoenix', label: 'America/Phoenix (Arizona)' },
  { value: 'America/Toronto', label: 'America/Toronto' },
  { value: 'America/Vancouver', label: 'America/Vancouver' },
  { value: 'America/Montreal', label: 'America/Montreal' },
  { value: 'America/Mexico_City', label: 'America/Mexico_City' },
  // South America
  { value: 'America/Sao_Paulo', label: 'America/Sao_Paulo' },
  { value: 'America/Buenos_Aires', label: 'America/Buenos_Aires' },
  { value: 'America/Santiago', label: 'America/Santiago' },
  { value: 'America/Bogota', label: 'America/Bogota' },
  { value: 'America/Lima', label: 'America/Lima' },
  // Europe
  { value: 'Europe/London', label: 'Europe/London (GMT)' },
  { value: 'Europe/Paris', label: 'Europe/Paris (CET)' },
  { value: 'Europe/Berlin', label: 'Europe/Berlin (CET)' },
  { value: 'Europe/Madrid', label: 'Europe/Madrid (CET)' },
  { value: 'Europe/Rome', label: 'Europe/Rome (CET)' },
  { value: 'Europe/Amsterdam', label: 'Europe/Amsterdam (CET)' },
  { value: 'Europe/Brussels', label: 'Europe/Brussels (CET)' },
  { value: 'Europe/Zurich', label: 'Europe/Zurich (CET)' },
  { value: 'Europe/Vienna', label: 'Europe/Vienna (CET)' },
  { value: 'Europe/Stockholm', label: 'Europe/Stockholm (CET)' },
  { value: 'Europe/Oslo', label: 'Europe/Oslo (CET)' },
  { value: 'Europe/Helsinki', label: 'Europe/Helsinki (EET)' },
  { value: 'Europe/Warsaw', label: 'Europe/Warsaw (CET)' },
  { value: 'Europe/Prague', label: 'Europe/Prague (CET)' },
  { value: 'Europe/Lisbon', label: 'Europe/Lisbon (WET)' },
  { value: 'Europe/Athens', label: 'Europe/Athens (EET)' },
  { value: 'Europe/Moscow', label: 'Europe/Moscow (MSK)' },
  // Asia Pacific
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo (JST)' },
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (CST)' },
  { value: 'Asia/Hong_Kong', label: 'Asia/Hong_Kong (HKT)' },
  { value: 'Asia/Singapore', label: 'Asia/Singapore (SGT)' },
  { value: 'Asia/Seoul', label: 'Asia/Seoul (KST)' },
  { value: 'Asia/Taipei', label: 'Asia/Taipei' },
  { value: 'Asia/Bangkok', label: 'Asia/Bangkok (ICT)' },
  { value: 'Asia/Jakarta', label: 'Asia/Jakarta (WIB)' },
  { value: 'Asia/Kuala_Lumpur', label: 'Asia/Kuala_Lumpur' },
  { value: 'Asia/Manila', label: 'Asia/Manila (PHT)' },
  { value: 'Asia/Kolkata', label: 'Asia/Kolkata (IST)' },
  { value: 'Asia/Dubai', label: 'Asia/Dubai (GST)' },
  { value: 'Australia/Sydney', label: 'Australia/Sydney (AEST)' },
  { value: 'Australia/Melbourne', label: 'Australia/Melbourne (AEST)' },
  { value: 'Australia/Brisbane', label: 'Australia/Brisbane (AEST)' },
  { value: 'Australia/Perth', label: 'Australia/Perth (AWST)' },
  { value: 'Pacific/Auckland', label: 'Pacific/Auckland (NZST)' },
  // Africa / Middle East
  { value: 'Africa/Cairo', label: 'Africa/Cairo (EET)' },
  { value: 'Africa/Johannesburg', label: 'Africa/Johannesburg (SAST)' },
  { value: 'Africa/Lagos', label: 'Africa/Lagos (WAT)' },
  { value: 'Africa/Nairobi', label: 'Africa/Nairobi (EAT)' },
  { value: 'Africa/Casablanca', label: 'Africa/Casablanca (WET)' },
  { value: 'Asia/Jerusalem', label: 'Asia/Jerusalem (IST)' },
  { value: 'Asia/Riyadh', label: 'Asia/Riyadh (AST)' },
]

// ISO 639-1 language codes commonly used in transit
const languageOptions = [
  { value: 'en', label: 'English (en)' },
  { value: 'es', label: 'Spanish (es)' },
  { value: 'fr', label: 'French (fr)' },
  { value: 'de', label: 'German (de)' },
  { value: 'it', label: 'Italian (it)' },
  { value: 'pt', label: 'Portuguese (pt)' },
  { value: 'nl', label: 'Dutch (nl)' },
  { value: 'pl', label: 'Polish (pl)' },
  { value: 'ru', label: 'Russian (ru)' },
  { value: 'ja', label: 'Japanese (ja)' },
  { value: 'zh', label: 'Chinese (zh)' },
  { value: 'ko', label: 'Korean (ko)' },
  { value: 'ar', label: 'Arabic (ar)' },
  { value: 'he', label: 'Hebrew (he)' },
  { value: 'hi', label: 'Hindi (hi)' },
  { value: 'th', label: 'Thai (th)' },
  { value: 'vi', label: 'Vietnamese (vi)' },
  { value: 'id', label: 'Indonesian (id)' },
  { value: 'ms', label: 'Malay (ms)' },
  { value: 'tr', label: 'Turkish (tr)' },
  { value: 'sv', label: 'Swedish (sv)' },
  { value: 'no', label: 'Norwegian (no)' },
  { value: 'da', label: 'Danish (da)' },
  { value: 'fi', label: 'Finnish (fi)' },
  { value: 'el', label: 'Greek (el)' },
  { value: 'cs', label: 'Czech (cs)' },
  { value: 'hu', label: 'Hungarian (hu)' },
  { value: 'ro', label: 'Romanian (ro)' },
  { value: 'uk', label: 'Ukrainian (uk)' },
]

export default function Agencies() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const isSmallMobile = useMediaQuery('(max-width: 480px)')

  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingAgency, setEditingAgency] = useState<Agency | null>(null)

  // Feed Sources state
  const [feedSourcesModalOpen, setFeedSourcesModalOpen] = useState(false)
  const [selectedAgencyForSources, setSelectedAgencyForSources] = useState<Agency | null>(null)
  const [feedSources, setFeedSources] = useState<FeedSource[]>([])
  const [feedSourcesLoading, setFeedSourcesLoading] = useState(false)

  // Feed Source Edit state
  const [sourceModalOpen, setSourceModalOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<FeedSource | null>(null)
  const [sourceFormData, setSourceFormData] = useState({
    name: '',
    description: '',
    url: '',
    source_type: 'gtfs_static' as FeedSourceType,
    check_frequency: 'daily' as CheckFrequency,
    is_enabled: true,
    auto_import: false,
    auth_type: '',
    auth_header: '',
    auth_value: '',
    replace_existing: true,
    skip_shapes: false,
  })

  // Logs modal state
  const [logsModalOpen, setLogsModalOpen] = useState(false)
  const [selectedSourceLogs, setSelectedSourceLogs] = useState<FeedSourceCheckLog[]>([])
  const [logsLoading, setLogsLoading] = useState(false)

  // Expanded cards for mobile feed sources
  const [expandedSourceId, setExpandedSourceId] = useState<number | null>(null)

  // Loading state for check/import operations
  const [checkingSourceId, setCheckingSourceId] = useState<number | null>(null)

  const form = useForm({
    initialValues: {
      name: '',
      slug: '',
      is_active: true,
      // GTFS agency.txt fields
      agency_id: '',
      agency_url: '',
      agency_timezone: '',
      agency_lang: '',
      agency_phone: '',
      agency_fare_url: '',
      agency_email: '',
    },
    validate: {
      name: (value) => (value.length < 1 ? t('common.required') : null),
      slug: (value) => {
        if (value.length < 1) return t('common.required')
        if (!/^[a-z0-9-]+$/.test(value)) return 'Slug must contain only lowercase letters, numbers, and hyphens'
        return null
      },
      agency_url: (value) => {
        if (value && !/^https?:\/\/.+/.test(value)) return t('agencies.validation.invalidUrl')
        return null
      },
      agency_fare_url: (value) => {
        if (value && !/^https?:\/\/.+/.test(value)) return t('agencies.validation.invalidUrl')
        return null
      },
      agency_email: (value) => {
        if (value && !/^\S+@\S+$/.test(value)) return t('agencies.validation.invalidEmail')
        return null
      },
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  const loadAgencies = async () => {
    setLoading(true)
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('errors.unknownError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleOpenCreate = () => {
    setEditingAgency(null)
    form.reset()
    open()
  }

  const handleOpenEdit = (agency: Agency) => {
    setEditingAgency(agency)
    form.setValues({
      name: agency.name,
      slug: agency.slug,
      is_active: agency.is_active,
      // GTFS agency.txt fields
      agency_id: agency.agency_id || '',
      agency_url: agency.agency_url || agency.website || '',
      agency_timezone: agency.agency_timezone || '',
      agency_lang: agency.agency_lang || '',
      agency_phone: agency.agency_phone || agency.contact_phone || '',
      agency_fare_url: agency.agency_fare_url || '',
      agency_email: agency.agency_email || agency.contact_email || '',
    })
    open()
  }

  const handleSubmit = async (values: typeof form.values) => {
    setLoading(true)
    try {
      if (editingAgency) {
        await agencyApi.update(editingAgency.id, values)
        notifications.show({
          title: t('common.success'),
          message: t('agencies.updateSuccess'),
          color: 'green',
        })
      } else {
        await agencyApi.create(values)
        notifications.show({
          title: t('common.success'),
          message: t('agencies.createSuccess'),
          color: 'green',
        })
      }
      close()
      loadAgencies()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('errors.unknownError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = (agency: Agency) => {
    modals.openConfirmModal({
      title: t('agencies.deleteAgency'),
      children: (
        <Text size="sm">
          {t('agencies.deleteConfirm')}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        setLoading(true)
        try {
          await agencyApi.delete(agency.id)
          notifications.show({
            title: t('common.success'),
            message: t('agencies.deleteQueued'),
            color: 'blue',
            autoClose: 5000,
          })
          loadAgencies()
        } catch (error: any) {
          notifications.show({
            title: t('common.error'),
            message: error.response?.data?.detail || t('errors.unknownError'),
            color: 'red',
          })
        } finally {
          setLoading(false)
        }
      },
    })
  }

  // Auto-generate slug from name
  const handleNameChange = (value: string) => {
    form.setFieldValue('name', value)
    if (!editingAgency) {
      const slug = value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
      form.setFieldValue('slug', slug)
    }
  }

  // Feed Sources functions
  const handleOpenFeedSources = async (agency: Agency) => {
    setSelectedAgencyForSources(agency)
    setFeedSourcesModalOpen(true)
    await loadFeedSources(agency.id)
  }

  const loadFeedSources = async (agencyId: number) => {
    setFeedSourcesLoading(true)
    try {
      const data = await feedSourcesApi.list({ agency_id: agencyId, limit: 1000 })
      setFeedSources(data.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('errors.unknownError'),
        color: 'red',
      })
    } finally {
      setFeedSourcesLoading(false)
    }
  }

  const resetSourceForm = () => {
    setSourceFormData({
      name: '',
      description: '',
      url: '',
      source_type: 'gtfs_static',
      check_frequency: 'daily',
      is_enabled: true,
      auto_import: false,
      auth_type: '',
      auth_header: '',
      auth_value: '',
      replace_existing: true,
      skip_shapes: false,
    })
  }

  const handleCreateSource = () => {
    setEditingSource(null)
    resetSourceForm()
    setSourceModalOpen(true)
  }

  const handleEditSource = (source: FeedSource) => {
    setEditingSource(source)
    setSourceFormData({
      name: source.name,
      description: source.description || '',
      url: source.url,
      source_type: source.source_type,
      check_frequency: source.check_frequency,
      is_enabled: source.is_enabled,
      auto_import: source.auto_import,
      auth_type: source.auth_type || '',
      auth_header: source.auth_header || '',
      auth_value: source.auth_value || '',
      replace_existing: source.import_options?.replace_existing ?? true,
      skip_shapes: source.import_options?.skip_shapes ?? false,
    })
    setSourceModalOpen(true)
  }

  const handleSaveSource = async () => {
    if (!sourceFormData.name || !sourceFormData.url) {
      notifications.show({
        title: t('common.error'),
        message: t('errors.validationError'),
        color: 'red',
      })
      return
    }

    try {
      const payload = {
        name: sourceFormData.name,
        description: sourceFormData.description || undefined,
        url: sourceFormData.url,
        source_type: sourceFormData.source_type,
        check_frequency: sourceFormData.check_frequency,
        is_enabled: sourceFormData.is_enabled,
        auto_import: sourceFormData.auto_import,
        auth_type: sourceFormData.auth_type || undefined,
        auth_header: sourceFormData.auth_header || undefined,
        auth_value: sourceFormData.auth_value || undefined,
        import_options: {
          replace_existing: sourceFormData.replace_existing,
          skip_shapes: sourceFormData.skip_shapes,
        },
      }

      if (editingSource) {
        await feedSourcesApi.update(editingSource.id, payload)
        notifications.show({
          title: t('common.success'),
          message: t('feedSources.updateSuccess'),
          color: 'green',
        })
      } else {
        await feedSourcesApi.create({
          agency_id: selectedAgencyForSources!.id,
          ...payload,
        })
        notifications.show({
          title: t('common.success'),
          message: t('feedSources.createSuccess'),
          color: 'green',
        })
      }

      setSourceModalOpen(false)
      loadFeedSources(selectedAgencyForSources!.id)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('errors.unknownError'),
        color: 'red',
      })
    }
  }

  const handleDeleteSource = async (source: FeedSource) => {
    modals.openConfirmModal({
      title: t('feedSources.deleteSource'),
      children: (
        <Text size="sm">
          {t('feedSources.deleteConfirm')}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          await feedSourcesApi.delete(source.id)
          notifications.show({
            title: t('common.success'),
            message: t('feedSources.deleteSuccess'),
            color: 'green',
          })
          loadFeedSources(selectedAgencyForSources!.id)
        } catch (error) {
          notifications.show({
            title: t('common.error'),
            message: t('errors.unknownError'),
            color: 'red',
          })
        }
      },
    })
  }

  const handleToggleEnabled = async (source: FeedSource) => {
    try {
      if (source.is_enabled) {
        await feedSourcesApi.disable(source.id)
        notifications.show({
          title: t('common.success'),
          message: t('feedSources.disableSuccess'),
          color: 'blue',
        })
      } else {
        await feedSourcesApi.enable(source.id)
        notifications.show({
          title: t('common.success'),
          message: t('feedSources.enableSuccess'),
          color: 'green',
        })
      }
      loadFeedSources(selectedAgencyForSources!.id)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('errors.unknownError'),
        color: 'red',
      })
    }
  }

  const handleCheckNow = async (source: FeedSource, forceImport: boolean = false) => {
    // Prevent double-clicks by tracking loading state
    if (checkingSourceId === source.id) return

    setCheckingSourceId(source.id)

    // Show immediate feedback
    notifications.show({
      id: `check-${source.id}`,
      title: forceImport ? t('feedSources.importStarting') : t('feedSources.checkStarting'),
      message: t('feedSources.pleaseWait'),
      color: 'blue',
      loading: true,
      autoClose: false,
    })

    try {
      const result = await feedSourcesApi.check(source.id, forceImport)

      // Update notification with result
      notifications.update({
        id: `check-${source.id}`,
        loading: false,
        autoClose: 5000,
        ...(result.success
          ? {
            title: t('common.success'),
            message: result.task_id
              ? t('feedSources.taskCreated', { taskId: result.task_id })
              : t('feedSources.checkTriggered'),
            color: 'green',
          }
          : {
            title: t('common.warning'),
            message: result.message,
            color: 'yellow',
          }),
      })

      loadFeedSources(selectedAgencyForSources!.id)
    } catch (error: any) {
      notifications.update({
        id: `check-${source.id}`,
        loading: false,
        autoClose: 5000,
        title: t('common.error'),
        message: error?.response?.data?.detail || t('feedSources.checkFailed'),
        color: 'red',
      })
    } finally {
      setCheckingSourceId(null)
    }
  }

  const handleViewLogs = async (source: FeedSource) => {
    setLogsLoading(true)
    setLogsModalOpen(true)
    try {
      const data = await feedSourcesApi.getLogs(source.id, { limit: 50 })
      setSelectedSourceLogs(data.items || [])
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('errors.unknownError'),
        color: 'red',
      })
    } finally {
      setLogsLoading(false)
    }
  }

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return '-'
    return new Date(dateString).toLocaleString()
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'green'
      case 'inactive': return 'gray'
      case 'error': return 'red'
      case 'checking': return 'blue'
      default: return 'gray'
    }
  }

  const sourceTypeOptions = [
    { value: 'gtfs_static', label: t('feedSources.sourceTypes.gtfs_static') },
    { value: 'gtfs_realtime', label: t('feedSources.sourceTypes.gtfs_realtime') },
    { value: 'gtfs_rt_trip_updates', label: t('feedSources.sourceTypes.gtfs_rt_trip_updates') },
    { value: 'gtfs_rt_vehicle_positions', label: t('feedSources.sourceTypes.gtfs_rt_vehicle_positions') },
    { value: 'gtfs_rt_alerts', label: t('feedSources.sourceTypes.gtfs_rt_alerts') },
    { value: 'gtfs_rt_trip_modifications', label: t('feedSources.sourceTypes.gtfs_rt_trip_modifications') },
  ]

  const frequencyOptions = [
    { value: 'hourly', label: t('feedSources.frequencies.hourly') },
    { value: 'daily', label: t('feedSources.frequencies.daily') },
    { value: 'weekly', label: t('feedSources.frequencies.weekly') },
  ]

  const authTypeOptions = [
    { value: '', label: t('feedSources.authTypes.none') },
    { value: 'api_key', label: t('feedSources.authTypes.api_key') },
    { value: 'bearer', label: t('feedSources.authTypes.bearer') },
    { value: 'basic', label: t('feedSources.authTypes.basic') },
  ]

  // Mobile Agency Card Component
  const AgencyCard = ({ agency }: { agency: Agency }) => (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
            <IconBuilding size={20} style={{ flexShrink: 0 }} />
            <Text fw={600} truncate style={{ flex: 1 }}>{agency.name}</Text>
          </Group>
          <Badge color={agency.is_active ? 'green' : 'gray'} variant="light" size="sm">
            {agency.is_active ? t('common.active') : t('common.inactive')}
          </Badge>
        </Group>

        <Text size="sm" c="dimmed">{agency.slug}</Text>

        {agency.contact_email && (
          <Group gap="xs">
            <IconMail size={14} color="gray" />
            <Text size="sm" truncate>{agency.contact_email}</Text>
          </Group>
        )}

        {agency.website && (
          <Group gap="xs">
            <IconWorld size={14} color="gray" />
            <Text size="sm" truncate>{agency.website}</Text>
          </Group>
        )}

        <Divider />

        <Group grow>
          <Button
            variant="light"
            size="xs"
            leftSection={<IconCloudDownload size={14} />}
            onClick={() => handleOpenFeedSources(agency)}
          >
            {t('feedSources.title')}
          </Button>
          <Button
            variant="light"
            size="xs"
            leftSection={<IconEdit size={14} />}
            onClick={() => handleOpenEdit(agency)}
          >
            {t('common.edit')}
          </Button>
          <Button
            variant="light"
            color="red"
            size="xs"
            leftSection={<IconTrash size={14} />}
            onClick={() => handleDelete(agency)}
          >
            {t('common.delete')}
          </Button>
        </Group>
      </Stack>
    </Card>
  )

  // Mobile Feed Source Card Component
  const FeedSourceCard = ({ source }: { source: FeedSource }) => {
    const isExpanded = expandedSourceId === source.id

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedSourceId(isExpanded ? null : source.id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Box style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                <Text fw={600} size="sm" truncate style={{ maxWidth: '100%' }}>
                  {source.name}
                </Text>
                <Text
                  size="xs"
                  c="dimmed"
                  style={{
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: '100%',
                    display: 'block'
                  }}
                >
                  {source.url}
                </Text>
              </Box>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Badge color={getStatusColor(source.status)} size="sm">
                  {t(`feedSources.statuses.${source.status}`)}
                </Badge>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              <Group gap="xs" wrap="wrap">
                <Badge variant="light" size="sm">
                  {t(`feedSources.sourceTypes.${source.source_type}`)}
                </Badge>
                <Badge variant="outline" size="sm">
                  {t(`feedSources.frequencies.${source.check_frequency}`)}
                </Badge>
                {source.auto_import && (
                  <Badge variant="filled" size="sm" color="green">
                    Auto
                  </Badge>
                )}
              </Group>

              <Box>
                <Text size="xs" c="dimmed" mb={2}>{t('feedSources.lastChecked')}</Text>
                <Text size="sm">{formatDate(source.last_checked_at)}</Text>
              </Box>

              {source.error_count > 0 && (
                <Badge color="red" variant="light" size="sm">
                  {source.error_count} errors
                </Badge>
              )}

              {source.last_error && (
                <Text size="xs" c="red" lineClamp={2}>
                  {source.last_error}
                </Text>
              )}

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  color={source.is_enabled ? 'red' : 'green'}
                  onClick={() => handleToggleEnabled(source)}
                  leftSection={source.is_enabled ? <IconX size={16} /> : <IconCheck size={16} />}
                  fullWidth
                >
                  {source.is_enabled ? t('feedSources.disable') : t('feedSources.enable')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="blue"
                  onClick={() => handleCheckNow(source)}
                  leftSection={<IconPlayerPlay size={16} />}
                  fullWidth
                  loading={checkingSourceId === source.id}
                  disabled={checkingSourceId !== null}
                >
                  {t('feedSources.checkNow')}
                </Button>
              </SimpleGrid>

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  color="green"
                  onClick={() => handleCheckNow(source, true)}
                  leftSection={<IconDownload size={16} />}
                  fullWidth
                  loading={checkingSourceId === source.id}
                  disabled={checkingSourceId !== null}
                >
                  {t('feedSources.forceImport')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="gray"
                  onClick={() => handleViewLogs(source)}
                  leftSection={<IconHistory size={16} />}
                  fullWidth
                >
                  {t('feedSources.viewLogs')}
                </Button>
              </SimpleGrid>

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleEditSource(source)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="red"
                  onClick={() => handleDeleteSource(source)}
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

  // Mobile Log Card Component
  const LogCard = ({ log }: { log: FeedSourceCheckLog }) => (
    <Card shadow="sm" padding="sm" radius="md" withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Text size="xs">{formatDate(log.checked_at)}</Text>
          <Badge color={log.success ? 'green' : 'red'} size="xs">
            {log.success ? t('common.yes') : t('common.no')}
          </Badge>
        </Group>

        <Group gap="xs">
          <Badge color={log.content_changed ? 'blue' : 'gray'} size="xs" variant="outline">
            {log.content_changed ? 'Changed' : 'No Change'}
          </Badge>
          {log.import_triggered && (
            <Badge color="green" size="xs" variant="outline">
              Imported
            </Badge>
          )}
          {log.http_status && (
            <Badge color="gray" size="xs" variant="outline">
              HTTP {log.http_status}
            </Badge>
          )}
        </Group>

        {log.error_message && (
          <Text size="xs" c="red" lineClamp={2}>
            {log.error_message}
          </Text>
        )}
      </Stack>
    </Card>
  )

  return (
    <Container size="xl" px={isMobile ? 'xs' : 'md'}>
      <Stack gap="lg">
        <Group justify="space-between" wrap={isMobile ? 'wrap' : 'nowrap'}>
          <div>
            <Title order={isMobile ? 2 : 1}>{t('agencies.title')}</Title>
            {!isMobile && (
              <Text c="dimmed" mt="sm">
                {t('dashboard.welcome')}
              </Text>
            )}
          </div>
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={handleOpenCreate}
            fullWidth={isSmallMobile}
          >
            {t('agencies.newAgency')}
          </Button>
        </Group>

        <Paper withBorder shadow="sm" p={isMobile ? 'sm' : 'xl'} radius="md" pos="relative">
          <LoadingOverlay visible={loading} />

          {agencies.length === 0 && !loading ? (
            <Stack align="center" gap="md" py="xl">
              <IconBuilding size={48} stroke={1.5} color="gray" />
              <div style={{ textAlign: 'center' }}>
                <Text size="lg" fw={500}>
                  {t('agencies.noAgencies')}
                </Text>
                <Text size="sm" c="dimmed" mt="xs">
                  {t('agencies.newAgency')}
                </Text>
              </div>
              <Button leftSection={<IconPlus size={16} />} onClick={handleOpenCreate}>
                {t('agencies.newAgency')}
              </Button>
            </Stack>
          ) : isMobile ? (
            // Mobile Card Layout
            <Stack gap="md">
              {agencies.map((agency) => (
                <AgencyCard key={agency.id} agency={agency} />
              ))}
            </Stack>
          ) : (
            // Desktop Table Layout
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('common.name')}</Table.Th>
                  <Table.Th>{t('agencies.agencySlug')}</Table.Th>
                  <Table.Th>{t('agencies.contactEmail')}</Table.Th>
                  <Table.Th>{t('common.status')}</Table.Th>
                  <Table.Th>{t('feedSources.title')}</Table.Th>
                  <Table.Th></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {agencies.map((agency) => (
                  <Table.Tr key={agency.id}>
                    <Table.Td>
                      <Group gap="sm">
                        <IconBuilding size={18} />
                        <Text fw={500}>{agency.name}</Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {agency.slug}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {agency.contact_email ? (
                        <Text size="sm">{agency.contact_email}</Text>
                      ) : (
                        <Text size="sm" c="dimmed">—</Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge color={agency.is_active ? 'green' : 'gray'} variant="light">
                        {agency.is_active ? t('common.active') : t('common.inactive')}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        variant="light"
                        size="xs"
                        leftSection={<IconCloudDownload size={14} />}
                        onClick={() => handleOpenFeedSources(agency)}
                      >
                        {t('feedSources.title')}
                      </Button>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" justify="flex-end">
                        <ActionIcon variant="subtle" onClick={() => handleOpenEdit(agency)}>
                          <IconEdit size={16} />
                        </ActionIcon>
                        <Menu shadow="md" width={200} position="bottom-end">
                          <Menu.Target>
                            <ActionIcon variant="subtle">
                              <IconDots size={16} />
                            </ActionIcon>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item
                              leftSection={<IconEdit style={{ width: rem(14), height: rem(14) }} />}
                              onClick={() => handleOpenEdit(agency)}
                            >
                              {t('common.edit')}
                            </Menu.Item>
                            <Menu.Item
                              leftSection={<IconCloudDownload style={{ width: rem(14), height: rem(14) }} />}
                              onClick={() => handleOpenFeedSources(agency)}
                            >
                              {t('feedSources.title')}
                            </Menu.Item>
                            <Menu.Divider />
                            <Menu.Item
                              color="red"
                              leftSection={<IconTrash style={{ width: rem(14), height: rem(14) }} />}
                              onClick={() => handleDelete(agency)}
                            >
                              {t('common.delete')}
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>

        {/* Create/Edit Agency Modal */}
        <Modal
          opened={opened}
          onClose={close}
          title={editingAgency ? t('agencies.editAgency') : t('agencies.newAgency')}
          size={isMobile ? '100%' : 'xl'}
          fullScreen={isMobile}
        >
          <ScrollArea h={isMobile ? 'calc(100vh - 100px)' : undefined}>
            <form onSubmit={form.onSubmit(handleSubmit)}>
              <Stack gap="md" p={isMobile ? 'xs' : 0}>
                {/* Application Fields */}
                <Paper p="md" withBorder>
                  <Title order={5} mb="md">{t('agencies.applicationFields')}</Title>
                  <Stack gap="sm">
                    <TextInput
                      label={t('agencies.agencyName')}
                      placeholder="Metro Transit"
                      description={t('agencies.gtfs.agencyNameDesc')}
                      required
                      leftSection={<IconBuilding size={16} />}
                      {...form.getInputProps('name')}
                      onChange={(e) => handleNameChange(e.currentTarget.value)}
                    />

                    <TextInput
                      label={t('agencies.agencySlug')}
                      placeholder="metro-transit"
                      description={t('agencies.gtfs.slugDesc')}
                      required
                      {...form.getInputProps('slug')}
                    />

                    <Switch
                      label={t('common.active')}
                      description={t('agencies.gtfs.activeDesc')}
                      {...form.getInputProps('is_active', { type: 'checkbox' })}
                    />
                  </Stack>
                </Paper>

                {/* GTFS Required Fields */}
                <Paper p="md" withBorder>
                  <Title order={5} mb="md">
                    <Group gap="xs">
                      {t('agencies.gtfs.requiredFields')}
                      <Badge size="sm" color="red">{t('agencies.gtfs.gtfsRequired')}</Badge>
                    </Group>
                  </Title>
                  <Stack gap="sm">
                    <TextInput
                      label={t('agencies.gtfs.agencyUrl')}
                      placeholder="https://www.metrotransit.org"
                      description={t('agencies.gtfs.agencyUrlDesc')}
                      leftSection={<IconWorld size={16} />}
                      {...form.getInputProps('agency_url')}
                    />

                    <Select
                      label={t('agencies.gtfs.agencyTimezone')}
                      placeholder={t('agencies.gtfs.selectTimezone')}
                      description={t('agencies.gtfs.agencyTimezoneDesc')}
                      leftSection={<IconClock size={16} />}
                      data={timezoneOptions}
                      searchable
                      clearable
                      {...form.getInputProps('agency_timezone')}
                    />
                  </Stack>
                </Paper>

                {/* GTFS Optional Fields */}
                <Paper p="md" withBorder>
                  <Title order={5} mb="md">{t('agencies.gtfs.optionalFields')}</Title>
                  <Stack gap="sm">
                    <SimpleGrid cols={isMobile ? 1 : 2}>
                      <TextInput
                        label={t('agencies.gtfs.agencyId')}
                        placeholder="metro_transit"
                        description={t('agencies.gtfs.agencyIdDesc')}
                        leftSection={<IconId size={16} />}
                        {...form.getInputProps('agency_id')}
                      />

                      <Select
                        label={t('agencies.gtfs.agencyLang')}
                        placeholder={t('agencies.gtfs.selectLanguage')}
                        description={t('agencies.gtfs.agencyLangDesc')}
                        leftSection={<IconLanguage size={16} />}
                        data={languageOptions}
                        searchable
                        clearable
                        {...form.getInputProps('agency_lang')}
                      />
                    </SimpleGrid>

                    <SimpleGrid cols={isMobile ? 1 : 2}>
                      <TextInput
                        label={t('agencies.gtfs.agencyPhone')}
                        placeholder="+1-612-555-0100"
                        description={t('agencies.gtfs.agencyPhoneDesc')}
                        leftSection={<IconPhone size={16} />}
                        {...form.getInputProps('agency_phone')}
                      />

                      <TextInput
                        label={t('agencies.gtfs.agencyEmail')}
                        placeholder="info@metrotransit.org"
                        description={t('agencies.gtfs.agencyEmailDesc')}
                        leftSection={<IconMail size={16} />}
                        type="email"
                        {...form.getInputProps('agency_email')}
                      />
                    </SimpleGrid>

                    <TextInput
                      label={t('agencies.gtfs.agencyFareUrl')}
                      placeholder="https://www.metrotransit.org/fares"
                      description={t('agencies.gtfs.agencyFareUrlDesc')}
                      leftSection={<IconCurrencyDollar size={16} />}
                      {...form.getInputProps('agency_fare_url')}
                    />
                  </Stack>
                </Paper>

                <Group justify="flex-end" mt="md" grow={isMobile}>
                  <Button variant="light" onClick={close}>
                    {t('common.cancel')}
                  </Button>
                  <Button type="submit" loading={loading}>
                    {editingAgency ? t('common.save') : t('common.create')}
                  </Button>
                </Group>
              </Stack>
            </form>
          </ScrollArea>
        </Modal>

        {/* Feed Sources Modal */}
        <Modal
          opened={feedSourcesModalOpen}
          onClose={() => setFeedSourcesModalOpen(false)}
          title={
            <Group gap="sm">
              <IconCloudDownload size={20} />
              <Text fw={500} truncate style={{ maxWidth: isMobile ? 200 : 400 }}>
                {t('feedSources.title')} - {selectedAgencyForSources?.name}
              </Text>
            </Group>
          }
          size={isMobile ? '100%' : 'xl'}
          fullScreen={isMobile}
        >
          <Stack gap="md">
            <Group justify="space-between" wrap="wrap" gap="xs">
              {!isMobile && (
                <Text size="sm" c="dimmed" style={{ flex: 1 }}>
                  {t('feedSources.description')}
                </Text>
              )}
              <Group gap="xs" grow={isSmallMobile}>
                <Button
                  variant="light"
                  size="sm"
                  leftSection={<IconRefresh size={14} />}
                  onClick={() => selectedAgencyForSources && loadFeedSources(selectedAgencyForSources.id)}
                  loading={feedSourcesLoading}
                >
                  {t('common.refresh')}
                </Button>
                <Button
                  size="sm"
                  leftSection={<IconPlus size={14} />}
                  onClick={handleCreateSource}
                >
                  {t('feedSources.newSource')}
                </Button>
              </Group>
            </Group>

            <Box pos="relative" style={{ minHeight: 200 }}>
              <LoadingOverlay visible={feedSourcesLoading} />
              {feedSources.length === 0 && !feedSourcesLoading ? (
                <Stack align="center" gap="md" py="xl">
                  <IconCloudDownload size={48} stroke={1.5} color="gray" />
                  <Text c="dimmed">{t('feedSources.noSources')}</Text>
                  <Button size="sm" leftSection={<IconPlus size={14} />} onClick={handleCreateSource}>
                    {t('feedSources.newSource')}
                  </Button>
                </Stack>
              ) : isMobile ? (
                // Mobile Card Layout for Feed Sources
                <ScrollArea h={isMobile ? 'calc(100vh - 250px)' : undefined}>
                  <Stack gap="sm">
                    {feedSources.map((source) => (
                      <FeedSourceCard key={source.id} source={source} />
                    ))}
                  </Stack>
                </ScrollArea>
              ) : (
                // Desktop Table Layout for Feed Sources
                <Paper withBorder p={0}>
                  <Table striped highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t('feedSources.name')}</Table.Th>
                        <Table.Th>{t('feedSources.sourceType')}</Table.Th>
                        <Table.Th>{t('common.status')}</Table.Th>
                        <Table.Th>{t('feedSources.lastChecked')}</Table.Th>
                        <Table.Th>{t('common.actions')}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {feedSources.map((source) => (
                        <Table.Tr key={source.id}>
                          <Table.Td>
                            <div>
                              <Text fw={500} size="sm">{source.name}</Text>
                              <Text size="xs" c="dimmed" truncate="end" maw={200}>
                                {source.url}
                              </Text>
                            </div>
                          </Table.Td>
                          <Table.Td>
                            <Badge variant="light" size="sm">
                              {t(`feedSources.sourceTypes.${source.source_type}`)}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Badge color={getStatusColor(source.status)} size="sm">
                              {t(`feedSources.statuses.${source.status}`)}
                            </Badge>
                            {source.error_count > 0 && (
                              <Text size="xs" c="red">{source.error_count} errors</Text>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{formatDate(source.last_checked_at)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Group gap={4}>
                              <Tooltip label={source.is_enabled ? t('feedSources.disable') : t('feedSources.enable')}>
                                <ActionIcon
                                  size="sm"
                                  color={source.is_enabled ? 'red' : 'green'}
                                  variant="light"
                                  onClick={() => handleToggleEnabled(source)}
                                >
                                  {source.is_enabled ? <IconX size={14} /> : <IconCheck size={14} />}
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('feedSources.checkNow')}>
                                <ActionIcon
                                  size="sm"
                                  color="blue"
                                  variant="light"
                                  onClick={() => handleCheckNow(source)}
                                  loading={checkingSourceId === source.id}
                                  disabled={checkingSourceId !== null}
                                >
                                  <IconPlayerPlay size={14} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('feedSources.forceImport')}>
                                <ActionIcon
                                  size="sm"
                                  color="green"
                                  variant="light"
                                  onClick={() => handleCheckNow(source, true)}
                                  loading={checkingSourceId === source.id}
                                  disabled={checkingSourceId !== null}
                                >
                                  <IconDownload size={14} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('feedSources.viewLogs')}>
                                <ActionIcon
                                  size="sm"
                                  color="gray"
                                  variant="light"
                                  onClick={() => handleViewLogs(source)}
                                >
                                  <IconHistory size={14} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('common.edit')}>
                                <ActionIcon
                                  size="sm"
                                  color="blue"
                                  variant="light"
                                  onClick={() => handleEditSource(source)}
                                >
                                  <IconEdit size={14} />
                                </ActionIcon>
                              </Tooltip>
                              <Tooltip label={t('common.delete')}>
                                <ActionIcon
                                  size="sm"
                                  color="red"
                                  variant="light"
                                  onClick={() => handleDeleteSource(source)}
                                >
                                  <IconTrash size={14} />
                                </ActionIcon>
                              </Tooltip>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Paper>
              )}
            </Box>
          </Stack>
        </Modal>

        {/* Create/Edit Feed Source Modal */}
        <Modal
          opened={sourceModalOpen}
          onClose={() => setSourceModalOpen(false)}
          title={editingSource ? t('feedSources.editSource') : t('feedSources.newSource')}
          size={isMobile ? '100%' : 'lg'}
          fullScreen={isMobile}
        >
          <ScrollArea h={isMobile ? 'calc(100vh - 100px)' : undefined}>
            <Stack gap="md" p={isMobile ? 'xs' : 0}>
              <TextInput
                label={t('feedSources.name')}
                placeholder={t('feedSources.name')}
                value={sourceFormData.name}
                onChange={(e) => setSourceFormData({ ...sourceFormData, name: e.target.value })}
                required
              />
              <Textarea
                label={t('common.description')}
                placeholder={t('common.description')}
                value={sourceFormData.description}
                onChange={(e) => setSourceFormData({ ...sourceFormData, description: e.target.value })}
                minRows={2}
              />
              <TextInput
                label={t('feedSources.url')}
                placeholder="https://example.com/gtfs.zip"
                value={sourceFormData.url}
                onChange={(e) => setSourceFormData({ ...sourceFormData, url: e.target.value })}
                required
              />

              <SimpleGrid cols={isMobile ? 1 : 2}>
                <Select
                  label={t('feedSources.sourceType')}
                  data={sourceTypeOptions}
                  value={sourceFormData.source_type}
                  onChange={(value) => setSourceFormData({ ...sourceFormData, source_type: value as FeedSourceType })}
                />
                <Select
                  label={t('feedSources.checkFrequency')}
                  data={frequencyOptions}
                  value={sourceFormData.check_frequency}
                  onChange={(value) => setSourceFormData({ ...sourceFormData, check_frequency: value as CheckFrequency })}
                />
              </SimpleGrid>

              <SimpleGrid cols={2}>
                <Switch
                  label={t('feedSources.enabled')}
                  checked={sourceFormData.is_enabled}
                  onChange={(e) => setSourceFormData({ ...sourceFormData, is_enabled: e.currentTarget.checked })}
                />
                <Switch
                  label={t('feedSources.autoImport')}
                  checked={sourceFormData.auto_import}
                  onChange={(e) => setSourceFormData({ ...sourceFormData, auto_import: e.currentTarget.checked })}
                />
              </SimpleGrid>

              {/* Authentication Section */}
              <Paper p="md" withBorder>
                <Title order={5} mb="md">{t('feedSources.authentication')}</Title>
                <Stack gap="sm">
                  <Select
                    label={t('feedSources.authType')}
                    data={authTypeOptions}
                    value={sourceFormData.auth_type}
                    onChange={(value) => setSourceFormData({ ...sourceFormData, auth_type: value || '' })}
                  />
                  {sourceFormData.auth_type && (
                    <>
                      <TextInput
                        label={t('feedSources.authHeader')}
                        placeholder="Authorization"
                        value={sourceFormData.auth_header}
                        onChange={(e) => setSourceFormData({ ...sourceFormData, auth_header: e.target.value })}
                      />
                      <PasswordInput
                        label={t('feedSources.authValue')}
                        placeholder="API key or token"
                        value={sourceFormData.auth_value}
                        onChange={(e) => setSourceFormData({ ...sourceFormData, auth_value: e.target.value })}
                      />
                    </>
                  )}
                </Stack>
              </Paper>

              {/* Import Options Section */}
              <Paper p="md" withBorder>
                <Title order={5} mb="md">{t('feedSources.importOptions')}</Title>
                <Stack gap="sm">
                  <Checkbox
                    label={t('feedSources.replaceExisting')}
                    checked={sourceFormData.replace_existing}
                    onChange={(e) => setSourceFormData({ ...sourceFormData, replace_existing: e.currentTarget.checked })}
                  />
                  <Checkbox
                    label={t('feedSources.skipShapes')}
                    checked={sourceFormData.skip_shapes}
                    onChange={(e) => setSourceFormData({ ...sourceFormData, skip_shapes: e.currentTarget.checked })}
                  />
                </Stack>
              </Paper>

              <Group justify="flex-end" mt="md" grow={isMobile}>
                <Button variant="light" onClick={() => setSourceModalOpen(false)}>
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleSaveSource}>{t('common.save')}</Button>
              </Group>
            </Stack>
          </ScrollArea>
        </Modal>

        {/* Check Logs Modal */}
        <Modal
          opened={logsModalOpen}
          onClose={() => setLogsModalOpen(false)}
          title={t('feedSources.logs.title')}
          size={isMobile ? '100%' : 'xl'}
          fullScreen={isMobile}
        >
          <Box pos="relative" style={{ minHeight: 200 }}>
            <LoadingOverlay visible={logsLoading} />
            {selectedSourceLogs.length === 0 && !logsLoading ? (
              <Text c="dimmed" ta="center" py="xl">
                {t('feedSources.logs.noLogs')}
              </Text>
            ) : isMobile ? (
              // Mobile Card Layout for Logs
              <ScrollArea h="calc(100vh - 150px)">
                <Stack gap="sm">
                  {selectedSourceLogs.map((log) => (
                    <LogCard key={log.id} log={log} />
                  ))}
                </Stack>
              </ScrollArea>
            ) : (
              // Desktop Table Layout for Logs
              <ScrollArea>
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('feedSources.logs.checkedAt')}</Table.Th>
                      <Table.Th>{t('feedSources.logs.success')}</Table.Th>
                      <Table.Th>{t('feedSources.logs.httpStatus')}</Table.Th>
                      <Table.Th>{t('feedSources.logs.contentChanged')}</Table.Th>
                      <Table.Th>{t('feedSources.logs.importTriggered')}</Table.Th>
                      <Table.Th>{t('feedSources.logs.errorMessage')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {selectedSourceLogs.map((log) => (
                      <Table.Tr key={log.id}>
                        <Table.Td>{formatDate(log.checked_at)}</Table.Td>
                        <Table.Td>
                          <Badge color={log.success ? 'green' : 'red'} size="sm">
                            {log.success ? t('common.yes') : t('common.no')}
                          </Badge>
                        </Table.Td>
                        <Table.Td>{log.http_status || '-'}</Table.Td>
                        <Table.Td>
                          <Badge color={log.content_changed ? 'blue' : 'gray'} size="sm">
                            {log.content_changed ? t('common.yes') : t('common.no')}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={log.import_triggered ? 'green' : 'gray'} size="sm">
                            {log.import_triggered ? t('common.yes') : t('common.no')}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" c="red" truncate="end" maw={200}>
                            {log.error_message || '-'}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}
          </Box>
        </Modal>
      </Stack>
    </Container>
  )
}
