import { useState, useEffect } from 'react'
import {
  Container,
  Title,
  Text,
  Paper,
  Stack,
  SimpleGrid,
  Card,
  Group,
  ThemeIcon,
  Badge,
  LoadingOverlay,
  Button,
} from '@mantine/core'
import {
  IconBuilding,
  IconRoute,
  IconMapPin,
  IconBus,
  IconCalendar,
  IconClock,
  IconFileImport,
  IconCheck,
  IconTestPipe,
} from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store/authStore'
import { useNavigate } from 'react-router-dom'
import { agencyApi } from '../lib/gtfs-api'
import { feedApi } from '../lib/feed-api'
import { notifications } from '@mantine/notifications'
import api from '../lib/api'

interface Statistics {
  agencies: number
  routes: number
  stops: number
  trips: number
  calendars: number
}

export default function Dashboard() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [stats, setStats] = useState<Statistics>({
    agencies: 0,
    routes: 0,
    stops: 0,
    trips: 0,
    calendars: 0,
  })
  const [loading, setLoading] = useState(true)
  const [creatingDemo, setCreatingDemo] = useState(false)

  useEffect(() => {
    loadStatistics()
  }, [])

  const loadStatistics = async () => {
    setLoading(true)
    try {
      // Get agencies
      const agenciesRes = await agencyApi.list({ limit: 1 })

      // Get all feeds to aggregate GTFS statistics
      const feedsRes = await feedApi.list({ limit: 1000 })
      const feeds = feedsRes.feeds || []

      // Aggregate stats across all feeds
      let totalRoutes = 0
      let totalStops = 0
      let totalTrips = 0
      let totalCalendars = 0

      // Use feed stats endpoint to get counts for each feed
      for (const feed of feeds) {
        try {
          const statsRes = await api.get(`/feeds/${feed.id}/stats`)
          const feedStats = statsRes.data.stats || {}
          totalRoutes += feedStats.routes || 0
          totalStops += feedStats.stops || 0
          totalTrips += feedStats.trips || 0
          totalCalendars += feedStats.calendars || 0
        } catch (err) {
          // Skip feeds that don't have stats or throw errors
          console.warn(`Failed to load stats for feed ${feed.id}:`, err)
        }
      }

      setStats({
        agencies: agenciesRes.total || 0,
        routes: totalRoutes,
        stops: totalStops,
        trips: totalTrips,
        calendars: totalCalendars,
      })
    } catch (error) {
      console.error('Failed to load statistics:', error)
      notifications.show({
        title: t('common.error'),
        message: t('errors.unknownError'),
        color: 'red',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleCreateDemoData = async () => {
    setCreatingDemo(true)
    try {
      const response = await api.post('/users/me/create-demo-data')
      notifications.show({
        title: t('common.success'),
        message: response.data.message || 'Demo agency created successfully!',
        color: 'green',
      })
      // Reload statistics to show new data
      loadStatistics()
    } catch (error: any) {
      notifications.show({
        title: t('common.error'),
        message: error.response?.data?.detail || 'Failed to create demo data',
        color: 'red',
      })
    } finally {
      setCreatingDemo(false)
    }
  }

  const statsCards = [
    {
      title: t('nav.agencies'),
      value: stats.agencies,
      icon: IconBuilding,
      color: 'blue',
      path: '/agencies',
    },
    {
      title: t('nav.routes'),
      value: stats.routes,
      icon: IconRoute,
      color: 'grape',
      path: '/routes',
    },
    {
      title: t('nav.stops'),
      value: stats.stops,
      icon: IconMapPin,
      color: 'red',
      path: '/stops',
    },
    {
      title: t('nav.trips'),
      value: stats.trips,
      icon: IconBus,
      color: 'orange',
      path: '/trips',
    },
    {
      title: t('nav.calendars'),
      value: stats.calendars,
      icon: IconCalendar,
      color: 'teal',
      path: '/calendars',
    },
  ]

  const features = [
    {
      icon: IconBuilding,
      title: t('nav.agencies'),
      path: '/agencies',
      color: 'blue',
    },
    {
      icon: IconRoute,
      title: t('nav.routes'),
      path: '/routes',
      color: 'grape',
    },
    {
      icon: IconMapPin,
      title: t('nav.stops'),
      path: '/stops',
      color: 'red',
    },
    {
      icon: IconBus,
      title: t('nav.trips'),
      path: '/trips',
      color: 'orange',
    },
    {
      icon: IconCalendar,
      title: t('nav.calendars'),
      path: '/calendars',
      color: 'teal',
    },
    {
      icon: IconClock,
      title: t('nav.stopTimes'),
      path: '/stop-times',
      color: 'cyan',
    },
    {
      icon: IconFileImport,
      title: t('import.title'),
      path: '/import-export',
      color: 'green',
    },
  ]

  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Group justify="space-between" align="center">
            <div>
              <Title order={1}>{t('auth.welcomeBack')}, {user?.full_name || user?.email}!</Title>
              <Text mt="sm" c="dimmed">
                {t('dashboard.welcome')}
              </Text>
            </div>
            {user?.is_superuser && (
              <Badge size="lg" variant="gradient" gradient={{ from: 'blue', to: 'cyan' }}>
                {t('users.roles.super_admin')}
              </Badge>
            )}
          </Group>
        </div>

        {/* Statistics Section */}
        <div>
          <Title order={3} mb="md">
            {t('feeds.statistics')}
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} spacing="lg">
            {statsCards.map((stat) => (
              <Paper
                key={stat.title}
                withBorder
                shadow="sm"
                p="md"
                radius="md"
                style={{ cursor: 'pointer', position: 'relative' }}
                onClick={() => navigate(stat.path)}
              >
                <LoadingOverlay visible={loading} />
                <Group justify="space-between">
                  <div>
                    <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                      {stat.title}
                    </Text>
                    <Title order={2} mt="sm">
                      {stat.value.toLocaleString()}
                    </Title>
                  </div>
                  <ThemeIcon size="xl" radius="md" variant="light" color={stat.color}>
                    <stat.icon size={28} stroke={1.5} />
                  </ThemeIcon>
                </Group>
              </Paper>
            ))}
          </SimpleGrid>
        </div>

        <Paper withBorder shadow="sm" p="xl" radius="md">
          <Stack gap="md">
            <Group justify="space-between">
              <Title order={3}>{t('dashboard.title')}</Title>
              <ThemeIcon size="lg" variant="light" color="green">
                <IconCheck size={20} />
              </ThemeIcon>
            </Group>
            <Text c="dimmed">
              {t('dashboard.welcome')}
            </Text>
            <Group>
              <Button
                leftSection={<IconTestPipe size={18} />}
                variant="light"
                color="violet"
                loading={creatingDemo}
                onClick={handleCreateDemoData}
              >
                {t('dashboard.createDemoData', 'Create Demo Data')}
              </Button>
              <Text size="sm" c="dimmed">
                {t('dashboard.createDemoDataDesc', 'Creates a sample agency with routes, stops, and trips to explore the features')}
              </Text>
            </Group>
          </Stack>
        </Paper>

        <div>
          <Title order={3} mb="md">
            {t('dashboard.quickActions')}
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
            {features.map((feature) => (
              <Card
                key={feature.path}
                shadow="sm"
                padding="lg"
                radius="md"
                withBorder
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(feature.path)}
              >
                <Group gap="md">
                  <ThemeIcon size="xl" radius="md" variant="light" color={feature.color}>
                    <feature.icon size={28} />
                  </ThemeIcon>
                  <Title order={4}>{feature.title}</Title>
                </Group>
              </Card>
            ))}
          </SimpleGrid>
        </div>

        <Paper withBorder shadow="sm" p="xl" radius="md" bg="var(--mantine-color-blue-light)">
          <Stack gap="xs">
            <Title order={4}>{t('dashboard.quickActions')}</Title>
            <Text size="sm">
              1. <strong>{t('dashboard.importGtfs')}:</strong> {t('import.dropZone')}
            </Text>
            <Text size="sm">
              2. <strong>{t('agencies.newAgency')}:</strong> {t('agencies.title')}
            </Text>
            <Text size="sm">
              3. <strong>{t('common.edit')}:</strong> {t('nav.routes')}, {t('nav.stops')}, {t('nav.trips')}
            </Text>
            <Text size="sm">
              4. <strong>{t('dashboard.exportGtfs')}:</strong> {t('export.title')}
            </Text>
          </Stack>
        </Paper>
      </Stack>
    </Container>
  )
}
