import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Paper,
  Tabs,
  FileButton,
  Button,
  Select,
  Switch,
  Alert,
  Badge,
  Table,
  List,
  LoadingOverlay,
  TextInput,
  Textarea,
  rem,
  Modal,
  Progress,
  Accordion,
  Divider,
} from '@mantine/core'
import {
  IconFileImport,
  IconFileExport,
  IconCheck,
  IconAlertCircle,
  IconInfoCircle,
  IconUpload,
  IconDownload,
  IconFileZip,
  IconShieldCheck,
  IconX,
} from '@tabler/icons-react'
import { gtfsApi, agencyApi, type GTFSValidationResult, type GTFSExportStats, type Agency, type MobilityDataValidationResult } from '../lib/gtfs-api'
import { tasksApi, type Task } from '../lib/tasks-api'
import { notifications } from '@mantine/notifications'
import { useNavigate } from 'react-router-dom'
import FeedSelector from '../components/FeedSelector'
import GTFSImportWizard from '../components/GTFSImportWizard'
import { useTranslation } from 'react-i18next'

// Helper function to get next season and year
function getSeasonAndYear(): string {
  const now = new Date()
  const month = now.getMonth() // 0-11
  let year = now.getFullYear()

  let season: string
  // Determine next season based on current month
  if (month >= 2 && month <= 4) {
    // Spring (Mar-May) -> Next is Summer
    season = 'Summer'
  } else if (month >= 5 && month <= 7) {
    // Summer (Jun-Aug) -> Next is Fall
    season = 'Fall'
  } else if (month >= 8 && month <= 10) {
    // Fall (Sep-Nov) -> Next is Winter
    season = 'Winter'
  } else {
    // Winter (Dec-Feb) -> Next is Spring
    season = 'Spring'
    // If we're in Dec, next Spring is next year
    if (month === 11) {
      year += 1
    }
  }

  return `${season} ${year}`
}

export default function ImportExport() {
  const { t: _t } = useTranslation()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<string | null>('import')
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgency, setSelectedAgency] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [validationResult, setValidationResult] = useState<GTFSValidationResult | null>(null)
  const [exportStats, setExportStats] = useState<GTFSExportStats | null>(null)

  // Ref to prevent duplicate imports (React StrictMode issue)
  const importInProgressRef = useRef(false)

  // Import options
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [skipShapes, setSkipShapes] = useState(false)
  const [stopOnError, setStopOnError] = useState(true)

  // Feed metadata - default name is current season and year
  const [feedName, setFeedName] = useState(getSeasonAndYear())
  const [feedDescription, setFeedDescription] = useState('')
  const [feedVersion, setFeedVersion] = useState('')

  // Export options
  const [selectedExportFeed, setSelectedExportFeed] = useState<string | null>(null)
  const [includeShapes, setIncludeShapes] = useState(true)
  const [includeCalendarDates, setIncludeCalendarDates] = useState(true)

  // MobilityData validation state
  const [useMobilityDataValidator, setUseMobilityDataValidator] = useState(true)
  const [mobilityDataResult, setMobilityDataResult] = useState<MobilityDataValidationResult | null>(null)
  const [validationTaskId, setValidationTaskId] = useState<number | null>(null)
  const [validationProgress, setValidationProgress] = useState(0)
  const [validationStatus, setValidationStatus] = useState<string>('')
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [_pendingImport, setPendingImport] = useState(false)
  const [validateOnlyMode, setValidateOnlyMode] = useState(false)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    loadAgencies()
  }, [])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [])

  // Poll for validation task completion
  const pollValidationTask = useCallback(async (taskId: number) => {
    try {
      const task: Task = await tasksApi.get(taskId)
      setValidationProgress(task.progress || 0)
      setValidationStatus(task.result_data?.status || task.status)

      if (task.status === 'completed') {
        // Clear polling
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setValidationTaskId(null)
        setLoading(false)

        // Get the validation result
        const result = task.result_data as MobilityDataValidationResult
        setMobilityDataResult(result)

        if (validateOnlyMode) {
          // Validate only mode - just show results, don't proceed with import
          if (result?.valid) {
            notifications.show({
              title: 'Validation Passed',
              message: `GTFS file is valid. ${result.warning_count || 0} warnings found. View the full report below.`,
              color: 'green',
            })
          } else {
            notifications.show({
              title: 'Validation Issues Found',
              message: `${result?.error_count || 0} errors, ${result?.warning_count || 0} warnings found.`,
              color: 'orange',
            })
          }
          setValidateOnlyMode(false)
        } else if (result?.valid) {
          // Valid - proceed with import automatically
          notifications.show({
            title: 'Validation Passed',
            message: `GTFS file is valid. ${result.warning_count} warnings found.`,
            color: 'green',
          })
          // Proceed with import
          await executeImport()
        } else {
          // Invalid - show confirmation dialog
          notifications.show({
            title: 'Validation Issues Found',
            message: `${result?.error_count || 0} errors, ${result?.warning_count || 0} warnings found.`,
            color: 'orange',
          })
          setShowConfirmModal(true)
        }
      } else if (task.status === 'failed') {
        // Clear polling
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setValidationTaskId(null)
        setLoading(false)

        notifications.show({
          title: 'Validation Failed',
          message: task.error_message || 'An error occurred during validation',
          color: 'red',
        })
      }
    } catch (error) {
      console.error('Error polling validation task:', error)
    }
  }, [])

  // Start polling when validation task is created
  useEffect(() => {
    if (validationTaskId) {
      // Poll immediately
      pollValidationTask(validationTaskId)
      // Then poll every 2 seconds
      pollingRef.current = setInterval(() => {
        pollValidationTask(validationTaskId)
      }, 2000)
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [validationTaskId, pollValidationTask])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
      if (data.items?.length > 0) {
        setSelectedAgency(data.items[0].id.toString())
      }
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load agencies',
        color: 'red',
      })
    }
  }

  const handleValidate = async () => {
    if (!file) {
      notifications.show({
        title: 'Error',
        message: 'Please select a GTFS ZIP file',
        color: 'red',
      })
      return
    }

    // Use MobilityData validation (async task)
    setLoading(true)
    setValidationResult(null)
    setMobilityDataResult(null)
    setValidationProgress(0)
    setValidationStatus('Queuing validation...')
    setValidateOnlyMode(true)

    try {
      // Queue MobilityData validation
      const response = await gtfsApi.validateMobilityData(file)
      setValidationTaskId(response.task_id)
      setValidationStatus('Validation in progress...')
      // Polling will handle the rest
    } catch (error: any) {
      console.error('Validation Error:', error)
      setLoading(false)
      setValidateOnlyMode(false)
      notifications.show({
        title: 'Validation Error',
        message: error.response?.data?.detail || 'Failed to start validation',
        color: 'red',
      })
    }
  }

  // Execute the actual import (after validation passes or user confirms)
  const executeImport = async () => {
    if (!file || !selectedAgency) return

    importInProgressRef.current = true
    setLoading(true)
    setPendingImport(false)

    try {
      // Queue the import task (returns Task object)
      const task = await gtfsApi.import(file, parseInt(selectedAgency), {
        replace_existing: replaceExisting,
        skip_shapes: skipShapes,
        stop_on_error: stopOnError,
        feed_name: feedName,
        feed_description: feedDescription,
        feed_version: feedVersion,
      })

      // Show success notification
      notifications.show({
        title: 'Import Task Queued',
        message: `Import task "${task.task_name}" has been queued. Track progress in Task Manager.`,
        color: 'blue',
        autoClose: 5000,
      })

      // Navigate to Task Manager to show the task
      setTimeout(() => {
        navigate('/tasks')
      }, 1500)
    } catch (error: any) {
      console.error('GTFS Import Error:', error)
      const errorMessage = error.response?.data?.detail
        || error.response?.data?.message
        || error.message
        || 'Failed to queue import task'

      notifications.show({
        title: 'Import Error',
        message: errorMessage,
        color: 'red',
      })
    } finally {
      setLoading(false)
      importInProgressRef.current = false
    }
  }

  const handleImport = async () => {
    // Prevent duplicate imports (React StrictMode causes duplicate function calls)
    if (importInProgressRef.current) {
      return
    }

    if (!file || !selectedAgency) {
      notifications.show({
        title: 'Error',
        message: 'Please select a GTFS ZIP file and an agency',
        color: 'red',
      })
      return
    }

    if (!feedName.trim()) {
      notifications.show({
        title: 'Error',
        message: 'Please provide a feed name',
        color: 'red',
      })
      return
    }

    // If MobilityData validation is enabled, validate first
    if (useMobilityDataValidator) {
      setLoading(true)
      setMobilityDataResult(null)
      setValidationProgress(0)
      setValidationStatus('Queuing validation...')

      try {
        // Queue MobilityData validation
        const response = await gtfsApi.validateMobilityData(file)
        setValidationTaskId(response.task_id)
        setValidationStatus('Validation in progress...')
        // Polling will handle the rest
      } catch (error: any) {
        console.error('Validation Error:', error)
        setLoading(false)
        notifications.show({
          title: 'Validation Error',
          message: error.response?.data?.detail || 'Failed to start validation',
          color: 'red',
        })
      }
    } else {
      // Skip validation, import directly
      await executeImport()
    }
  }

  // Handle user confirmation to proceed despite validation errors
  const handleConfirmImport = async () => {
    setShowConfirmModal(false)
    await executeImport()
  }

  // Handle user canceling import due to validation errors
  const handleCancelImport = () => {
    setShowConfirmModal(false)
    setPendingImport(false)
  }

  const handleLoadExportStats = async () => {
    if (!selectedAgency) {
      notifications.show({
        title: 'Error',
        message: 'Please select an agency',
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      const feedId = selectedExportFeed ? parseInt(selectedExportFeed) : undefined
      const stats = await gtfsApi.getExportStats(parseInt(selectedAgency), feedId)
      setExportStats(stats)
    } catch (error: any) {
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to load export statistics',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    if (!selectedAgency) {
      notifications.show({
        title: 'Error',
        message: 'Please select an agency',
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      await gtfsApi.export(parseInt(selectedAgency), {
        feed_id: selectedExportFeed ? parseInt(selectedExportFeed) : undefined,
        include_shapes: includeShapes,
        include_calendar_dates: includeCalendarDates,
      })

      notifications.show({
        title: 'Export Started',
        message: 'Your GTFS export will download shortly',
        color: 'green',
      })
    } catch (error: any) {
      notifications.show({
        title: 'Export Error',
        message: error.response?.data?.detail || 'Failed to export GTFS data',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>GTFS Import & Export</Title>
          <Text c="dimmed" mt="sm">
            Import GTFS data from ZIP files or export your data to GTFS format
          </Text>
        </div>

        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="import" leftSection={<IconFileImport style={{ width: rem(16), height: rem(16) }} />}>
              Import
            </Tabs.Tab>
            <Tabs.Tab value="export" leftSection={<IconFileExport style={{ width: rem(16), height: rem(16) }} />}>
              Export
            </Tabs.Tab>
          </Tabs.List>

          {/* Import Tab */}
          <Tabs.Panel value="import" pt="xl">
            <GTFSImportWizard
              onComplete={() => navigate('/tasks')}
              onCancel={() => setActiveTab('export')}
            />
          </Tabs.Panel>

          {/* Export Tab */}
          <Tabs.Panel value="export" pt="xl">
            <Stack gap="lg">
              <Paper withBorder shadow="sm" p="xl" radius="md" pos="relative">
                <LoadingOverlay visible={loading} />
                <Stack gap="md">
                  <Title order={3}>Export GTFS Data</Title>

                  <Group gap="md" grow>
                    <Select
                      label="Select Agency"
                      placeholder="Choose an agency"
                      data={agencies.map((a) => ({ value: a.id.toString(), label: a.name }))}
                      value={selectedAgency}
                      onChange={setSelectedAgency}
                      required
                    />
                    <FeedSelector
                      agencyId={selectedAgency ? parseInt(selectedAgency) : null}
                      value={selectedExportFeed}
                      onChange={setSelectedExportFeed}
                      showAllOption={true}
                      style={{ flex: 1 }}
                    />
                  </Group>

                  <Stack gap="xs">
                    <Title order={5}>Export Options</Title>
                    <Switch
                      label="Include shapes"
                      description="Include shapes.txt in export"
                      checked={includeShapes}
                      onChange={(e) => setIncludeShapes(e.currentTarget.checked)}
                    />
                    <Switch
                      label="Include calendar dates"
                      description="Include calendar_dates.txt (exceptions) in export"
                      checked={includeCalendarDates}
                      onChange={(e) => setIncludeCalendarDates(e.currentTarget.checked)}
                    />
                  </Stack>

                  <Group>
                    <Button
                      leftSection={<IconInfoCircle size={16} />}
                      onClick={handleLoadExportStats}
                      disabled={!selectedAgency}
                      variant="light"
                    >
                      Preview Export
                    </Button>
                    <Button leftSection={<IconDownload size={16} />} onClick={handleExport} disabled={!selectedAgency}>
                      Export to ZIP
                    </Button>
                  </Group>
                </Stack>
              </Paper>

              {/* Export Statistics */}
              {exportStats && (
                <Paper withBorder shadow="sm" p="xl" radius="md">
                  <Stack gap="md">
                    <Title order={4}>Export Preview</Title>

                    <Alert icon={<IconInfoCircle size={16} />} title="Data Summary" color="blue">
                      This export will include the following data from the selected agency:
                    </Alert>

                    <Table>
                      <Table.Tbody>
                        <Table.Tr>
                          <Table.Td fw={500}>Routes</Table.Td>
                          <Table.Td>{exportStats.route_count}</Table.Td>
                        </Table.Tr>
                        <Table.Tr>
                          <Table.Td fw={500}>Stops</Table.Td>
                          <Table.Td>{exportStats.stop_count}</Table.Td>
                        </Table.Tr>
                        <Table.Tr>
                          <Table.Td fw={500}>Trips</Table.Td>
                          <Table.Td>{exportStats.trip_count}</Table.Td>
                        </Table.Tr>
                        <Table.Tr>
                          <Table.Td fw={500}>Stop Times</Table.Td>
                          <Table.Td>{exportStats.stop_time_count}</Table.Td>
                        </Table.Tr>
                        <Table.Tr>
                          <Table.Td fw={500}>Calendars (Services)</Table.Td>
                          <Table.Td>{exportStats.calendar_count}</Table.Td>
                        </Table.Tr>
                        <Table.Tr>
                          <Table.Td fw={500}>Calendar Exceptions</Table.Td>
                          <Table.Td>{exportStats.calendar_date_count}</Table.Td>
                        </Table.Tr>
                        <Table.Tr>
                          <Table.Td fw={500}>Shape Points</Table.Td>
                          <Table.Td>{exportStats.shape_count}</Table.Td>
                        </Table.Tr>
                      </Table.Tbody>
                    </Table>
                  </Stack>
                </Paper>
              )}
            </Stack>
          </Tabs.Panel>
        </Tabs>
      </Stack>

      {/* Validation Confirmation Modal */}
      <Modal
        opened={showConfirmModal}
        onClose={handleCancelImport}
        title={
          <Group gap="sm">
            <IconAlertCircle size={24} color="orange" />
            <Text fw={600}>Validation Issues Found</Text>
          </Group>
        }
        size="lg"
      >
        <Stack gap="md">
          {mobilityDataResult && (
            <>
              <Alert color="orange" icon={<IconAlertCircle size={16} />}>
                The GTFS file has validation issues. You can still proceed with the import, but it's recommended to fix these issues first.
              </Alert>

              <Group gap="lg">
                <div>
                  <Text size="sm" c="dimmed">Errors</Text>
                  <Text size="xl" fw={700} c="red">{mobilityDataResult.error_count}</Text>
                </div>
                <div>
                  <Text size="sm" c="dimmed">Warnings</Text>
                  <Text size="xl" fw={700} c="orange">{mobilityDataResult.warning_count}</Text>
                </div>
                <div>
                  <Text size="sm" c="dimmed">Info</Text>
                  <Text size="xl" fw={700} c="blue">{mobilityDataResult.info_count}</Text>
                </div>
              </Group>

              {mobilityDataResult.report_json?.notices && mobilityDataResult.report_json.notices.length > 0 && (
                <Accordion>
                  <Accordion.Item value="errors">
                    <Accordion.Control icon={<IconAlertCircle size={16} color="red" />}>
                      Errors ({mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length})
                    </Accordion.Control>
                    <Accordion.Panel>
                      <Stack gap="xs">
                        {mobilityDataResult.report_json.notices
                          .filter(n => n.severity === 'ERROR')
                          .slice(0, 10)
                          .map((notice, idx) => (
                            <Alert key={idx} color="red" variant="light" p="xs">
                              <Text size="sm" fw={500}>{notice.code}</Text>
                              {notice.totalNotices && (
                                <Text size="xs" c="dimmed">{notice.totalNotices} occurrences</Text>
                              )}
                            </Alert>
                          ))}
                        {mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length > 10 && (
                          <Text size="xs" c="dimmed">
                            ... and {mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length - 10} more errors
                          </Text>
                        )}
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                  <Accordion.Item value="warnings">
                    <Accordion.Control icon={<IconInfoCircle size={16} color="orange" />}>
                      Warnings ({mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length})
                    </Accordion.Control>
                    <Accordion.Panel>
                      <Stack gap="xs">
                        {mobilityDataResult.report_json.notices
                          .filter(n => n.severity === 'WARNING')
                          .slice(0, 10)
                          .map((notice, idx) => (
                            <Alert key={idx} color="yellow" variant="light" p="xs">
                              <Text size="sm" fw={500}>{notice.code}</Text>
                              {notice.totalNotices && (
                                <Text size="xs" c="dimmed">{notice.totalNotices} occurrences</Text>
                              )}
                            </Alert>
                          ))}
                        {mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length > 10 && (
                          <Text size="xs" c="dimmed">
                            ... and {mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length - 10} more warnings
                          </Text>
                        )}
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              )}
            </>
          )}

          <Group justify="flex-end" mt="md">
            <Button variant="outline" onClick={handleCancelImport} leftSection={<IconX size={16} />}>
              Cancel Import
            </Button>
            <Button color="orange" onClick={handleConfirmImport} leftSection={<IconUpload size={16} />}>
              Import Anyway
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Container>
  )
}
