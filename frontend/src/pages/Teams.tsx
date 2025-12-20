import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
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
  Box,
  SimpleGrid,
  Avatar,
  Menu,
  Tabs,
  LoadingOverlay,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDisclosure } from '@mantine/hooks'
import {
  IconEdit,
  IconTrash,
  IconUsers,
  IconUserPlus,
  IconCrown,
  IconUser,
  IconDotsVertical,
  IconRefresh,
  IconMail,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { useTranslation } from 'react-i18next'

// Helper to get auth headers
const getAuthHeaders = (): HeadersInit => {
  const token = localStorage.getItem('access_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
}

// API functions (will call the team's backend)
const teamMembersApi = {
  list: async (includeInactive = false) => {
    const response = await fetch(`/api/v1/team/members?include_inactive=${includeInactive}`, {
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to fetch members')
    return response.json()
  },
  update: async (memberId: string, data: { role?: string; is_active?: boolean }) => {
    const response = await fetch(`/api/v1/team/members/${memberId}`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify(data)
    })
    if (!response.ok) throw new Error('Failed to update member')
    return response.json()
  },
  remove: async (memberId: string) => {
    const response = await fetch(`/api/v1/team/members/${memberId}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to remove member')
  },
  listInvitations: async () => {
    const response = await fetch('/api/v1/team/invitations', {
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to fetch invitations')
    return response.json()
  },
  createInvitation: async (data: { email: string; role: string; message?: string }) => {
    const response = await fetch('/api/v1/team/invitations', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data)
    })
    if (!response.ok) throw new Error('Failed to create invitation')
    return response.json()
  },
  resendInvitation: async (invitationId: string) => {
    const response = await fetch(`/api/v1/team/invitations/${invitationId}/resend`, {
      method: 'POST',
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to resend invitation')
    return response.json()
  },
  cancelInvitation: async (invitationId: string) => {
    const response = await fetch(`/api/v1/team/invitations/${invitationId}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    })
    if (!response.ok) throw new Error('Failed to cancel invitation')
  }
}

interface TeamMember {
  id: string
  email: string
  name: string
  role: 'owner' | 'admin' | 'editor' | 'viewer'
  is_active: boolean
  avatar_url?: string
  created_at: string
  last_seen?: string
}

interface Invitation {
  id: string
  email: string
  role: string
  status: 'pending' | 'accepted' | 'cancelled' | 'expired'
  created_at: string
  expires_at: string
}

type TeamRole = 'owner' | 'admin' | 'editor' | 'viewer'

const getRoleIcon = (role: TeamRole) => {
  switch (role) {
    case 'owner':
      return IconCrown
    case 'admin':
      return IconUsers
    case 'editor':
      return IconEdit
    case 'viewer':
      return IconUser
    default:
      return IconUser
  }
}

const getRoleColor = (role: TeamRole) => {
  switch (role) {
    case 'owner':
      return 'yellow'
    case 'admin':
      return 'orange'
    case 'editor':
      return 'blue'
    case 'viewer':
      return 'gray'
    default:
      return 'gray'
  }
}

export default function Teams() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { user: currentUser } = useAuthStore()
  const [activeTab, setActiveTab] = useState<string | null>('members')
  const [inviteModalOpened, { open: openInviteModal, close: closeInviteModal }] = useDisclosure(false)
  const [editModalOpened, { open: openEditModal, close: closeEditModal }] = useDisclosure(false)
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null)

  const inviteForm = useForm({
    initialValues: {
      email: '',
      role: 'editor' as TeamRole,
      message: '',
    },
    validate: {
      email: (value) => {
        if (!value) return t('teams.emailRequired')
        if (!/^\S+@\S+$/.test(value)) return t('teams.emailInvalid')
        return null
      },
    },
  })

  const editForm = useForm({
    initialValues: {
      role: 'editor' as TeamRole,
    },
  })

  const { data: membersData, isLoading: membersLoading } = useQuery({
    queryKey: ['team-members'],
    queryFn: () => teamMembersApi.list(false),
    retry: false,
  })

  const { data: invitationsData } = useQuery({
    queryKey: ['team-invitations'],
    queryFn: teamMembersApi.listInvitations,
    retry: false,
  })

  const inviteMutation = useMutation({
    mutationFn: teamMembersApi.createInvitation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      closeInviteModal()
      inviteForm.reset()
      notifications.show({
        title: t('common.success'),
        message: t('teams.invitationSent'),
        color: 'green',
      })
    },
    onError: () => {
      notifications.show({
        title: t('common.error'),
        message: t('teams.inviteError'),
        color: 'red',
      })
    },
  })

  const updateMemberMutation = useMutation({
    mutationFn: ({ memberId, data }: { memberId: string; data: { role?: string; is_active?: boolean } }) =>
      teamMembersApi.update(memberId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      closeEditModal()
      setSelectedMember(null)
      notifications.show({
        title: t('common.success'),
        message: t('teams.roleUpdated'),
        color: 'green',
      })
    },
    onError: () => {
      notifications.show({
        title: t('common.error'),
        message: t('teams.updateError'),
        color: 'red',
      })
    },
  })

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: string) => teamMembersApi.remove(memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      notifications.show({
        title: t('common.success'),
        message: t('teams.memberRemoved'),
        color: 'green',
      })
    },
    onError: () => {
      notifications.show({
        title: t('common.error'),
        message: t('teams.removeError'),
        color: 'red',
      })
    },
  })

  const resendInvitationMutation = useMutation({
    mutationFn: teamMembersApi.resendInvitation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      notifications.show({
        title: t('common.success'),
        message: t('teams.invitationSent'),
        color: 'green',
      })
    },
  })

  const cancelInvitationMutation = useMutation({
    mutationFn: teamMembersApi.cancelInvitation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      notifications.show({
        title: t('common.success'),
        message: t('teams.invitationRevoked'),
        color: 'green',
      })
    },
  })

  const members: TeamMember[] = membersData?.members || []
  const invitations: Invitation[] = invitationsData?.invitations || []
  const pendingInvitations = invitations.filter(i => i.status === 'pending')

  // Find current user's role from members list
  const currentUserRole = useMemo(() => {
    if (!currentUser?.email) return null
    const currentMember = members.find(m => m.email === currentUser.email)
    return currentMember?.role || null
  }, [members, currentUser?.email])

  // Permission helpers
  // Owner: can edit/delete others except themselves
  // Admin: can edit/delete others except owners and themselves
  // Editor/Viewer: cannot edit/delete anyone
  const canEditMember = (targetMember: TeamMember): boolean => {
    if (!currentUserRole) return false
    // Cannot edit yourself
    if (targetMember.email === currentUser?.email) return false

    if (currentUserRole === 'owner') {
      return true
    }
    if (currentUserRole === 'admin') {
      // Admin cannot edit owners
      return targetMember.role !== 'owner'
    }
    return false
  }

  const canDeleteMember = (targetMember: TeamMember): boolean => {
    if (!currentUserRole) return false
    // Cannot delete yourself
    if (targetMember.email === currentUser?.email) return false

    if (currentUserRole === 'owner') {
      return true
    }
    if (currentUserRole === 'admin') {
      // Admin cannot delete owners
      return targetMember.role !== 'owner'
    }
    return false
  }

  // Check if current user can invite members (owners and admins can invite)
  const canInviteMembers = currentUserRole === 'owner' || currentUserRole === 'admin'

  const handleOpenEditMember = (member: TeamMember) => {
    setSelectedMember(member)
    editForm.setFieldValue('role', member.role)
    openEditModal()
  }

  const handleRemoveMember = (member: TeamMember) => {
    if (window.confirm(t('teams.removeMemberMessage', { email: member.email }))) {
      removeMemberMutation.mutate(member.id)
    }
  }

  return (
    <Container size="lg" py="xl">
      <LoadingOverlay visible={membersLoading} />

      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between">
          <Box>
            <Title order={1}>{t('teams.title')}</Title>
            <Text c="dimmed">{t('teams.description')}</Text>
          </Box>
          <Group>
            <Button
              leftSection={<IconRefresh size={16} />}
              variant="light"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['team-members'] })}
            >
              {t('common.refresh')}
            </Button>
            {canInviteMembers && (
              <Button leftSection={<IconUserPlus size={16} />} onClick={openInviteModal}>
                {t('teams.inviteMember')}
              </Button>
            )}
          </Group>
        </Group>

        {/* Stats */}
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
          <Paper withBorder p="md">
            <Text size="sm" c="dimmed">{t('teams.members')}</Text>
            <Text size="xl" fw={700}>{membersData?.count || 0}</Text>
          </Paper>
          <Paper withBorder p="md">
            <Text size="sm" c="dimmed">{t('teams.roles.owner')}</Text>
            <Text size="xl" fw={700} c="yellow">{membersData?.by_role?.owners || 0}</Text>
          </Paper>
          <Paper withBorder p="md">
            <Text size="sm" c="dimmed">{t('teams.roles.editor')}</Text>
            <Text size="xl" fw={700} c="blue">{membersData?.by_role?.editors || 0}</Text>
          </Paper>
          <Paper withBorder p="md">
            <Text size="sm" c="dimmed">{t('teams.invitations')}</Text>
            <Text size="xl" fw={700} c="orange">{pendingInvitations.length}</Text>
          </Paper>
        </SimpleGrid>

        {/* Tabs */}
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="members" leftSection={<IconUsers size={16} />}>
              {t('teams.members')} ({members.length})
            </Tabs.Tab>
            <Tabs.Tab value="invitations" leftSection={<IconMail size={16} />}>
              {t('teams.invitations')} ({pendingInvitations.length})
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="members" pt="md">
            <Stack gap="md">
              {/* Members Table */}
              <Paper withBorder>
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('teams.member')}</Table.Th>
                      <Table.Th>{t('teams.role')}</Table.Th>
                      <Table.Th>{t('common.status')}</Table.Th>
                      <Table.Th style={{ width: 80 }}>{t('common.actions')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {members.length === 0 ? (
                      <Table.Tr>
                        <Table.Td colSpan={4}>
                          <Text ta="center" c="dimmed" py="xl">
                            {t('teams.noMembers') || 'No members found'}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ) : (
                      members.map((member) => {
                        const RoleIcon = getRoleIcon(member.role)
                        return (
                          <Table.Tr key={member.id} style={{ opacity: member.is_active ? 1 : 0.5 }}>
                            <Table.Td>
                              <Group gap="sm">
                                <Avatar size="sm" radius="xl">
                                  {member.name?.charAt(0).toUpperCase() || '?'}
                                </Avatar>
                                <Box>
                                  <Text size="sm" fw={500}>{member.name}</Text>
                                  <Text size="xs" c="dimmed">{member.email}</Text>
                                </Box>
                              </Group>
                            </Table.Td>
                            <Table.Td>
                              <Badge
                                color={getRoleColor(member.role)}
                                leftSection={<RoleIcon size={12} />}
                              >
                                {t(`teams.roles.${member.role}`)}
                              </Badge>
                            </Table.Td>
                            <Table.Td>
                              <Badge
                                color={member.is_active ? 'green' : 'red'}
                                variant="light"
                              >
                                {member.is_active ? t('common.active') : t('common.inactive')}
                              </Badge>
                            </Table.Td>
                            <Table.Td>
                              {(canEditMember(member) || canDeleteMember(member)) ? (
                                <Menu withinPortal position="bottom-end">
                                  <Menu.Target>
                                    <ActionIcon variant="subtle">
                                      <IconDotsVertical size={16} />
                                    </ActionIcon>
                                  </Menu.Target>
                                  <Menu.Dropdown>
                                    {canEditMember(member) && (
                                      <Menu.Item
                                        leftSection={<IconEdit size={14} />}
                                        onClick={() => handleOpenEditMember(member)}
                                      >
                                        {t('common.edit')}
                                      </Menu.Item>
                                    )}
                                    {canDeleteMember(member) && (
                                      <Menu.Item
                                        leftSection={<IconTrash size={14} />}
                                        color="red"
                                        onClick={() => handleRemoveMember(member)}
                                      >
                                        {t('teams.removeMember')}
                                      </Menu.Item>
                                    )}
                                  </Menu.Dropdown>
                                </Menu>
                              ) : null}
                            </Table.Td>
                          </Table.Tr>
                        )
                      })
                    )}
                  </Table.Tbody>
                </Table>
              </Paper>
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="invitations" pt="md">
            <Paper withBorder>
              {pendingInvitations.length === 0 ? (
                <Text ta="center" c="dimmed" py="xl">
                  {t('teams.noInvitations')}
                </Text>
              ) : (
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('teams.email')}</Table.Th>
                      <Table.Th>{t('teams.role')}</Table.Th>
                      <Table.Th>{t('teams.sentAt') || 'Sent'}</Table.Th>
                      <Table.Th>{t('teams.expiresAt') || 'Expires'}</Table.Th>
                      <Table.Th style={{ width: 150 }}>{t('common.actions')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {pendingInvitations.map((invitation) => (
                      <Table.Tr key={invitation.id}>
                        <Table.Td>{invitation.email}</Table.Td>
                        <Table.Td>
                          <Badge color={getRoleColor(invitation.role as TeamRole)}>
                            {t(`teams.roles.${invitation.role}`)}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{new Date(invitation.created_at).toLocaleDateString()}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{new Date(invitation.expires_at).toLocaleDateString()}</Text>
                        </Table.Td>
                        <Table.Td>
                          {canInviteMembers && (
                            <Group gap="xs">
                              <Button
                                size="xs"
                                variant="light"
                                onClick={() => resendInvitationMutation.mutate(invitation.id)}
                                loading={resendInvitationMutation.isPending}
                              >
                                {t('teams.resend') || 'Resend'}
                              </Button>
                              <Button
                                size="xs"
                                variant="light"
                                color="red"
                                onClick={() => cancelInvitationMutation.mutate(invitation.id)}
                                loading={cancelInvitationMutation.isPending}
                              >
                                {t('common.cancel')}
                              </Button>
                            </Group>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Paper>
          </Tabs.Panel>
        </Tabs>
      </Stack>

      {/* Invite Modal */}
      <Modal
        opened={inviteModalOpened}
        onClose={closeInviteModal}
        title={t('teams.inviteMember')}
        size="md"
      >
        <form onSubmit={inviteForm.onSubmit((values) => inviteMutation.mutate(values))}>
          <Stack gap="md">
            <TextInput
              label={t('teams.email')}
              placeholder={t('teams.emailPlaceholder')}
              required
              {...inviteForm.getInputProps('email')}
            />
            <Select
              label={t('teams.role')}
              data={[
                { value: 'viewer', label: t('teams.roles.viewer') },
                { value: 'editor', label: t('teams.roles.editor') },
                { value: 'admin', label: t('teams.roles.admin') },
                { value: 'owner', label: t('teams.roles.owner') },
              ]}
              {...inviteForm.getInputProps('role')}
            />
            <TextInput
              label={t('teams.message') || 'Message (optional)'}
              placeholder={t('teams.messagePlaceholder') || 'Add a personal message...'}
              {...inviteForm.getInputProps('message')}
            />
            <Group justify="flex-end">
              <Button variant="light" onClick={closeInviteModal}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" loading={inviteMutation.isPending}>
                {t('teams.sendInvitation')}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Edit Member Modal */}
      <Modal
        opened={editModalOpened}
        onClose={closeEditModal}
        title={t('teams.editMember') || 'Edit Member'}
        size="md"
      >
        {selectedMember && (
          <form onSubmit={editForm.onSubmit((values) =>
            updateMemberMutation.mutate({ memberId: selectedMember.id, data: values })
          )}>
            <Stack gap="md">
              {/* Member info */}
              <Group gap="sm" pb="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
                <Avatar size="lg" radius="xl">
                  {selectedMember.name?.charAt(0).toUpperCase() || '?'}
                </Avatar>
                <Box>
                  <Text fw={500}>{selectedMember.name}</Text>
                  <Text size="sm" c="dimmed">{selectedMember.email}</Text>
                </Box>
              </Group>

              <Select
                label={t('teams.role')}
                data={[
                  { value: 'owner', label: t('teams.roles.owner'), disabled: currentUserRole === 'admin' },
                  { value: 'admin', label: t('teams.roles.admin') },
                  { value: 'editor', label: t('teams.roles.editor') },
                  { value: 'viewer', label: t('teams.roles.viewer') },
                ]}
                disabled={currentUserRole === 'admin' && selectedMember.role === 'owner'}
                {...editForm.getInputProps('role')}
              />

              {currentUserRole === 'admin' && selectedMember.role === 'owner' && (
                <Text size="sm" c="dimmed">
                  {t('teams.cannotEditOwnerAsAdmin') || 'Admins cannot change owner roles.'}
                </Text>
              )}

              {!selectedMember.is_active && (
                <Button
                  color="green"
                  onClick={() => updateMemberMutation.mutate({
                    memberId: selectedMember.id,
                    data: { is_active: true }
                  })}
                >
                  {t('teams.reactivateMember') || 'Reactivate Member'}
                </Button>
              )}

              <Group justify="flex-end">
                <Button variant="light" onClick={closeEditModal}>
                  {t('common.cancel')}
                </Button>
                <Button
                  type="submit"
                  loading={updateMemberMutation.isPending}
                  disabled={currentUserRole === 'admin' && selectedMember.role === 'owner'}
                >
                  {t('common.save')}
                </Button>
              </Group>
            </Stack>
          </form>
        )}
      </Modal>
    </Container>
  )
}
