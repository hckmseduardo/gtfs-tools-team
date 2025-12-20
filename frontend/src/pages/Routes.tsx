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
  NumberInput,
  Textarea,
  LoadingOverlay,
  Card,
  Box,
  Collapse,
  UnstyledButton,
  Divider,
  SimpleGrid,
  ColorSwatch,
  ColorInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconRoute,
  IconBus,
  IconTrain,
  IconShip,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
  IconCopy,
} from '@tabler/icons-react'
import { routesApi, agencyApi, type Route, type Agency } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { useTranslation } from 'react-i18next'

// Route types per GTFS specification
const getRouteTypes = (t: (key: string) => string) => [
  { value: '0', label: t('routes.routeTypes.tram') },
  { value: '1', label: t('routes.routeTypes.subway') },
  { value: '2', label: t('routes.routeTypes.rail') },
  { value: '3', label: t('routes.routeTypes.bus') },
  { value: '4', label: t('routes.routeTypes.ferry') },
  { value: '5', label: t('routes.routeTypes.cableTram') },
  { value: '6', label: t('routes.routeTypes.aerialLift') },
  { value: '7', label: t('routes.routeTypes.funicular') },
  { value: '11', label: t('routes.routeTypes.trolleybus') },
  { value: '12', label: t('routes.routeTypes.monorail') },
]

// Continuous pickup/drop-off types per GTFS specification
const getContinuousPickupTypes = (t: (key: string) => string) => [
  { value: '', label: t('routes.continuousTypes.notSpecified') },
  { value: '0', label: t('routes.continuousTypes.continuous') },
  { value: '1', label: t('routes.continuousTypes.noContinuous') },
  { value: '2', label: t('routes.continuousTypes.phoneAgency') },
  { value: '3', label: t('routes.continuousTypes.coordinateDriver') },
]

const getRouteIcon = (type: number) => {
  if (type === 0 || type === 1 || type === 2 || type === 12) return IconTrain
  if (type === 4) return IconShip
  return IconBus
}

const getRouteTypeLabelByValue = (type: number, t: (key: string) => string): string => {
  const routeTypes = getRouteTypes(t)
  return routeTypes.find(rt => rt.value === String(type))?.label || t('routes.routeTypes.unknown')
}

export default function Routes() {
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [routes, setRoutes] = useState<Route[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingRoute, setEditingRoute] = useState<Route | null>(null)
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [expandedRouteId, setExpandedRouteId] = useState<string | null>(null)

  const form = useForm({
    initialValues: {
      route_id: '',
      route_short_name: '',
      route_long_name: '',
      route_desc: '',
      route_type: '3',
      route_url: '',
      route_color: '',
      route_text_color: '',
      route_sort_order: 0,
      continuous_pickup: '',
      continuous_drop_off: '',
      network_id: '',
    },
    validate: {
      route_id: (value) => (value.length < 1 ? t('routes.validation.routeIdRequired') : null),
      route_type: (value) => (value === '' ? t('routes.validation.routeTypeRequired') : null),
      route_color: (value) => {
        if (value && !/^[0-9A-Fa-f]{6}$/.test(value)) {
          return t('routes.validation.colorFormat')
        }
        return null
      },
      route_text_color: (value) => {
        if (value && !/^[0-9A-Fa-f]{6}$/.test(value)) {
          return t('routes.validation.colorFormat')
        }
        return null
      },
      route_url: (value) => {
        if (value && !value.match(/^https?:\/\/.+/)) {
          return t('routes.validation.urlFormat')
        }
        return null
      },
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadRoutes()
    }
  }, [selectedAgency, selectedFeed])

  const loadAgencies = async () => {
    try {
      const data = await agencyApi.list({ limit: 1000 })
      setAgencies(data.items || [])
      if (data.items && data.items.length > 0) {
        setSelectedAgency(data.items[0].id)
      }
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: t('agencies.loadError'),
        color: 'red',
      })
    }
  }

  const loadRoutes = async () => {
    if (!selectedFeed) {
      setRoutes([])
      return
    }

    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const data = await routesApi.list(feed_id, { limit: 1000 })
      setRoutes(data.items || [])
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: t('routes.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleOpenCreate = () => {
    setEditingRoute(null)
    form.reset()
    open()
  }

  const handleOpenEdit = (route: Route) => {
    setEditingRoute(route)
    form.setValues({
      route_id: route.route_id,
      route_short_name: route.route_short_name,
      route_long_name: route.route_long_name || '',
      route_desc: route.route_desc || '',
      route_type: String(route.route_type),
      route_url: route.route_url || '',
      route_color: route.route_color || '',
      route_text_color: route.route_text_color || '',
      route_sort_order: route.route_sort_order || 0,
      continuous_pickup: route.continuous_pickup !== undefined && route.continuous_pickup !== null ? String(route.continuous_pickup) : '',
      continuous_drop_off: route.continuous_drop_off !== undefined && route.continuous_drop_off !== null ? String(route.continuous_drop_off) : '',
      network_id: route.network_id || '',
    })
    open()
  }

  const handleSubmit = async (values: typeof form.values) => {
    if (!selectedFeed || !selectedAgency) {
      notifications.show({
        title: t('common.error'),
        message: t('routes.validation.selectFeedFirst'),
        color: 'red',
      })
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const data = {
        ...values,
        agency_id: selectedAgency,
        route_type: parseInt(values.route_type),
        continuous_pickup: values.continuous_pickup ? parseInt(values.continuous_pickup) : null,
        continuous_drop_off: values.continuous_drop_off ? parseInt(values.continuous_drop_off) : null,
        network_id: values.network_id || null,
      }

      if (editingRoute) {
        await routesApi.update(feed_id, editingRoute.route_id, data)
        notifications.show({
          title: t('common.success'),
          message: t('routes.updateSuccess'),
          color: 'green',
        })
      } else {
        await routesApi.create(feed_id, data)
        notifications.show({
          title: t('common.success'),
          message: t('routes.createSuccess'),
          color: 'green',
        })
      }
      close()
      loadRoutes()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || t('routes.saveError'),
        color: 'red',
      })
    }
  }

  const handleDelete = (route: Route) => {
    if (!selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: 'Please select a feed first',
        color: 'red',
      })
      return
    }

    modals.openConfirmModal({
      title: t('routes.deleteRoute'),
      children: (
        <Text size="sm">
          {t('routes.deleteConfirm', { name: route.route_short_name })}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          const feed_id = parseInt(selectedFeed!)
          await routesApi.delete(feed_id, route.route_id)
          notifications.show({
            title: t('common.success'),
            message: t('routes.deleteSuccess'),
            color: 'green',
          })
          loadRoutes()
        } catch (error: any) {
          notifications.show({
            title: t('common.error'),
            message: error.response?.data?.detail || t('routes.deleteError'),
            color: 'red',
          })
        }
      },
    })
  }

  const handleCopy = (route: Route) => {
    modals.open({
      title: t('routes.copyRoute'),
      children: (
        <Stack>
          <Text size="sm">
            {t('routes.copyDescription', { name: route.route_short_name })}
          </Text>
          <TextInput
            label={t('routes.newRouteId')}
            placeholder={t('routes.newRouteIdPlaceholder')}
            required
            id="copy-route-id"
            defaultValue={`${route.route_id}_copy`}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => modals.closeAll()}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={async () => {
                const input = document.getElementById('copy-route-id') as HTMLInputElement
                const newRouteId = input?.value
                if (!newRouteId) {
                  notifications.show({
                    title: t('common.error'),
                    message: t('routes.routeIdRequired'),
                    color: 'red',
                  })
                  return
                }
                try {
                  if (!selectedFeed || !selectedAgency) {
                    notifications.show({
                      title: t('common.error'),
                      message: t('routes.validation.selectFeedFirst'),
                      color: 'red',
                    })
                    return
                  }
                  const feed_id = parseInt(selectedFeed)
                  const routeData = {
                    agency_id: selectedAgency,
                    route_id: newRouteId,
                    route_short_name: route.route_short_name,
                    route_long_name: route.route_long_name || route.route_short_name,
                    route_desc: route.route_desc || undefined,
                    route_type: route.route_type,
                    route_url: route.route_url || undefined,
                    route_color: route.route_color || undefined,
                    route_text_color: route.route_text_color || undefined,
                    route_sort_order: route.route_sort_order ?? undefined,
                    continuous_pickup: route.continuous_pickup ?? undefined,
                    continuous_drop_off: route.continuous_drop_off ?? undefined,
                    network_id: route.network_id || undefined,
                  }
                  await routesApi.create(feed_id, routeData)
                  notifications.show({
                    title: t('common.success'),
                    message: t('routes.copySuccess'),
                    color: 'green',
                  })
                  modals.closeAll()
                  loadRoutes()
                } catch (error: any) {
                  const detail = error?.response?.data?.detail
                  let errorMessage = t('routes.copyError')
                  if (typeof detail === 'string') {
                    errorMessage = detail
                  } else if (Array.isArray(detail) && detail.length > 0) {
                    errorMessage = detail.map((d: any) => d.msg || d).join(', ')
                  }
                  notifications.show({
                    title: t('common.error'),
                    message: errorMessage,
                    color: 'red',
                  })
                }
              }}
            >
              {t('common.copy')}
            </Button>
          </Group>
        </Stack>
      ),
    })
  }

  // Mobile Route Card Component
  const RouteCard = ({ route }: { route: Route }) => {
    const isExpanded = expandedRouteId === route.route_id
    const RouteIcon = getRouteIcon(route.route_type)

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedRouteId(isExpanded ? null : route.route_id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                {route.route_color && (
                  <ColorSwatch color={`#${route.route_color}`} size={24} style={{ flexShrink: 0 }} />
                )}
                {!route.route_color && <RouteIcon size={20} style={{ flexShrink: 0 }} />}
                <Box style={{ minWidth: 0 }}>
                  <Text fw={600} size="sm" truncate>
                    {route.route_short_name}
                  </Text>
                  <Text size="xs" c="dimmed" truncate>
                    {route.route_long_name}
                  </Text>
                </Box>
              </Group>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Badge size="sm" variant="light">
                  {getRouteTypeLabelByValue(route.route_type, t)}
                </Badge>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              {route.route_desc && (
                <Text size="sm" c="dimmed">
                  {route.route_desc}
                </Text>
              )}

              <Group gap="xs">
                <Text size="xs" c="dimmed">{t('routes.routeId')}:</Text>
                <Badge variant="outline" size="sm">{route.route_id}</Badge>
              </Group>

              {route.route_color && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('routes.color')}:</Text>
                  <ColorSwatch color={`#${route.route_color}`} size={16} />
                  <Text size="xs">#{route.route_color}</Text>
                </Group>
              )}

              {route.route_url && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('routes.url')}:</Text>
                  <Text size="xs" truncate style={{ maxWidth: '200px' }}>{route.route_url}</Text>
                </Group>
              )}

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={3} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleOpenEdit(route)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="blue"
                  onClick={() => handleCopy(route)}
                  leftSection={<IconCopy size={16} />}
                  fullWidth
                >
                  {t('common.copy')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="red"
                  onClick={() => handleDelete(route)}
                  leftSection={<IconTrash size={16} />}
                  fullWidth
                >
                  {t('common.delete')}
                </Button>
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
        {/* Header */}
        {isMobile ? (
          <Stack gap="xs">
            <Group justify="space-between" align="flex-start">
              <Box>
                <Group gap="xs">
                  <IconRoute size={20} />
                  <Title order={3}>{t('routes.title')}</Title>
                </Group>
                <Text c="dimmed" size="xs">
                  {t('routes.description')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadRoutes} loading={loading}>
                  <IconRefresh size={18} />
                </ActionIcon>
                <ActionIcon variant="filled" size="lg" onClick={handleOpenCreate} disabled={!selectedFeed}>
                  <IconPlus size={18} />
                </ActionIcon>
              </Group>
            </Group>
          </Stack>
        ) : (
          <Group justify="space-between">
            <div>
              <Title order={1}>
                <IconRoute style={{ marginRight: 8, verticalAlign: 'middle' }} />
                {t('routes.title')}
              </Title>
              <Text c="dimmed" size="sm" mt="xs">
                {t('routes.description')}
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleOpenCreate} disabled={!selectedFeed}>
              {t('routes.newRoute')}
            </Button>
          </Group>
        )}

        {/* Filters */}
        <Paper shadow="sm" p={isMobile ? 'sm' : 'md'} withBorder>
          <Stack gap="sm">
            <Select
              label={t('agencies.title')}
              placeholder={t('agencies.selectAgency')}
              data={agencies.map(a => ({ value: String(a.id), label: a.name }))}
              value={selectedAgency ? String(selectedAgency) : null}
              onChange={(value) => setSelectedAgency(value ? parseInt(value) : null)}
              size={isMobile ? 'sm' : 'md'}
            />
            <FeedSelector
              label={t('feeds.title')}
              agencyId={selectedAgency}
              value={selectedFeed}
              onChange={setSelectedFeed}
              showAllOption={false}
            />
          </Stack>
        </Paper>

        {/* Routes List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {routes.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">{t('routes.noRoutes')}</Text>
              </Paper>
            ) : (
              routes.map((route) => (
                <RouteCard key={`${route.feed_id}:${route.route_id}`} route={route} />
              ))
            )}
          </Stack>
        ) : (
          /* Desktop Table */
          <Paper shadow="sm" p="md" withBorder pos="relative">
            <LoadingOverlay visible={loading} />
            {routes.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">
                {t('routes.noRoutes')}
              </Text>
            ) : (
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('routes.routeId')}</Table.Th>
                    <Table.Th>{t('routes.shortName')}</Table.Th>
                    <Table.Th>{t('routes.longName')}</Table.Th>
                    <Table.Th>{t('routes.type')}</Table.Th>
                    <Table.Th>{t('routes.color')}</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>{t('common.actions')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {routes.map((route) => {
                    const RouteIcon = getRouteIcon(route.route_type)
                    return (
                      <Table.Tr key={`${route.feed_id}:${route.route_id}`}>
                        <Table.Td>
                          <Text size="sm" fw={500}>
                            {route.route_id}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <RouteIcon size={16} />
                            <Text size="sm" fw={600}>
                              {route.route_short_name}
                            </Text>
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{route.route_long_name}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge size="sm" variant="light">
                            {getRouteTypeLabelByValue(route.route_type, t)}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          {route.route_color && (
                            <Group gap="xs">
                              <ColorSwatch color={`#${route.route_color}`} size={20} />
                              <Text size="xs" c="dimmed">
                                #{route.route_color}
                              </Text>
                            </Group>
                          )}
                        </Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>
                          <Group gap={4} justify="flex-end">
                            <ActionIcon variant="subtle" color="blue" onClick={() => handleOpenEdit(route)}>
                              <IconEdit size={16} />
                            </ActionIcon>
                            <ActionIcon variant="subtle" color="gray" onClick={() => handleCopy(route)}>
                              <IconCopy size={16} />
                            </ActionIcon>
                            <ActionIcon variant="subtle" color="red" onClick={() => handleDelete(route)}>
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
        )}
      </Stack>

      {/* Create/Edit Modal */}
      <Modal
        opened={opened}
        onClose={close}
        title={editingRoute ? t('routes.editRoute') : t('routes.newRoute')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            {/* Required Fields Section */}
            <Text fw={600} size="sm" c="dimmed">{t('routes.sections.required')}</Text>

            <TextInput
              label={t('routes.fields.routeId')}
              description={t('routes.fields.routeIdDesc')}
              placeholder={t('routes.placeholders.routeId')}
              {...form.getInputProps('route_id')}
              required
              disabled={!!editingRoute}
            />

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <TextInput
                label={t('routes.fields.shortName')}
                description={t('routes.fields.shortNameDesc')}
                placeholder={t('routes.placeholders.shortName')}
                {...form.getInputProps('route_short_name')}
              />
              <TextInput
                label={t('routes.fields.longName')}
                description={t('routes.fields.longNameDesc')}
                placeholder={t('routes.placeholders.longName')}
                {...form.getInputProps('route_long_name')}
              />
            </SimpleGrid>

            <Select
              label={t('routes.fields.routeType')}
              description={t('routes.fields.routeTypeDesc')}
              data={getRouteTypes(t)}
              {...form.getInputProps('route_type')}
              required
              searchable
            />

            {/* Optional Fields Section */}
            <Divider my="sm" />
            <Text fw={600} size="sm" c="dimmed">{t('routes.sections.optional')}</Text>

            <Textarea
              label={t('routes.fields.description')}
              description={t('routes.fields.descriptionDesc')}
              placeholder={t('routes.placeholders.description')}
              {...form.getInputProps('route_desc')}
              minRows={2}
            />

            <TextInput
              label={t('routes.fields.url')}
              description={t('routes.fields.urlDesc')}
              placeholder={t('routes.placeholders.url')}
              {...form.getInputProps('route_url')}
            />

            {/* Display Section */}
            <Divider my="sm" />
            <Text fw={600} size="sm" c="dimmed">{t('routes.sections.display')}</Text>

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <ColorInput
                label={t('routes.fields.routeColor')}
                description={t('routes.fields.routeColorDesc')}
                placeholder={t('routes.placeholders.color')}
                format="hex"
                swatches={['#FF0000', '#FF6600', '#FFCC00', '#00FF00', '#0066FF', '#6600FF', '#FF00FF', '#000000', '#FFFFFF']}
                value={form.values.route_color ? `#${form.values.route_color}` : ''}
                onChange={(value) => form.setFieldValue('route_color', value ? value.replace('#', '') : '')}
                error={form.errors.route_color}
              />
              <ColorInput
                label={t('routes.fields.textColor')}
                description={t('routes.fields.textColorDesc')}
                placeholder={t('routes.placeholders.textColor')}
                format="hex"
                swatches={['#FFFFFF', '#000000', '#FF0000', '#00FF00', '#0000FF']}
                value={form.values.route_text_color ? `#${form.values.route_text_color}` : ''}
                onChange={(value) => form.setFieldValue('route_text_color', value ? value.replace('#', '') : '')}
                error={form.errors.route_text_color}
              />
            </SimpleGrid>

            <NumberInput
              label={t('routes.fields.sortOrder')}
              description={t('routes.fields.sortOrderDesc')}
              placeholder="0"
              {...form.getInputProps('route_sort_order')}
              min={0}
            />

            {/* Service Options Section */}
            <Divider my="sm" />
            <Text fw={600} size="sm" c="dimmed">{t('routes.sections.serviceOptions')}</Text>

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <Select
                label={t('routes.fields.continuousPickup')}
                description={t('routes.fields.continuousPickupDesc')}
                data={getContinuousPickupTypes(t)}
                {...form.getInputProps('continuous_pickup')}
                clearable
              />
              <Select
                label={t('routes.fields.continuousDropOff')}
                description={t('routes.fields.continuousDropOffDesc')}
                data={getContinuousPickupTypes(t)}
                {...form.getInputProps('continuous_drop_off')}
                clearable
              />
            </SimpleGrid>

            <TextInput
              label={t('routes.fields.networkId')}
              description={t('routes.fields.networkIdDesc')}
              placeholder={t('routes.placeholders.networkId')}
              {...form.getInputProps('network_id')}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="light" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button type="submit">
                {editingRoute ? t('common.update') : t('common.create')}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Container>
  )
}
