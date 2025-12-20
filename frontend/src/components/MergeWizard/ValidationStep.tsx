import {
  Stack,
  Alert,
  Group,
  Text,
  Badge,
  List,
  Paper,
  Table,
  Button,
  Select,
} from '@mantine/core'
import { IconCheck, IconAlertCircle, IconAlertTriangle } from '@tabler/icons-react'
import { AgencyMergeValidationResult } from '../../lib/agency-operations-api'

interface ValidationStepProps {
  validationResult: AgencyMergeValidationResult | null
  onRunValidation: () => void
  isValidating: boolean
  entityStrategies: Record<string, 'fail_on_conflict' | 'auto_prefix'>
  onEntityStrategyChange: (entityType: string, strategy: 'fail_on_conflict' | 'auto_prefix') => void
}

export default function ValidationStep({
  validationResult,
  onRunValidation,
  isValidating,
  entityStrategies,
  onEntityStrategyChange,
}: ValidationStepProps) {
  if (!validationResult) {
    return (
      <Stack gap="md">
        <Alert icon={<IconAlertCircle />} title="Validation Not Run" color="blue">
          Click the button below to validate the selected feeds for merging.
        </Alert>
        <Group justify="center">
          <Button
            size="lg"
            onClick={onRunValidation}
            loading={isValidating}
            leftSection={<IconCheck />}
          >
            Run Validation
          </Button>
        </Group>
      </Stack>
    )
  }

  const hasConflicts = validationResult.conflicts.length > 0
  const hasWarnings = validationResult.warnings.length > 0

  return (
    <Stack gap="md">
      {validationResult.valid ? (
        <Alert icon={<IconCheck />} title="Validation Successful" color="green">
          The merge can proceed. All requirements are met.
        </Alert>
      ) : (
        <Alert icon={<IconAlertCircle />} title="Conflicts Detected" color="yellow">
          Some conflicts were detected. You can still proceed - conflicts will be resolved using the selected strategies.
        </Alert>
      )}

      <Paper p="md" withBorder>
        <Text size="sm" fw={500} mb="sm">
          Merge Preview - Entity Counts
        </Text>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Entity Type</Table.Th>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Th key={fc.feed_id} ta="right">
                  {fc.feed_name}
                  <br />
                  <Text size="xs" c="dimmed" fw="normal">
                    ({fc.agency_name})
                  </Text>
                </Table.Th>
              ))}
              <Table.Th ta="right" fw="bold">
                Expected Total
              </Table.Th>
              <Table.Th ta="center">Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            <Table.Tr>
              <Table.Td>Routes</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.routes.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_routes.toLocaleString()}
              </Table.Td>
              <Table.Td ta="center">
                {validationResult.conflicts.filter(c => c.entity_type === 'route').length > 0 ? (
                  <Badge color="yellow" size="sm">Conflicts</Badge>
                ) : (
                  <Badge color="green" size="sm">✓</Badge>
                )}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Trips</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.trips.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_trips.toLocaleString()}
              </Table.Td>
              <Table.Td ta="center">
                {validationResult.conflicts.filter(c => c.entity_type === 'trip').length > 0 ? (
                  <Badge color="yellow" size="sm">Conflicts</Badge>
                ) : (
                  <Badge color="green" size="sm">✓</Badge>
                )}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Stops</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.stops.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_stops.toLocaleString()}
              </Table.Td>
              <Table.Td ta="center">
                {validationResult.conflicts.filter(c => c.entity_type === 'stop').length > 0 ? (
                  <Badge color="yellow" size="sm">Conflicts</Badge>
                ) : (
                  <Badge color="green" size="sm">✓</Badge>
                )}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Stop Times</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.stop_times.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_stop_times?.toLocaleString() || 0}
              </Table.Td>
              <Table.Td ta="center">
                <Badge color="green" size="sm">✓</Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Shapes</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.shapes.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_shapes.toLocaleString()}
              </Table.Td>
              <Table.Td ta="center">
                {validationResult.conflicts.filter(c => c.entity_type === 'shape').length > 0 ? (
                  <Badge color="yellow" size="sm">Conflicts</Badge>
                ) : (
                  <Badge color="green" size="sm">✓</Badge>
                )}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Calendars</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.calendars.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_calendars?.toLocaleString() || 0}
              </Table.Td>
              <Table.Td ta="center">
                {validationResult.conflicts.filter(c => c.entity_type === 'calendar').length > 0 ? (
                  <Badge color="yellow" size="sm">Conflicts</Badge>
                ) : (
                  <Badge color="green" size="sm">✓</Badge>
                )}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Calendar Dates</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.calendar_dates.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_calendar_dates?.toLocaleString() || 0}
              </Table.Td>
              <Table.Td ta="center">
                <Badge color="green" size="sm">✓</Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Fare Attributes</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.fare_attributes.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_fare_attributes?.toLocaleString() || 0}
              </Table.Td>
              <Table.Td ta="center">
                {validationResult.conflicts.filter(c => c.entity_type === 'fare').length > 0 ? (
                  <Badge color="yellow" size="sm">Conflicts</Badge>
                ) : (
                  <Badge color="green" size="sm">✓</Badge>
                )}
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>Fare Rules</Table.Td>
              {validationResult.feed_counts?.map((fc) => (
                <Table.Td key={fc.feed_id} ta="right">
                  {fc.fare_rules.toLocaleString()}
                </Table.Td>
              ))}
              <Table.Td ta="right" fw="bold">
                {validationResult.total_fare_rules?.toLocaleString() || 0}
              </Table.Td>
              <Table.Td ta="center">
                <Badge color="green" size="sm">✓</Badge>
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      </Paper>

      {validationResult.errors.length > 0 && (
        <Alert icon={<IconAlertCircle />} title="Errors" color="red">
          <List size="sm">
            {validationResult.errors.map((error, idx) => (
              <List.Item key={idx}>{error}</List.Item>
            ))}
          </List>
        </Alert>
      )}

      {validationResult.warnings.length > 0 && (
        <Alert icon={<IconAlertTriangle />} title="Warnings" color="yellow">
          <List size="sm">
            {validationResult.warnings.map((warning, idx) => (
              <List.Item key={idx}>{warning}</List.Item>
            ))}
          </List>
        </Alert>
      )}

      {validationResult.conflicts.length > 0 && (
        <>
          <Paper p="md" withBorder>
            <Text size="sm" fw={500} mb="sm">
              ID Conflicts ({validationResult.conflicts.length})
            </Text>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Entity Type</Table.Th>
                  <Table.Th>Conflicting ID</Table.Th>
                  <Table.Th>Source Agencies</Table.Th>
                  <Table.Th>Count</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {validationResult.conflicts.map((conflict, idx) => (
                  <Table.Tr key={idx}>
                    <Table.Td>
                      <Badge>{conflict.entity_type}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {conflict.conflicting_id}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{conflict.source_agencies.join(', ')}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{conflict.count}</Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>

          <Paper p="md" withBorder>
            <Text size="sm" fw={500} mb="sm">
              Conflict Resolution Strategies
            </Text>
            <Text size="xs" c="dimmed" mb="md">
              Choose how to handle ID conflicts for each entity type:
            </Text>
            <Stack gap="sm">
              {Array.from(new Set(validationResult.conflicts.map((c) => c.entity_type))).map((entityType) => (
                <Group key={entityType} justify="space-between">
                  <div>
                    <Text size="sm" fw={500}>
                      {entityType.charAt(0).toUpperCase() + entityType.slice(1)}s
                    </Text>
                    <Text size="xs" c="dimmed">
                      {validationResult.conflicts.filter((c) => c.entity_type === entityType).length} conflict(s)
                    </Text>
                  </div>
                  <Select
                    w={250}
                    value={entityStrategies[entityType] || 'auto_prefix'}
                    onChange={(value) =>
                      onEntityStrategyChange(entityType, value as 'fail_on_conflict' | 'auto_prefix')
                    }
                    data={[
                      { value: 'auto_prefix', label: 'Auto-prefix IDs (Recommended)' },
                      { value: 'fail_on_conflict', label: 'Fail on Conflict' },
                    ]}
                  />
                </Group>
              ))}
            </Stack>
          </Paper>
        </>
      )}

      {validationResult.valid && validationResult.conflicts.length === 0 && validationResult.warnings.length === 0 && (
        <Alert icon={<IconCheck />} color="green">
          No conflicts or warnings found. The merge can proceed safely.
        </Alert>
      )}
    </Stack>
  )
}
