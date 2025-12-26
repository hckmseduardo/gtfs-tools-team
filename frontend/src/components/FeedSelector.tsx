import { Select, Group, Badge } from '@mantine/core'
import { IconDatabase } from '@tabler/icons-react'
import { feedApi, type GTFSFeed } from '../lib/feed-api'
import { useState, useEffect } from 'react'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'

interface FeedSelectorProps {
  agencyId: number | null
  value: string | null
  onChange: (feedId: string | null) => void
  onFeedsLoaded?: (feeds: GTFSFeed[]) => void
  onLoadingChange?: (loading: boolean) => void
  showAllOption?: boolean
  disabled?: boolean
  style?: React.CSSProperties
  label?: string
}

export default function FeedSelector({
  agencyId,
  value,
  onChange,
  onFeedsLoaded,
  onLoadingChange,
  showAllOption = true,
  disabled = false,
  style,
  label,
}: FeedSelectorProps) {
  const { t } = useTranslation()
  const [feeds, setFeeds] = useState<GTFSFeed[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (agencyId) {
      loadFeeds(agencyId)
    } else {
      setFeeds([])
      onChange(null)
    }
  }, [agencyId])

  const loadFeeds = async (agencyId: number) => {
    setLoading(true)
    onLoadingChange?.(true)
    try {
      const agencyFeeds = await feedApi.getByAgency(agencyId, true) // Only active feeds
      setFeeds(agencyFeeds)

      if (onFeedsLoaded) {
        onFeedsLoaded(agencyFeeds)
      }

      // Auto-select feed logic:
      // 1. If current value exists in new feeds, keep it (persist last selection)
      // 2. Otherwise, auto-select the most recent feed
      if (agencyFeeds.length > 0) {
        const currentFeedExists = value && agencyFeeds.some(f => f.id.toString() === value)

        if (!currentFeedExists) {
          // Auto-select most recent feed (sorted by imported_at desc)
          const sortedFeeds = [...agencyFeeds].sort((a, b) =>
            new Date(b.imported_at).getTime() - new Date(a.imported_at).getTime()
          )
          const mostRecent = sortedFeeds[0]

          // Only auto-select if showAllOption is false (edit mode)
          // or if there was no previous selection
          if (!showAllOption || !value) {
            onChange(mostRecent.id.toString())
          }
        }
      }
    } catch (error) {
      console.error('Failed to load feeds:', error)
      notifications.show({
        title: t('common.error'),
        message: t('feedSelector.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
      onLoadingChange?.(false)
    }
  }

  const formatFeedLabel = (feed: GTFSFeed) => {
    const date = new Date(feed.imported_at).toLocaleDateString()
    const stats = []
    if (feed.total_routes) stats.push(`${feed.total_routes}R`)
    if (feed.total_stops) stats.push(`${feed.total_stops}S`)
    const statsStr = stats.length > 0 ? ` [${stats.join('/')}]` : ''
    return `${feed.name} (${date})${statsStr}`
  }

  const selectData = [
    ...(showAllOption ? [{ value: '', label: t('feedSelector.allActiveFeeds') }] : []),
    ...feeds.map(f => ({
      value: f.id.toString(),
      label: formatFeedLabel(f)
    }))
  ]

  const selectedFeed = feeds.find(f => f.id.toString() === value)

  return (
    <Group gap="xs">
      <Select
        label={label}
        placeholder={feeds.length === 0 ? t('feedSelector.noFeedsAvailable') : t('feedSelector.selectFeed')}
        leftSection={<IconDatabase size={16} />}
        data={selectData}
        value={value || ''}
        onChange={(val) => onChange(val === '' ? null : val)}
        searchable
        clearable={showAllOption}
        disabled={disabled || loading || feeds.length === 0}
        style={style || { minWidth: 300 }}
        styles={{
          dropdown: {
            zIndex: 3000,
          }
        }}
        comboboxProps={{ zIndex: 3000 }}
      />
      {selectedFeed && (
        <Badge color={selectedFeed.is_active ? 'green' : 'gray'} variant="light">
          {selectedFeed.is_active ? t('feedSelector.active') : t('feedSelector.inactive')}
        </Badge>
      )}
    </Group>
  )
}
