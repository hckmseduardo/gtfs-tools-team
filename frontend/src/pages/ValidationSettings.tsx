import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Paper,
  Select,
  Switch,
  Button,
  Alert,
  LoadingOverlay,
  Accordion,
  Badge,
  Progress,
  Divider,
  ThemeIcon,
  Tabs,
  Table,
  rem,
} from '@mantine/core'
import {
  IconCheck,
  IconAlertCircle,
  IconSettings,
  IconRoute,
  IconBus,
  IconMapPin,
  IconCalendar,
  IconCalendarEvent,
  IconCurrencyDollar,
  IconInfoCircle,
  IconClock,
  IconDeviceFloppy,
  IconPlayerPlay,
  IconExternalLink,
  IconBrandGithub,
  IconDownload,
} from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { notifications } from '@mantine/notifications'
import {
  validationApi,
  type ValidationPreferences,
  type FeedValidationResult,
  type MobilityDataValidationResult,
  VALIDATION_CATEGORIES,
} from '../lib/validation-api'
import { agencyApi, gtfsApi, type Agency } from '../lib/gtfs-api'
import { tasksApi, TaskStatus, type Task } from '../lib/tasks-api'
import FeedSelector from '../components/FeedSelector'
import { useNavigate } from 'react-router-dom'

// Category icons mapping
const categoryIcons: Record<string, React.ReactNode> = {
  routes: <IconRoute size={18} />,
  shapes: <IconBus size={18} />,
  stops: <IconMapPin size={18} />,
  calendar: <IconCalendar size={18} />,
  calendar_dates: <IconCalendarEvent size={18} />,
  fare_attributes: <IconCurrencyDollar size={18} />,
  feed_info: <IconInfoCircle size={18} />,
  trips: <IconRoute size={18} />,
  stop_times: <IconClock size={18} />,
}

export default function ValidationSettings() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [selectedAgency, setSelectedAgency] = useState<string | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [preferences, setPreferences] = useState<ValidationPreferences | null>(null)
  const [hasChanges, setHasChanges] = useState(false)
  const [validationResult, setValidationResult] = useState<FeedValidationResult | null>(null)
  const [activeTab, setActiveTab] = useState<string | null>('settings')
  const [validationTask, setValidationTask] = useState<Task | null>(null)
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null)
  const [mobilityDataResult, setMobilityDataResult] = useState<MobilityDataValidationResult | null>(null)
  const [validatorType, setValidatorType] = useState<'internal' | 'mobilitydata'>('internal')

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadPreferences(parseInt(selectedAgency))
    }
  }, [selectedAgency])

  // Clean up polling interval on unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [pollingInterval])

  // Poll for task completion
  const pollTaskStatus = async (taskId: number) => {
    try {
      const task = await tasksApi.get(taskId)
      setValidationTask(task)

      if (task.status === TaskStatus.COMPLETED) {
        // Stop polling
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
        setValidating(false)

        // Check if this is a MobilityData validation result
        if (task.result_data?.validator === 'mobilitydata') {
          setMobilityDataResult(task.result_data as MobilityDataValidationResult)
          setValidationResult(null)
        } else {
          // Extract internal validation result from task.result_data
          setMobilityDataResult(null)
          if (task.result_data?.validation) {
            setValidationResult(task.result_data.validation as FeedValidationResult)
          } else if (task.result_data) {
            // Fallback: construct result from result_data fields
            setValidationResult({
              valid: task.result_data.valid ?? false,
              error_count: task.result_data.error_count ?? 0,
              warning_count: task.result_data.warning_count ?? 0,
              info_count: task.result_data.info_count ?? 0,
              issues: task.result_data.validation?.issues ?? [],
              summary: task.result_data.summary ?? '',
            })
          }
        }

        notifications.show({
          title: t('common.success'),
          message: t('validationSettings.validationComplete'),
          color: 'green',
        })
      } else if (task.status === TaskStatus.FAILED) {
        // Stop polling on failure
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
        setValidating(false)

        notifications.show({
          title: t('common.error'),
          message: task.error_message || t('validationSettings.validationFailed'),
          color: 'red',
        })
      }
    } catch (error) {
      console.error('Error polling task status:', error)
    }
  }

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
      if (data.items?.length > 0) {
        setSelectedAgency(data.items[0].id.toString())
      }
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('validationSettings.loadError'),
        color: 'red',
      })
    }
  }

  const loadPreferences = async (agencyId: number) => {
    setLoading(true)
    try {
      const prefs = await validationApi.getPreferences(agencyId)
      setPreferences(prefs)
      setHasChanges(false)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('validationSettings.loadPreferencesError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = (key: string, value: boolean) => {
    if (preferences) {
      setPreferences({
        ...preferences,
        [key]: value,
      })
      setHasChanges(true)
    }
  }

  const handleSave = async () => {
    if (!selectedAgency || !preferences) return

    setSaving(true)
    try {
      const updated = await validationApi.updatePreferences(parseInt(selectedAgency), preferences)
      setPreferences(updated)
      setHasChanges(false)
      notifications.show({
        title: t('common.success'),
        message: t('validationSettings.saveSuccess'),
        color: 'green',
      })
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('validationSettings.saveError'),
        color: 'red',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleEnableAll = () => {
    if (preferences) {
      const updated = { ...preferences }
      Object.values(VALIDATION_CATEGORIES).forEach((category) => {
        category.rules.forEach((rule) => {
          ;(updated as any)[rule.key] = true
        })
      })
      setPreferences(updated)
      setHasChanges(true)
    }
  }

  const handleDisableAll = () => {
    if (preferences) {
      const updated = { ...preferences }
      Object.values(VALIDATION_CATEGORIES).forEach((category) => {
        category.rules.forEach((rule) => {
          ;(updated as any)[rule.key] = false
        })
      })
      setPreferences(updated)
      setHasChanges(true)
    }
  }

  const handleRunValidation = async (validator: 'internal' | 'mobilitydata' = 'internal') => {
    if (!selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: t('validationSettings.selectFeedFirst'),
        color: 'red',
      })
      return
    }

    setValidating(true)
    setValidationResult(null)
    setMobilityDataResult(null)
    setValidationTask(null)
    setValidatorType(validator)

    // Clear any existing polling interval
    if (pollingInterval) {
      clearInterval(pollingInterval)
      setPollingInterval(null)
    }

    try {
      // Queue the validation task
      const taskResponse = validator === 'mobilitydata'
        ? await validationApi.validateFeedMobilityData(parseInt(selectedFeed))
        : await validationApi.validateFeed(parseInt(selectedFeed))

      notifications.show({
        title: t('validationSettings.validationQueued'),
        message: taskResponse.message,
        color: 'blue',
      })

      // Start polling for task completion
      const interval = setInterval(() => {
        pollTaskStatus(taskResponse.task_id)
      }, 2000) // Poll every 2 seconds

      setPollingInterval(interval)

      // Initial poll
      await pollTaskStatus(taskResponse.task_id)
    } catch (error: any) {
      setValidating(false)
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('validationSettings.validationError'),
        color: 'red',
      })
    }
  }

  const handleOpenMobilityDataReport = async () => {
    if (!mobilityDataResult?.validation_id) return

    try {
      // Use authenticated blob fetch so the report opens even when direct URL requests are blocked by auth
      await gtfsApi.openValidationReport(mobilityDataResult.validation_id, 'branded')
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('validationSettings.openReportError') || 'Failed to open original report',
        color: 'red',
      })
    }
  }

  const handleDownloadGtfsFile = async () => {
    if (!mobilityDataResult?.validation_id) return

    try {
      await gtfsApi.downloadValidationGtfsFile(mobilityDataResult.validation_id, mobilityDataResult.feed_name ? `${mobilityDataResult.feed_name}.zip` : 'gtfs.zip')
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('taskManager.gtfsDownloadError'),
        color: 'red',
      })
    }
  }

  const handleGoToTaskManager = () => {
    navigate('/tasks')
  }

  const countEnabledRules = (): { enabled: number; total: number } => {
    if (!preferences) return { enabled: 0, total: 0 }

    let enabled = 0
    let total = 0

    Object.values(VALIDATION_CATEGORIES).forEach((category) => {
      category.rules.forEach((rule) => {
        total++
        if ((preferences as any)[rule.key]) {
          enabled++
        }
      })
    })

    return { enabled, total }
  }

  const { enabled, total } = countEnabledRules()

  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>{t('validationSettings.title')}</Title>
          <Text c="dimmed" mt="sm">
            {t('validationSettings.description')}
          </Text>
        </div>

        {/* Agency Selector */}
        <Paper withBorder shadow="sm" p="md" radius="md">
          <Group gap="md" grow>
            <Select
              label={t('validationSettings.selectAgency')}
              placeholder={t('validationSettings.selectAgencyPlaceholder')}
              data={agencies.map((a) => ({ value: a.id.toString(), label: a.name }))}
              value={selectedAgency}
              onChange={setSelectedAgency}
              searchable
            />
            <FeedSelector
              agencyId={selectedAgency ? parseInt(selectedAgency) : null}
              value={selectedFeed}
              onChange={setSelectedFeed}
              style={{ flex: 1 }}
            />
          </Group>
        </Paper>

        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="settings" leftSection={<IconSettings style={{ width: rem(16), height: rem(16) }} />}>
              {t('validationSettings.settingsTab')}
            </Tabs.Tab>
            <Tabs.Tab value="validate" leftSection={<IconPlayerPlay style={{ width: rem(16), height: rem(16) }} />}>
              {t('validationSettings.validateTab')}
            </Tabs.Tab>
          </Tabs.List>

          {/* Settings Tab */}
          <Tabs.Panel value="settings" pt="xl">
            <Paper withBorder shadow="sm" p="xl" radius="md" pos="relative">
              <LoadingOverlay visible={loading || saving} />

              <Stack gap="lg">
                {/* Summary and Actions */}
                <Group justify="space-between">
                  <div>
                    <Text size="sm" c="dimmed">
                      {t('validationSettings.enabledRules')}
                    </Text>
                    <Group gap="xs" mt={4}>
                      <Badge size="lg" variant="filled" color={enabled === total ? 'green' : enabled > 0 ? 'blue' : 'gray'}>
                        {enabled} / {total}
                      </Badge>
                      <Progress value={(enabled / total) * 100} size="lg" w={100} />
                    </Group>
                  </div>
                  <Group>
                    <Button variant="light" size="sm" onClick={handleEnableAll}>
                      {t('validationSettings.enableAll')}
                    </Button>
                    <Button variant="light" size="sm" color="gray" onClick={handleDisableAll}>
                      {t('validationSettings.disableAll')}
                    </Button>
                  </Group>
                </Group>

                <Divider />

                {/* Validation Rules by Category */}
                {preferences && (
                  <Accordion variant="separated" radius="md">
                    {Object.entries(VALIDATION_CATEGORIES).map(([categoryKey, category]) => {
                      const enabledInCategory = category.rules.filter((rule) => (preferences as any)[rule.key]).length
                      const totalInCategory = category.rules.length

                      return (
                        <Accordion.Item key={categoryKey} value={categoryKey}>
                          <Accordion.Control
                            icon={
                              <ThemeIcon variant="light" size="md">
                                {categoryIcons[categoryKey]}
                              </ThemeIcon>
                            }
                          >
                            <Group gap="xs">
                              <Text fw={500}>{t(`validationSettings.categories.${categoryKey}`)}</Text>
                              <Badge size="sm" variant="light">
                                {enabledInCategory}/{totalInCategory}
                              </Badge>
                            </Group>
                          </Accordion.Control>
                          <Accordion.Panel>
                            <Stack gap="sm">
                              {category.rules.map((rule) => (
                                <Switch
                                  key={rule.key}
                                  label={t(rule.labelKey)}
                                  description={t(`${rule.labelKey}Desc`)}
                                  checked={(preferences as any)[rule.key]}
                                  onChange={(event) => handleToggle(rule.key, event.currentTarget.checked)}
                                />
                              ))}
                            </Stack>
                          </Accordion.Panel>
                        </Accordion.Item>
                      )
                    })}
                  </Accordion>
                )}

                {/* Save Button */}
                <Group justify="flex-end">
                  <Button leftSection={<IconDeviceFloppy size={16} />} onClick={handleSave} disabled={!hasChanges}>
                    {t('validationSettings.savePreferences')}
                  </Button>
                </Group>
              </Stack>
            </Paper>
          </Tabs.Panel>

          {/* Validate Tab */}
          <Tabs.Panel value="validate" pt="xl">
            <Stack gap="lg">
              <Paper withBorder shadow="sm" p="xl" radius="md" pos="relative">
                <Stack gap="md">
                  <Title order={3}>{t('validationSettings.runValidation')}</Title>

                  <Alert icon={<IconInfoCircle size={16} />} color="blue">
                    {t('validationSettings.validationInfo')}
                  </Alert>

                  <Group>
                    <Button
                      leftSection={<IconPlayerPlay size={16} />}
                      onClick={() => handleRunValidation('internal')}
                      disabled={!selectedFeed || validating}
                      loading={validating && validatorType === 'internal' && !validationTask}
                    >
                      {t('validationSettings.validateFeed')}
                    </Button>
                    <Button
                      leftSection={<IconBrandGithub size={16} />}
                      onClick={() => handleRunValidation('mobilitydata')}
                      disabled={!selectedFeed || validating}
                      loading={validating && validatorType === 'mobilitydata' && !validationTask}
                      variant="outline"
                      color="grape"
                    >
                      {t('validationSettings.validateMobilityData') || 'MobilityData Validator'}
                    </Button>
                    <Button
                      variant="light"
                      onClick={handleGoToTaskManager}
                    >
                      {t('validationSettings.goToTaskManager')}
                    </Button>
                  </Group>
                </Stack>
              </Paper>

              {/* Task Progress */}
              {validationTask && validating && (
                <Paper withBorder shadow="sm" p="xl" radius="md">
                  <Stack gap="md">
                    <Group justify="space-between">
                      <Title order={4}>{t('validationSettings.taskProgress')}</Title>
                      <Badge color="blue" size="lg">
                        {validationTask.status.toUpperCase()}
                      </Badge>
                    </Group>

                    <Text size="sm" c="dimmed">
                      {validationTask.description}
                    </Text>

                    <Progress
                      value={validationTask.progress}
                      size="lg"
                      animated={validationTask.status === TaskStatus.RUNNING}
                    />

                    <Text size="sm" ta="center">
                      {validationTask.progress.toFixed(0)}%
                    </Text>
                  </Stack>
                </Paper>
              )}

              {/* Internal Validation Results */}
              {validationResult && (
                <Paper withBorder shadow="sm" p="xl" radius="md">
                  <Stack gap="md">
                    <Group justify="space-between">
                      <Title order={4}>{t('validationSettings.validationResults')}</Title>
                      <Badge color={validationResult.valid ? 'green' : 'red'} size="lg">
                        {validationResult.valid ? t('validation.passed') : t('validationSettings.failed')}
                      </Badge>
                    </Group>

                    <Alert
                      icon={validationResult.valid ? <IconCheck size={16} /> : <IconAlertCircle size={16} />}
                      title={validationResult.summary}
                      color={validationResult.valid ? 'green' : 'orange'}
                    />

                    <Group gap="lg">
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('validation.errors')}
                        </Text>
                        <Text size="xl" fw={700} c="red">
                          {validationResult.error_count}
                        </Text>
                      </div>
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('validation.warnings')}
                        </Text>
                        <Text size="xl" fw={700} c="orange">
                          {validationResult.warning_count}
                        </Text>
                      </div>
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('common.info')}
                        </Text>
                        <Text size="xl" fw={700} c="blue">
                          {validationResult.info_count}
                        </Text>
                      </div>
                    </Group>

                    {validationResult.issues.length > 0 && (
                      <>
                        <Title order={5}>{t('validationSettings.issues')}</Title>
                        <Table striped highlightOnHover>
                          <Table.Thead>
                            <Table.Tr>
                              <Table.Th>{t('validationSettings.severity')}</Table.Th>
                              <Table.Th>{t('validationSettings.category')}</Table.Th>
                              <Table.Th>{t('validationSettings.message')}</Table.Th>
                              <Table.Th>{t('validationSettings.entity')}</Table.Th>
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {validationResult.issues.slice(0, 50).map((issue, idx) => (
                              <Table.Tr key={idx}>
                                <Table.Td>
                                  <Badge
                                    color={issue.severity === 'error' ? 'red' : issue.severity === 'warning' ? 'orange' : 'blue'}
                                  >
                                    {issue.severity.toUpperCase()}
                                  </Badge>
                                </Table.Td>
                                <Table.Td>{issue.category}</Table.Td>
                                <Table.Td>{issue.message}</Table.Td>
                                <Table.Td>
                                  {issue.entity_type && issue.entity_id
                                    ? `${issue.entity_type}: ${issue.entity_id}`
                                    : '-'}
                                </Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                        {validationResult.issues.length > 50 && (
                          <Text size="sm" c="dimmed" ta="center">
                            {t('validationSettings.moreIssues', { count: validationResult.issues.length - 50 })}
                          </Text>
                        )}
                      </>
                    )}
                  </Stack>
                </Paper>
              )}

              {/* MobilityData Validation Results */}
              {mobilityDataResult && (
                <Paper withBorder shadow="sm" p="xl" radius="md">
                  <Stack gap="md">
                    <Group justify="space-between">
                      <Group>
                        <ThemeIcon color="grape" size="lg" variant="light">
                          <IconBrandGithub size={20} />
                        </ThemeIcon>
                        <Title order={4}>
                          {t('validationSettings.mobilityDataResults') || 'MobilityData Validation Results'}
                        </Title>
                      </Group>
                      <Badge color={mobilityDataResult.valid ? 'green' : 'red'} size="lg">
                        {mobilityDataResult.valid ? t('validation.passed') : t('validationSettings.failed')}
                      </Badge>
                    </Group>

                    <Alert
                      icon={mobilityDataResult.valid ? <IconCheck size={16} /> : <IconAlertCircle size={16} />}
                      title={mobilityDataResult.valid
                        ? t('validationSettings.feedIsValid') || 'Feed is valid according to GTFS specification'
                        : t('validationSettings.feedHasErrors') || 'Feed has validation errors'}
                      color={mobilityDataResult.valid ? 'green' : 'orange'}
                    >
                      {t('validationSettings.validatedIn') || 'Validated in'} {mobilityDataResult.duration_seconds?.toFixed(2)}s
                    </Alert>

                    <Group gap="lg">
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('validation.errors')}
                        </Text>
                        <Text size="xl" fw={700} c="red">
                          {mobilityDataResult.error_count}
                        </Text>
                      </div>
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('validation.warnings')}
                        </Text>
                        <Text size="xl" fw={700} c="orange">
                          {mobilityDataResult.warning_count}
                        </Text>
                      </div>
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('common.info')}
                        </Text>
                        <Text size="xl" fw={700} c="blue">
                          {mobilityDataResult.info_count}
                        </Text>
                      </div>
                      <div>
                        <Text size="sm" c="dimmed">
                          {t('validationSettings.totalNotices') || 'Total Notices'}
                        </Text>
                        <Text size="xl" fw={700}>
                          {mobilityDataResult.total_notices}
                        </Text>
                      </div>
                    </Group>

                    {mobilityDataResult.validation_id && (
                      <Group>
                        <Button
                          leftSection={<IconExternalLink size={16} />}
                          variant="light"
                          onClick={handleOpenMobilityDataReport}
                        >
                          {t('validationSettings.viewFullReport') || 'View Full Report'}
                        </Button>
                        <Button
                          leftSection={<IconDownload size={16} />}
                          variant="subtle"
                          onClick={async () => {
                            try {
                              await gtfsApi.downloadValidationReport(mobilityDataResult.validation_id!, 'branded')
                            } catch (error) {
                              notifications.show({
                                title: t('common.error'),
                                message: t('validationSettings.downloadReportError') || 'Failed to download validation report',
                                color: 'red',
                              })
                            }
                          }}
                        >
                          {t('validationSettings.downloadReport') || 'Download Report'}
                        </Button>
                        <Button
                          leftSection={<IconExternalLink size={16} />}
                          variant="subtle"
                          onClick={async () => {
                            try {
                              await gtfsApi.openValidationReport(mobilityDataResult.validation_id!, 'original')
                            } catch (error) {
                              notifications.show({
                                title: t('common.error'),
                                message: t('validationSettings.openReportError') || 'Failed to open original report',
                                color: 'red',
                              })
                            }
                          }}
                        >
                          {t('validationSettings.originalReport') || 'Original MobilityData Report'}
                        </Button>
                        <Button
                          leftSection={<IconDownload size={16} />}
                          variant="outline"
                          onClick={handleDownloadGtfsFile}
                        >
                          {t('validationSettings.downloadGtfs') || 'Download GTFS'}
                        </Button>
                      </Group>
                    )}

                    {/* Notices Accordion */}
                    {mobilityDataResult.report_json?.notices && mobilityDataResult.report_json.notices.length > 0 && (
                      <Accordion variant="separated">
                        {mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length > 0 && (
                          <Accordion.Item value="errors">
                            <Accordion.Control icon={<IconAlertCircle size={16} color="red" />}>
                              {t('validation.errors')} ({mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length})
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
                                        <Text size="xs" c="dimmed">{notice.totalNotices} {t('validationSettings.occurrences') || 'occurrences'}</Text>
                                      )}
                                    </Alert>
                                  ))}
                                {mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length > 10 && (
                                  <Text size="xs" c="dimmed">
                                    ... {t('validationSettings.andMore') || 'and'} {mobilityDataResult.report_json.notices.filter(n => n.severity === 'ERROR').length - 10} {t('validationSettings.moreErrors') || 'more errors'}
                                  </Text>
                                )}
                              </Stack>
                            </Accordion.Panel>
                          </Accordion.Item>
                        )}
                        {mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length > 0 && (
                          <Accordion.Item value="warnings">
                            <Accordion.Control icon={<IconInfoCircle size={16} color="orange" />}>
                              {t('validation.warnings')} ({mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length})
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
                                        <Text size="xs" c="dimmed">{notice.totalNotices} {t('validationSettings.occurrences') || 'occurrences'}</Text>
                                      )}
                                    </Alert>
                                  ))}
                                {mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length > 10 && (
                                  <Text size="xs" c="dimmed">
                                    ... {t('validationSettings.andMore') || 'and'} {mobilityDataResult.report_json.notices.filter(n => n.severity === 'WARNING').length - 10} {t('validationSettings.moreWarnings') || 'more warnings'}
                                  </Text>
                                )}
                              </Stack>
                            </Accordion.Panel>
                          </Accordion.Item>
                        )}
                      </Accordion>
                    )}

                    {/* Show GTFS Features if available */}
                    {mobilityDataResult.report_json?.gtfsFeatures && mobilityDataResult.report_json.gtfsFeatures.length > 0 && (
                      <>
                        <Divider />
                        <Title order={5}>{t('validationSettings.gtfsFeatures') || 'GTFS Features Detected'}</Title>
                        <Group gap="xs">
                          {mobilityDataResult.report_json.gtfsFeatures.map((feature, idx) => (
                            <Badge key={idx} color="blue" variant="light">
                              {feature}
                            </Badge>
                          ))}
                        </Group>
                      </>
                    )}
                  </Stack>
                </Paper>
              )}
            </Stack>
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  )
}
