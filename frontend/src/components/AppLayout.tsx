import { AppShell, Group, Title, NavLink, Avatar, Menu, Text, UnstyledButton, rem, Badge, useMantineColorScheme, ActionIcon, Drawer, Stack, Divider, Box, ScrollArea } from '@mantine/core'
import { useDisclosure, useMediaQuery } from '@mantine/hooks'
import {
  IconHome,
  IconBuilding,
  IconRoute,
  IconMapPin,
  IconBus,
  IconCalendar,
  IconClock,
  IconFileImport,
  IconFileExport,
  IconChecklist,
  IconMap2,
  IconEdit,
  IconHistory,
  IconDatabase,
  IconLogout,
  IconChevronDown,
  IconSun,
  IconMoon,
  IconGitMerge,
  IconGitBranch,
  IconShieldCheck,
  IconTable,
  IconSettings,
  IconUsers,
  IconLivePhoto,
  IconCoin,
  IconRuler2,
  IconArrowBack,
} from '@tabler/icons-react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store/authStore'
import { ReactNode, useState, useEffect, ComponentType } from 'react'
import { tasksApi } from '../lib/tasks-api'
import { LanguageSwitcher } from './LanguageSwitcher'
import { BottomNavigation } from './BottomNavigation'
import { useTaskNotifications } from '../hooks/useTaskNotifications'

interface AppLayoutProps {
  children: ReactNode
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [drawerOpened, { open: openDrawer, close: closeDrawer }] = useDisclosure()
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [activeTaskCount, setActiveTaskCount] = useState(0)
  const { colorScheme, setColorScheme } = useMantineColorScheme()
  const { t } = useTranslation()
  const isMobile = useMediaQuery('(max-width: 48em)')

  // Enable global task completion notifications
  useTaskNotifications()

  // Check if we're on a team subdomain
  const portalDomain = 'app.gtfs-tools.com'
  const hostname = window.location.hostname
  const isTeamSubdomain = hostname.endsWith(`.${portalDomain}`) && hostname !== portalDomain

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleReturnToPortal = () => {
    window.location.href = `https://${portalDomain}/`
  }

  const handleNavigate = (path: string) => {
    navigate(path)
    closeDrawer()
  }

  // Fetch active task count every 5 seconds
  useEffect(() => {
    const fetchActiveCount = async () => {
      try {
        const data = await tasksApi.getActiveCount()
        setActiveTaskCount(data.active_tasks)
      } catch (error) {
        console.error('Failed to fetch active task count:', error)
      }
    }

    fetchActiveCount()
    const interval = setInterval(fetchActiveCount, 5000)
    return () => clearInterval(interval)
  }, [])

  // Grouped navigation for mobile drawer
  const navGroups = [
    {
      label: t('nav.dashboard'),
      icon: IconHome,
      path: '/',
    },
    {
      label: t('nav.map'),
      icon: IconMap2,
      path: '/map',
    },
    {
      label: t('nav.realtime'),
      icon: IconLivePhoto,
      path: '/realtime',
    },
    {
      icon: IconBuilding,
      label: t('nav.agencies'),
      path: '/agencies',
      items: [
        { icon: IconBuilding, label: t('nav.agencies'), path: '/agencies' },
        { icon: IconGitMerge, label: t('nav.mergeAgencies'), path: '/agencies/merge' },
        { icon: IconGitBranch, label: t('nav.splitAgency'), path: '/agencies/split' },
      ],
    },
    {
      label: t('nav.feeds'),
      icon: IconDatabase,
      items: [
        { icon: IconDatabase, label: t('nav.feeds'), path: '/feeds' },
        { icon: IconFileImport, label: t('nav.import'), path: '/feeds/import' },
        { icon: IconFileExport, label: t('nav.export'), path: '/feeds/export' },
        { icon: IconCalendar, label: t('nav.calendars'), path: '/calendars' },
        { icon: IconRoute, label: t('nav.routes'), path: '/routes' },
        { icon: IconMapPin, label: t('nav.stops'), path: '/stops' },
        { icon: IconBus, label: t('nav.trips'), path: '/trips' },
        { icon: IconClock, label: t('nav.stopTimes'), path: '/stop-times' },
        { icon: IconCoin, label: t('nav.fareAttributes'), path: '/fare-attributes' },
        { icon: IconRuler2, label: t('nav.fareRules'), path: '/fare-rules' },
      ],
    },
    {
      label: t('nav.tools'),
      icon: IconSettings,
      items: [
        { icon: IconShieldCheck, label: t('nav.validationSettings'), path: '/validation-settings' },
      ],
    },
    {
      label: t('nav.tasks'),
      icon: IconChecklist,
      path: '/tasks',
      badge: activeTaskCount,
    },
    {
      label: t('nav.auditLogs'),
      icon: IconHistory,
      path: '/audit',
    },
    {
      label: t('nav.teams'),
      icon: IconUsers,
      path: '/teams',
    },
    {
      label: t('nav.settings'),
      icon: IconSettings,
      path: '/settings',
    },
  ]

  // Flat navigation items for desktop sidebar
  const navItems = [
    { icon: IconHome, label: t('nav.dashboard'), path: '/' },
    { icon: IconMap2, label: t('nav.map'), path: '/map' },
    {
      icon: IconBuilding,
      label: t('nav.agencies'),
      path: '/agencies',
      items: [
        { icon: IconBuilding, label: t('nav.agencies'), path: '/agencies' },
        { icon: IconGitMerge, label: t('nav.mergeAgencies'), path: '/agencies/merge' },
        { icon: IconGitBranch, label: t('nav.splitAgency'), path: '/agencies/split' },
      ],
    },
    {
      icon: IconDatabase,
      label: t('nav.feeds'),
      path: '/feeds',
      items: [
        { icon: IconDatabase, label: t('nav.feeds'), path: '/feeds' },
        { icon: IconFileImport, label: t('nav.import'), path: '/feeds/import' },
        { icon: IconFileExport, label: t('nav.export'), path: '/feeds/export' },
        { icon: IconCalendar, label: t('nav.calendars'), path: '/calendars' },
        { icon: IconRoute, label: t('nav.routes'), path: '/routes' },
        { icon: IconMapPin, label: t('nav.stops'), path: '/stops' },
        { icon: IconBus, label: t('nav.trips'), path: '/trips' },
        { icon: IconClock, label: t('nav.stopTimes'), path: '/stop-times' },
        { icon: IconCoin, label: t('nav.fareAttributes'), path: '/fare-attributes' },
        { icon: IconRuler2, label: t('nav.fareRules'), path: '/fare-rules' },
      ],
    },
    { icon: IconLivePhoto, label: t('nav.realtime'), path: '/realtime' },
    { icon: IconShieldCheck, label: t('nav.validationSettings'), path: '/validation-settings' },
    { icon: IconChecklist, label: t('nav.tasks'), path: '/tasks' },
    { icon: IconHistory, label: t('nav.auditLogs'), path: '/audit' },
    { icon: IconUsers, label: t('nav.teams'), path: '/teams' },
    { icon: IconSettings, label: t('nav.settings'), path: '/settings' },
  ]

  // Check if current path is in a group
  const isPathInGroup = (items: Array<{ path: string; items?: Array<{ path: string }> }>): boolean =>
    items.some(item =>
      location.pathname === item.path || (item.items ? isPathInGroup(item.items) : false)
    )

  const renderNestedNavItem = (item: {
    icon: ComponentType<any>
    label: string
    path: string
    items?: Array<{ icon: React.ComponentType<any>; label: string; path: string }>
  }) =>
    item.items ? (
      <NavLink
        key={item.path}
        label={item.label}
        leftSection={<item.icon size={18} stroke={1.5} />}
        defaultOpened={isPathInGroup(item.items)}
        childrenOffset={28}
      >
        {item.items.map((child) => (
          <NavLink
            key={child.path}
            active={location.pathname === child.path}
            label={child.label}
            leftSection={<child.icon size={16} stroke={1.5} />}
            onClick={() => handleNavigate(child.path)}
          />
        ))}
      </NavLink>
    ) : (
      <NavLink
        key={item.path}
        active={location.pathname === item.path}
        label={item.label}
        leftSection={<item.icon size={18} stroke={1.5} />}
        onClick={() => handleNavigate(item.path)}
      />
    )

  return (
    <>
      <AppShell
        header={{ height: 60 }}
        padding="md"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between" wrap="nowrap">
            <Group gap="lg" wrap="nowrap">
              <Title order={3} visibleFrom="xs" style={{ whiteSpace: 'nowrap' }}>GTFS Tools</Title>
              <Title order={4} hiddenFrom="xs">GTFS</Title>

              {/* Desktop Navigation */}
              <Group gap="xs" visibleFrom="sm" wrap="nowrap">
                <UnstyledButton
                  onClick={() => handleNavigate('/')}
                  px="sm"
                  py="xs"
                  style={{
                    borderRadius: 'var(--mantine-radius-sm)',
                    backgroundColor: location.pathname === '/' ? 'var(--mantine-color-blue-light)' : 'transparent',
                    color: location.pathname === '/' ? 'var(--mantine-color-blue-filled)' : 'inherit',
                  }}
                >
                  <Text size="sm" fw={location.pathname === '/' ? 600 : 400}>{t('nav.dashboard')}</Text>
                </UnstyledButton>

                <UnstyledButton
                  onClick={() => handleNavigate('/map')}
                  px="sm"
                  py="xs"
                  style={{
                    borderRadius: 'var(--mantine-radius-sm)',
                    backgroundColor: location.pathname === '/map' ? 'var(--mantine-color-blue-light)' : 'transparent',
                    color: location.pathname === '/map' ? 'var(--mantine-color-blue-filled)' : 'inherit',
                  }}
                >
                  <Text size="sm" fw={location.pathname === '/map' ? 600 : 400}>{t('nav.map')}</Text>
                </UnstyledButton>

                {/* Agencies Menu */}
                <Menu shadow="md" width={200} position="bottom-start" zIndex={9999}>
                  <Menu.Target>
                    <UnstyledButton
                      px="sm"
                      py="xs"
                      style={{
                        borderRadius: 'var(--mantine-radius-sm)',
                        backgroundColor: location.pathname.startsWith('/agencies') ? 'var(--mantine-color-blue-light)' : 'transparent',
                        color: location.pathname.startsWith('/agencies') ? 'var(--mantine-color-blue-filled)' : 'inherit',
                      }}
                    >
                      <Group gap={4}>
                        <Text size="sm" fw={location.pathname.startsWith('/agencies') ? 600 : 400}>{t('nav.agencies')}</Text>
                        <IconChevronDown size={14} />
                      </Group>
                    </UnstyledButton>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item onClick={() => handleNavigate('/agencies')}>{t('nav.agencies')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/agencies/merge')}>{t('nav.mergeAgencies')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/agencies/split')}>{t('nav.splitAgency')}</Menu.Item>
                  </Menu.Dropdown>
                </Menu>

                {/* Feeds Menu */}
                <Menu shadow="md" width={200} position="bottom-start" zIndex={9999}>
                  <Menu.Target>
                    <UnstyledButton
                      px="sm"
                      py="xs"
                      style={{
                        borderRadius: 'var(--mantine-radius-sm)',
                        backgroundColor: (location.pathname.startsWith('/feeds') || location.pathname.startsWith('/routes') ||
                          location.pathname.startsWith('/stops') || location.pathname.startsWith('/trips') ||
                          location.pathname.startsWith('/stop-times') || location.pathname.startsWith('/calendars') ||
                          location.pathname.startsWith('/fare-'))
                          ? 'var(--mantine-color-blue-light)' : 'transparent',
                        color: (location.pathname.startsWith('/feeds') || location.pathname.startsWith('/routes') ||
                          location.pathname.startsWith('/stops') || location.pathname.startsWith('/trips') ||
                          location.pathname.startsWith('/stop-times') || location.pathname.startsWith('/calendars') ||
                          location.pathname.startsWith('/fare-'))
                          ? 'var(--mantine-color-blue-filled)' : 'inherit',
                      }}
                    >
                      <Group gap={4}>
                        <Text size="sm" fw={(location.pathname.startsWith('/feeds') || location.pathname.startsWith('/routes') ||
                          location.pathname.startsWith('/stops') || location.pathname.startsWith('/trips') ||
                          location.pathname.startsWith('/stop-times') || location.pathname.startsWith('/calendars') ||
                          location.pathname.startsWith('/fare-')) ? 600 : 400}>{t('nav.feeds')}</Text>
                        <IconChevronDown size={14} />
                      </Group>
                    </UnstyledButton>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item onClick={() => handleNavigate('/feeds')}>{t('nav.feeds')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/feeds/import')}>{t('nav.import')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/feeds/export')}>{t('nav.export')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/calendars')}>{t('nav.calendars')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/routes')}>{t('nav.routes')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/stops')}>{t('nav.stops')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/trips')}>{t('nav.trips')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/stop-times')}>{t('nav.stopTimes')}</Menu.Item>
                    <Menu.Divider />
                    <Menu.Item onClick={() => handleNavigate('/fare-attributes')}>{t('nav.fareAttributes')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/fare-rules')}>{t('nav.fareRules')}</Menu.Item>
                  </Menu.Dropdown>
                </Menu>

                <UnstyledButton
                  onClick={() => handleNavigate('/realtime')}
                  px="sm"
                  py="xs"
                  style={{
                    borderRadius: 'var(--mantine-radius-sm)',
                    backgroundColor: location.pathname === '/realtime' ? 'var(--mantine-color-blue-light)' : 'transparent',
                    color: location.pathname === '/realtime' ? 'var(--mantine-color-blue-filled)' : 'inherit',
                  }}
                >
                  <Text size="sm" fw={location.pathname === '/realtime' ? 600 : 400}>{t('nav.realtime')}</Text>
                </UnstyledButton>

                <UnstyledButton
                  onClick={() => handleNavigate('/tasks')}
                  px="sm"
                  py="xs"
                  style={{
                    borderRadius: 'var(--mantine-radius-sm)',
                    backgroundColor: location.pathname === '/tasks' ? 'var(--mantine-color-blue-light)' : 'transparent',
                    color: location.pathname === '/tasks' ? 'var(--mantine-color-blue-filled)' : 'inherit',
                    position: 'relative',
                  }}
                >
                  <Group gap={4}>
                    <Text size="sm" fw={location.pathname === '/tasks' ? 600 : 400}>{t('nav.tasks')}</Text>
                    {activeTaskCount > 0 && (
                      <Badge size="xs" variant="filled" color="blue">{activeTaskCount}</Badge>
                    )}
                  </Group>
                </UnstyledButton>

                {/* More Menu */}
                <Menu shadow="md" width={200} position="bottom-start" zIndex={9999}>
                  <Menu.Target>
                    <UnstyledButton px="sm" py="xs">
                      <Group gap={4}>
                        <Text size="sm">{t('nav.more')}</Text>
                        <IconChevronDown size={14} />
                      </Group>
                    </UnstyledButton>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item onClick={() => handleNavigate('/validation-settings')}>{t('nav.validationSettings')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/audit')}>{t('nav.auditLogs')}</Menu.Item>
                    <Menu.Divider />
                    <Menu.Item onClick={() => handleNavigate('/teams')}>{t('nav.teams')}</Menu.Item>
                    <Menu.Item onClick={() => handleNavigate('/settings')}>{t('nav.settings')}</Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              </Group>
            </Group>

            <Group gap="sm">
              <LanguageSwitcher />

              <ActionIcon
                onClick={() => setColorScheme(colorScheme === 'dark' ? 'light' : 'dark')}
                variant="subtle"
                size="lg"
                aria-label="Toggle color scheme"
              >
                {colorScheme === 'dark' ? (
                  <IconSun style={{ width: rem(20), height: rem(20) }} />
                ) : (
                  <IconMoon style={{ width: rem(20), height: rem(20) }} />
                )}
              </ActionIcon>

              <Menu shadow="md" width={200} position="bottom-end" zIndex={9999}>
                <Menu.Target>
                  <UnstyledButton>
                    <Group gap="xs">
                      <Avatar color="blue" radius="xl" size="sm">
                        {user?.full_name?.[0] || user?.email?.[0] || '?'}
                      </Avatar>
                      <Box visibleFrom="sm">
                        <Text size="sm" fw={500}>
                          {user?.full_name || user?.email}
                        </Text>
                        <Text c="dimmed" size="xs">
                          {user?.is_superuser ? 'Admin' : 'User'}
                        </Text>
                      </Box>
                      <IconChevronDown style={{ width: rem(16), height: rem(16) }} />
                    </Group>
                  </UnstyledButton>
                </Menu.Target>

                <Menu.Dropdown>
                  <Menu.Label>{t('settings.profile')}</Menu.Label>
                  {isTeamSubdomain ? (
                    <Menu.Item
                      leftSection={<IconArrowBack style={{ width: rem(14), height: rem(14) }} />}
                      onClick={handleReturnToPortal}
                    >
                      {t('nav.returnToPortal')}
                    </Menu.Item>
                  ) : (
                    <Menu.Item
                      leftSection={<IconLogout style={{ width: rem(14), height: rem(14) }} />}
                      onClick={handleLogout}
                      color="red"
                    >
                      {t('nav.logout')}
                    </Menu.Item>
                  )}
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Main style={isMobile ? { paddingBottom: 80 } : undefined}>
          {children}
        </AppShell.Main>
      </AppShell>

      {/* Mobile Drawer for grouped navigation */}
      <Drawer
        opened={drawerOpened}
        onClose={closeDrawer}
        title={
          <Group gap="xs">
            <Avatar color="blue" radius="xl" size="sm">
              {user?.full_name?.[0] || user?.email?.[0] || '?'}
            </Avatar>
            <div>
              <Text size="sm" fw={500}>
                {user?.full_name || user?.email}
              </Text>
              <Text c="dimmed" size="xs">
                {user?.is_superuser ? 'Admin' : 'User'}
              </Text>
            </div>
          </Group>
        }
        position="bottom"
        size="75%"
        radius="lg"
        styles={{
          content: {
            borderTopLeftRadius: 'var(--mantine-radius-lg)',
            borderTopRightRadius: 'var(--mantine-radius-lg)',
          },
          body: {
            paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 80px)',
          },
        }}
      >
        <ScrollArea h="100%">
          <Stack gap="xs">
            {navGroups.map((group, index) => (
              'items' in group && group.items ? (
                <NavLink
                  key={index}
                  label={group.label}
                  leftSection={<group.icon size={20} stroke={1.5} />}
                  defaultOpened={isPathInGroup(group.items)}
                  childrenOffset={28}
                >
                  {group.items.map((item) => renderNestedNavItem(item))}
                </NavLink>
              ) : (
                <NavLink
                  key={group.path}
                  active={location.pathname === group.path}
                  label={group.label}
                  leftSection={<group.icon size={20} stroke={1.5} />}
                  rightSection={
                    group.badge && group.badge > 0 ? (
                      <Badge size="sm" variant="filled" color="blue">
                        {group.badge}
                      </Badge>
                    ) : undefined
                  }
                  onClick={() => handleNavigate(group.path!)}
                />
              )
            ))}

            <Divider my="sm" />

            {isTeamSubdomain ? (
              <NavLink
                label={t('nav.returnToPortal')}
                leftSection={<IconArrowBack size={20} stroke={1.5} />}
                onClick={handleReturnToPortal}
              />
            ) : (
              <NavLink
                label={t('nav.logout')}
                leftSection={<IconLogout size={20} stroke={1.5} />}
                color="red"
                onClick={handleLogout}
              />
            )}
          </Stack>
        </ScrollArea>
      </Drawer>

      {/* Bottom navigation for mobile */}
      <BottomNavigation onMoreClick={openDrawer} />
    </>
  )
}
