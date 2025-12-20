import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Stepper,
  Group,
  Button,
  Paper,
  Text,
  Stack,
  Alert,
  Select,
  Progress,
  Loader,
  ThemeIcon,
  Badge,
  Table,
  Divider,
} from '@mantine/core'
import {
  IconFileZip,
  IconCheck,
  IconAlertCircle,
  IconShieldCheck,
  IconDownload,
  IconExternalLink,
  IconDatabase,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'
import { gtfsApi, agencyApi, type Agency } from '../lib/gtfs-api'
import { feedApi, type GTFSFeed } from '../lib/feed-api'
import { tasksApi, type Task } from '../lib/tasks-api'

interface GTFSExportWizardProps {
  onComplete?: () => void
  onCancel?: () => void
}

// Helper function to format file size
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Validation result from the export task
interface ExportValidationResult {
  valid: boolean
  error_count: number
  warning_count: number
  info_count: number
  duration_seconds?: number
  error?: string
}

// Export task result
interface ExportTaskResult {
  success: boolean
  export_id: string
  feed_id: number
  feed_name: string
  gtfs_file_size: number
  validation: ExportValidationResult
}

export default function GTFSExportWizard({ onComplete, onCancel }: GTFSExportWizardProps) {
  const { t } = useTranslation()
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)

  // Step 1: Feed selection
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgencyId, setSelectedAgencyId] = useState<string | null>(null)
  const [feeds, setFeeds] = useState<GTFSFeed[]>([])
  const [selectedFeedId, setSelectedFeedId] = useState<string | null>(null)
  const [loadingFeeds, setLoadingFeeds] = useState(false)

  // Step 2: Validation (generated after export task completes)
  const [exportTaskId, setExportTaskId] = useState<number | null>(null)
  const [exportProgress, setExportProgress] = useState(0)
  const [exportResult, setExportResult] = useState<ExportTaskResult | null>(null)
  const [exportId, setExportId] = useState<string | null>(null)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  // Step 3: Download
  const [downloadComplete, setDownloadComplete] = useState(false)

  // Load agencies on mount
  useEffect(() => {
    loadAgencies()
  }, [])

  // Load feeds when agency changes
  useEffect(() => {
    if (selectedAgencyId) {
      loadFeeds(parseInt(selectedAgencyId))
    } else {
      setFeeds([])
      setSelectedFeedId(null)
    }
  }, [selectedAgencyId])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [])

  const loadAgencies = async () => {
    try {
      const response = await agencyApi.list()
      setAgencies(response.items || response)
    } catch (error) {
      console.error('Failed to load agencies:', error)
      notifications.show({
        title: t('common.error'),
        message: t('agencies.loadError', 'Failed to load agencies'),
        color: 'red',
      })
    }
  }

  const loadFeeds = async (agencyId: number) => {
    setLoadingFeeds(true)
    try {
      const response = await feedApi.list({ agency_id: agencyId, limit: 1000 })
      setFeeds(response.feeds || response.items || [])
      // Auto-select the first active feed if available
      const activeFeeds = (response.feeds || response.items || []).filter((f: GTFSFeed) => f.is_active)
      if (activeFeeds.length > 0) {
        setSelectedFeedId(activeFeeds[0].id.toString())
      } else if ((response.feeds || response.items || []).length > 0) {
        setSelectedFeedId((response.feeds || response.items)[0].id.toString())
      }
    } catch (error) {
      console.error('Failed to load feeds:', error)
      notifications.show({
        title: t('common.error'),
        message: t('feeds.loadError', 'Failed to load feeds'),
        color: 'red',
      })
    } finally {
      setLoadingFeeds(false)
    }
  }

  // Step 1 -> Step 2: Start export generation
  const handleStartExport = async () => {
    if (!selectedFeedId) {
      notifications.show({
        title: t('common.error'),
        message: t('export.selectFeedFirst', 'Please select a feed to export'),
        color: 'red',
      })
      return
    }

    setLoading(true)
    setExportProgress(0)
    setExportResult(null)
    setActive(1)

    try {
      const response = await gtfsApi.generateExport(parseInt(selectedFeedId))
      setExportTaskId(response.task_id)
      setExportId(response.export_id)

      // Start polling for export progress
      pollingRef.current = setInterval(() => {
        pollExportTask(response.task_id)
      }, 1500)
    } catch (error: any) {
      setLoading(false)
      setActive(0)
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('export.startError', 'Failed to start export'),
        color: 'red',
      })
    }
  }

  const pollExportTask = useCallback(async (taskId: number) => {
    try {
      const task: Task = await tasksApi.get(taskId)
      setExportProgress(task.progress || 0)

      if (task.status === 'completed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setExportTaskId(null)
        setLoading(false)

        const result = task.result_data as ExportTaskResult
        setExportResult(result)
        if (result.export_id) {
          setExportId(result.export_id)
        }
      } else if (task.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setExportTaskId(null)
        setLoading(false)
        setActive(0)

        notifications.show({
          title: t('export.failed', 'Export failed'),
          message: task.error_message || t('export.unknownError', 'Unknown error during export'),
          color: 'red',
        })
      }
    } catch (error) {
      console.error('Error polling export task:', error)
    }
  }, [t])

  // Step 2 -> Step 3: Go to download
  const handleProceedToDownload = () => {
    setActive(2)
  }

  // Step 3: Download actions
  const handleDownloadGtfs = async () => {
    if (!exportId) return

    try {
      const feedName = exportResult?.feed_name || 'export'
      await gtfsApi.downloadExportGtfs(exportId, `gtfs_${feedName.replace(/\s+/g, '_').toLowerCase()}.zip`)
      setDownloadComplete(true)
      notifications.show({
        title: t('common.success'),
        message: t('export.downloadStarted', 'GTFS download started'),
        color: 'green',
      })
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('export.downloadError', 'Failed to download GTFS file'),
        color: 'red',
      })
    }
  }

  const handleDownloadReport = async () => {
    if (!exportId) return

    try {
      await gtfsApi.downloadExportReport(exportId)
      notifications.show({
        title: t('common.success'),
        message: t('export.reportDownloadStarted', 'Validation report download started'),
        color: 'green',
      })
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('export.reportDownloadError', 'Failed to download validation report'),
        color: 'red',
      })
    }
  }

  const handleViewReport = async () => {
    if (!exportId) return

    try {
      await gtfsApi.openExportReport(exportId)
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('export.reportViewError', 'Failed to open validation report'),
        color: 'red',
      })
    }
  }

  const handleComplete = () => {
    if (onComplete) {
      onComplete()
    }
  }

  const handleCancel = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
    }
    if (onCancel) {
      onCancel()
    }
  }

  // Get selected feed info
  const selectedFeed = feeds.find(f => f.id.toString() === selectedFeedId)
  const selectedAgency = agencies.find(a => a.id.toString() === selectedAgencyId)

  // Render Step 1: Feed Selection
  const renderStep1 = () => (
    <Stack>
      <Text size="lg" fw={500}>{t('export.selectFeed', 'Select Feed to Export')}</Text>
      <Text c="dimmed" size="sm">
        {t('export.selectFeedDesc', 'Choose the agency and feed you want to export. The system will generate a GTFS ZIP file and validate it.')}
      </Text>

      <Group gap="md" grow>
        <Select
          label={t('export.selectAgency', 'Select Agency')}
          placeholder={t('export.chooseAgency', 'Choose an agency')}
          data={agencies.map((a) => ({ value: a.id.toString(), label: a.name }))}
          value={selectedAgencyId}
          onChange={setSelectedAgencyId}
          searchable
          required
        />
        <Select
          label={t('export.selectFeed', 'Select Feed')}
          placeholder={loadingFeeds ? t('common.loading', 'Loading...') : t('export.chooseFeed', 'Choose a feed')}
          data={feeds.map((f) => ({
            value: f.id.toString(),
            label: `${f.name}${f.is_active ? ' (Active)' : ''}`,
          }))}
          value={selectedFeedId}
          onChange={setSelectedFeedId}
          disabled={!selectedAgencyId || loadingFeeds}
          searchable
          required
          rightSection={loadingFeeds ? <Loader size="xs" /> : null}
        />
      </Group>

      {selectedFeed && (
        <Paper p="md" withBorder>
          <Text fw={500} mb="sm">{t('export.feedSummary', 'Feed Summary')}</Text>
          <Table>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td fw={500}>{t('export.feedName', 'Name')}</Table.Td>
                <Table.Td>{selectedFeed.name}</Table.Td>
              </Table.Tr>
              {selectedFeed.description && (
                <Table.Tr>
                  <Table.Td fw={500}>{t('export.description', 'Description')}</Table.Td>
                  <Table.Td>{selectedFeed.description}</Table.Td>
                </Table.Tr>
              )}
              {selectedFeed.version && (
                <Table.Tr>
                  <Table.Td fw={500}>{t('export.version', 'Version')}</Table.Td>
                  <Table.Td>{selectedFeed.version}</Table.Td>
                </Table.Tr>
              )}
              <Table.Tr>
                <Table.Td fw={500}>{t('export.status', 'Status')}</Table.Td>
                <Table.Td>
                  <Badge color={selectedFeed.is_active ? 'green' : 'gray'}>
                    {selectedFeed.is_active ? t('common.active', 'Active') : t('common.inactive', 'Inactive')}
                  </Badge>
                </Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td fw={500}>{t('export.importedAt', 'Imported At')}</Table.Td>
                <Table.Td>{new Date(selectedFeed.imported_at).toLocaleString()}</Table.Td>
              </Table.Tr>
              {(selectedFeed.total_routes || selectedFeed.total_stops || selectedFeed.total_trips) && (
                <Table.Tr>
                  <Table.Td fw={500}>{t('export.stats', 'Statistics')}</Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      {selectedFeed.total_routes && <Badge variant="light">{selectedFeed.total_routes} routes</Badge>}
                      {selectedFeed.total_stops && <Badge variant="light">{selectedFeed.total_stops} stops</Badge>}
                      {selectedFeed.total_trips && <Badge variant="light">{selectedFeed.total_trips} trips</Badge>}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
    </Stack>
  )

  // Render Step 2: Validation
  const renderStep2 = () => (
    <Stack>
      <Text size="lg" fw={500}>{t('export.validation', 'Validation')}</Text>
      <Text c="dimmed" size="sm">
        {t('export.validationDesc', 'The system is generating and validating your GTFS export using the MobilityData GTFS Validator.')}
      </Text>

      {exportTaskId && (
        <Paper p="md" withBorder>
          <Stack>
            <Group>
              <Loader size="sm" />
              <Text>
                {exportProgress < 40
                  ? t('export.generating', 'Generating GTFS file...')
                  : t('export.validating', 'Validating GTFS file...')}
              </Text>
            </Group>
            <Progress value={exportProgress} animated />
            <Text size="sm" c="dimmed">{t('export.progress', 'Progress')}: {Math.round(exportProgress)}%</Text>
          </Stack>
        </Paper>
      )}

      {exportResult && (
        <Stack>
          <Paper p="md" withBorder>
            <Stack>
              <Group>
                {exportResult.validation.valid ? (
                  <ThemeIcon color="green" size="lg" radius="xl">
                    <IconCheck size={20} />
                  </ThemeIcon>
                ) : (
                  <ThemeIcon color="yellow" size="lg" radius="xl">
                    <IconAlertCircle size={20} />
                  </ThemeIcon>
                )}
                <div>
                  <Text fw={500}>
                    {exportResult.validation.valid
                      ? t('export.validationPassed', 'Validation Passed')
                      : t('export.validationIssues', 'Validation Completed with Issues')}
                  </Text>
                  <Text size="sm" c="dimmed">
                    {exportResult.validation.error_count} {t('export.errors', 'errors')}, {exportResult.validation.warning_count} {t('export.warnings', 'warnings')}, {exportResult.validation.info_count} {t('export.info', 'info')}
                  </Text>
                </div>
              </Group>

              <Divider />

              <Group gap="xs">
                <Text size="sm" c="dimmed">{t('export.fileSize', 'File Size')}:</Text>
                <Badge variant="light">{formatFileSize(exportResult.gtfs_file_size)}</Badge>
              </Group>

              {exportId && (
                <Button
                  variant="light"
                  leftSection={<IconExternalLink size={16} />}
                  onClick={handleViewReport}
                >
                  {t('export.viewFullReport', 'View Full Report')}
                </Button>
              )}
            </Stack>
          </Paper>

          {exportResult.validation.error_count > 0 && (
            <Alert color="yellow" icon={<IconAlertCircle />}>
              {t('export.hasErrors', 'The exported file has validation errors. You can still download it, but it may not work correctly with some GTFS consumers.')}
            </Alert>
          )}
        </Stack>
      )}
    </Stack>
  )

  // Render Step 3: Download
  const renderStep3 = () => (
    <Stack>
      <Text size="lg" fw={500}>{t('export.download', 'Download')}</Text>
      <Text c="dimmed" size="sm">
        {t('export.downloadDesc', 'Your GTFS export is ready. Download the ZIP file and the validation report.')}
      </Text>

      {exportResult && (
        <Paper p="md" withBorder>
          <Stack>
            <Group>
              <ThemeIcon color="green" size="lg" radius="xl">
                <IconFileZip size={20} />
              </ThemeIcon>
              <div>
                <Text fw={500}>{exportResult.feed_name}</Text>
                <Text size="sm" c="dimmed">
                  {formatFileSize(exportResult.gtfs_file_size)} • {t('export.ready', 'Ready to download')}
                </Text>
              </div>
            </Group>

            <Divider />

            {/* Summary */}
            <Paper p="sm" bg="gray.0" radius="md">
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm">{t('export.agency', 'Agency')}:</Text>
                  <Text size="sm" fw={500}>{selectedAgency?.name}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm">{t('export.feed', 'Feed')}:</Text>
                  <Text size="sm" fw={500}>{exportResult.feed_name}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm">{t('export.validation', 'Validation')}:</Text>
                  <Badge color={exportResult.validation.valid ? 'green' : 'yellow'}>
                    {exportResult.validation.error_count} {t('export.errors', 'errors')}, {exportResult.validation.warning_count} {t('export.warnings', 'warnings')}
                  </Badge>
                </Group>
              </Stack>
            </Paper>

            <Divider />

            <Group grow>
              <Button
                size="lg"
                leftSection={<IconDownload size={20} />}
                onClick={handleDownloadGtfs}
              >
                {t('export.downloadGtfs', 'Download GTFS')}
              </Button>
              <Button
                size="lg"
                variant="light"
                leftSection={<IconDownload size={20} />}
                onClick={handleDownloadReport}
              >
                {t('export.downloadReport', 'Download Report')}
              </Button>
            </Group>

            {downloadComplete && (
              <Alert color="green" icon={<IconCheck />}>
                {t('export.downloadComplete', 'Download started! Check your downloads folder.')}
              </Alert>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  )

  const canProceed = () => {
    switch (active) {
      case 0:
        return selectedAgencyId !== null && selectedFeedId !== null
      case 1:
        return exportResult !== null
      case 2:
        return true
      default:
        return false
    }
  }

  return (
    <Paper p="xl">
      <Stepper active={active} onStepClick={setActive} allowNextStepsSelect={false}>
        <Stepper.Step
          label={t('export.step1', 'Select Feed')}
          description={t('export.step1Desc', 'Choose agency and feed')}
          icon={<IconDatabase size={18} />}
        >
          {renderStep1()}
        </Stepper.Step>

        <Stepper.Step
          label={t('export.step2', 'Validate')}
          description={t('export.step2Desc', 'Check GTFS validity')}
          icon={<IconShieldCheck size={18} />}
        >
          {renderStep2()}
        </Stepper.Step>

        <Stepper.Step
          label={t('export.step3', 'Download')}
          description={t('export.step3Desc', 'Get your files')}
          icon={<IconDownload size={18} />}
        >
          {renderStep3()}
        </Stepper.Step>
      </Stepper>

      <Group justify="space-between" mt="xl">
        <Button variant="default" onClick={active === 0 ? handleCancel : () => setActive(active - 1)} disabled={loading}>
          {active === 0 ? t('common.cancel', 'Cancel') : t('common.back', 'Back')}
        </Button>

        {active === 0 && (
          <Button
            onClick={handleStartExport}
            disabled={!canProceed() || loading}
            loading={loading}
          >
            {t('export.generateAndValidate', 'Generate & Validate')}
          </Button>
        )}

        {active === 1 && exportResult && (
          <Button onClick={handleProceedToDownload}>
            {t('common.next', 'Next')}
          </Button>
        )}

        {active === 2 && (
          <Button onClick={handleComplete} color="green">
            {t('common.done', 'Done')}
          </Button>
        )}
      </Group>
    </Paper>
  )
}
