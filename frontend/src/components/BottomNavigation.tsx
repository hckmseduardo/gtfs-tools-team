import { Box, UnstyledButton, Text, Badge, rem } from '@mantine/core'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  IconHome,
  IconMap2,
  IconRoute,
  IconMapPin,
  IconDotsVertical,
} from '@tabler/icons-react'
import classes from './BottomNavigation.module.css'

interface BottomNavItemProps {
  icon: React.ElementType
  label: string
  path: string
  active: boolean
  onClick: () => void
  badge?: number
}

function BottomNavItem({ icon: Icon, label, active, onClick, badge }: BottomNavItemProps) {
  return (
    <UnstyledButton className={classes.navItem} onClick={onClick} data-active={active || undefined}>
      <Box className={classes.iconWrapper}>
        <Icon style={{ width: rem(24), height: rem(24) }} stroke={1.5} />
        {badge && badge > 0 && (
          <Badge size="xs" variant="filled" color="red" className={classes.badge}>
            {badge > 99 ? '99+' : badge}
          </Badge>
        )}
      </Box>
      <Text size="xs" className={classes.label}>
        {label}
      </Text>
    </UnstyledButton>
  )
}

interface BottomNavigationProps {
  onMoreClick: () => void
}

export function BottomNavigation({ onMoreClick }: BottomNavigationProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()

  const mainNavItems = [
    { icon: IconHome, label: t('nav.dashboard'), path: '/' },
    { icon: IconMap2, label: t('nav.map'), path: '/map' },
    { icon: IconRoute, label: t('nav.routes'), path: '/routes' },
    { icon: IconMapPin, label: t('nav.stops'), path: '/stops' },
  ]

  const isMoreActive = !['/','','/map', '/routes', '/stops'].includes(location.pathname)

  return (
    <Box className={classes.container}>
      <Box className={classes.navigation}>
        {mainNavItems.map((item) => (
          <BottomNavItem
            key={item.path}
            icon={item.icon}
            label={item.label}
            path={item.path}
            active={location.pathname === item.path}
            onClick={() => navigate(item.path)}
          />
        ))}
        <BottomNavItem
          icon={IconDotsVertical}
          label={t('nav.more')}
          path="/more"
          active={isMoreActive}
          onClick={onMoreClick}
        />
      </Box>
    </Box>
  )
}
