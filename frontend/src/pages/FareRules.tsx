import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Button,
  Paper,
  Table,
  Badge,
  ActionIcon,
  Modal,
  TextInput,
  Select,
  LoadingOverlay,
  Card,
  Box,
  Collapse,
  UnstyledButton,
  Divider,
  SimpleGrid,
  Alert,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconRuler,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
  IconInfoCircle,
  IconArrowLeft,
} from '@tabler/icons-react'
import { fareRulesApi, fareAttributesApi, routesApi, agencyApi, type FareRule, type FareAttribute, type Route, type Agency } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'

export default function FareRules() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [fareRules, setFareRules] = useState<FareRule[]>([])
  const [fareAttributes, setFareAttributes] = useState<FareAttribute[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingRule, setEditingRule] = useState<FareRule | null>(null)
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [filterFareId, setFilterFareId] = useState<string | null>(null)
  const [expandedRuleKey, setExpandedRuleKey] = useState<string | null>(null)

  const form = useForm({
    initialValues: {
      fare_id: '',
      route_id: '',
      origin_id: '',
      destination_id: '',
      contains_id: '',
    },
    validate: {
      fare_id: (value) => (value.length < 1 ? t('fareRules.validation.fareIdRequired') : null),
    },
  })

  useEffect(() => {
    const fareIdParam = searchParams.get('fare_id')
    const feedIdParam = searchParams.get('feed_id')
    if (fareIdParam) setFilterFareId(fareIdParam)
    if (feedIdParam) setSelectedFeed(feedIdParam)
  }, [searchParams])

  useEffect(() => { loadAgencies() }, [])

  useEffect(() => {
    if (selectedAgency && selectedFeed) {
      loadFareRules()
      loadFareAttributes()
      loadRoutes()
    }
  }, [selectedAgency, selectedFeed, filterFareId])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
      if (data.items && data.items.length > 0 && !selectedAgency) {
        setSelectedAgency(data.items[0].id)
      }
    } catch (error: any) {
      notifications.show({ title: t('common.error'), message: t('agencies.loadError'), color: 'red' })
    }
  }

  const loadFareRules = async () => {
    if (!selectedFeed) { setFareRules([]); return }
    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const params: { limit: number; fare_id?: string } = { limit: 1000 }
      if (filterFareId) params.fare_id = filterFareId
      const data = await fareRulesApi.list(feed_id, params)
      setFareRules(data.items || [])
    } catch (error: any) {
      notifications.show({ title: t('common.error'), message: t('fareRules.loadError'), color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  const loadFareAttributes = async () => {
    if (!selectedFeed) { setFareAttributes([]); return }
    try {
      const feed_id = parseInt(selectedFeed)
      const data = await fareAttributesApi.list(feed_id, { limit: 1000 })
      setFareAttributes(data.items || [])
    } catch (error: any) { console.error('Failed to load fare attributes:', error) }
  }

  const loadRoutes = async () => {
    if (!selectedFeed) { setRoutes([]); return }
    try {
      const feed_id = parseInt(selectedFeed)
      const data = await routesApi.list(feed_id, { limit: 1000 })
      setRoutes(data.items || [])
    } catch (error: any) { console.error('Failed to load routes:', error) }
  }

  const handleOpenCreate = () => {
    setEditingRule(null)
    form.reset()
    if (filterFareId) form.setFieldValue('fare_id', filterFareId)
    open()
  }

  const handleOpenEdit = (rule: FareRule) => {
    setEditingRule(rule)
    form.setValues({
      fare_id: rule.fare_id,
      route_id: rule.route_id || '',
      origin_id: rule.origin_id || '',
      destination_id: rule.destination_id || '',
      contains_id: rule.contains_id || '',
    })
    open()
  }

  const handleSubmit = async (values: typeof form.values) => {
    if (!selectedFeed || !selectedAgency) {
      notifications.show({ title: t('common.error'), message: t('fareRules.validation.selectFeedFirst'), color: 'red' })
      return
    }
    try {
      const feed_id = parseInt(selectedFeed)
      const data = {
        fare_id: values.fare_id,
        route_id: values.route_id || '',
        origin_id: values.origin_id || '',
        destination_id: values.destination_id || '',
        contains_id: values.contains_id || '',
      }

      if (editingRule) {
        await fareRulesApi.update(feed_id, {
          fare_id: editingRule.fare_id,
          route_id: editingRule.route_id,
          origin_id: editingRule.origin_id,
          destination_id: editingRule.destination_id,
          contains_id: editingRule.contains_id,
        }, data)
        notifications.show({ title: t('common.success'), message: t('fareRules.updateSuccess'), color: 'green' })
      } else {
        await fareRulesApi.create(feed_id, data)
        notifications.show({ title: t('common.success'), message: t('fareRules.createSuccess'), color: 'green' })
      }
      close()
      loadFareRules()
    } catch (error: any) {
      notifications.show({ title: t('common.error'), message: error.response?.data?.detail || t('fareRules.saveError'), color: 'red' })
    }
  }

  const handleDelete = (rule: FareRule) => {
    if (!selectedFeed) {
      notifications.show({ title: t('common.error'), message: t('fareRules.validation.selectFeedFirst'), color: 'red' })
      return
    }
    modals.openConfirmModal({
      title: t('fareRules.deleteRule'),
      children: <Text size="sm">{t('fareRules.deleteConfirm', { id: rule.fare_id })}</Text>,
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          const feed_id = parseInt(selectedFeed!)
          await fareRulesApi.delete(feed_id, {
            fare_id: rule.fare_id, route_id: rule.route_id,
            origin_id: rule.origin_id, destination_id: rule.destination_id, contains_id: rule.contains_id,
          })
          notifications.show({ title: t('common.success'), message: t('fareRules.deleteSuccess'), color: 'green' })
          loadFareRules()
        } catch (error: any) {
          notifications.show({ title: t('common.error'), message: error.response?.data?.detail || t('fareRules.deleteError'), color: 'red' })
        }
      },
    })
  }

  const getRuleKey = (rule: FareRule) => `${rule.feed_id}:${rule.fare_id}:${rule.route_id}:${rule.origin_id}:${rule.destination_id}:${rule.contains_id}`

  const getRouteName = (routeId: string) => {
    if (!routeId) return t('fareRules.allRoutes')
    const route = routes.find(r => r.route_id === routeId)
    return route ? `${route.route_short_name} - ${route.route_long_name ?? ''}` : routeId
  }

  const handleClearFilter = () => { setFilterFareId(null); navigate('/fare-rules') }

  const RuleCard = ({ rule }: { rule: FareRule }) => {
    const ruleKey = getRuleKey(rule)
    const isExpanded = expandedRuleKey === ruleKey
    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton onClick={() => setExpandedRuleKey(isExpanded ? null : ruleKey)} style={{ width: '100%' }}>
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                <IconRuler size={20} style={{ flexShrink: 0 }} />
                <Box style={{ minWidth: 0 }}>
                  <Text fw={600} size="sm" truncate>{rule.fare_id}</Text>
                  <Text size="xs" c="dimmed" truncate>{rule.route_id ? getRouteName(rule.route_id) : t('fareRules.allRoutes')}</Text>
                </Box>
              </Group>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>
          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />
              <Group gap="xs"><Text size="xs" c="dimmed">{t('fareRules.routeId')}:</Text><Badge variant="outline" size="sm">{rule.route_id || t('fareRules.any')}</Badge></Group>
              <Group gap="xs"><Text size="xs" c="dimmed">{t('fareRules.originZone')}:</Text><Badge variant="outline" size="sm">{rule.origin_id || t('fareRules.any')}</Badge></Group>
              <Group gap="xs"><Text size="xs" c="dimmed">{t('fareRules.destinationZone')}:</Text><Badge variant="outline" size="sm">{rule.destination_id || t('fareRules.any')}</Badge></Group>
              {rule.contains_id && <Group gap="xs"><Text size="xs" c="dimmed">{t('fareRules.containsZone')}:</Text><Badge variant="outline" size="sm">{rule.contains_id}</Badge></Group>}
              <Divider label={t('common.actions')} labelPosition="center" />
              <SimpleGrid cols={2} spacing="xs">
                <Button variant="light" size="sm" onClick={() => handleOpenEdit(rule)} leftSection={<IconEdit size={16} />} fullWidth>{t('common.edit')}</Button>
                <Button variant="light" size="sm" color="red" onClick={() => handleDelete(rule)} leftSection={<IconTrash size={16} />} fullWidth>{t('common.delete')}</Button>
              </SimpleGrid>
            </Stack>
          </Collapse>
        </Stack>
      </Card>
    )
  }

  return (
    <Container size="xl" py={isMobile ? 'sm' : 'xl'} px={isMobile ? 'xs' : 'md'}>
      <Stack gap="lg">
        {isMobile ? (
          <Stack gap="xs">
            <Group justify="space-between" align="flex-start">
              <Box>
                <Group gap="xs"><IconRuler size={20} /><Title order={3}>{t('fareRules.title')}</Title></Group>
                <Text c="dimmed" size="xs">{t('fareRules.description')}</Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadFareRules} loading={loading}><IconRefresh size={18} /></ActionIcon>
                <ActionIcon variant="filled" size="lg" onClick={handleOpenCreate} disabled={!selectedFeed}><IconPlus size={18} /></ActionIcon>
              </Group>
            </Group>
          </Stack>
        ) : (
          <Group justify="space-between">
            <div>
              <Group gap="xs">
                <Button variant="subtle" size="compact-sm" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate('/fare-attributes')}>{t('fareRules.backToFares')}</Button>
              </Group>
              <Title order={1} mt="xs"><IconRuler style={{ marginRight: 8, verticalAlign: 'middle' }} />{t('fareRules.title')}</Title>
              <Text c="dimmed" size="sm" mt="xs">{t('fareRules.description')}</Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleOpenCreate} disabled={!selectedFeed}>{t('fareRules.newRule')}</Button>
          </Group>
        )}

        <Paper shadow="sm" p={isMobile ? 'sm' : 'md'} withBorder>
          <Stack gap="sm">
            <Select label={t('agencies.title')} placeholder={t('agencies.selectAgency')} data={agencies.map(a => ({ value: String(a.id), label: a.name }))} value={selectedAgency ? String(selectedAgency) : null} onChange={(value) => setSelectedAgency(value ? parseInt(value) : null)} size={isMobile ? 'sm' : 'md'} />
            <FeedSelector label={t('feeds.title')} agencyId={selectedAgency} value={selectedFeed} onChange={setSelectedFeed} showAllOption={false} />
            <Select label={t('fareRules.filterByFare')} placeholder={t('fareRules.selectFare')} data={fareAttributes.map(f => ({ value: f.fare_id, label: `${f.fare_id} (${f.currency_type} ${f.price})` }))} value={filterFareId} onChange={setFilterFareId} clearable searchable />
          </Stack>
        </Paper>

        {filterFareId && (
          <Alert icon={<IconInfoCircle size={16} />} color="blue" variant="light">
            <Group justify="space-between">
              <Text size="sm">{t('fareRules.filteringByFare', { fareId: filterFareId })}</Text>
              <Button variant="subtle" size="xs" onClick={handleClearFilter}>{t('fareRules.clearFilter')}</Button>
            </Group>
          </Alert>
        )}

        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {fareRules.length === 0 && !loading ? (
              <Paper p="xl" withBorder><Text c="dimmed" ta="center">{t('fareRules.noRules')}</Text></Paper>
            ) : fareRules.map((rule) => <RuleCard key={getRuleKey(rule)} rule={rule} />)}
          </Stack>
        ) : (
          <Paper shadow="sm" p="md" withBorder pos="relative">
            <LoadingOverlay visible={loading} />
            {fareRules.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">{t('fareRules.noRules')}</Text>
            ) : (
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('fareRules.fareId')}</Table.Th>
                    <Table.Th>{t('fareRules.route')}</Table.Th>
                    <Table.Th>{t('fareRules.originZone')}</Table.Th>
                    <Table.Th>{t('fareRules.destinationZone')}</Table.Th>
                    <Table.Th>{t('fareRules.containsZone')}</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>{t('common.actions')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {fareRules.map((rule) => (
                    <Table.Tr key={getRuleKey(rule)}>
                      <Table.Td><Text size="sm" fw={500}>{rule.fare_id}</Text></Table.Td>
                      <Table.Td><Text size="sm">{rule.route_id ? getRouteName(rule.route_id) : <Badge size="sm" variant="light">{t('fareRules.allRoutes')}</Badge>}</Text></Table.Td>
                      <Table.Td><Text size="sm">{rule.origin_id || <Badge size="sm" variant="light">{t('fareRules.any')}</Badge>}</Text></Table.Td>
                      <Table.Td><Text size="sm">{rule.destination_id || <Badge size="sm" variant="light">{t('fareRules.any')}</Badge>}</Text></Table.Td>
                      <Table.Td><Text size="sm">{rule.contains_id || '-'}</Text></Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>
                        <Group gap={4} justify="flex-end">
                          <ActionIcon variant="subtle" color="blue" onClick={() => handleOpenEdit(rule)}><IconEdit size={16} /></ActionIcon>
                          <ActionIcon variant="subtle" color="red" onClick={() => handleDelete(rule)}><IconTrash size={16} /></ActionIcon>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
        )}
      </Stack>

      <Modal opened={opened} onClose={close} title={editingRule ? t('fareRules.editRule') : t('fareRules.newRule')} size={isMobile ? '100%' : 'lg'} fullScreen={isMobile}>
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            <Alert icon={<IconInfoCircle size={16} />} color="blue" variant="light"><Text size="sm">{t('fareRules.formHelp')}</Text></Alert>
            <Select label={t('fareRules.fields.fareId')} description={t('fareRules.fields.fareIdDesc')} data={fareAttributes.map(f => ({ value: f.fare_id, label: `${f.fare_id} (${f.currency_type} ${f.price})` }))} {...form.getInputProps('fare_id')} required searchable />
            <Select label={t('fareRules.fields.routeId')} description={t('fareRules.fields.routeIdDesc')} placeholder={t('fareRules.placeholders.routeId')} data={[{ value: '', label: t('fareRules.allRoutes') }, ...routes.map(r => ({ value: r.route_id, label: `${r.route_short_name} - ${r.route_long_name ?? r.route_id}` }))]} {...form.getInputProps('route_id')} searchable clearable />
            <Divider my="sm" label={t('fareRules.zoneSettings')} labelPosition="center" />
            <TextInput label={t('fareRules.fields.originId')} description={t('fareRules.fields.originIdDesc')} placeholder={t('fareRules.placeholders.originId')} {...form.getInputProps('origin_id')} />
            <TextInput label={t('fareRules.fields.destinationId')} description={t('fareRules.fields.destinationIdDesc')} placeholder={t('fareRules.placeholders.destinationId')} {...form.getInputProps('destination_id')} />
            <TextInput label={t('fareRules.fields.containsId')} description={t('fareRules.fields.containsIdDesc')} placeholder={t('fareRules.placeholders.containsId')} {...form.getInputProps('contains_id')} />
            <Group justify="flex-end" mt="md">
              <Button variant="light" onClick={close}>{t('common.cancel')}</Button>
              <Button type="submit">{editingRule ? t('common.update') : t('common.create')}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Container>
  )
}
