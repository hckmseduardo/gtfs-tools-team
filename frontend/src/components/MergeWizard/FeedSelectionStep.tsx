import {
  Stack,
  Text,
  Checkbox,
  Paper,
  Group,
  Badge,
  SegmentedControl,
  Select,
  TextInput,
  Textarea,
  Switch,
  Box,
  Accordion,
  Alert,
  Button,
} from '@mantine/core'
import { IconBuilding, IconPlus, IconAlertCircle } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

interface Feed {
  id: number
  agency_id: number
  name: string
  description?: string
  is_active: boolean
  stop_count?: number
  route_count?: number
  trip_count?: number
  stop_time_count?: number
}

interface Agency {
  id: number
  name: string
  slug: string
  feeds: Feed[]
}

interface FeedSelectionStepProps {
  agencies: Agency[]
  selectedFeedIds: number[]
  onFeedSelection: (feedIds: number[]) => void
  targetMode: 'existing' | 'new'
  onTargetModeChange: (mode: 'existing' | 'new') => void
  targetAgencyId: number | null
  onTargetAgencyChange: (id: number | null) => void
  newAgencyName: string
  onNewAgencyNameChange: (name: string) => void
  newAgencyDescription: string
  onNewAgencyDescriptionChange: (desc: string) => void
  feedName: string
  onFeedNameChange: (name: string) => void
  feedDescription: string
  onFeedDescriptionChange: (desc: string) => void
  activateOnSuccess: boolean
  onActivateOnSuccessChange: (active: boolean) => void
}

export default function FeedSelectionStep({
  agencies,
  selectedFeedIds,
  onFeedSelection,
  targetMode,
  onTargetModeChange,
  targetAgencyId,
  onTargetAgencyChange,
  newAgencyName,
  onNewAgencyNameChange,
  newAgencyDescription,
  onNewAgencyDescriptionChange,
  feedName,
  onFeedNameChange,
  feedDescription,
  onFeedDescriptionChange,
  activateOnSuccess,
  onActivateOnSuccessChange,
}: FeedSelectionStepProps) {
  const { t } = useTranslation()

  const handleFeedToggle = (feedId: number) => {
    if (selectedFeedIds.includes(feedId)) {
      onFeedSelection(selectedFeedIds.filter((id) => id !== feedId))
    } else {
      onFeedSelection([...selectedFeedIds, feedId])
    }
  }

  const handleAgencyToggle = (agency: Agency) => {
    const agencyFeedIds = agency.feeds.map((f) => f.id)
    const allSelected = agencyFeedIds.every((id) => selectedFeedIds.includes(id))

    if (allSelected) {
      // Deselect all feeds from this agency
      onFeedSelection(selectedFeedIds.filter((id) => !agencyFeedIds.includes(id)))
    } else {
      // Select all feeds from this agency
      const newSelection = [...new Set([...selectedFeedIds, ...agencyFeedIds])]
      onFeedSelection(newSelection)
    }
  }

  const isAgencyFullySelected = (agency: Agency) => {
    if (agency.feeds.length === 0) return false
    return agency.feeds.every((f) => selectedFeedIds.includes(f.id))
  }

  const isAgencyPartiallySelected = (agency: Agency) => {
    const selected = agency.feeds.filter((f) => selectedFeedIds.includes(f.id)).length
    return selected > 0 && selected < agency.feeds.length
  }

  // Get agencies that are not in the source feeds (for target selection)
  const sourceAgencyIds = new Set(
    agencies
      .filter((agency) => agency.feeds.some((feed) => selectedFeedIds.includes(feed.id)))
      .map((agency) => agency.id)
  )

  const availableTargetAgencies = agencies.filter(
    (agency) => !sourceAgencyIds.has(agency.id) && agency.feeds.length > 0
  )

  const targetAgencyOptions = availableTargetAgencies.map((agency) => ({
    value: agency.id.toString(),
    label: agency.name,
  }))

  const handleSelectAll = () => {
    const allFeedIds = agencies.flatMap(agency => agency.feeds.map(f => f.id))
    onFeedSelection(allFeedIds)
  }

  const handleClearSelection = () => {
    onFeedSelection([])
  }

  return (
    <Stack gap="md">
      <Alert icon={<IconAlertCircle />} title="Select Feeds to Merge" color="blue">
        Select at least 2 feeds from different agencies to merge. Feeds will be combined into a new feed in the target
        agency.
      </Alert>

      <Group justify="space-between">
        <Text size="sm" fw={500}>
          Source Feeds
        </Text>
        <Group gap="xs">
          <Button variant="subtle" size="xs" onClick={handleSelectAll}>
            Select All
          </Button>
          <Button variant="subtle" size="xs" onClick={handleClearSelection} disabled={selectedFeedIds.length === 0}>
            Clear Selection
          </Button>
        </Group>
      </Group>

      <Accordion variant="separated">
        {agencies
          .filter((agency) => agency.feeds.length > 0)
          .map((agency) => (
            <Accordion.Item key={agency.id} value={agency.id.toString()}>
              <Accordion.Control>
                <Group justify="space-between">
                  <Group>
                    <Checkbox
                      checked={isAgencyFullySelected(agency)}
                      indeterminate={isAgencyPartiallySelected(agency)}
                      onChange={() => handleAgencyToggle(agency)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <Text fw={500}>{agency.name}</Text>
                  </Group>
                  <Badge>{agency.feeds.length} feeds</Badge>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  {agency.feeds.map((feed) => (
                    <Paper key={feed.id} p="xs" withBorder>
                      <Group>
                        <Checkbox
                          checked={selectedFeedIds.includes(feed.id)}
                          onChange={() => handleFeedToggle(feed.id)}
                        />
                        <Box flex={1}>
                          <Group justify="space-between">
                            <div>
                              <Text size="sm" fw={500}>
                                {feed.name}
                              </Text>
                              {feed.description && (
                                <Text size="xs" c="dimmed">
                                  {feed.description}
                                </Text>
                              )}
                            </div>
                            <Group gap="xs">
                              {feed.is_active && <Badge color="green" size="sm">Active</Badge>}
                              <Text size="xs" c="dimmed">
                                {feed.route_count || 0} routes • {feed.stop_count || 0} stops •{' '}
                                {feed.trip_count || 0} trips
                              </Text>
                            </Group>
                          </Group>
                        </Box>
                      </Group>
                    </Paper>
                  ))}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
      </Accordion>

      {selectedFeedIds.length > 0 && (
        <Alert color="blue">
          Selected {selectedFeedIds.length} feed{selectedFeedIds.length !== 1 ? 's' : ''} for merge
        </Alert>
      )}

      <Text size="sm" fw={500} mt="md">
        Target Agency
      </Text>

      <SegmentedControl
        value={targetMode}
        onChange={(value) => {
          onTargetModeChange(value as 'existing' | 'new')
          onTargetAgencyChange(null)
        }}
        data={[
          {
            value: 'existing',
            label: (
              <Group gap="xs">
                <IconBuilding size={16} />
                <span>Existing Agency</span>
              </Group>
            ),
          },
          {
            value: 'new',
            label: (
              <Group gap="xs">
                <IconPlus size={16} />
                <span>Create New Agency</span>
              </Group>
            ),
          },
        ]}
        fullWidth
      />

      {targetMode === 'existing' ? (
        <Select
          label="Target Agency"
          description="The agency that will receive the merged feed"
          placeholder="Select target agency"
          data={targetAgencyOptions}
          value={targetAgencyId?.toString() || null}
          onChange={(value) => onTargetAgencyChange(value ? Number(value) : null)}
          searchable
          required
        />
      ) : (
        <Stack gap="sm">
          <TextInput
            label="New Agency Name"
            description="Name for the new agency that will contain the merged data"
            placeholder="e.g., Regional Transit Authority"
            value={newAgencyName}
            onChange={(e) => onNewAgencyNameChange(e.target.value)}
            required
          />
          <Textarea
            label="New Agency Description"
            description="Optional description for the new agency"
            placeholder="Combined transit services for the region"
            value={newAgencyDescription}
            onChange={(e) => onNewAgencyDescriptionChange(e.target.value)}
            minRows={2}
          />
        </Stack>
      )}

      <Text size="sm" fw={500} mt="md">
        Merge Settings
      </Text>

      <TextInput
        label="New Feed Name"
        description="Name for the merged feed"
        placeholder="e.g., Merged Transit Network 2025"
        value={feedName}
        onChange={(e) => onFeedNameChange(e.target.value)}
        required
      />

      <Textarea
        label="Feed Description"
        description="Optional description"
        placeholder="Merger of multiple transit feeds"
        value={feedDescription}
        onChange={(e) => onFeedDescriptionChange(e.target.value)}
        minRows={2}
      />

      <Switch
        label="Activate on Success"
        description="Automatically activate the new feed after successful merge"
        checked={activateOnSuccess}
        onChange={(e) => onActivateOnSuccessChange(e.currentTarget.checked)}
      />
    </Stack>
  )
}
