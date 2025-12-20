import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

// Create axios instance with auth token
const api = axios.create({
  baseURL: API_URL,
})

// Add auth token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ==================== Types ====================

export type TeamRole = 'owner' | 'editor' | 'viewer'
export type InvitationStatus = 'pending' | 'accepted' | 'declined' | 'expired'

export interface Team {
  id: number
  name: string
  slug: string
  description: string | null
  is_active: boolean
  created_by_id: number | null
  created_at: string
  updated_at: string
}

export interface TeamMember {
  id: number
  team_id: number
  user_id: number
  role: TeamRole
  email: string
  full_name: string
  created_at: string
}

export interface TeamMemberInfo {
  id: number
  user_id: number
  email: string
  full_name: string
  role: TeamRole
}

export interface WorkspaceSummary {
  id: number
  name: string
  slug: string
  is_active: boolean
  agency_count: number
}

export interface TeamWithDetails extends Team {
  members: TeamMemberInfo[]
  workspaces: WorkspaceSummary[]
  member_count: number
  workspace_count: number
}

export interface TeamList {
  items: Team[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface TeamMemberList {
  items: TeamMember[]
  total: number
}

export interface TeamCreate {
  name: string
  slug: string
  description?: string
}

export interface TeamUpdate {
  name?: string
  slug?: string
  description?: string
  is_active?: boolean
}

export interface TeamMemberCreate {
  user_id: number
  role: TeamRole
}

export interface TeamMemberUpdate {
  role: TeamRole
}

// ==================== Workspace Types ====================

export interface Workspace {
  id: number
  team_id: number
  name: string
  slug: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AgencySummary {
  id: number
  name: string
  slug: string
  is_active: boolean
}

export interface WorkspaceWithDetails extends Workspace {
  agencies: AgencySummary[]
  agency_count: number
}

export interface WorkspaceList {
  items: Workspace[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface WorkspaceCreate {
  name: string
  slug: string
  description?: string
}

export interface WorkspaceUpdate {
  name?: string
  slug?: string
  description?: string
  is_active?: boolean
}

// ==================== Invitation Types ====================

export interface TeamInvitation {
  id: number
  team_id: number
  email: string
  role: TeamRole
  status: InvitationStatus
  invited_by_id: number | null
  invited_by_name: string | null
  expires_at: string
  created_at: string
}

export interface TeamInvitationList {
  items: TeamInvitation[]
  total: number
}

export interface TeamInvitationCreate {
  email: string
  role: TeamRole
}

export interface TeamInvitationPublic {
  email: string
  role: TeamRole
  team_name: string
  team_slug: string
  invited_by_name: string | null
  expires_at: string
}

// ==================== Filter Types ====================

export interface TeamFilters {
  skip?: number
  limit?: number
  search?: string
  is_active?: boolean
}

export interface WorkspaceFilters {
  skip?: number
  limit?: number
  team_id?: number
  search?: string
  is_active?: boolean
}

// ==================== Teams API ====================

export const teamsApi = {
  // List teams
  list: async (filters?: TeamFilters): Promise<TeamList> => {
    const response = await api.get('/teams/', { params: filters })
    return response.data
  },

  // Get team by ID
  get: async (teamId: number): Promise<TeamWithDetails> => {
    const response = await api.get(`/teams/${teamId}`)
    return response.data
  },

  // Create team
  create: async (data: TeamCreate): Promise<TeamWithDetails> => {
    const response = await api.post('/teams/', data)
    return response.data
  },

  // Update team
  update: async (teamId: number, data: TeamUpdate): Promise<Team> => {
    const response = await api.patch(`/teams/${teamId}`, data)
    return response.data
  },

  // Delete team
  delete: async (teamId: number): Promise<void> => {
    await api.delete(`/teams/${teamId}`)
  },

  // ==================== Team Members ====================

  // List team members
  listMembers: async (teamId: number): Promise<TeamMemberList> => {
    const response = await api.get(`/teams/${teamId}/members`)
    return response.data
  },

  // Add team member
  addMember: async (teamId: number, data: TeamMemberCreate): Promise<TeamMember> => {
    const response = await api.post(`/teams/${teamId}/members`, data)
    return response.data
  },

  // Update team member role
  updateMember: async (teamId: number, userId: number, data: TeamMemberUpdate): Promise<TeamMember> => {
    const response = await api.patch(`/teams/${teamId}/members/${userId}`, data)
    return response.data
  },

  // Remove team member
  removeMember: async (teamId: number, userId: number): Promise<void> => {
    await api.delete(`/teams/${teamId}/members/${userId}`)
  },

  // ==================== Team Invitations ====================

  // List team invitations
  listInvitations: async (teamId: number, status?: InvitationStatus): Promise<TeamInvitationList> => {
    const response = await api.get(`/teams/${teamId}/invitations`, {
      params: status ? { status_filter: status } : undefined,
    })
    return response.data
  },

  // Create invitation
  createInvitation: async (teamId: number, data: TeamInvitationCreate): Promise<TeamInvitation> => {
    const response = await api.post(`/teams/${teamId}/invitations`, data)
    return response.data
  },

  // Revoke invitation
  revokeInvitation: async (teamId: number, invitationId: number): Promise<void> => {
    await api.delete(`/teams/${teamId}/invitations/${invitationId}`)
  },

  // Get invitation by token (public - for join page)
  getInvitationByToken: async (token: string): Promise<TeamInvitationPublic> => {
    const response = await api.get('/team/invitations/by-token', { params: { token } })
    return response.data
  },

  // Exchange portal SSO token for user info (public - no auth required)
  exchangeSSOToken: async (ssoToken: string): Promise<{
    user: {
      id: string
      email: string
      display_name: string | null
      avatar_url: string | null
    }
  }> => {
    const response = await api.post('/team/auth/exchange', null, { params: { token: ssoToken } })
    return response.data
  },

  // Accept invitation (join team) - passes user details from SSO exchange
  acceptInvitation: async (
    token: string,
    userId?: string,
    userName?: string,
    userEmail?: string
  ): Promise<{ message: string; member: TeamMember }> => {
    const response = await api.post('/team/join', null, {
      params: {
        token,
        user_id: userId,
        user_name: userName,
        user_email: userEmail,
      },
    })
    return response.data
  },
}

// ==================== Workspaces API ====================

export const workspacesApi = {
  // List workspaces
  list: async (filters?: WorkspaceFilters): Promise<WorkspaceList> => {
    const response = await api.get('/workspaces/', { params: filters })
    return response.data
  },

  // Get workspace by ID
  get: async (workspaceId: number): Promise<WorkspaceWithDetails> => {
    const response = await api.get(`/workspaces/${workspaceId}`)
    return response.data
  },

  // Create workspace
  create: async (teamId: number, data: WorkspaceCreate): Promise<WorkspaceWithDetails> => {
    const response = await api.post('/workspaces/', data, {
      params: { team_id: teamId },
    })
    return response.data
  },

  // Update workspace
  update: async (workspaceId: number, data: WorkspaceUpdate): Promise<Workspace> => {
    const response = await api.patch(`/workspaces/${workspaceId}`, data)
    return response.data
  },

  // Delete workspace
  delete: async (workspaceId: number): Promise<void> => {
    await api.delete(`/workspaces/${workspaceId}`)
  },

  // ==================== Workspace Agencies ====================

  // List workspace agencies
  listAgencies: async (workspaceId: number): Promise<AgencySummary[]> => {
    const response = await api.get(`/workspaces/${workspaceId}/agencies`)
    return response.data
  },

  // Add agency to workspace
  addAgency: async (workspaceId: number, agencyId: number): Promise<{ message: string }> => {
    const response = await api.post(`/workspaces/${workspaceId}/agencies`, {
      agency_id: agencyId,
    })
    return response.data
  },

  // Remove agency from workspace
  removeAgency: async (workspaceId: number, agencyId: number): Promise<void> => {
    await api.delete(`/workspaces/${workspaceId}/agencies/${agencyId}`)
  },

  // ==================== Workspace Members ====================

  // List workspace members
  listMembers: async (workspaceId: number): Promise<{ id: number; email: string; full_name: string }[]> => {
    const response = await api.get(`/workspaces/${workspaceId}/members`)
    return response.data
  },

  // Add member to workspace
  addMember: async (workspaceId: number, userId: number): Promise<{ message: string }> => {
    const response = await api.post(`/workspaces/${workspaceId}/members`, null, {
      params: { user_id: userId },
    })
    return response.data
  },

  // Remove member from workspace
  removeMember: async (workspaceId: number, userId: number): Promise<void> => {
    await api.delete(`/workspaces/${workspaceId}/members/${userId}`)
  },
}
