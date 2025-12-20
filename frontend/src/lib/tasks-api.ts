/**
 * Tasks API client
 */

import { api } from './api'

export enum TaskStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

export enum TaskType {
  IMPORT_GTFS = 'import_gtfs',
  EXPORT_GTFS = 'export_gtfs',
  VALIDATE_GTFS = 'validate_gtfs',
  BULK_UPDATE = 'bulk_update',
  BULK_DELETE = 'bulk_delete',
  DELETE_FEED = 'delete_feed',
  CLONE_FEED = 'clone_feed',
  DELETE_AGENCY = 'delete_agency',
  MERGE_AGENCIES = 'merge_agencies',
  SPLIT_AGENCY = 'split_agency',
  ROUTE_EXPORT = 'route_export',
}

export interface Task {
  id: number
  celery_task_id: string
  task_name: string
  description?: string
  task_type: TaskType
  user_id: number
  agency_id?: number
  status: TaskStatus
  progress: number
  started_at?: string
  completed_at?: string
  error_message?: string
  input_data?: Record<string, any>
  result_data?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface TaskListResponse {
  items: Task[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface TaskFilters {
  skip?: number
  limit?: number
  status?: TaskStatus
  task_type?: TaskType
  agency_id?: number
}

export const tasksApi = {
  /**
   * List tasks
   */
  list: async (filters: TaskFilters = {}): Promise<TaskListResponse> => {
    const response = await api.get('/tasks/', { params: filters })
    return response.data
  },

  /**
   * Get task by ID
   */
  get: async (taskId: number): Promise<Task> => {
    const response = await api.get(`/tasks/${taskId}`)
    return response.data
  },

  /**
   * Cancel a task
   */
  cancel: async (taskId: number): Promise<void> => {
    await api.delete(`/tasks/${taskId}`)
  },

  /**
   * Get active task count
   */
  getActiveCount: async (): Promise<{ active_tasks: number }> => {
    const response = await api.get('/tasks/active/count')
    return response.data
  },

  /**
   * Retry a failed task
   */
  retry: async (taskId: number): Promise<Task> => {
    const response = await api.post(`/tasks/${taskId}/retry`)
    return response.data
  },
}
