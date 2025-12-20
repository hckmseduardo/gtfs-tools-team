import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Paper,
  Stack,
  Select,
  MultiSelect,
  TextInput,
  Textarea,
  Button,
  Alert,
  Group,
  Text,
  Badge,
  List,
  Switch,
  LoadingOverlay,
  SegmentedControl,
  Box,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconAlertCircle, IconCheck, IconGitMerge, IconPlus, IconBuilding } from '@tabler/icons-react'
import { useNavigate } from 'react-router-dom'
import { agencyOperationsApi, AgencyMergeValidationResult } from '../lib/agency-operations-api'
import { agencyApi } from '../lib/gtfs-api'
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

interface Agency {
  id: number
  name: string
  feed_count?: number
}

export default function AgencyMerge() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)

  const [sourceAgencyIds, setSourceAgencyIds] = useState<string[]>([])
  const [targetMode, setTargetMode] = useState<'existing' | 'new'>('existing')
  const [targetAgencyId, setTargetAgencyId] = useState<string | null>(null)
  const [newAgencyName, setNewAgencyName] = useState('')
  const [newAgencyDescription, setNewAgencyDescription] = useState('')
  const [mergeStrategy, setMergeStrategy] = useState<string>('fail_on_conflict')
  const [feedName, setFeedName] = useState(getSeasonAndYear())
  const [feedDescription, setFeedDescription] = useState('')
  const [activateOnSuccess, setActivateOnSuccess] = useState(true)

  const [validationResult, setValidationResult] = useState<AgencyMergeValidationResult | null>(null)

  useEffect(() => {
    loadAgencies()
  }, [])

  const loadAgencies = async () => {
    try {
      const response = await agencyApi.list({ limit: 1000 })
      setAgencies(response.items || [])
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load agencies',
        color: 'red',
      })
    }
  }

  const handleValidate = async () => {
    if (sourceAgencyIds.length < 2) {
      notifications.show({
        title: t('common.validationError', 'Validation Error'),
        message: t('agencies.merge.selectAtLeastTwo', 'Please select at least 2 source agencies'),
        color: 'red',
      })
      return
    }

    if (targetMode === 'existing' && !targetAgencyId) {
      notifications.show({
        title: t('common.validationError', 'Validation Error'),
        message: t('agencies.merge.selectTargetAgency', 'Please select a target agency'),
        color: 'red',
      })
      return
    }

    if (targetMode === 'new' && !newAgencyName.trim()) {
      notifications.show({
        title: t('common.validationError', 'Validation Error'),
        message: t('agencies.merge.enterNewAgencyName', 'Please enter a name for the new agency'),
        color: 'red',
      })
      return
    }

    if (!feedName.trim()) {
      notifications.show({
        title: t('common.validationError', 'Validation Error'),
        message: t('agencies.merge.enterFeedName', 'Please enter a feed name'),
        color: 'red',
      })
      return
    }

    setValidating(true)
    try {
      const result = await agencyOperationsApi.validateMerge({
        source_agency_ids: sourceAgencyIds.map(Number),
        target_agency_id: targetMode === 'existing' ? Number(targetAgencyId) : undefined,
        create_new_agency: targetMode === 'new',
        new_agency_name: targetMode === 'new' ? newAgencyName.trim() : undefined,
        new_agency_description: targetMode === 'new' ? newAgencyDescription.trim() || undefined : undefined,
        merge_strategy: mergeStrategy as 'fail_on_conflict' | 'auto_prefix',
        feed_name: feedName,
        feed_description: feedDescription,
        activate_on_success: activateOnSuccess,
      })

      setValidationResult(result)

      if (result.valid) {
        if (result.conflicts.length > 0) {
          notifications.show({
            title: t('agencies.merge.validationSuccessWithWarnings', 'Validation Successful'),
            message: t('agencies.merge.conflictsAsWarnings', `${result.conflicts.length} conflicts will be resolved with auto-prefix. Ready to merge!`),
            color: 'blue',
            icon: <IconCheck />,
          })
        } else {
          notifications.show({
            title: t('agencies.merge.validationSuccess', 'Validation Successful'),
            message: t('agencies.merge.noConflicts', 'No conflicts found. Ready to merge!'),
            color: 'green',
            icon: <IconCheck />,
          })
        }
      } else {
        const errorMsg = result.errors.length > 0
          ? result.errors[0]
          : `Found ${result.conflicts.length} conflicts`
        notifications.show({
          title: t('agencies.merge.validationFailed', 'Validation Failed'),
          message: errorMsg,
          color: 'red',
        })
      }
    } catch (error: any) {
      notifications.show({
        title: 'Validation Error',
        message: error.response?.data?.detail || 'Failed to validate merge',
        color: 'red',
      })
    } finally {
      setValidating(false)
    }
  }

  const handleMerge = async () => {
    if (!validationResult?.valid) {
      notifications.show({
        title: t('agencies.merge.cannotMerge', 'Cannot Merge'),
        message: t('agencies.merge.validateFirst', 'Please validate first and resolve any conflicts'),
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      const response = await agencyOperationsApi.executeMerge({
        source_agency_ids: sourceAgencyIds.map(Number),
        target_agency_id: targetMode === 'existing' ? Number(targetAgencyId!) : undefined,
        create_new_agency: targetMode === 'new',
        new_agency_name: targetMode === 'new' ? newAgencyName.trim() : undefined,
        new_agency_description: targetMode === 'new' ? newAgencyDescription.trim() || undefined : undefined,
        merge_strategy: mergeStrategy as 'fail_on_conflict' | 'auto_prefix',
        feed_name: feedName,
        feed_description: feedDescription,
        activate_on_success: activateOnSuccess,
      })

      // Check if the merge failed validation
      if (response.status === 'failed') {
        // Update validation result to show the errors
        if (response.validation_result) {
          setValidationResult(response.validation_result)
        }
        const errorMsg = response.validation_result?.errors?.[0] || response.message
        notifications.show({
          title: t('agencies.merge.mergeFailed', 'Merge Failed'),
          message: errorMsg,
          color: 'red',
        })
        return
      }

      notifications.show({
        title: t('agencies.merge.mergeStarted', 'Merge Started'),
        message: response.message,
        color: 'blue',
      })

      navigate('/tasks')
    } catch (error: any) {
      notifications.show({
        title: t('agencies.merge.mergeFailed', 'Merge Failed'),
        message: error.response?.data?.detail || t('agencies.merge.failedToStart', 'Failed to start merge'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const agencyOptions = agencies.map((agency) => ({
    value: agency.id.toString(),
    label: agency.name,
  }))

  const availableTargets = agencyOptions.filter(
    (opt) => !sourceAgencyIds.includes(opt.value)
  )

  const availableSources = agencyOptions.filter(
    (opt) => opt.value !== targetAgencyId
  )

  return (
    <Container size="lg">
      <Stack gap="md">
        <Title order={2}>Merge Agencies</Title>

        <Paper p="md" withBorder>
          <LoadingOverlay visible={loading || validating} />

          <Stack gap="md">
            <Alert icon={<IconAlertCircle />} title="Important" color="blue">
              Merging agencies will combine GTFS data from multiple source agencies into a new feed in the target agency.
              This operation creates a new feed and does not modify existing data.
            </Alert>

            <MultiSelect
              label={t('agencies.merge.sourceAgencies', 'Source Agencies')}
              description={t('agencies.merge.sourceAgenciesDesc', 'Select 2 or more agencies to merge')}
              placeholder={t('agencies.merge.selectAgencies', 'Select agencies')}
              data={availableSources}
              value={sourceAgencyIds}
              onChange={setSourceAgencyIds}
              searchable
              required
            />

            <Box>
              <Text size="sm" fw={500} mb={4}>
                {t('agencies.merge.targetAgency', 'Target Agency')}
              </Text>
              <SegmentedControl
                value={targetMode}
                onChange={(value) => {
                  setTargetMode(value as 'existing' | 'new')
                  setValidationResult(null)
                }}
                data={[
                  {
                    value: 'existing',
                    label: (
                      <Group gap="xs">
                        <IconBuilding size={16} />
                        <span>{t('agencies.merge.existingAgency', 'Existing Agency')}</span>
                      </Group>
                    ),
                  },
                  {
                    value: 'new',
                    label: (
                      <Group gap="xs">
                        <IconPlus size={16} />
                        <span>{t('agencies.merge.createNewAgency', 'Create New Agency')}</span>
                      </Group>
                    ),
                  },
                ]}
                fullWidth
                mb="md"
              />

              {targetMode === 'existing' ? (
                <Select
                  description={t('agencies.merge.targetAgencyDesc', 'The agency that will receive the merged feed')}
                  placeholder={t('agencies.merge.selectTargetAgency', 'Select target agency')}
                  data={availableTargets}
                  value={targetAgencyId}
                  onChange={setTargetAgencyId}
                  searchable
                  required
                />
              ) : (
                <Stack gap="sm">
                  <TextInput
                    label={t('agencies.merge.newAgencyName', 'New Agency Name')}
                    description={t('agencies.merge.newAgencyNameDesc', 'Name for the new agency that will contain the merged data')}
                    placeholder={t('agencies.merge.newAgencyNamePlaceholder', 'e.g., Regional Transit Authority')}
                    value={newAgencyName}
                    onChange={(e) => setNewAgencyName(e.target.value)}
                    required
                  />
                  <Textarea
                    label={t('agencies.merge.newAgencyDescription', 'New Agency Description')}
                    description={t('agencies.merge.newAgencyDescriptionDesc', 'Optional description for the new agency')}
                    placeholder={t('agencies.merge.newAgencyDescriptionPlaceholder', 'Combined transit services for the region')}
                    value={newAgencyDescription}
                    onChange={(e) => setNewAgencyDescription(e.target.value)}
                    minRows={2}
                  />
                </Stack>
              )}
            </Box>

            <Select
              label="Merge Strategy"
              description="How to handle ID conflicts"
              data={[
                { value: 'fail_on_conflict', label: 'Fail on Conflict (Safe)' },
                { value: 'auto_prefix', label: 'Auto-prefix IDs (Future)' },
              ]}
              value={mergeStrategy}
              onChange={(value) => setMergeStrategy(value || 'fail_on_conflict')}
              required
            />

            <TextInput
              label="New Feed Name"
              description="Name for the merged feed"
              placeholder="e.g., Merged Transit Network 2025"
              value={feedName}
              onChange={(e) => setFeedName(e.target.value)}
              required
            />

            <Textarea
              label="Feed Description"
              description="Optional description"
              placeholder="Merger of City Transit and Suburban Bus Lines"
              value={feedDescription}
              onChange={(e) => setFeedDescription(e.target.value)}
              minRows={2}
            />

            <Switch
              label="Activate on Success"
              description="Automatically activate the new feed after successful merge"
              checked={activateOnSuccess}
              onChange={(e) => setActivateOnSuccess(e.currentTarget.checked)}
            />

            <Group justify="flex-end">
              <Button variant="default" onClick={() => navigate(-1)}>
                Cancel
              </Button>
              <Button onClick={handleValidate} loading={validating}>
                Validate Merge
              </Button>
            </Group>
          </Stack>
        </Paper>

        {validationResult && (
          <Paper p="md" withBorder>
            <Stack gap="md">
              <Group justify="space-between">
                <Title order={4}>Validation Results</Title>
                <Badge color={validationResult.valid ? 'green' : 'red'} size="lg">
                  {validationResult.valid ? 'Valid' : 'Has Conflicts'}
                </Badge>
              </Group>

              <Group>
                <Text size="sm">
                  <strong>Routes:</strong> {validationResult.total_routes}
                </Text>
                <Text size="sm">
                  <strong>Trips:</strong> {validationResult.total_trips}
                </Text>
                <Text size="sm">
                  <strong>Stops:</strong> {validationResult.total_stops}
                </Text>
                <Text size="sm">
                  <strong>Shapes:</strong> {validationResult.total_shapes}
                </Text>
              </Group>

              {validationResult.conflicts.length > 0 && (
                <Alert icon={<IconAlertCircle />} title="ID Conflicts Found" color="red">
                  <List size="sm">
                    {validationResult.conflicts.map((conflict, idx) => (
                      <List.Item key={idx}>
                        <strong>{conflict.entity_type}:</strong> {conflict.conflicting_id}
                        ({conflict.count} conflicts across agencies {conflict.source_agencies.join(', ')})
                      </List.Item>
                    ))}
                  </List>
                </Alert>
              )}

              {validationResult.warnings.length > 0 && (
                <Alert icon={<IconAlertCircle />} title="Warnings" color="yellow">
                  <List size="sm">
                    {validationResult.warnings.map((warning, idx) => (
                      <List.Item key={idx}>{warning}</List.Item>
                    ))}
                  </List>
                </Alert>
              )}

              {validationResult.errors.length > 0 && (
                <Alert icon={<IconAlertCircle />} title="Errors" color="red">
                  <List size="sm">
                    {validationResult.errors.map((error, idx) => (
                      <List.Item key={idx}>{error}</List.Item>
                    ))}
                  </List>
                </Alert>
              )}

              {validationResult.valid && (
                <Group justify="flex-end">
                  <Button
                    leftSection={<IconGitMerge size={16} />}
                    onClick={handleMerge}
                    loading={loading}
                    color="green"
                  >
                    Execute Merge
                  </Button>
                </Group>
              )}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Container>
  )
}
