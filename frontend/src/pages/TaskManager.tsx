import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Container,
  Title,
  Text,
  Paper,
  Stack,
  Group,
  Badge,
  Button,
  Progress,
  Table,
  ActionIcon,
  Tooltip,
  Select,
  LoadingOverlay,
  Center,
  Card,
  Box,
  Divider,
  SegmentedControl,
  Collapse,
  UnstyledButton,
  Loader,
  Modal,
  Alert,
} from '@mantine/core'
import { useMediaQuery, useIntersection, useDisclosure } from '@mantine/hooks'
import {
  IconRefresh,
  IconX,
  IconCheck,
  IconAlertTriangle,
  IconClock,
  IconPlayerPlay,
  IconBan,
  IconChevronDown,
  IconChevronUp,
  IconReload,
  IconFileExport,
  IconDownload,
  IconFileZip,
  IconEye,
} from '@tabler/icons-react'
import { tasksApi, Task, TaskStatus, TaskType } from '../lib/tasks-api'
import { gtfsApi } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { formatDistanceToNow, format } from 'date-fns'
import { useTranslation } from 'react-i18next'

const STATUS_COLORS: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: 'gray',
  [TaskStatus.RUNNING]: 'blue',
  [TaskStatus.COMPLETED]: 'green',
  [TaskStatus.FAILED]: 'red',
  [TaskStatus.CANCELLED]: 'orange',
}

const STATUS_ICONS: Record<TaskStatus, any> = {
  [TaskStatus.PENDING]: IconClock,
  [TaskStatus.RUNNING]: IconPlayerPlay,
  [TaskStatus.COMPLETED]: IconCheck,
  [TaskStatus.FAILED]: IconAlertTriangle,
  [TaskStatus.CANCELLED]: IconBan,
}

// Mobile Task Card component
function TaskCard({
  task,
  onCancel,
  onRetry,
  getTaskTypeLabel,
  formatDuration,

  t,
  getLocalizedTaskName,
}: {
  task: Task
  onCancel: (id: number, name: string) => void
  onRetry: (id: number, name: string) => void
  getTaskTypeLabel: (type: TaskType) => string
  formatDuration: (start?: string, end?: string) => string
  t: (key: string, options?: any) => string
  getLocalizedTaskName: (name: string) => string
}) {
  const [expanded, setExpanded] = useState(false)
  const StatusIcon = STATUS_ICONS[task.status]
  const isActive = task.status === TaskStatus.PENDING || task.status === TaskStatus.RUNNING
  const canRetry = task.status === TaskStatus.FAILED && task.result_data?.can_retry

  return (
    <Card shadow="sm" padding="sm" radius="md" withBorder>
      <UnstyledButton onClick={() => setExpanded(!expanded)} w="100%">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
            <Box
              style={{
                width: 36,
                height: 36,
                borderRadius: '50%',
                backgroundColor: `var(--mantine-color-${STATUS_COLORS[task.status]}-light)`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <StatusIcon size={18} color={`var(--mantine-color-${STATUS_COLORS[task.status]}-6)`} />
            </Box>
            <Box style={{ minWidth: 0, flex: 1 }}>
              <Text size="sm" fw={500} truncate>
                {getLocalizedTaskName(task.task_name)}
              </Text>
              <Group gap={4}>
                <Badge size="xs" variant="light">
                  {getTaskTypeLabel(task.task_type)}
                </Badge>
                {isActive && (
                  <Text size="xs" c="dimmed">
                    {task.progress.toFixed(0)}%
                  </Text>
                )}
              </Group>
            </Box>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {canRetry && (
              <ActionIcon
                color="blue"
                variant="subtle"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  onRetry(task.id, task.task_name)
                }}
              >
                <IconReload size={14} />
              </ActionIcon>
            )}
            {isActive && (
              <ActionIcon
                color="red"
                variant="subtle"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  onCancel(task.id, task.task_name)
                }}
              >
                <IconX size={14} />
              </ActionIcon>
            )}
            {expanded ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}
          </Group>
        </Group>

        {/* Progress bar for active tasks */}
        {isActive && (
          <>
            <Progress
              value={task.progress}
              size="xs"
              color={STATUS_COLORS[task.status]}
              mt="xs"
              animated={task.status === TaskStatus.RUNNING}
            />
            {task.result_data?.current_step && (
              <Text size="xs" c="dimmed" mt={4}>
                {task.result_data.current_step}
              </Text>
            )}
          </>
        )}
      </UnstyledButton>

      <Collapse in={expanded}>
        <Divider my="xs" />
        <Stack gap="xs">
          {task.description && (
            <Text size="xs" c="dimmed">
              {task.description}
            </Text>
          )}

          <Group justify="space-between">
            <Text size="xs" c="dimmed">Status</Text>
            <Badge color={STATUS_COLORS[task.status]} size="sm">
              {task.status}
            </Badge>
          </Group>

          <Group justify="space-between">
            <Text size="xs" c="dimmed">Progress</Text>
            <Text size="xs">{task.progress.toFixed(0)}%</Text>
          </Group>

          <Group justify="space-between">
            <Text size="xs" c="dimmed">Duration</Text>
            <Text size="xs">{formatDuration(task.started_at, task.completed_at)}</Text>
          </Group>

          <Group justify="space-between">
            <Text size="xs" c="dimmed">Started</Text>
            <Text size="xs">
              {task.started_at
                ? formatDistanceToNow(new Date(task.started_at), { addSuffix: true })
                : 'Not started'}
            </Text>
          </Group>

          {task.status === TaskStatus.FAILED && task.error_message && (
            <Box
              p="xs"
              style={{
                backgroundColor: 'var(--mantine-color-red-light)',
                borderRadius: 'var(--mantine-radius-sm)',
              }}
            >
              <Text size="xs" c="red">
                {task.error_message}
              </Text>
            </Box>
          )}

          {canRetry && (
            <Button
              leftSection={<IconReload size={14} />}
              size="xs"
              variant="light"
              color="blue"
              onClick={() => onRetry(task.id, task.task_name)}
            >
              {t('tasks.retry')}
            </Button>
          )}
        </Stack>
      </Collapse>
    </Card>
  )
}

// Task Detail Modal Component
function TaskDetailModal({
  task,
  opened,
  onClose,
  onRetry,
  getTaskTypeLabel,
  formatDuration,
  t,
  getLocalizedTaskName,
}: {
  task: Task | null
  opened: boolean
  onClose: () => void
  onRetry: (id: number, name: string) => void
  getTaskTypeLabel: (type: TaskType) => string
  formatDuration: (start?: string, end?: string) => string

  t: (key: string, options?: any) => string
  getLocalizedTaskName: (name: string) => string
}) {
  if (!task) return null

  const StatusIcon = STATUS_ICONS[task.status]
  const isValidationTask = task.task_type === TaskType.VALIDATE_GTFS
  const validationId = task.result_data?.validation_id
  const canRetry = task.result_data?.can_retry && task.status === TaskStatus.FAILED
  const isCompleted = task.status === TaskStatus.COMPLETED
  const isFailed = task.status === TaskStatus.FAILED

  const handleViewReport = async (type: 'branded' | 'original') => {
    if (!validationId) return
    try {
      await gtfsApi.openValidationReport(validationId, type)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('tasks.reportError'),
        color: 'red',
      })
    }
  }

  const handleDownloadReport = async () => {
    if (!validationId) return
    try {
      await gtfsApi.downloadValidationReport(validationId, 'branded')
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('tasks.reportError'),
        color: 'red',
      })
    }
  }

  const handleDownloadGtfs = async () => {
    if (!validationId) return
    try {
      const filename = task.result_data?.filename || `gtfs_${validationId}.zip`
      await gtfsApi.downloadValidationGtfsFile(validationId, filename)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('tasks.gtfsDownloadError'),
        color: 'red',
      })
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap="sm">
          <StatusIcon size={20} color={`var(--mantine-color-${STATUS_COLORS[task.status]}-6)`} />
          <Text fw={600}>{getLocalizedTaskName(task.task_name)}</Text>
        </Group>
      }
      size="lg"
    >
      <Stack gap="md">
        {/* Status and Type Badges */}
        <Group gap="xs">
          <Badge color={STATUS_COLORS[task.status]} size="lg">
            {task.status.toUpperCase()}
          </Badge>
          <Badge variant="light" size="lg">
            {getTaskTypeLabel(task.task_type)}
          </Badge>
        </Group>

        {/* Description */}
        {task.description && (
          <Text size="sm" c="dimmed">
            {task.description}
          </Text>
        )}

        {/* Progress */}
        <Box>
          <Group justify="space-between" mb={4}>
            <Text size="sm" fw={500}>{t('tasks.columns.progress')}</Text>
            <Text size="sm">{task.progress.toFixed(0)}%</Text>
          </Group>
          <Progress
            value={task.progress}
            size="md"
            color={isFailed ? 'red' : isCompleted ? 'green' : 'blue'}
            animated={task.status === TaskStatus.RUNNING}
          />
          {task.result_data?.current_step && task.status === TaskStatus.RUNNING && (
            <Text size="xs" c="dimmed" mt={4}>
              {task.result_data.current_step}
            </Text>
          )}
        </Box>

        {/* Time Info */}
        <Stack gap="xs">
          <Group justify="space-between">
            <Text size="sm" c="dimmed">{t('tasks.columns.duration')}</Text>
            <Text size="sm" fw={500}>{formatDuration(task.started_at, task.completed_at)}</Text>
          </Group>
          <Group justify="space-between">
            <Text size="sm" c="dimmed">{t('tasks.columns.started')}</Text>
            <Text size="sm">
              {task.started_at
                ? format(new Date(task.started_at), 'PPp')
                : t('tasks.notStarted')}
            </Text>
          </Group>
          {task.completed_at && (
            <Group justify="space-between">
              <Text size="sm" c="dimmed">{t('tasks.completedAt')}</Text>
              <Text size="sm">{format(new Date(task.completed_at), 'PPp')}</Text>
            </Group>
          )}
        </Stack>

        {/* Error Message */}
        {isFailed && task.error_message && (
          <Alert color="red" title={t('common.error')} icon={<IconAlertTriangle size={16} />}>
            <Text size="sm">{task.error_message}</Text>
          </Alert>
        )}

        {/* Validation Results Summary */}
        {isValidationTask && task.result_data && (isCompleted || isFailed) && (
          <Box>
            <Text size="sm" fw={500} mb="xs">{t('tasks.validationSummary')}</Text>
            <Group gap="lg">
              <Box ta="center">
                <Text size="xs" c="dimmed">{t('tasks.errors')}</Text>
                <Text size="xl" fw={700} c="red">{task.result_data.error_count || 0}</Text>
              </Box>
              <Box ta="center">
                <Text size="xs" c="dimmed">{t('tasks.warnings')}</Text>
                <Text size="xl" fw={700} c="orange">{task.result_data.warning_count || 0}</Text>
              </Box>
              <Box ta="center">
                <Text size="xs" c="dimmed">{t('tasks.info')}</Text>
                <Text size="xl" fw={700} c="blue">{task.result_data.info_count || 0}</Text>
              </Box>
              {task.result_data.valid !== undefined && (
                <Box ta="center">
                  <Text size="xs" c="dimmed">{t('tasks.result')}</Text>
                  <Badge color={task.result_data.valid ? 'green' : 'red'} size="lg">
                    {task.result_data.valid ? t('tasks.valid') : t('tasks.invalid')}
                  </Badge>
                </Box>
              )}
            </Group>
          </Box>
        )}

        <Divider />

        {/* Action Buttons */}
        <Stack gap="sm">
          {/* Validation Report Buttons */}
          {isValidationTask && validationId && (
            <>
              <Text size="sm" fw={500}>{t('tasks.reports')}</Text>
              <Group gap="sm" wrap="wrap">
                <Button
                  leftSection={<IconEye size={16} />}
                  variant="light"
                  onClick={() => handleViewReport('branded')}
                >
                  {t('tasks.viewFullReport')}
                </Button>
                <Button
                  leftSection={<IconDownload size={16} />}
                  variant="subtle"
                  onClick={handleDownloadReport}
                >
                  {t('tasks.downloadReport')}
                </Button>
                <Button
                  leftSection={<IconFileExport size={16} />}
                  variant="subtle"
                  onClick={() => handleViewReport('original')}
                >
                  {t('tasks.originalReport')}
                </Button>
                <Button
                  leftSection={<IconFileZip size={16} />}
                  variant="subtle"
                  onClick={handleDownloadGtfs}
                >
                  {t('tasks.downloadGtfs')}
                </Button>
              </Group>
            </>
          )}

          {/* Retry Button */}
          {canRetry && (
            <Button
              leftSection={<IconReload size={16} />}
              color="blue"
              onClick={() => {
                onRetry(task.id, task.task_name)
                onClose()
              }}
            >
              {t('tasks.retry')}
            </Button>
          )}
        </Stack>
      </Stack>
    </Modal>
  )
}

const PAGE_SIZE = 10

export default function TaskManager() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [filterStatus, setFilterStatus] = useState<TaskStatus | 'all'>('all')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [detailModalOpened, { open: openDetailModal, close: closeDetailModal }] = useDisclosure(false)

  const getLocalizedTaskName = useCallback((taskName: string) => {
    const mergeMatch = taskName.match(/^Merge feeds into new agency '(.*)'$/)
    if (mergeMatch) {
      return t('agencies.merge.mergeTaskName', { agencyName: mergeMatch[1] })
    }
    return taskName
  }, [t])

  // Track running tasks to detect when they complete
  const runningTasksRef = useRef<Map<number, string>>(new Map())

  // Intersection observer for infinite scroll
  const containerRef = useRef<HTMLDivElement>(null)
  const { ref: loadMoreRef, entry } = useIntersection({
    root: containerRef.current,
    threshold: 0.5,
  })

  useEffect(() => {
    loadTasks()
  }, [filterStatus])

  // Auto-refresh every 3 seconds if enabled (only refresh current items, don't reset pagination)
  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      loadTasks(true) // Silent refresh
    }, 3000)

    return () => clearInterval(interval)
  }, [autoRefresh, filterStatus])

  // Load more when scrolling to bottom
  useEffect(() => {
    if (entry?.isIntersecting && hasMore && !loadingMore && !loading) {
      loadMore()
    }
  }, [entry?.isIntersecting, hasMore, loadingMore, loading])

  const loadTasks = async (silent = false) => {
    if (!silent) setLoading(true)

    try {
      const filters = filterStatus !== 'all' ? { status: filterStatus as TaskStatus } : {}
      const data = await tasksApi.list({ ...filters, limit: PAGE_SIZE, skip: 0 })

      // Check for task state transitions and show notifications
      if (silent) {
        const prevRunning = runningTasksRef.current

        for (const task of data.items) {
          const wasRunning = prevRunning.has(task.id)

          if (wasRunning) {
            const taskName = prevRunning.get(task.id) || task.task_name

            if (task.status === TaskStatus.COMPLETED) {
              const localizedTaskName = getLocalizedTaskName(taskName)
              notifications.show({
                title: t('tasks.completed'),
                message: `${localizedTaskName} ${t('tasks.completedSuccessfully')}`,
                color: 'green',
              })
              prevRunning.delete(task.id)
            } else if (task.status === TaskStatus.FAILED) {
              const localizedTaskName = getLocalizedTaskName(taskName)
              const errorMsg = task.result_data?.error || t('tasks.failedMessage')
              notifications.show({
                title: t('tasks.failed'),
                message: `${localizedTaskName}: ${errorMsg}`,
                color: 'red',
              })
              prevRunning.delete(task.id)
            } else if (task.status === TaskStatus.CANCELLED) {
              prevRunning.delete(task.id)
            }
          }
        }
      }

      // Update tracking of running tasks
      const newRunning = new Map<number, string>()
      for (const task of data.items) {
        if (task.status === TaskStatus.RUNNING || task.status === TaskStatus.PENDING) {
          newRunning.set(task.id, task.task_name)
        }
      }
      runningTasksRef.current = newRunning

      setTasks(data.items)
      setHasMore(data.items.length >= PAGE_SIZE && data.total > PAGE_SIZE)
    } catch (error: any) {
      if (!silent) {
        notifications.show({
          title: t('common.error'),
          message: error.response?.data?.detail || t('tasks.loadError'),
          color: 'red',
        })
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return

    setLoadingMore(true)
    try {
      const filters = filterStatus !== 'all' ? { status: filterStatus as TaskStatus } : {}
      const data = await tasksApi.list({ ...filters, limit: PAGE_SIZE, skip: tasks.length })

      if (data.items.length > 0) {
        setTasks(prev => [...prev, ...data.items])
        setHasMore(data.items.length >= PAGE_SIZE && tasks.length + data.items.length < data.total)
      } else {
        setHasMore(false)
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('tasks.loadError'),
        color: 'red',
      })
    } finally {
      setLoadingMore(false)
    }
  }, [loadingMore, hasMore, tasks.length, filterStatus, t])

  const handleCancelTask = async (taskId: number, taskName: string) => {
    try {
      const localizedTaskName = getLocalizedTaskName(taskName)
      await tasksApi.cancel(taskId)
      notifications.show({
        title: t('tasks.cancelled'),
        message: `${localizedTaskName} ${t('tasks.hasBeenCancelled')}`,
        color: 'orange',
      })
      await loadTasks()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('tasks.cancelError'),
        color: 'red',
      })
    }
  }

  const handleRetryTask = async (taskId: number, taskName: string) => {
    try {
      const localizedTaskName = getLocalizedTaskName(taskName)
      notifications.show({
        id: `retry-${taskId}`,
        title: t('tasks.retrying'),
        message: localizedTaskName,
        color: 'blue',
        loading: true,
        autoClose: false,
      })

      await tasksApi.retry(taskId)

      notifications.update({
        id: `retry-${taskId}`,
        title: t('tasks.retryStarted'),
        message: `${localizedTaskName} ${t('tasks.hasBeenRetried')}`,
        color: 'green',
        loading: false,
        autoClose: 5000,
      })

      await loadTasks()
    } catch (error: any) {
      notifications.update({
        id: `retry-${taskId}`,
        title: t('common.error'),
        message: error.response?.data?.detail || t('tasks.retryError'),
        color: 'red',
        loading: false,
        autoClose: 5000,
      })
    }
  }

  const getTaskTypeLabel = (type: TaskType): string => {
    const labels: Record<TaskType, string> = {
      [TaskType.IMPORT_GTFS]: t('tasks.types.import_gtfs'),
      [TaskType.EXPORT_GTFS]: t('tasks.types.export_gtfs'),
      [TaskType.VALIDATE_GTFS]: t('tasks.types.validate_gtfs'),
      [TaskType.BULK_UPDATE]: t('tasks.types.bulkUpdate'),
      [TaskType.BULK_DELETE]: t('tasks.types.bulkDelete'),
      [TaskType.DELETE_FEED]: t('tasks.types.delete_feed'),
      [TaskType.CLONE_FEED]: t('tasks.types.clone_feed'),
      [TaskType.DELETE_AGENCY]: t('tasks.types.delete_agency'),
      [TaskType.MERGE_AGENCIES]: t('tasks.types.merge_agencies'),
      [TaskType.SPLIT_AGENCY]: t('tasks.types.split_agency'),
    }
    return labels[type] || type
  }

  const formatDuration = (startedAt?: string, completedAt?: string): string => {
    if (!startedAt) return '-'

    const start = new Date(startedAt)
    const end = completedAt ? new Date(completedAt) : new Date()
    const durationMs = end.getTime() - start.getTime()
    const seconds = Math.floor(durationMs / 1000)

    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ${seconds % 60}s`
    const hours = Math.floor(minutes / 60)
    return `${hours}h ${minutes % 60}m`
  }

  const activeTasks = tasks.filter(t =>
    t.status === TaskStatus.PENDING || t.status === TaskStatus.RUNNING
  )

  // Mobile Layout
  if (isMobile) {
    return (
      <Container size="xl" px="xs">
        <Stack gap="md">
          {/* Mobile Header */}
          <Group justify="space-between" align="center">
            <Box>
              <Title order={3}>{t('nav.tasks')}</Title>
              {activeTasks.length > 0 && (
                <Badge size="sm" color="blue" variant="light" mt={4}>
                  {activeTasks.length} {t('tasks.active')}
                </Badge>
              )}
            </Box>
            <Group gap="xs">
              <ActionIcon
                variant={autoRefresh ? 'filled' : 'light'}
                color="blue"
                onClick={() => setAutoRefresh(!autoRefresh)}
                size="lg"
              >
                <IconRefresh size={18} style={{ animation: autoRefresh ? 'spin 2s linear infinite' : 'none' }} />
              </ActionIcon>
            </Group>
          </Group>

          {/* Mobile Filter */}
          <SegmentedControl
            value={filterStatus}
            onChange={(value) => setFilterStatus(value as TaskStatus | 'all')}
            data={[
              { value: 'all', label: t('tasks.filters.all') },
              { value: TaskStatus.RUNNING, label: t('tasks.filters.running') },
              { value: TaskStatus.COMPLETED, label: t('tasks.filters.completed') },
              { value: TaskStatus.FAILED, label: t('tasks.filters.failed') },
            ]}
            size="xs"
            fullWidth
          />

          {/* Tasks List */}
          <Box pos="relative" style={{ minHeight: 200 }}>
            <LoadingOverlay visible={loading} />

            {tasks.length === 0 ? (
              <Center p="xl">
                <Stack align="center" gap="xs">
                  <IconClock size={48} color="var(--mantine-color-dimmed)" />
                  <Text size="md" fw={500} c="dimmed">
                    {t('tasks.noTasks')}
                  </Text>
                  <Text size="sm" c="dimmed" ta="center">
                    {t('tasks.noTasksDescription')}
                  </Text>
                </Stack>
              </Center>
            ) : (
              <Stack gap="sm">
                {tasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onCancel={handleCancelTask}
                    onRetry={handleRetryTask}
                    getTaskTypeLabel={getTaskTypeLabel}
                    formatDuration={formatDuration}
                    t={t}
                    getLocalizedTaskName={getLocalizedTaskName}
                  />
                ))}

                {/* Infinite scroll loader */}
                <div ref={loadMoreRef}>
                  {loadingMore && (
                    <Center py="md">
                      <Loader size="sm" />
                    </Center>
                  )}
                  {!hasMore && tasks.length > 0 && (
                    <Text size="sm" c="dimmed" ta="center" py="md">
                      {t('tasks.noMoreTasks')}
                    </Text>
                  )}
                </div>
              </Stack>
            )}
          </Box>
        </Stack>

        {/* CSS for spinning refresh icon */}
        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </Container>
    )
  }

  // Desktop Layout (original table-based)
  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Group justify="space-between" align="center">
            <div>
              <Title order={1}>{t('nav.tasks')}</Title>
              <Text mt="sm" c="dimmed">
                {t('tasks.subtitle')}
              </Text>
            </div>
            {activeTasks.length > 0 && (
              <Badge size="lg" color="blue" variant="filled">
                {activeTasks.length} {t('tasks.active')}
              </Badge>
            )}
          </Group>
        </div>

        {/* Controls */}
        <Paper withBorder shadow="sm" p="md">
          <Group justify="space-between">
            <Group>
              <Select
                value={filterStatus}
                onChange={(value) => setFilterStatus((value as TaskStatus | 'all') || 'all')}
                data={[
                  { value: 'all', label: t('tasks.filters.all') },
                  { value: TaskStatus.RUNNING, label: t('tasks.filters.running') },
                  { value: TaskStatus.COMPLETED, label: t('tasks.filters.completed') },
                  { value: TaskStatus.FAILED, label: t('tasks.filters.failed') },
                  { value: TaskStatus.CANCELLED, label: t('tasks.filters.cancelled') },
                ]}
                style={{ width: 200 }}
              />
            </Group>
            <Group>
              <Button
                variant={autoRefresh ? 'filled' : 'light'}
                onClick={() => setAutoRefresh(!autoRefresh)}
                size="sm"
              >
                {autoRefresh ? t('tasks.autoRefreshOn') : t('tasks.autoRefreshOff')}
              </Button>
              <Button
                leftSection={<IconRefresh size={16} />}
                onClick={() => loadTasks()}
                variant="light"
                size="sm"
              >
                {t('common.refresh')}
              </Button>
            </Group>
          </Group>
        </Paper>

        {/* Tasks List */}
        <Paper withBorder shadow="sm" p="md" pos="relative">
          <LoadingOverlay visible={loading} />

          {tasks.length === 0 ? (
            <Center p="xl">
              <Stack align="center" gap="xs">
                <Text size="lg" fw={500} c="dimmed">
                  {t('tasks.noTasks')}
                </Text>
                <Text size="sm" c="dimmed">
                  {t('tasks.noTasksDescription')}
                </Text>
              </Stack>
            </Center>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('tasks.columns.task')}</Table.Th>
                  <Table.Th>{t('tasks.columns.type')}</Table.Th>
                  <Table.Th>{t('tasks.columns.status')}</Table.Th>
                  <Table.Th>{t('tasks.columns.progress')}</Table.Th>
                  <Table.Th>{t('tasks.columns.duration')}</Table.Th>
                  <Table.Th>{t('tasks.columns.started')}</Table.Th>
                  <Table.Th>{t('tasks.columns.actions')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {tasks.map((task) => {
                  const StatusIcon = STATUS_ICONS[task.status]

                  return (
                    <Table.Tr
                      key={task.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => {
                        setSelectedTask(task)
                        openDetailModal()
                      }}
                    >
                      <Table.Td>
                        <div>
                          <Text size="sm" fw={500}>{getLocalizedTaskName(task.task_name)}</Text>
                          {task.description && (
                            <Text size="xs" c="dimmed">{task.description}</Text>
                          )}
                          {task.status === TaskStatus.FAILED && task.error_message && (
                            <Text size="xs" c="red" mt={4}>
                              {t('common.error')}: {task.error_message}
                            </Text>
                          )}
                        </div>
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="light" size="sm">
                          {getTaskTypeLabel(task.task_type)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs">
                          <StatusIcon size={16} color={`var(--mantine-color-${STATUS_COLORS[task.status]}-6)`} />
                          <Badge color={STATUS_COLORS[task.status]} variant="light">
                            {task.status}
                          </Badge>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <div style={{ width: 200 }}>
                          <Progress
                            value={task.progress}
                            size="sm"
                            color={task.status === TaskStatus.FAILED ? 'red' : 'blue'}
                            animated={task.status === TaskStatus.RUNNING}
                          />
                          <Text size="xs" c="dimmed" mt={4}>
                            {task.progress.toFixed(0)}%
                            {task.result_data?.current_step && task.status === TaskStatus.RUNNING && (
                              <> - {task.result_data.current_step}</>
                            )}
                          </Text>
                        </div>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">
                          {formatDuration(task.started_at, task.completed_at)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {task.started_at
                            ? formatDistanceToNow(new Date(task.started_at), { addSuffix: true })
                            : t('tasks.notStarted')}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs">
                          <Tooltip label={t('tasks.viewDetails')}>
                            <ActionIcon
                              color="gray"
                              variant="subtle"
                              onClick={(e) => {
                                e.stopPropagation()
                                setSelectedTask(task)
                                openDetailModal()
                              }}
                            >
                              <IconEye size={16} />
                            </ActionIcon>
                          </Tooltip>
                          {task.status === TaskStatus.FAILED && task.result_data?.can_retry && (
                            <Tooltip label={t('tasks.retryTask')}>
                              <ActionIcon
                                color="blue"
                                variant="subtle"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleRetryTask(task.id, task.task_name)
                                }}
                              >
                                <IconReload size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {(task.status === TaskStatus.PENDING || task.status === TaskStatus.RUNNING) && (
                            <Tooltip label={t('tasks.cancelTask')}>
                              <ActionIcon
                                color="red"
                                variant="subtle"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleCancelTask(task.id, task.task_name)
                                }}
                              >
                                <IconX size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          )}

          {/* Infinite scroll loader */}
          <div ref={loadMoreRef}>
            {loadingMore && (
              <Center py="md">
                <Loader size="sm" />
              </Center>
            )}
            {!hasMore && tasks.length > 0 && (
              <Text size="sm" c="dimmed" ta="center" py="md">
                {t('tasks.noMoreTasks')}
              </Text>
            )}
          </div>
        </Paper>
      </Stack>

      {/* Task Detail Modal */}
      <TaskDetailModal
        task={selectedTask}
        opened={detailModalOpened}
        onClose={closeDetailModal}
        onRetry={handleRetryTask}
        getTaskTypeLabel={getTaskTypeLabel}
        formatDuration={formatDuration}
        t={t}
        getLocalizedTaskName={getLocalizedTaskName}
      />
    </Container>
  )
}
