import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Stepper,
  Group,
  Button,
  Paper,
  Text,
  Stack,
  FileButton,
  Alert,
  Table,
  Badge,
  Select,
  TextInput,
  Progress,
  Accordion,
  List,
  Divider,
  Radio,
  Switch,
  Loader,
  ThemeIcon,
  Box,
  rem,
} from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import {
  IconUpload,
  IconFileZip,
  IconX,
  IconCheck,
  IconAlertCircle,
  IconInfoCircle,
  IconBuilding,
  IconPlus,
  IconShieldCheck,
  IconPlayerPlay,
  IconExternalLink,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { useNavigate } from 'react-router-dom'
import {
  gtfsApi,
  agencyApi,
  type Agency,
  type GTFSAnalysisResult,
  type GTFSAgencyInfo,
  type MobilityDataValidationResult,
} from '../lib/gtfs-api'
import { tasksApi, type Task } from '../lib/tasks-api'

interface GTFSImportWizardProps {
  onComplete?: () => void
  onCancel?: () => void
}

// Helper function to format file size
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Helper function to get next season and year
function getSeasonAndYear(): string {
  const now = new Date()
  const month = now.getMonth()
  let year = now.getFullYear()

  let season: string
  if (month >= 2 && month <= 4) {
    season = 'Summer'
  } else if (month >= 5 && month <= 7) {
    season = 'Fall'
  } else if (month >= 8 && month <= 10) {
    season = 'Winter'
  } else {
    season = 'Spring'
    if (month === 11) {
      year += 1
    }
  }

  return `${season} ${year}`
}

export default function GTFSImportWizard({ onComplete, onCancel }: GTFSImportWizardProps) {
  const navigate = useNavigate()
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)

  // Step 1: File upload
  const [file, setFile] = useState<File | null>(null)

  // Step 2: Agency detection
  const [analysisResult, setAnalysisResult] = useState<GTFSAnalysisResult | null>(null)
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [agencyChoice, setAgencyChoice] = useState<'existing' | 'new'>('existing')
  const [selectedAgencyId, setSelectedAgencyId] = useState<string | null>(null)
  const [newAgencyName, setNewAgencyName] = useState('')
  const [newAgencyTimezone, setNewAgencyTimezone] = useState('America/New_York')

  // Step 3: Validation
  const [validationTaskId, setValidationTaskId] = useState<number | null>(null)
  const [validationProgress, setValidationProgress] = useState(0)
  const [validationResult, setValidationResult] = useState<MobilityDataValidationResult | null>(null)
  const [skipValidation, setSkipValidation] = useState(false)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  // Step 4: Import options and execution
  const [feedName, setFeedName] = useState(getSeasonAndYear())
  const [feedDescription, setFeedDescription] = useState('')
  const [feedVersion, setFeedVersion] = useState('')
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [skipShapes, setSkipShapes] = useState(false)
  const [stopOnError, setStopOnError] = useState(false)
  const [importTaskId, setImportTaskId] = useState<number | null>(null)
  const [importProgress, setImportProgress] = useState(0)
  const [importStatus, setImportStatus] = useState<string>('')
  const [importComplete, setImportComplete] = useState(false)

  // Load agencies on mount
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

  const loadAgencies = async () => {
    try {
      const response = await agencyApi.list()
      setAgencies(response.items || response)
    } catch (error) {
      console.error('Failed to load agencies:', error)
    }
  }

  // Step 1: Handle file upload and analyze
  const handleFileSelect = async (selectedFile: File | null) => {
    if (!selectedFile) return

    setFile(selectedFile)
    setLoading(true)

    try {
      const result = await gtfsApi.analyze(selectedFile)
      setAnalysisResult(result)

      // Pre-fill agency info if detected
      if (result.agencies_in_file.length > 0) {
        const gtfsAgency = result.agencies_in_file[0]
        setNewAgencyName(gtfsAgency.agency_name)
        if (gtfsAgency.agency_timezone) {
          setNewAgencyTimezone(gtfsAgency.agency_timezone)
        }
      }

      // Pre-select matching agency if found
      if (result.matching_agencies.length > 0) {
        setSelectedAgencyId(result.matching_agencies[0].id.toString())
        setAgencyChoice('existing')
      } else if (result.agencies_in_file.length > 0) {
        setAgencyChoice('new')
      }

      // Move to step 2
      setActive(1)
    } catch (error: any) {
      notifications.show({
        title: 'Error analyzing file',
        message: error.response?.data?.detail || error.message,
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  // Step 2: Proceed to validation
  const handleProceedToValidation = () => {
    if (agencyChoice === 'existing' && !selectedAgencyId) {
      notifications.show({
        title: 'Please select an agency',
        message: 'You must select an existing agency or choose to create a new one',
        color: 'red',
      })
      return
    }
    if (agencyChoice === 'new' && !newAgencyName.trim()) {
      notifications.show({
        title: 'Please enter agency name',
        message: 'Agency name is required when creating a new agency',
        color: 'red',
      })
      return
    }
    setActive(2)
  }

  // Step 3: Start validation
  const startValidation = async () => {
    if (!analysisResult) return

    setLoading(true)
    setValidationProgress(0)
    setValidationResult(null)

    try {
      const response = await gtfsApi.validateUploadedFile(analysisResult.upload_id)
      setValidationTaskId(response.task_id)

      // Start polling for validation progress
      pollingRef.current = setInterval(() => {
        pollValidationTask(response.task_id)
      }, 1500)
    } catch (error: any) {
      setLoading(false)
      notifications.show({
        title: 'Error starting validation',
        message: error.response?.data?.detail || error.message,
        color: 'red',
      })
    }
  }

  const pollValidationTask = useCallback(async (taskId: number) => {
    try {
      const task: Task = await tasksApi.get(taskId)
      setValidationProgress(task.progress || 0)

      if (task.status === 'completed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setValidationTaskId(null)
        setLoading(false)

        const result = task.result_data as MobilityDataValidationResult
        setValidationResult(result)
      } else if (task.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setValidationTaskId(null)
        setLoading(false)

        notifications.show({
          title: 'Validation failed',
          message: task.error_message || 'Unknown error during validation',
          color: 'red',
        })
      }
    } catch (error) {
      console.error('Error polling validation task:', error)
    }
  }, [])

  // Step 4: Start import
  const startImport = async () => {
    if (!analysisResult) return

    setLoading(true)
    setImportProgress(0)
    setImportStatus('Starting import...')

    try {
      const agencyId = agencyChoice === 'existing' ? parseInt(selectedAgencyId!) : 0

      const response = await gtfsApi.importFromUpload(analysisResult.upload_id, agencyId, {
        create_agency: agencyChoice === 'new',
        agency_name: agencyChoice === 'new' ? newAgencyName : undefined,
        agency_timezone: agencyChoice === 'new' ? newAgencyTimezone : undefined,
        replace_existing: replaceExisting,
        skip_shapes: skipShapes,
        stop_on_error: stopOnError,
        feed_name: feedName,
        feed_description: feedDescription || undefined,
        feed_version: feedVersion || undefined,
      })

      setImportTaskId(response.id)

      // Start polling for import progress
      pollingRef.current = setInterval(() => {
        pollImportTask(response.id)
      }, 1500)
    } catch (error: any) {
      setLoading(false)
      notifications.show({
        title: 'Error starting import',
        message: error.response?.data?.detail || error.message,
        color: 'red',
      })
    }
  }

  const pollImportTask = useCallback(async (taskId: number) => {
    try {
      const task: Task = await tasksApi.get(taskId)
      setImportProgress(task.progress || 0)
      setImportStatus(task.result_data?.current_file || task.description || 'Importing...')

      if (task.status === 'completed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setImportTaskId(null)
        setLoading(false)
        setImportComplete(true)

        notifications.show({
          title: 'Import complete',
          message: 'GTFS data has been successfully imported',
          color: 'green',
        })
      } else if (task.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setImportTaskId(null)
        setLoading(false)

        notifications.show({
          title: 'Import failed',
          message: task.error_message || 'Unknown error during import',
          color: 'red',
        })
      }
    } catch (error) {
      console.error('Error polling import task:', error)
    }
  }, [])

  const handleComplete = () => {
    if (onComplete) {
      onComplete()
    } else {
      navigate('/tasks')
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

  // Render Step 1: File Upload
  const renderStep1 = () => (
    <Stack>
      <Text size="lg" fw={500}>Select GTFS File</Text>
      <Text c="dimmed" size="sm">
        Upload a GTFS ZIP file to begin the import process. We'll analyze the file and extract agency information.
      </Text>

      <Dropzone
        onDrop={(files) => handleFileSelect(files[0])}
        accept={['application/zip', 'application/x-zip-compressed']}
        maxSize={500 * 1024 * 1024}
        loading={loading}
      >
        <Group justify="center" gap="xl" mih={180} style={{ pointerEvents: 'none' }}>
          <Dropzone.Accept>
            <IconUpload style={{ width: rem(52), height: rem(52), color: 'var(--mantine-color-blue-6)' }} stroke={1.5} />
          </Dropzone.Accept>
          <Dropzone.Reject>
            <IconX style={{ width: rem(52), height: rem(52), color: 'var(--mantine-color-red-6)' }} stroke={1.5} />
          </Dropzone.Reject>
          <Dropzone.Idle>
            <IconFileZip style={{ width: rem(52), height: rem(52), color: 'var(--mantine-color-dimmed)' }} stroke={1.5} />
          </Dropzone.Idle>

          <div>
            <Text size="xl" inline>
              Drag GTFS file here or click to select
            </Text>
            <Text size="sm" c="dimmed" inline mt={7}>
              File should be a valid GTFS ZIP archive (max 500MB)
            </Text>
          </div>
        </Group>
      </Dropzone>

      {file && (
        <Alert color="green" icon={<IconCheck />}>
          Selected: {file.name} ({formatFileSize(file.size)})
        </Alert>
      )}
    </Stack>
  )

  // Render Step 2: Agency Detection
  const renderStep2 = () => {
    if (!analysisResult) return null

    const gtfsAgency = analysisResult.agencies_in_file[0]

    return (
      <Stack>
        <Text size="lg" fw={500}>Agency Selection</Text>

        {/* File Summary */}
        <Paper p="md" withBorder>
          <Stack gap="xs">
            <Group>
              <Text fw={500}>File:</Text>
              <Text>{analysisResult.filename}</Text>
              <Badge>{formatFileSize(analysisResult.file_size_bytes)}</Badge>
            </Group>

            {!analysisResult.has_required_files && (
              <Alert color="yellow" icon={<IconAlertCircle />}>
                Missing required files: {analysisResult.missing_files.join(', ')}
              </Alert>
            )}

            {analysisResult.extra_files.length > 0 && (
              <Alert color="blue" icon={<IconInfoCircle />}>
                Extra (non-standard) files found: {analysisResult.extra_files.join(', ')}
              </Alert>
            )}
          </Stack>
        </Paper>

        {/* Agency from file */}
        {gtfsAgency && (
          <Paper p="md" withBorder>
            <Text fw={500} mb="sm">Agency found in GTFS file:</Text>
            <Table>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td fw={500}>Name</Table.Td>
                  <Table.Td>{gtfsAgency.agency_name}</Table.Td>
                </Table.Tr>
                {gtfsAgency.agency_id && (
                  <Table.Tr>
                    <Table.Td fw={500}>ID</Table.Td>
                    <Table.Td>{gtfsAgency.agency_id}</Table.Td>
                  </Table.Tr>
                )}
                {gtfsAgency.agency_url && (
                  <Table.Tr>
                    <Table.Td fw={500}>URL</Table.Td>
                    <Table.Td>{gtfsAgency.agency_url}</Table.Td>
                  </Table.Tr>
                )}
                {gtfsAgency.agency_timezone && (
                  <Table.Tr>
                    <Table.Td fw={500}>Timezone</Table.Td>
                    <Table.Td>{gtfsAgency.agency_timezone}</Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Paper>
        )}

        {/* Agency choice */}
        <Radio.Group
          value={agencyChoice}
          onChange={(v) => setAgencyChoice(v as 'existing' | 'new')}
          label="Import destination"
          description="Choose where to import this GTFS data"
        >
          <Stack mt="sm">
            <Radio value="existing" label="Import to existing agency" />
            <Radio value="new" label="Create new agency" />
          </Stack>
        </Radio.Group>

        {agencyChoice === 'existing' && (
          <Stack>
            {analysisResult.matching_agencies.length > 0 && (
              <Alert color="blue" icon={<IconInfoCircle />}>
                We found {analysisResult.matching_agencies.length} potential match(es) based on the GTFS file
              </Alert>
            )}

            <Select
              label="Select Agency"
              placeholder="Choose an agency"
              value={selectedAgencyId}
              onChange={setSelectedAgencyId}
              data={agencies.map((a) => {
                const match = analysisResult.matching_agencies.find((m) => m.id === a.id)
                return {
                  value: a.id.toString(),
                  label: match
                    ? `${a.name} (${Math.round(match.match_score * 100)}% match)`
                    : a.name,
                }
              })}
              searchable
            />

            {selectedAgencyId && analysisResult.matching_agencies.find((m) => m.id === parseInt(selectedAgencyId)) && (
              <Text size="sm" c="dimmed">
                Match reason: {analysisResult.matching_agencies.find((m) => m.id === parseInt(selectedAgencyId))?.match_reason}
              </Text>
            )}
          </Stack>
        )}

        {agencyChoice === 'new' && (
          <Stack>
            <TextInput
              label="Agency Name"
              placeholder="Enter agency name"
              value={newAgencyName}
              onChange={(e) => setNewAgencyName(e.currentTarget.value)}
              required
            />
            <Select
              label="Timezone"
              value={newAgencyTimezone}
              onChange={(v) => setNewAgencyTimezone(v || 'America/New_York')}
              data={[
                { value: 'America/New_York', label: 'America/New_York (Eastern)' },
                { value: 'America/Chicago', label: 'America/Chicago (Central)' },
                { value: 'America/Denver', label: 'America/Denver (Mountain)' },
                { value: 'America/Los_Angeles', label: 'America/Los_Angeles (Pacific)' },
                { value: 'America/Toronto', label: 'America/Toronto' },
                { value: 'America/Montreal', label: 'America/Montreal' },
                { value: 'America/Vancouver', label: 'America/Vancouver' },
                { value: 'America/Sao_Paulo', label: 'America/Sao_Paulo' },
                { value: 'Europe/London', label: 'Europe/London' },
                { value: 'Europe/Paris', label: 'Europe/Paris' },
                { value: 'Europe/Berlin', label: 'Europe/Berlin' },
              ]}
              searchable
            />
          </Stack>
        )}

        {/* File contents summary */}
        <Accordion variant="contained">
          <Accordion.Item value="files">
            <Accordion.Control icon={<IconFileZip size={20} />}>
              Files in GTFS ({analysisResult.files_summary.length} files)
            </Accordion.Control>
            <Accordion.Panel>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>File</Table.Th>
                    <Table.Th>Rows</Table.Th>
                    <Table.Th>Columns</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {analysisResult.files_summary.map((f) => (
                    <Table.Tr key={f.filename}>
                      <Table.Td>{f.filename}</Table.Td>
                      <Table.Td>{f.row_count.toLocaleString()}</Table.Td>
                      <Table.Td>{f.columns.length}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Stack>
    )
  }

  // Render Step 3: Validation
  const renderStep3 = () => (
    <Stack>
      <Text size="lg" fw={500}>Validation</Text>
      <Text c="dimmed" size="sm">
        Validate the GTFS file using the MobilityData GTFS Validator. You can skip validation and proceed directly to import if needed.
      </Text>

      {!validationResult && !validationTaskId && (
        <Stack>
          <Switch
            label="Skip validation"
            description="Proceed directly to import without validating"
            checked={skipValidation}
            onChange={(e) => setSkipValidation(e.currentTarget.checked)}
          />

          {!skipValidation && (
            <Button
              leftSection={<IconShieldCheck size={20} />}
              onClick={startValidation}
              loading={loading}
            >
              Start Validation
            </Button>
          )}

          {skipValidation && (
            <Alert color="yellow" icon={<IconAlertCircle />}>
              Validation will be skipped. The file will be imported without checking for errors.
            </Alert>
          )}
        </Stack>
      )}

      {validationTaskId && (
        <Paper p="md" withBorder>
          <Stack>
            <Group>
              <Loader size="sm" />
              <Text>Validating GTFS file...</Text>
            </Group>
            <Progress value={validationProgress} animated />
            <Text size="sm" c="dimmed">Progress: {Math.round(validationProgress)}%</Text>
          </Stack>
        </Paper>
      )}

      {validationResult && (
        <Stack>
          <Paper p="md" withBorder>
            <Stack>
              <Group>
                {validationResult.valid ? (
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
                    {validationResult.valid ? 'Validation Passed' : 'Validation Completed with Issues'}
                  </Text>
                  <Text size="sm" c="dimmed">
                    {validationResult.error_count} errors, {validationResult.warning_count} warnings, {validationResult.info_count} info
                  </Text>
                </div>
              </Group>

              {validationResult.validation_id && (
                <Button
                  variant="light"
                  leftSection={<IconExternalLink size={16} />}
                  onClick={() => gtfsApi.openValidationReport(validationResult.validation_id!)}
                >
                  View Full Report
                </Button>
              )}
            </Stack>
          </Paper>

          {validationResult.error_count > 0 && (
            <Alert color="yellow" icon={<IconAlertCircle />}>
              The file has {validationResult.error_count} validation errors. You can still proceed with the import, but some data may be invalid.
            </Alert>
          )}
        </Stack>
      )}
    </Stack>
  )

  // Render Step 4: Import
  const renderStep4 = () => (
    <Stack>
      <Text size="lg" fw={500}>Import Options</Text>

      {!importTaskId && !importComplete && (
        <Stack>
          <Paper p="md" withBorder>
            <Stack>
              <TextInput
                label="Feed Name"
                description="A name to identify this GTFS feed"
                value={feedName}
                onChange={(e) => setFeedName(e.currentTarget.value)}
              />
              <TextInput
                label="Feed Description"
                description="Optional description for this feed"
                value={feedDescription}
                onChange={(e) => setFeedDescription(e.currentTarget.value)}
              />
              <TextInput
                label="Feed Version"
                description="Optional version identifier"
                value={feedVersion}
                onChange={(e) => setFeedVersion(e.currentTarget.value)}
              />
            </Stack>
          </Paper>

          <Paper p="md" withBorder>
            <Stack>
              <Text fw={500}>Import Options</Text>
              <Switch
                label="Replace existing data"
                description="Deactivate existing feeds for this agency"
                checked={replaceExisting}
                onChange={(e) => setReplaceExisting(e.currentTarget.checked)}
              />
              <Switch
                label="Skip shapes"
                description="Don't import shapes.txt (faster import)"
                checked={skipShapes}
                onChange={(e) => setSkipShapes(e.currentTarget.checked)}
              />
              <Switch
                label="Stop on error"
                description="Stop import if validation errors are found"
                checked={stopOnError}
                onChange={(e) => setStopOnError(e.currentTarget.checked)}
              />
            </Stack>
          </Paper>

          {/* Summary */}
          <Paper p="md" withBorder bg="gray.0">
            <Stack gap="xs">
              <Text fw={500}>Import Summary</Text>
              <Divider />
              <Group>
                <Text size="sm" c="dimmed">File:</Text>
                <Text size="sm">{analysisResult?.filename}</Text>
              </Group>
              <Group>
                <Text size="sm" c="dimmed">Agency:</Text>
                <Text size="sm">
                  {agencyChoice === 'new'
                    ? `New: ${newAgencyName}`
                    : agencies.find((a) => a.id.toString() === selectedAgencyId)?.name}
                </Text>
              </Group>
              <Group>
                <Text size="sm" c="dimmed">Feed Name:</Text>
                <Text size="sm">{feedName}</Text>
              </Group>
              {validationResult && (
                <Group>
                  <Text size="sm" c="dimmed">Validation:</Text>
                  <Badge color={validationResult.valid ? 'green' : 'yellow'}>
                    {validationResult.error_count} errors, {validationResult.warning_count} warnings
                  </Badge>
                </Group>
              )}
            </Stack>
          </Paper>

          <Button
            size="lg"
            leftSection={<IconPlayerPlay size={20} />}
            onClick={startImport}
            loading={loading}
          >
            Start Import
          </Button>
        </Stack>
      )}

      {importTaskId && (
        <Paper p="md" withBorder>
          <Stack>
            <Group>
              <Loader size="sm" />
              <Text fw={500}>Importing GTFS data...</Text>
            </Group>
            <Progress value={importProgress} animated />
            <Text size="sm" c="dimmed">{importStatus}</Text>
            <Text size="sm" c="dimmed">Progress: {Math.round(importProgress)}%</Text>
          </Stack>
        </Paper>
      )}

      {importComplete && (
        <Paper p="md" withBorder>
          <Stack align="center">
            <ThemeIcon color="green" size={60} radius="xl">
              <IconCheck size={40} />
            </ThemeIcon>
            <Text fw={500} size="lg">Import Complete!</Text>
            <Text c="dimmed">Your GTFS data has been successfully imported.</Text>
            <Button onClick={handleComplete}>Go to Task Manager</Button>
          </Stack>
        </Paper>
      )}
    </Stack>
  )

  const canProceed = () => {
    switch (active) {
      case 0:
        return file !== null && analysisResult !== null
      case 1:
        return (agencyChoice === 'existing' && selectedAgencyId) || (agencyChoice === 'new' && newAgencyName.trim())
      case 2:
        return skipValidation || validationResult !== null
      case 3:
        return !loading
      default:
        return false
    }
  }

  return (
    <Paper p="xl">
      <Stepper active={active} onStepClick={setActive} allowNextStepsSelect={false}>
        <Stepper.Step
          label="Upload File"
          description="Select GTFS ZIP"
          icon={<IconUpload size={18} />}
        >
          {renderStep1()}
        </Stepper.Step>

        <Stepper.Step
          label="Select Agency"
          description="Choose or create agency"
          icon={<IconBuilding size={18} />}
        >
          {renderStep2()}
        </Stepper.Step>

        <Stepper.Step
          label="Validate"
          description="Check GTFS validity"
          icon={<IconShieldCheck size={18} />}
        >
          {renderStep3()}
        </Stepper.Step>

        <Stepper.Step
          label="Import"
          description="Import GTFS data"
          icon={<IconCheck size={18} />}
        >
          {renderStep4()}
        </Stepper.Step>
      </Stepper>

      {!importComplete && (
        <Group justify="space-between" mt="xl">
          <Button variant="default" onClick={active === 0 ? handleCancel : () => setActive(active - 1)}>
            {active === 0 ? 'Cancel' : 'Back'}
          </Button>

          {active < 3 && (
            <Button
              onClick={() => {
                if (active === 1) {
                  handleProceedToValidation()
                } else if (active === 2) {
                  setActive(3)
                } else {
                  setActive(active + 1)
                }
              }}
              disabled={!canProceed()}
            >
              Next
            </Button>
          )}
        </Group>
      )}
    </Paper>
  )
}
