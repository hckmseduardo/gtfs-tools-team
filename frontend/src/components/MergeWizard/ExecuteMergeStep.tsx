import {
  Stack,
  Alert,
  Text,
  Button,
  Paper,
  List,
  Group,
  ThemeIcon,
} from '@mantine/core'
import { IconGitMerge, IconInfoCircle, IconCheck } from '@tabler/icons-react'

interface Feed {
  id: number
  agency_id: number
  name: string
}

interface Agency {
  id: number
  name: string
  slug: string
  feeds: Feed[]
}

interface ExecuteMergeStepProps {
  selectedFeedsCount: number
  targetMode: 'existing' | 'new'
  targetAgencyId: number | null
  newAgencyName: string
  feedName: string
  agencies: Agency[]
  onExecute: () => void
  isExecuting: boolean
}

export default function ExecuteMergeStep({
  selectedFeedsCount,
  targetMode,
  targetAgencyId,
  newAgencyName,
  feedName,
  agencies,
  onExecute,
  isExecuting,
}: ExecuteMergeStepProps) {
  const targetAgency = targetMode === 'existing' && targetAgencyId
    ? agencies.find((a) => a.id === targetAgencyId)
    : null

  const targetName = targetMode === 'new' ? newAgencyName : targetAgency?.name || 'Unknown'

  // Get list of selected feeds grouped by agency
  const selectedFeedsByAgency = agencies
    .map(agency => ({
      agency,
      feeds: agency.feeds.filter(f => agencies.flatMap(a => a.feeds.map(feed => feed.id)).length > 0),
    }))
    .filter(item => item.feeds.length > 0)

  return (
    <Stack gap="md">
      <Alert icon={<IconInfoCircle />} title="Ready to Merge" color="blue">
        Review the merge details below and click "Execute Merge" to proceed.
      </Alert>

      <Paper p="md" withBorder>
        <Stack gap="md">
          <div>
            <Text size="sm" c="dimmed">
              Merge Type
            </Text>
            <Text size="lg" fw={500}>
              {targetMode === 'new' ? 'Create New Agency' : 'Merge into Existing Agency'}
            </Text>
          </div>

          <div>
            <Text size="sm" c="dimmed">
              Target Agency
            </Text>
            <Text size="lg" fw={500}>
              {targetName}
            </Text>
          </div>

          <div>
            <Text size="sm" c="dimmed">
              New Feed Name
            </Text>
            <Text size="lg" fw={500}>
              {feedName}
            </Text>
          </div>

          <div>
            <Text size="sm" c="dimmed">
              Source Feeds
            </Text>
            <Text size="lg" fw={500}>
              {selectedFeedsCount} feeds will be merged
            </Text>
          </div>
        </Stack>
      </Paper>

      <Paper p="md" withBorder>
        <Text size="sm" fw={500} mb="sm">
          📋 Actions to be performed:
        </Text>
        <List
          spacing="xs"
          size="sm"
          icon={
            <ThemeIcon color="blue" size={20} radius="xl">
              <IconCheck size={12} />
            </ThemeIcon>
          }
        >
          {targetMode === 'new' && (
            <List.Item>
              Create new agency: <strong>"{newAgencyName}"</strong>
            </List.Item>
          )}
          <List.Item>
            Create new feed: <strong>"{feedName}"</strong> in {targetName}
          </List.Item>
          <List.Item>
            Merge {selectedFeedsCount} feed{selectedFeedsCount !== 1 ? 's' : ''} from selected agencies
          </List.Item>
          <List.Item>
            Copy all routes, stops, trips, shapes, calendars, stop times, fare attributes, and fare rules
          </List.Item>
          <List.Item>
            Resolve any ID conflicts using the selected merge strategy
          </List.Item>
          <List.Item>
            Validate merged GTFS data for consistency
          </List.Item>
          <List.Item>
            Original feeds will remain unchanged
          </List.Item>
        </List>
      </Paper>

      <Alert color="yellow">
        <Text size="sm">
          <strong>Important:</strong> The merge operation will run in the background. You can track its progress in the
          Task Manager.
        </Text>
      </Alert>

      <Group justify="center" mt="md">
        <Button
          size="lg"
          leftSection={<IconGitMerge size={20} />}
          onClick={onExecute}
          loading={isExecuting}
          color="blue"
        >
          Execute Merge
        </Button>
      </Group>
    </Stack>
  )
}
