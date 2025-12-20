import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Paper,
  Table,
  Badge,
  Group,
  Select,
  Button,
  Pagination,
  LoadingOverlay,
  Grid,
  Card,
  Modal,
  JsonInput,
} from '@mantine/core'
import { IconRefresh, IconFilter, IconFileAnalytics, IconEye } from '@tabler/icons-react'
import { auditApi, type AuditLog, type AuditLogStats } from '../lib/audit-api'
import { agencyApi, type Agency } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { format } from 'date-fns'

const ACTION_COLORS: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  import: 'cyan',
  export: 'violet',
  login: 'gray',
  logout: 'gray',
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [stats, setStats] = useState<AuditLogStats | null>(null)
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const limit = 50

  // Filters
  const [selectedAgency, setSelectedAgency] = useState<string | null>(null)
  const [selectedAction, setSelectedAction] = useState<string | null>(null)
  const [selectedEntityType, setSelectedEntityType] = useState<string | null>(null)

  // Detail modal
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null)
  const [detailModalOpened, setDetailModalOpened] = useState(false)

  useEffect(() => {
    loadAgencies()
    loadStats()
  }, [])

  useEffect(() => {
    loadLogs()
  }, [page, selectedAgency, selectedAction, selectedEntityType])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
    } catch (error) {
      console.error('Failed to load agencies:', error)
    }
  }

  const loadStats = async () => {
    try {
      const data = await auditApi.getStats()
      setStats(data)
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load audit statistics',
        color: 'red',
      })
    }
  }

  const loadLogs = async () => {
    setLoading(true)
    try {
      const skip = (page - 1) * limit
      const data = await auditApi.list({
        skip,
        limit,
        agency_id: selectedAgency ? parseInt(selectedAgency) : undefined,
        action: selectedAction || undefined,
        entity_type: selectedEntityType || undefined,
      })
      setLogs(data.items)
      setTotal(data.total)
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load audit logs',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleClearFilters = () => {
    setSelectedAgency(null)
    setSelectedAction(null)
    setSelectedEntityType(null)
    setPage(1)
  }

  const handleViewDetails = (log: AuditLog) => {
    setSelectedLog(log)
    setDetailModalOpened(true)
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>Audit Logs</Title>
          <Text c="dimmed" mt="sm">
            Track all changes and actions in the system
          </Text>
        </div>

        {/* Statistics Cards */}
        {stats && (
          <Grid>
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Card shadow="sm" padding="lg">
                <Group justify="apart">
                  <div>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                      Total Logs
                    </Text>
                    <Text fw={700} size="xl">
                      {stats.total_logs.toLocaleString()}
                    </Text>
                  </div>
                  <IconFileAnalytics size={32} opacity={0.6} />
                </Group>
              </Card>
            </Grid.Col>

            {Object.entries(stats.action_counts).map(([action, count]) => (
              <Grid.Col key={action} span={{ base: 12, sm: 6, md: 3 }}>
                <Card shadow="sm" padding="lg">
                  <Group justify="apart">
                    <div>
                      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                        {action}
                      </Text>
                      <Text fw={700} size="xl">
                        {count.toLocaleString()}
                      </Text>
                    </div>
                    <Badge color={ACTION_COLORS[action] || 'gray'} size="xl" circle>
                      {Math.round((count / stats.total_logs) * 100)}%
                    </Badge>
                  </Group>
                </Card>
              </Grid.Col>
            ))}
          </Grid>
        )}

        {/* Filters */}
        <Paper withBorder shadow="sm" p="md">
          <Group justify="space-between">
            <Group>
              <Select
                placeholder="Filter by Agency"
                data={agencies.map(a => ({ value: a.id.toString(), label: a.name }))}
                value={selectedAgency}
                onChange={setSelectedAgency}
                clearable
                style={{ minWidth: 200 }}
                leftSection={<IconFilter size={16} />}
              />
              <Select
                placeholder="Filter by Action"
                data={[
                  { value: 'create', label: 'Create' },
                  { value: 'update', label: 'Update' },
                  { value: 'delete', label: 'Delete' },
                  { value: 'import', label: 'Import' },
                  { value: 'export', label: 'Export' },
                  { value: 'login', label: 'Login' },
                  { value: 'logout', label: 'Logout' },
                ]}
                value={selectedAction}
                onChange={setSelectedAction}
                clearable
                style={{ minWidth: 150 }}
              />
              <Select
                placeholder="Filter by Entity Type"
                data={
                  stats
                    ? Object.keys(stats.entity_type_counts).map(type => ({
                        value: type,
                        label: type.charAt(0).toUpperCase() + type.slice(1),
                      }))
                    : []
                }
                value={selectedEntityType}
                onChange={setSelectedEntityType}
                clearable
                style={{ minWidth: 150 }}
              />
            </Group>
            <Group>
              <Button variant="light" onClick={handleClearFilters}>
                Clear Filters
              </Button>
              <Button leftSection={<IconRefresh size={16} />} onClick={loadLogs}>
                Refresh
              </Button>
            </Group>
          </Group>
        </Paper>

        {/* Logs Table */}
        <Paper withBorder shadow="sm" p="md" pos="relative">
          <LoadingOverlay visible={loading} />
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Timestamp</Table.Th>
                <Table.Th>Action</Table.Th>
                <Table.Th>Entity</Table.Th>
                <Table.Th>Description</Table.Th>
                <Table.Th>User ID</Table.Th>
                <Table.Th>Actions</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {logs.map((log) => (
                <Table.Tr key={log.id}>
                  <Table.Td>
                    <Text size="sm">
                      {format(new Date(log.created_at), 'MMM dd, yyyy HH:mm:ss')}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={ACTION_COLORS[log.action] || 'gray'}>
                      {log.action.toUpperCase()}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{log.entity_type}</Text>
                    <Text size="xs" c="dimmed">
                      ID: {log.entity_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={2}>
                      {log.description || '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{log.user_id}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Button
                      size="xs"
                      variant="light"
                      leftSection={<IconEye size={14} />}
                      onClick={() => handleViewDetails(log)}
                    >
                      Details
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>

          {logs.length === 0 && !loading && (
            <Text ta="center" c="dimmed" py="xl">
              No audit logs found
            </Text>
          )}

          {totalPages > 1 && (
            <Group justify="center" mt="md">
              <Pagination value={page} onChange={setPage} total={totalPages} />
            </Group>
          )}
        </Paper>
      </Stack>

      {/* Detail Modal */}
      <Modal
        opened={detailModalOpened}
        onClose={() => setDetailModalOpened(false)}
        title={`Audit Log #${selectedLog?.id}`}
        size="lg"
      >
        {selectedLog && (
          <Stack gap="md">
            <Group>
              <Badge color={ACTION_COLORS[selectedLog.action] || 'gray'} size="lg">
                {selectedLog.action.toUpperCase()}
              </Badge>
              <Text size="sm" c="dimmed">
                {format(new Date(selectedLog.created_at), 'MMM dd, yyyy HH:mm:ss')}
              </Text>
            </Group>

            <div>
              <Text size="sm" fw={500}>
                Entity
              </Text>
              <Text size="sm" c="dimmed">
                {selectedLog.entity_type} (ID: {selectedLog.entity_id})
              </Text>
            </div>

            {selectedLog.description && (
              <div>
                <Text size="sm" fw={500}>
                  Description
                </Text>
                <Text size="sm">{selectedLog.description}</Text>
              </div>
            )}

            <div>
              <Text size="sm" fw={500}>
                User ID
              </Text>
              <Text size="sm">{selectedLog.user_id}</Text>
            </div>

            {selectedLog.ip_address && (
              <div>
                <Text size="sm" fw={500}>
                  IP Address
                </Text>
                <Text size="sm" ff="monospace">
                  {selectedLog.ip_address}
                </Text>
              </div>
            )}

            {selectedLog.old_values && (
              <div>
                <Text size="sm" fw={500} mb="xs">
                  Old Values
                </Text>
                <JsonInput
                  value={JSON.stringify(selectedLog.old_values, null, 2)}
                  readOnly
                  autosize
                  minRows={4}
                  maxRows={10}
                />
              </div>
            )}

            {selectedLog.new_values && (
              <div>
                <Text size="sm" fw={500} mb="xs">
                  New Values
                </Text>
                <JsonInput
                  value={JSON.stringify(selectedLog.new_values, null, 2)}
                  readOnly
                  autosize
                  minRows={4}
                  maxRows={10}
                />
              </div>
            )}
          </Stack>
        )}
      </Modal>
    </Container>
  )
}
