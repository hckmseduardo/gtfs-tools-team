import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Table,
  Badge,
  Group,
  Button,
  ActionIcon,
  Modal,
  TextInput,
  Textarea,
  Select,
  Paper,
  LoadingOverlay,
  Switch,
  Tooltip,
  Card,
  Grid,
  Box,
  Collapse,
  UnstyledButton,
  Divider,
  SimpleGrid,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import {
  IconCheck,
  IconX,
  IconEdit,
  IconTrash,
  IconRefresh,
  IconChartBar,
  IconChevronDown,
  IconChevronUp,
  IconCopy,
  IconArrowsExchange,
  IconPlus,
  IconMinus,
  IconEqual,
  IconInfoCircle,
} from '@tabler/icons-react'
import { FeedInfoModal } from '../components/FeedInfoModal'
import { feedApi, type GTFSFeed, type GTFSFeedStats, type GTFSFeedUpdate, type GTFSFeedCreate, type FeedComparisonResult } from '../lib/feed-api'
import { agencyApi, type Agency } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'

export default function Feeds() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [feeds, setFeeds] = useState<GTFSFeed[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedAgency, setSelectedAgency] = useState<string | null>(null)
  const [showActiveOnly, setShowActiveOnly] = useState(false)
  const [expandedFeedId, setExpandedFeedId] = useState<number | null>(null)

  // Edit modal state
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingFeed, setEditingFeed] = useState<GTFSFeed | null>(null)
  const [editForm, setEditForm] = useState<GTFSFeedUpdate>({})

  // Feed Info modal state
  const [feedInfoModalOpen, setFeedInfoModalOpen] = useState(false)
  const [feedInfoFeedId, setFeedInfoFeedId] = useState<number | null>(null)
  const [feedInfoFeedName, setFeedInfoFeedName] = useState<string>('')

  // Stats modal state
  const [statsModalOpen, setStatsModalOpen] = useState(false)
  const [feedStats, setFeedStats] = useState<GTFSFeedStats | null>(null)

  // Clone modal state
  const [cloneModalOpen, setCloneModalOpen] = useState(false)
  const [cloningFeed, setCloningFeed] = useState<GTFSFeed | null>(null)
  const [cloneName, setCloneName] = useState('')

  // Compare modal state
  const [compareModalOpen, setCompareModalOpen] = useState(false)
  const [compareFeed1, setCompareFeed1] = useState<string | null>(null)
  const [compareFeed2, setCompareFeed2] = useState<string | null>(null)
  const [comparisonResult, setComparisonResult] = useState<FeedComparisonResult | null>(null)
  const [comparing, setComparing] = useState(false)

  // Create feed modal state
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createForm, setCreateForm] = useState<GTFSFeedCreate>({
    agency_id: 0,
    name: '',
    description: '',
    version: '',
  })
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    loadFeeds()
  }, [selectedAgency, showActiveOnly])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])

      // Auto-select first active agency
      const activeAgencies = (data.items || []).filter((a: Agency) => a.is_active)
      if (activeAgencies.length > 0) {
        setSelectedAgency(activeAgencies[0].id.toString())
      }
    } catch (error) {
      console.error('Failed to load agencies:', error)
      notifications.show({
        title: t('common.error'),
        message: t('agencies.loadError'),
        color: 'red',
      })
    }
  }

  const loadFeeds = async () => {
    setLoading(true)
    try {
      const params: any = { limit: 1000 }
      if (selectedAgency) {
        params.agency_id = parseInt(selectedAgency)
      }
      if (showActiveOnly) {
        params.is_active = true
      }

      const data = await feedApi.list(params)
      setFeeds(data.feeds || [])
    } catch (error) {
      console.error('Failed to load feeds:', error)
      notifications.show({
        title: t('common.error'),
        message: t('feeds.noFeeds'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleToggleActive = async (feed: GTFSFeed) => {
    try {
      if (feed.is_active) {
        await feedApi.deactivate(feed.id)
        notifications.show({
          title: t('common.success'),
          message: `${feed.name} ${t('feeds.deactivate').toLowerCase()}`,
          color: 'blue',
        })
      } else {
        await feedApi.activate(feed.id)
        notifications.show({
          title: t('common.success'),
          message: `${feed.name} ${t('feeds.activate').toLowerCase()}`,
          color: 'green',
        })
      }
      loadFeeds()
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('common.error'),
        color: 'red',
      })
    }
  }

  const handleEdit = (feed: GTFSFeed) => {
    setEditingFeed(feed)
    setEditForm({
      name: feed.name,
      description: feed.description,
      version: feed.version,
    })
    setEditModalOpen(true)
  }

  const handleSaveEdit = async () => {
    if (!editingFeed) return

    try {
      await feedApi.update(editingFeed.id, editForm)
      notifications.show({
        title: t('common.success'),
        message: t('common.saved'),
        color: 'green',
      })
      setEditModalOpen(false)
      loadFeeds()
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('common.error'),
        color: 'red',
      })
    }
  }

  const handleDelete = async (feed: GTFSFeed) => {
    if (!confirm(t('feeds.deleteConfirm'))) {
      return
    }

    try {
      await feedApi.delete(feed.id)
      notifications.show({
        title: t('feeds.deleteFeed'),
        message: t('feeds.deleteQueued'),
        color: 'blue',
        autoClose: 10000,
      })
      loadFeeds()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('common.error'),
        color: 'red',
      })
    }
  }

  const handleViewStats = async (feed: GTFSFeed) => {
    try {
      const stats = await feedApi.getStats(feed.id)
      setFeedStats(stats)
      setStatsModalOpen(true)
    } catch (error) {
      notifications.show({
        title: t('common.error'),
        message: t('common.error'),
        color: 'red',
      })
    }
  }

  const handleEditFeedInfo = (feed: GTFSFeed) => {
    setFeedInfoFeedId(feed.id)
    setFeedInfoFeedName(feed.name)
    setFeedInfoModalOpen(true)
  }

  const handleClone = (feed: GTFSFeed) => {
    setCloningFeed(feed)
    setCloneName(`Copy of ${feed.name}`)
    setCloneModalOpen(true)
  }

  const handleCloneSubmit = async () => {
    if (!cloningFeed || !cloneName.trim()) return

    try {
      await feedApi.clone(cloningFeed.id, cloneName.trim())
      notifications.show({
        title: t('common.success'),
        message: t('feeds.cloneQueued'),
        color: 'blue',
        autoClose: 10000,
      })
      setCloneModalOpen(false)
      setCloningFeed(null)
      setCloneName('')
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('common.error'),
        color: 'red',
      })
    }
  }

  const handleCompare = async () => {
    if (!compareFeed1 || !compareFeed2) return

    setComparing(true)
    try {
      const result = await feedApi.compare(parseInt(compareFeed1), parseInt(compareFeed2))
      setComparisonResult(result)
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('common.error'),
        color: 'red',
      })
    } finally {
      setComparing(false)
    }
  }

  const openCompareModal = () => {
    setCompareFeed1(null)
    setCompareFeed2(null)
    setComparisonResult(null)
    setCompareModalOpen(true)
  }

  const openCreateModal = () => {
    // Pre-select the currently selected agency
    setCreateForm({
      agency_id: selectedAgency ? parseInt(selectedAgency) : 0,
      name: '',
      description: '',
      version: '',
    })
    setCreateModalOpen(true)
  }

  const handleCreateFeed = async () => {
    if (!createForm.name.trim() || !createForm.agency_id) return

    setCreating(true)
    try {
      await feedApi.create({
        agency_id: createForm.agency_id,
        name: createForm.name.trim(),
        description: createForm.description?.trim() || undefined,
        version: createForm.version?.trim() || undefined,
      })
      notifications.show({
        title: t('common.success'),
        message: t('feeds.createSuccess'),
        color: 'green',
      })
      setCreateModalOpen(false)
      setCreateForm({
        agency_id: 0,
        name: '',
        description: '',
        version: '',
      })
      loadFeeds()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error?.response?.data?.detail || t('common.error'),
        color: 'red',
      })
    } finally {
      setCreating(false)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  const getAgencyName = (agencyId: number) => {
    return agencies.find((a) => a.id === agencyId)?.name || 'Unknown'
  }

  // Mobile Feed Card Component
  const FeedCard = ({ feed }: { feed: GTFSFeed }) => {
    const isExpanded = expandedFeedId === feed.id

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedFeedId(isExpanded ? null : feed.id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Text fw={600} size="sm" truncate>
                  {feed.name}
                </Text>
                <Text size="xs" c="dimmed" truncate>
                  {getAgencyName(feed.agency_id)}
                </Text>
              </Box>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Badge color={feed.is_active ? 'green' : 'gray'} size="sm">
                  {feed.is_active ? t('feeds.isActive') : t('common.inactive')}
                </Badge>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              {feed.description && (
                <Text size="sm" c="dimmed">
                  {feed.description}
                </Text>
              )}

              {feed.version && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('feeds.feedVersion')}:</Text>
                  <Badge variant="light" size="sm">{feed.version}</Badge>
                </Group>
              )}

              <Box>
                <Text size="xs" c="dimmed" mb={4}>{t('feeds.importedAt')}</Text>
                <Text size="sm">{formatDate(feed.imported_at)}</Text>
              </Box>

              <Divider label={t('feeds.statistics')} labelPosition="center" />

              <Group gap="xs" justify="center">
                <Badge size="md" variant="light" color="blue">
                  {feed.total_routes || 0} {t('feeds.totalRoutes')}
                </Badge>
                <Badge size="md" variant="light" color="grape">
                  {feed.total_stops || 0} {t('feeds.totalStops')}
                </Badge>
                <Badge size="md" variant="light" color="orange">
                  {feed.total_trips || 0} {t('feeds.totalTrips')}
                </Badge>
              </Group>

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  color={feed.is_active ? 'red' : 'green'}
                  onClick={() => handleToggleActive(feed)}
                  leftSection={feed.is_active ? <IconX size={16} /> : <IconCheck size={16} />}
                  fullWidth
                >
                  {feed.is_active ? t('feeds.deactivate') : t('feeds.activate')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="blue"
                  onClick={() => handleViewStats(feed)}
                  leftSection={<IconChartBar size={16} />}
                  fullWidth
                >
                  {t('feeds.statistics')}
                </Button>
              </SimpleGrid>

              <SimpleGrid cols={2} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  color="teal"
                  onClick={() => handleClone(feed)}
                  leftSection={<IconCopy size={16} />}
                  fullWidth
                >
                  {t('feeds.cloneFeed')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="violet"
                  onClick={() => handleEditFeedInfo(feed)}
                  leftSection={<IconInfoCircle size={16} />}
                  fullWidth
                >
                  {t('feedInfo.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleEdit(feed)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
              </SimpleGrid>

              <Button
                variant="light"
                size="sm"
                color="red"
                onClick={() => handleDelete(feed)}
                leftSection={<IconTrash size={16} />}
                fullWidth
              >
                {t('common.delete')}
              </Button>
            </Stack>
          </Collapse>
        </Stack>
      </Card>
    )
  }

  return (
    <Container size="xl" py={isMobile ? 'sm' : 'xl'} px={isMobile ? 'xs' : 'md'}>
      <Stack gap="lg">
        {/* Header */}
        {isMobile ? (
          <Stack gap="xs">
            <Group justify="space-between" align="flex-start">
              <Box>
                <Title order={3}>{t('feeds.title')}</Title>
                <Text c="dimmed" size="xs">
                  {t('feeds.title')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon
                  variant="filled"
                  color="green"
                  size="lg"
                  onClick={openCreateModal}
                >
                  <IconPlus size={18} />
                </ActionIcon>
                <ActionIcon
                  variant="light"
                  size="lg"
                  onClick={loadFeeds}
                  loading={loading}
                >
                  <IconRefresh size={18} />
                </ActionIcon>
              </Group>
            </Group>
          </Stack>
        ) : (
          <Group justify="space-between">
            <div>
              <Title order={2}>{t('feeds.title')}</Title>
              <Text c="dimmed" size="sm">
                {t('feeds.title')}
              </Text>
            </div>
            <Group gap="sm">
              <Button
                variant="filled"
                color="green"
                leftSection={<IconPlus size={16} />}
                onClick={openCreateModal}
              >
                {t('feeds.createFromScratch')}
              </Button>
              <Button
                variant="light"
                leftSection={<IconArrowsExchange size={16} />}
                onClick={openCompareModal}
              >
                {t('feeds.compareFeeds')}
              </Button>
              <Button
                leftSection={<IconRefresh size={16} />}
                onClick={loadFeeds}
                loading={loading}
              >
                {t('common.refresh')}
              </Button>
            </Group>
          </Group>
        )}

        {/* Filters */}
        <Paper p={isMobile ? 'sm' : 'md'} withBorder>
          <Stack gap="sm">
            <Select
              label={t('agencies.title')}
              placeholder={t('common.all')}
              data={agencies.map((a) => ({
                value: a.id.toString(),
                label: a.name,
              }))}
              value={selectedAgency}
              onChange={setSelectedAgency}
              clearable
              size={isMobile ? 'sm' : 'md'}
            />
            <Switch
              label={t('feeds.isActive')}
              checked={showActiveOnly}
              onChange={(e) => setShowActiveOnly(e.currentTarget.checked)}
            />
          </Stack>
        </Paper>

        {/* Feeds List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {feeds.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">{t('feeds.noFeeds')}</Text>
              </Paper>
            ) : (
              feeds.map((feed) => (
                <FeedCard key={feed.id} feed={feed} />
              ))
            )}
          </Stack>
        ) : (
          /* Desktop Table View */
          <Paper withBorder pos="relative">
            <LoadingOverlay visible={loading} />
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('feeds.feedName')}</Table.Th>
                  <Table.Th>{t('agencies.title')}</Table.Th>
                  <Table.Th>{t('feeds.feedVersion')}</Table.Th>
                  <Table.Th>{t('common.status')}</Table.Th>
                  <Table.Th>{t('feeds.statistics')}</Table.Th>
                  <Table.Th>{t('feeds.importedAt')}</Table.Th>
                  <Table.Th>{t('common.actions')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {feeds.length === 0 && !loading ? (
                  <Table.Tr>
                    <Table.Td colSpan={7} ta="center" py="xl">
                      <Text c="dimmed">{t('feeds.noFeeds')}</Text>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  feeds.map((feed) => (
                    <Table.Tr key={feed.id}>
                      <Table.Td>
                        <div>
                          <Text fw={500}>{feed.name}</Text>
                          {feed.description && (
                            <Text size="xs" c="dimmed">
                              {feed.description}
                            </Text>
                          )}
                        </div>
                      </Table.Td>
                      <Table.Td>
                        {getAgencyName(feed.agency_id)}
                      </Table.Td>
                      <Table.Td>
                        {feed.version ? (
                          <Badge variant="light">{feed.version}</Badge>
                        ) : (
                          <Text c="dimmed" size="sm">-</Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Badge color={feed.is_active ? 'green' : 'gray'}>
                          {feed.is_active ? t('feeds.isActive') : t('common.inactive')}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs">
                          <Tooltip label={t('feeds.totalRoutes')}>
                            <Badge size="sm" variant="light" color="blue">
                              {feed.total_routes || 0} {t('feeds.totalRoutes')}
                            </Badge>
                          </Tooltip>
                          <Tooltip label={t('feeds.totalStops')}>
                            <Badge size="sm" variant="light" color="grape">
                              {feed.total_stops || 0} {t('feeds.totalStops')}
                            </Badge>
                          </Tooltip>
                          <Tooltip label={t('feeds.totalTrips')}>
                            <Badge size="sm" variant="light" color="orange">
                              {feed.total_trips || 0} {t('feeds.totalTrips')}
                            </Badge>
                          </Tooltip>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{formatDate(feed.imported_at)}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs">
                          <Tooltip label={feed.is_active ? t('feeds.deactivate') : t('feeds.activate')}>
                            <ActionIcon
                              color={feed.is_active ? 'red' : 'green'}
                              variant="light"
                              onClick={() => handleToggleActive(feed)}
                            >
                              {feed.is_active ? <IconX size={16} /> : <IconCheck size={16} />}
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t('feeds.statistics')}>
                            <ActionIcon
                              color="blue"
                              variant="light"
                              onClick={() => handleViewStats(feed)}
                            >
                              <IconChartBar size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t('feeds.cloneFeed')}>
                            <ActionIcon
                              color="teal"
                              variant="light"
                              onClick={() => handleClone(feed)}
                            >
                              <IconCopy size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t('feedInfo.edit')}>
                            <ActionIcon
                              color="violet"
                              variant="light"
                              onClick={() => handleEditFeedInfo(feed)}
                            >
                              <IconInfoCircle size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t('common.edit')}>
                            <ActionIcon
                              color="blue"
                              variant="light"
                              onClick={() => handleEdit(feed)}
                            >
                              <IconEdit size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t('common.delete')}>
                            <ActionIcon
                              color="red"
                              variant="light"
                              onClick={() => handleDelete(feed)}
                            >
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))
                )}
              </Table.Tbody>
            </Table>
          </Paper>
        )}
      </Stack>

      {/* Edit Modal */}
      <Modal
        opened={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        title={t('common.edit')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        <Stack gap="md">
          <TextInput
            label={t('feeds.feedName')}
            placeholder={t('feeds.feedName')}
            value={editForm.name || ''}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            required
          />
          <Textarea
            label={t('common.description')}
            placeholder={t('common.description')}
            value={editForm.description || ''}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            minRows={3}
          />
          <TextInput
            label={t('feeds.feedVersion')}
            placeholder={t('feeds.feedVersion')}
            value={editForm.version || ''}
            onChange={(e) => setEditForm({ ...editForm, version: e.target.value })}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="light" onClick={() => setEditModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSaveEdit}>{t('common.save')}</Button>
          </Group>
        </Stack>
      </Modal>

      {/* Stats Modal */}
      <Modal
        opened={statsModalOpen}
        onClose={() => setStatsModalOpen(false)}
        title={t('feeds.statistics')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        {feedStats && (
          <Stack gap="md">
            <div>
              <Text size="sm" c="dimmed">{t('feeds.feedName')}</Text>
              <Text fw={500}>{feedStats.name}</Text>
            </div>
            <div>
              <Text size="sm" c="dimmed">{t('feeds.importedAt')}</Text>
              <Text>{formatDate(feedStats.imported_at)}</Text>
            </div>
            <div>
              <Text size="sm" c="dimmed">{t('common.status')}</Text>
              <Badge color={feedStats.is_active ? 'green' : 'gray'}>
                {feedStats.is_active ? t('feeds.isActive') : t('common.inactive')}
              </Badge>
            </div>
            <Card withBorder>
              <Grid>
                <Grid.Col span={4}>
                  <Stack gap="xs" ta="center">
                    <Text size="xl" fw={700} c="blue">
                      {feedStats.stats.routes}
                    </Text>
                    <Text size="sm" c="dimmed">{t('feeds.totalRoutes')}</Text>
                  </Stack>
                </Grid.Col>
                <Grid.Col span={4}>
                  <Stack gap="xs" ta="center">
                    <Text size="xl" fw={700} c="grape">
                      {feedStats.stats.stops}
                    </Text>
                    <Text size="sm" c="dimmed">{t('feeds.totalStops')}</Text>
                  </Stack>
                </Grid.Col>
                <Grid.Col span={4}>
                  <Stack gap="xs" ta="center">
                    <Text size="xl" fw={700} c="orange">
                      {feedStats.stats.trips}
                    </Text>
                    <Text size="sm" c="dimmed">{t('feeds.totalTrips')}</Text>
                  </Stack>
                </Grid.Col>
              </Grid>
            </Card>
          </Stack>
        )}
      </Modal>

      {/* Feed Info Modal */}
      {feedInfoFeedId && (
        <FeedInfoModal
          opened={feedInfoModalOpen}
          onClose={() => setFeedInfoModalOpen(false)}
          feedId={feedInfoFeedId}
          feedName={feedInfoFeedName}
        />
      )}

      {/* Clone Modal */}
      <Modal
        opened={cloneModalOpen}
        onClose={() => setCloneModalOpen(false)}
        title={t('feeds.cloneFeed')}
        size={isMobile ? '100%' : 'md'}
        fullScreen={isMobile}
      >
        <Stack gap="md">
          {cloningFeed && (
            <Paper p="md" withBorder>
              <Text size="sm" c="dimmed">{t('feeds.cloneSource')}</Text>
              <Text fw={500}>{cloningFeed.name}</Text>
            </Paper>
          )}
          <TextInput
            label={t('feeds.cloneName')}
            placeholder={t('feeds.cloneName')}
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            required
          />
          <Text size="sm" c="dimmed">
            {t('feeds.cloneDescription')}
          </Text>
          <Group justify="flex-end" mt="md">
            <Button variant="light" onClick={() => setCloneModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              leftSection={<IconCopy size={16} />}
              onClick={handleCloneSubmit}
              disabled={!cloneName.trim()}
            >
              {t('feeds.cloneFeed')}
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Compare Modal */}
      <Modal
        opened={compareModalOpen}
        onClose={() => setCompareModalOpen(false)}
        title={t('feeds.compareFeeds')}
        size={isMobile ? '100%' : 'xl'}
        fullScreen={isMobile}
      >
        <Stack gap="md">
          <Grid>
            <Grid.Col span={isMobile ? 12 : 6}>
              <Select
                label={t('feeds.compareFeed1')}
                placeholder={t('feeds.selectFeed')}
                data={feeds.map((f) => ({
                  value: f.id.toString(),
                  label: `${f.name} (${getAgencyName(f.agency_id)})`,
                }))}
                value={compareFeed1}
                onChange={setCompareFeed1}
                searchable
              />
            </Grid.Col>
            <Grid.Col span={isMobile ? 12 : 6}>
              <Select
                label={t('feeds.compareFeed2')}
                placeholder={t('feeds.selectFeed')}
                data={feeds.filter(f => f.id.toString() !== compareFeed1).map((f) => ({
                  value: f.id.toString(),
                  label: `${f.name} (${getAgencyName(f.agency_id)})`,
                }))}
                value={compareFeed2}
                onChange={setCompareFeed2}
                searchable
              />
            </Grid.Col>
          </Grid>

          <Button
            onClick={handleCompare}
            loading={comparing}
            disabled={!compareFeed1 || !compareFeed2}
            leftSection={<IconArrowsExchange size={16} />}
          >
            {t('feeds.runComparison')}
          </Button>

          {comparisonResult && (
            <Stack gap="md">
              <Divider label={t('feeds.comparisonResults')} labelPosition="center" />

              {/* Summary */}
              <Paper p="md" withBorder>
                <Group justify="space-between" mb="sm">
                  <Text fw={500}>{t('feeds.comparisonSummary')}</Text>
                  <Badge
                    color={comparisonResult.summary.has_changes ? 'orange' : 'green'}
                    size="lg"
                  >
                    {comparisonResult.summary.total_changes} {t('feeds.totalChanges')}
                  </Badge>
                </Group>
                <Grid>
                  <Grid.Col span={6}>
                    <Text size="sm" c="dimmed">{comparisonResult.feed1.name}</Text>
                    <Text size="xs" c="dimmed">{formatDate(comparisonResult.feed1.imported_at)}</Text>
                  </Grid.Col>
                  <Grid.Col span={6}>
                    <Text size="sm" c="dimmed">{comparisonResult.feed2.name}</Text>
                    <Text size="xs" c="dimmed">{formatDate(comparisonResult.feed2.imported_at)}</Text>
                  </Grid.Col>
                </Grid>
              </Paper>

              {/* Detailed comparison */}
              <SimpleGrid cols={isMobile ? 1 : 2} spacing="md">
                {/* Routes */}
                <Card withBorder>
                  <Text fw={500} mb="sm">{t('nav.routes')}</Text>
                  <Group gap="xs" mb="xs">
                    <Badge variant="light" color="gray">{comparisonResult.comparison.routes.feed1_count} → {comparisonResult.comparison.routes.feed2_count}</Badge>
                  </Group>
                  <Group gap="xs">
                    <Badge color="green" leftSection={<IconPlus size={12} />}>
                      +{comparisonResult.comparison.routes.added}
                    </Badge>
                    <Badge color="red" leftSection={<IconMinus size={12} />}>
                      -{comparisonResult.comparison.routes.removed}
                    </Badge>
                    <Badge color="blue" leftSection={<IconEqual size={12} />}>
                      {comparisonResult.comparison.routes.common}
                    </Badge>
                  </Group>
                </Card>

                {/* Stops */}
                <Card withBorder>
                  <Text fw={500} mb="sm">{t('nav.stops')}</Text>
                  <Group gap="xs" mb="xs">
                    <Badge variant="light" color="gray">{comparisonResult.comparison.stops.feed1_count} → {comparisonResult.comparison.stops.feed2_count}</Badge>
                  </Group>
                  <Group gap="xs">
                    <Badge color="green" leftSection={<IconPlus size={12} />}>
                      +{comparisonResult.comparison.stops.added}
                    </Badge>
                    <Badge color="red" leftSection={<IconMinus size={12} />}>
                      -{comparisonResult.comparison.stops.removed}
                    </Badge>
                    <Badge color="blue" leftSection={<IconEqual size={12} />}>
                      {comparisonResult.comparison.stops.common}
                    </Badge>
                  </Group>
                </Card>

                {/* Trips */}
                <Card withBorder>
                  <Text fw={500} mb="sm">{t('nav.trips')}</Text>
                  <Group gap="xs" mb="xs">
                    <Badge variant="light" color="gray">{comparisonResult.comparison.trips.feed1_count} → {comparisonResult.comparison.trips.feed2_count}</Badge>
                  </Group>
                  <Group gap="xs">
                    <Badge color="green" leftSection={<IconPlus size={12} />}>
                      +{comparisonResult.comparison.trips.added}
                    </Badge>
                    <Badge color="red" leftSection={<IconMinus size={12} />}>
                      -{comparisonResult.comparison.trips.removed}
                    </Badge>
                    <Badge color="blue" leftSection={<IconEqual size={12} />}>
                      {comparisonResult.comparison.trips.common}
                    </Badge>
                  </Group>
                </Card>

                {/* Calendars */}
                <Card withBorder>
                  <Text fw={500} mb="sm">{t('nav.calendars')}</Text>
                  <Group gap="xs" mb="xs">
                    <Badge variant="light" color="gray">{comparisonResult.comparison.calendars.feed1_count} → {comparisonResult.comparison.calendars.feed2_count}</Badge>
                  </Group>
                  <Group gap="xs">
                    <Badge color="green" leftSection={<IconPlus size={12} />}>
                      +{comparisonResult.comparison.calendars.added}
                    </Badge>
                    <Badge color="red" leftSection={<IconMinus size={12} />}>
                      -{comparisonResult.comparison.calendars.removed}
                    </Badge>
                    <Badge color="blue" leftSection={<IconEqual size={12} />}>
                      {comparisonResult.comparison.calendars.common}
                    </Badge>
                  </Group>
                </Card>

                {/* Shapes */}
                <Card withBorder>
                  <Text fw={500} mb="sm">{t('nav.shapes')}</Text>
                  <Group gap="xs" mb="xs">
                    <Badge variant="light" color="gray">{comparisonResult.comparison.shapes.feed1_count} → {comparisonResult.comparison.shapes.feed2_count}</Badge>
                  </Group>
                  <Group gap="xs">
                    <Badge color="green" leftSection={<IconPlus size={12} />}>
                      +{comparisonResult.comparison.shapes.added}
                    </Badge>
                    <Badge color="red" leftSection={<IconMinus size={12} />}>
                      -{comparisonResult.comparison.shapes.removed}
                    </Badge>
                    <Badge color="blue" leftSection={<IconEqual size={12} />}>
                      {comparisonResult.comparison.shapes.common}
                    </Badge>
                  </Group>
                </Card>
              </SimpleGrid>
            </Stack>
          )}
        </Stack>
      </Modal>

      {/* Create Feed Modal */}
      <Modal
        opened={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title={t('feeds.createFromScratch')}
        size={isMobile ? '100%' : 'md'}
        fullScreen={isMobile}
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            {t('feeds.createFromScratchDesc')}
          </Text>

          <Select
            label={t('agencies.title')}
            placeholder={t('feeds.selectAgency')}
            data={agencies.map((a) => ({
              value: a.id.toString(),
              label: a.name,
            }))}
            value={createForm.agency_id ? createForm.agency_id.toString() : null}
            onChange={(value) => setCreateForm({ ...createForm, agency_id: value ? parseInt(value) : 0 })}
            required
            searchable
          />

          <TextInput
            label={t('feeds.feedName')}
            placeholder={t('feeds.feedNamePlaceholder')}
            value={createForm.name}
            onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
            required
          />

          <Textarea
            label={t('common.description')}
            placeholder={t('feeds.feedDescriptionPlaceholder')}
            value={createForm.description || ''}
            onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
            minRows={3}
          />

          <TextInput
            label={t('feeds.feedVersion')}
            placeholder={t('feeds.feedVersionPlaceholder')}
            value={createForm.version || ''}
            onChange={(e) => setCreateForm({ ...createForm, version: e.target.value })}
          />

          <Group justify="flex-end" mt="md">
            <Button variant="light" onClick={() => setCreateModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              color="green"
              leftSection={<IconPlus size={16} />}
              onClick={handleCreateFeed}
              loading={creating}
              disabled={!createForm.name.trim() || !createForm.agency_id}
            >
              {t('feeds.createFeed')}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Container>
  )
}
