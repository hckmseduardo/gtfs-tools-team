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
  LoadingOverlay,
  Card,
  Box,
  Collapse,
  UnstyledButton,
  Divider,
  SimpleGrid,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconCash,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
  IconListDetails,
} from '@tabler/icons-react'
import { fareAttributesApi, agencyApi, type FareAttribute, type Agency } from '../lib/gtfs-api'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import FeedSelector from '../components/FeedSelector'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

// Payment method types per GTFS specification
const getPaymentMethods = (t: (key: string) => string) => [
  { value: '0', label: t('fareAttributes.paymentMethods.onBoard') },
  { value: '1', label: t('fareAttributes.paymentMethods.beforeBoarding') },
]

// Transfers types per GTFS specification
const getTransfersTypes = (t: (key: string) => string) => [
  { value: '', label: t('fareAttributes.transfers.unlimited') },
  { value: '0', label: t('fareAttributes.transfers.none') },
  { value: '1', label: t('fareAttributes.transfers.once') },
  { value: '2', label: t('fareAttributes.transfers.twice') },
]

// Common currency codes
const currencyCodes = [
  { value: 'USD', label: 'USD - US Dollar' },
  { value: 'EUR', label: 'EUR - Euro' },
  { value: 'GBP', label: 'GBP - British Pound' },
  { value: 'CAD', label: 'CAD - Canadian Dollar' },
  { value: 'BRL', label: 'BRL - Brazilian Real' },
  { value: 'AUD', label: 'AUD - Australian Dollar' },
  { value: 'JPY', label: 'JPY - Japanese Yen' },
  { value: 'CHF', label: 'CHF - Swiss Franc' },
  { value: 'MXN', label: 'MXN - Mexican Peso' },
]

export default function FareAttributes() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [fareAttributes, setFareAttributes] = useState<FareAttribute[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [loading, setLoading] = useState(false)
  const [opened, { open, close }] = useDisclosure(false)
  const [editingFare, setEditingFare] = useState<FareAttribute | null>(null)
  const [originalFareId, setOriginalFareId] = useState<string | null>(null)
  const [selectedAgency, setSelectedAgency] = useState<number | null>(null)
  const [selectedFeed, setSelectedFeed] = useState<string | null>(null)
  const [expandedFareId, setExpandedFareId] = useState<string | null>(null)

  const form = useForm({
    initialValues: {
      fare_id: '',
      price: 0,
      currency_type: 'USD',
      payment_method: '0',
      transfers: '',
      agency_id: '',
      transfer_duration: '',
    },
    validate: {
      fare_id: (value) => (value.length < 1 ? t('fareAttributes.validation.fareIdRequired') : null),
      price: (value) => (value < 0 ? t('fareAttributes.validation.pricePositive') : null),
      currency_type: (value) => (value.length !== 3 ? t('fareAttributes.validation.currencyFormat') : null),
    },
  })

  useEffect(() => {
    loadAgencies()
  }, [])

  useEffect(() => {
    if (selectedAgency) {
      loadFareAttributes()
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

  const loadFareAttributes = async () => {
    if (!selectedFeed) {
      setFareAttributes([])
      return
    }

    setLoading(true)
    try {
      const feed_id = parseInt(selectedFeed)
      const data = await fareAttributesApi.list(feed_id, { limit: 1000 })
      setFareAttributes(data.items || [])
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: t('fareAttributes.loadError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleOpenCreate = () => {
    setEditingFare(null)
    setOriginalFareId(null)
    form.reset()
    open()
  }

  const handleOpenEdit = (fare: FareAttribute) => {
    setEditingFare(fare)
    setOriginalFareId(fare.fare_id)  // Store the original fare_id for the API call
    form.setValues({
      fare_id: fare.fare_id,
      price: fare.price,
      currency_type: fare.currency_type,
      payment_method: String(fare.payment_method),
      transfers: fare.transfers !== null && fare.transfers !== undefined ? String(fare.transfers) : '',
      agency_id: fare.agency_id || '',
      transfer_duration: fare.transfer_duration !== null && fare.transfer_duration !== undefined ? String(fare.transfer_duration) : '',
    })
    open()
  }

  const handleSubmit = async (values: typeof form.values) => {
    if (!selectedFeed || !selectedAgency) {
      notifications.show({
        title: t('common.error'),
        message: t('fareAttributes.validation.selectFeedFirst'),
        color: 'red',
      })
      return
    }

    try {
      const feed_id = parseInt(selectedFeed)
      const data = {
        fare_id: values.fare_id,
        price: Number(values.price),
        currency_type: values.currency_type,
        payment_method: parseInt(values.payment_method),
        transfers: values.transfers !== '' ? parseInt(values.transfers) : undefined,
        transfer_duration: values.transfer_duration !== '' ? parseInt(values.transfer_duration) : undefined,
        agency_id: values.agency_id || undefined,
      }

      console.log('Submitting fare attribute:', { feed_id, originalFareId, data })

      if (editingFare && originalFareId) {
        await fareAttributesApi.update(feed_id, originalFareId, data)
        notifications.show({
          title: t('common.success'),
          message: t('fareAttributes.updateSuccess'),
          color: 'green',
        })
      } else {
        await fareAttributesApi.create(feed_id, data)
        notifications.show({
          title: t('common.success'),
          message: t('fareAttributes.createSuccess'),
          color: 'green',
        })
      }
      close()
      loadFareAttributes()
    } catch (error: any) {
      console.error('Fare attribute save error:', error.response?.data)
      let errorMessage = t('fareAttributes.saveError')
      const detail = error.response?.data?.detail
      if (detail) {
        if (typeof detail === 'string') {
          errorMessage = detail
        } else if (Array.isArray(detail)) {
          // Pydantic validation errors
          errorMessage = detail.map((e: any) => `${e.loc?.join('.')}: ${e.msg}`).join('; ')
        }
      }
      notifications.show({
        title: t('common.error'),
        message: errorMessage,
        color: 'red',
      })
    }
  }

  const handleDelete = (fare: FareAttribute) => {
    if (!selectedFeed) {
      notifications.show({
        title: t('common.error'),
        message: t('fareAttributes.validation.selectFeedFirst'),
        color: 'red',
      })
      return
    }

    modals.openConfirmModal({
      title: t('fareAttributes.deleteFare'),
      children: (
        <Text size="sm">
          {t('fareAttributes.deleteConfirm', { id: fare.fare_id })}
        </Text>
      ),
      labels: { confirm: t('common.delete'), cancel: t('common.cancel') },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          const feed_id = parseInt(selectedFeed!)
          await fareAttributesApi.delete(feed_id, fare.fare_id)
          notifications.show({
            title: t('common.success'),
            message: t('fareAttributes.deleteSuccess'),
            color: 'green',
          })
          loadFareAttributes()
        } catch (error: any) {
          notifications.show({
            title: t('common.error'),
            message: error.response?.data?.detail || t('fareAttributes.deleteError'),
            color: 'red',
          })
        }
      },
    })
  }

  const handleViewRules = (fare: FareAttribute) => {
    navigate(`/fare-rules?fare_id=${fare.fare_id}&feed_id=${selectedFeed}`)
  }

  const formatPrice = (price: number, currency: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(price)
  }

  const formatTransferDuration = (seconds: number | undefined) => {
    if (!seconds) return '-'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  // Mobile Fare Card Component
  const FareCard = ({ fare }: { fare: FareAttribute }) => {
    const isExpanded = expandedFareId === fare.fare_id

    return (
      <Card shadow="sm" padding="md" radius="md" withBorder>
        <Stack gap="sm">
          <UnstyledButton
            onClick={() => setExpandedFareId(isExpanded ? null : fare.fare_id)}
            style={{ width: '100%' }}
          >
            <Group justify="space-between" wrap="nowrap" gap="sm">
              <Group gap="sm" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                <IconCash size={20} style={{ flexShrink: 0 }} />
                <Box style={{ minWidth: 0 }}>
                  <Text fw={600} size="sm" truncate>
                    {fare.fare_id}
                  </Text>
                  <Text size="xs" c="dimmed" truncate>
                    {formatPrice(fare.price, fare.currency_type)}
                  </Text>
                </Box>
              </Group>
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Badge size="sm" variant="light">
                  {fare.payment_method === 0 ? t('fareAttributes.paymentMethods.onBoard') : t('fareAttributes.paymentMethods.beforeBoarding')}
                </Badge>
                {isExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
              </Group>
            </Group>
          </UnstyledButton>

          <Collapse in={isExpanded}>
            <Stack gap="sm" mt="xs">
              <Divider />

              <Group gap="xs">
                <Text size="xs" c="dimmed">{t('fareAttributes.transfers.label')}:</Text>
                <Badge variant="outline" size="sm">
                  {fare.transfers === null ? t('fareAttributes.transfers.unlimited') :
                   fare.transfers === 0 ? t('fareAttributes.transfers.none') :
                   fare.transfers === 1 ? t('fareAttributes.transfers.once') :
                   t('fareAttributes.transfers.twice')}
                </Badge>
              </Group>

              {fare.transfer_duration && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('fareAttributes.transferDuration')}:</Text>
                  <Text size="xs">{formatTransferDuration(fare.transfer_duration)}</Text>
                </Group>
              )}

              {fare.agency_id && (
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{t('fareAttributes.agencyId')}:</Text>
                  <Text size="xs">{fare.agency_id}</Text>
                </Group>
              )}

              <Divider label={t('common.actions')} labelPosition="center" />

              <SimpleGrid cols={3} spacing="xs">
                <Button
                  variant="light"
                  size="sm"
                  onClick={() => handleOpenEdit(fare)}
                  leftSection={<IconEdit size={16} />}
                  fullWidth
                >
                  {t('common.edit')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="blue"
                  onClick={() => handleViewRules(fare)}
                  leftSection={<IconListDetails size={16} />}
                  fullWidth
                >
                  {t('fareAttributes.rules')}
                </Button>
                <Button
                  variant="light"
                  size="sm"
                  color="red"
                  onClick={() => handleDelete(fare)}
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
                  <IconCash size={20} />
                  <Title order={3}>{t('fareAttributes.title')}</Title>
                </Group>
                <Text c="dimmed" size="xs">
                  {t('fareAttributes.description')}
                </Text>
              </Box>
              <Group gap="xs">
                <ActionIcon variant="light" size="lg" onClick={loadFareAttributes} loading={loading}>
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
                <IconCash style={{ marginRight: 8, verticalAlign: 'middle' }} />
                {t('fareAttributes.title')}
              </Title>
              <Text c="dimmed" size="sm" mt="xs">
                {t('fareAttributes.description')}
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={handleOpenCreate} disabled={!selectedFeed}>
              {t('fareAttributes.newFare')}
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

        {/* Fare Attributes List */}
        {isMobile ? (
          <Stack gap="sm" pos="relative">
            <LoadingOverlay visible={loading} />
            {fareAttributes.length === 0 && !loading ? (
              <Paper p="xl" withBorder>
                <Text c="dimmed" ta="center">{t('fareAttributes.noFares')}</Text>
              </Paper>
            ) : (
              fareAttributes.map((fare) => (
                <FareCard key={`${fare.feed_id}:${fare.fare_id}`} fare={fare} />
              ))
            )}
          </Stack>
        ) : (
          /* Desktop Table */
          <Paper shadow="sm" p="md" withBorder pos="relative">
            <LoadingOverlay visible={loading} />
            {fareAttributes.length === 0 && !loading ? (
              <Text c="dimmed" ta="center" py="xl">
                {t('fareAttributes.noFares')}
              </Text>
            ) : (
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('fareAttributes.fareId')}</Table.Th>
                    <Table.Th>{t('fareAttributes.price')}</Table.Th>
                    <Table.Th>{t('fareAttributes.paymentMethod')}</Table.Th>
                    <Table.Th>{t('fareAttributes.transfers.label')}</Table.Th>
                    <Table.Th>{t('fareAttributes.transferDuration')}</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>{t('common.actions')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {fareAttributes.map((fare) => (
                    <Table.Tr key={`${fare.feed_id}:${fare.fare_id}`}>
                      <Table.Td>
                        <Text size="sm" fw={500}>
                          {fare.fare_id}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" fw={600}>
                          {formatPrice(fare.price, fare.currency_type)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge size="sm" variant="light">
                          {fare.payment_method === 0 ? t('fareAttributes.paymentMethods.onBoard') : t('fareAttributes.paymentMethods.beforeBoarding')}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Badge size="sm" variant="outline">
                          {fare.transfers === null ? t('fareAttributes.transfers.unlimited') :
                           fare.transfers === 0 ? t('fareAttributes.transfers.none') :
                           fare.transfers === 1 ? t('fareAttributes.transfers.once') :
                           t('fareAttributes.transfers.twice')}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{formatTransferDuration(fare.transfer_duration)}</Text>
                      </Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>
                        <Group gap={4} justify="flex-end">
                          <ActionIcon variant="subtle" color="blue" onClick={() => handleOpenEdit(fare)}>
                            <IconEdit size={16} />
                          </ActionIcon>
                          <ActionIcon variant="subtle" color="gray" onClick={() => handleViewRules(fare)}>
                            <IconListDetails size={16} />
                          </ActionIcon>
                          <ActionIcon variant="subtle" color="red" onClick={() => handleDelete(fare)}>
                            <IconTrash size={16} />
                          </ActionIcon>
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

      {/* Create/Edit Modal */}
      <Modal
        opened={opened}
        onClose={close}
        title={editingFare ? t('fareAttributes.editFare') : t('fareAttributes.newFare')}
        size={isMobile ? '100%' : 'lg'}
        fullScreen={isMobile}
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            {/* Required Fields Section */}
            <Text fw={600} size="sm" c="dimmed">{t('fareAttributes.sections.required')}</Text>

            <TextInput
              label={t('fareAttributes.fields.fareId')}
              description={editingFare
                ? t('fareAttributes.fields.fareIdEditDesc')
                : t('fareAttributes.fields.fareIdDesc')}
              placeholder={t('fareAttributes.placeholders.fareId')}
              {...form.getInputProps('fare_id')}
              required
            />

            <SimpleGrid cols={isMobile ? 1 : 2}>
              <NumberInput
                label={t('fareAttributes.fields.price')}
                description={t('fareAttributes.fields.priceDesc')}
                placeholder="0.00"
                {...form.getInputProps('price')}
                required
                min={0}
                decimalScale={2}
                fixedDecimalScale
              />
              <Select
                label={t('fareAttributes.fields.currencyType')}
                description={t('fareAttributes.fields.currencyTypeDesc')}
                data={currencyCodes}
                {...form.getInputProps('currency_type')}
                required
                searchable
                allowDeselect={false}
              />
            </SimpleGrid>

            <Select
              label={t('fareAttributes.fields.paymentMethod')}
              description={t('fareAttributes.fields.paymentMethodDesc')}
              data={getPaymentMethods(t)}
              {...form.getInputProps('payment_method')}
              required
              allowDeselect={false}
            />

            <Select
              label={t('fareAttributes.fields.transfers')}
              description={t('fareAttributes.fields.transfersDesc')}
              data={getTransfersTypes(t)}
              {...form.getInputProps('transfers')}
              clearable
            />

            {/* Optional Fields Section */}
            <Divider my="sm" />
            <Text fw={600} size="sm" c="dimmed">{t('fareAttributes.sections.optional')}</Text>

            <TextInput
              label={t('fareAttributes.fields.agencyId')}
              description={t('fareAttributes.fields.agencyIdDesc')}
              placeholder={t('fareAttributes.placeholders.agencyId')}
              {...form.getInputProps('agency_id')}
            />

            <NumberInput
              label={t('fareAttributes.fields.transferDuration')}
              description={t('fareAttributes.fields.transferDurationDesc')}
              placeholder={t('fareAttributes.placeholders.transferDuration')}
              value={form.values.transfer_duration !== '' ? parseInt(form.values.transfer_duration) : ''}
              onChange={(val) => form.setFieldValue('transfer_duration', val !== '' ? String(val) : '')}
              min={0}
              suffix=" seconds"
            />

            <Group justify="flex-end" mt="md">
              <Button variant="light" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button type="submit">
                {editingFare ? t('common.update') : t('common.create')}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Container>
  )
}
