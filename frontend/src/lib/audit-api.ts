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

export interface AuditLog {
  id: number
  user_id: number
  agency_id: number | null
  action: string
  entity_type: string
  entity_id: string
  description: string | null
  old_values: Record<string, any> | null
  new_values: Record<string, any> | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
  updated_at: string
}

export interface AuditLogList {
  items: AuditLog[]
  total: number
  skip: number
  limit: number
}

export interface AuditLogStats {
  total_logs: number
  action_counts: Record<string, number>
  entity_type_counts: Record<string, number>
}

export interface AuditLogFilters {
  skip?: number
  limit?: number
  agency_id?: number
  user_id?: number
  action?: string
  entity_type?: string
}

export const auditApi = {
  // List audit logs with filters
  list: async (filters?: AuditLogFilters): Promise<AuditLogList> => {
    const response = await api.get('/audit/', {
      params: filters,
    })
    return response.data
  },

  // Get audit log by ID
  get: async (id: number): Promise<AuditLog> => {
    const response = await api.get(`/audit/${id}/`)
    return response.data
  },

  // Get audit log statistics
  getStats: async (agencyId?: number): Promise<AuditLogStats> => {
    const response = await api.get('/audit/stats', {
      params: agencyId ? { agency_id: agencyId } : undefined,
    })
    return response.data
  },
}
