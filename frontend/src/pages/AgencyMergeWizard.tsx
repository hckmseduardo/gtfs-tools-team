import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Paper,
  Stack,
  Stepper,
  Button,
  Group,
  LoadingOverlay,
  Alert,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCheck, IconAlertCircle } from '@tabler/icons-react'
import { useNavigate } from 'react-router-dom'
import { agencyOperationsApi, AgencyMergeValidationResult } from '../lib/agency-operations-api'
import { agencyApi } from '../lib/gtfs-api'
import { feedApi } from '../lib/feed-api'
import { useTranslation } from 'react-i18next'
import FeedSelectionStep from '../components/MergeWizard/FeedSelectionStep'
import ValidationStep from '../components/MergeWizard/ValidationStep'
import MapPreviewStep from '../components/MergeWizard/MapPreviewStep'
import ExecuteMergeStep from '../components/MergeWizard/ExecuteMergeStep'

interface Agency {
  id: number
  name: string
  slug: string
}

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

interface AgencyWithFeeds extends Agency {
  feeds: Feed[]
}

export default function AgencyMergeWizard() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)

  // Data
  const [agencies, setAgencies] = useState<AgencyWithFeeds[]>([])
  const [selectedFeedIds, setSelectedFeedIds] = useState<number[]>([])
  const [targetMode, setTargetMode] = useState<'existing' | 'new'>('existing')
  const [targetAgencyId, setTargetAgencyId] = useState<number | null>(null)
  const [newAgencyName, setNewAgencyName] = useState('')
  const [newAgencyDescription, setNewAgencyDescription] = useState('')
  const [feedName, setFeedName] = useState('')
  const [feedDescription, setFeedDescription] = useState('')
  const [activateOnSuccess, setActivateOnSuccess] = useState(true)

  // Validation result
  const [validationResult, setValidationResult] = useState<AgencyMergeValidationResult | null>(null)

  // Per-entity merge strategies
  const [entityStrategies, setEntityStrategies] = useState<Record<string, 'fail_on_conflict' | 'auto_prefix'>>({
    route: 'auto_prefix',
    trip: 'auto_prefix',
    stop: 'auto_prefix',
    shape: 'auto_prefix',
    calendar: 'auto_prefix',
    calendar_date: 'auto_prefix',
    fare_attribute: 'auto_prefix',
    fare_rule: 'auto_prefix',
  })

  useEffect(() => {
    loadAgenciesWithFeeds()
    setFeedName(getDefaultFeedName())
  }, [])

  const loadAgenciesWithFeeds = async () => {
    try {
      setLoading(true)
      const agenciesResponse = await agencyApi.list({ limit: 1000 })
      const agenciesList = agenciesResponse.items || []

      // Load feeds for each agency
      const agenciesWithFeeds: AgencyWithFeeds[] = await Promise.all(
        agenciesList.map(async (agency) => {
          try {
            const feedsResponse = await feedApi.list({ agency_id: agency.id, limit: 1000 })
            return {
              ...agency,
              feeds: feedsResponse.feeds || feedsResponse.items || [],
            }
          } catch {
            return {
              ...agency,
              feeds: [],
            }
          }
        })
      )

      setAgencies(agenciesWithFeeds)
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load agencies and feeds',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const getDefaultFeedName = (): string => {
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

  const nextStep = () => {
    if (active === 0) {
      // Validate basic inputs before moving to next step
      if (selectedFeedIds.length < 2) {
        notifications.show({
          title: t('common.validationError', 'Validation Error'),
          message: t('agencies.merge.selectAtLeastTwo', 'Please select at least 2 feeds to merge'),
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
          message: 'Please enter a name for the merged feed',
          color: 'red',
        })
        return
      }

      // Don't block - let user proceed to validation step to see results
      setActive(active + 1)
      // Trigger validation in background if not done yet
      if (!validationResult) {
        performValidation()
      }
    } else if (active === 1) {
      // Allow proceeding even if validation hasn't passed - user might want to see map preview
      setActive(active + 1)
    } else {
      setActive(active + 1)
    }
  }

  const prevStep = () => setActive(active - 1)

  const performValidation = async () => {
    setValidating(true)
    try {
      const result = await agencyOperationsApi.validateMerge({
        source_feed_ids: selectedFeedIds,
        target_agency_id: targetMode === 'existing' ? targetAgencyId! : undefined,
        create_new_agency: targetMode === 'new',
        new_agency_name: targetMode === 'new' ? newAgencyName.trim() : undefined,
        new_agency_description: targetMode === 'new' ? newAgencyDescription.trim() || undefined : undefined,
        merge_strategy: 'auto_prefix', // Use auto_prefix so validation doesn't fail with conflicts
        feed_name: feedName,
        feed_description: feedDescription,
        activate_on_success: activateOnSuccess,
      })

      setValidationResult(result)

      if (result.valid) {
        if (result.conflicts.length > 0) {
          notifications.show({
            title: 'Validation Complete',
            message: `Found ${result.conflicts.length} conflicts that need resolution strategies`,
            color: 'yellow',
            icon: <IconAlertCircle />,
          })
        } else {
          notifications.show({
            title: 'Validation Successful',
            message: 'No conflicts found. Ready to merge!',
            color: 'green',
            icon: <IconCheck />,
          })
        }
      } else {
        const errorMsg = result.errors.length > 0 ? result.errors[0] : `Found ${result.conflicts.length} conflicts`
        notifications.show({
          title: 'Validation Complete',
          message: errorMsg,
          color: 'orange',
          icon: <IconAlertCircle />,
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

  const handleExecuteMerge = async () => {
    if (!validationResult) {
      notifications.show({
        title: 'Validation Required',
        message: 'Please run validation first',
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      const response = await agencyOperationsApi.executeMerge({
        source_feed_ids: selectedFeedIds,
        target_agency_id: targetMode === 'existing' ? targetAgencyId! : undefined,
        create_new_agency: targetMode === 'new',
        new_agency_name: targetMode === 'new' ? newAgencyName.trim() : undefined,
        new_agency_description: targetMode === 'new' ? newAgencyDescription.trim() || undefined : undefined,
        merge_strategy: 'auto_prefix', // Default to auto_prefix for now - will be replaced with per-entity strategies
        feed_name: feedName,
        feed_description: feedDescription,
        activate_on_success: activateOnSuccess,
      })

      if (response.status === 'failed') {
        if (response.validation_result) {
          setValidationResult(response.validation_result)
        }
        const errorMsg = response.validation_result?.errors?.[0] || response.message
        notifications.show({
          title: 'Merge Failed',
          message: errorMsg,
          color: 'red',
        })
        return
      }

      notifications.show({
        title: t('agencies.merge.mergeStarted', 'Merge Started'),
        message: t('agencies.merge.mergeTaskQueued', 'Merge task queued. Track progress in Task Manager.'),
        color: 'blue',
      })

      navigate('/tasks')
    } catch (error: any) {
      notifications.show({
        title: 'Merge Failed',
        message: error.response?.data?.detail || 'Failed to start merge',
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const steps = [
    'Select Feeds',
    'Validation Results',
    'Preview on Map',
    'Execute Merge',
  ]

  return (
    <Container size="xl">
      <Stack gap="md">
        <Title order={2}>Merge Feeds</Title>

        <Stepper active={active} onStepClick={setActive}>
          {steps.map((label, index) => (
            <Stepper.Step key={index} label={label} />
          ))}
        </Stepper>

        <Paper p="md" withBorder>
          <LoadingOverlay visible={loading || validating} />

          {active === 0 && (
            <FeedSelectionStep
              agencies={agencies}
              selectedFeedIds={selectedFeedIds}
              onFeedSelection={setSelectedFeedIds}
              targetMode={targetMode}
              onTargetModeChange={setTargetMode}
              targetAgencyId={targetAgencyId}
              onTargetAgencyChange={setTargetAgencyId}
              newAgencyName={newAgencyName}
              onNewAgencyNameChange={setNewAgencyName}
              newAgencyDescription={newAgencyDescription}
              onNewAgencyDescriptionChange={setNewAgencyDescription}
              feedName={feedName}
              onFeedNameChange={setFeedName}
              feedDescription={feedDescription}
              onFeedDescriptionChange={setFeedDescription}
              activateOnSuccess={activateOnSuccess}
              onActivateOnSuccessChange={setActivateOnSuccess}
            />
          )}

          {active === 1 && (
            <ValidationStep
              validationResult={validationResult}
              onRunValidation={performValidation}
              isValidating={validating}
              entityStrategies={entityStrategies}
              onEntityStrategyChange={(entityType, strategy) => {
                setEntityStrategies((prev) => ({ ...prev, [entityType]: strategy }))
              }}
            />
          )}

          {active === 2 && validationResult && (
            <MapPreviewStep
              agencies={agencies}
              selectedFeedIds={selectedFeedIds}
              validationResult={validationResult}
            />
          )}

          {active === 3 && (
            <ExecuteMergeStep
              selectedFeedsCount={selectedFeedIds.length}
              targetMode={targetMode}
              targetAgencyId={targetAgencyId}
              newAgencyName={newAgencyName}
              feedName={feedName}
              agencies={agencies}
              onExecute={handleExecuteMerge}
              isExecuting={loading}
            />
          )}
        </Paper>

        <Group justify="space-between">
          <Button variant="default" onClick={() => navigate('/agencies/merge')} disabled={loading || validating}>
            Cancel
          </Button>
          <Group>
            {active > 0 && (
              <Button variant="default" onClick={prevStep} disabled={loading || validating}>
                Back
              </Button>
            )}
            {active < steps.length - 1 ? (
              <Button onClick={nextStep} loading={validating} disabled={loading}>
                {active === 0 ? 'Validate & Continue' : 'Next'}
              </Button>
            ) : null}
          </Group>
        </Group>
      </Stack>
    </Container>
  )
}
