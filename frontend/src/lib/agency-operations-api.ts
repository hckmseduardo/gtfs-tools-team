import api from './api'

export interface AgencyMergeRequest {
  source_feed_ids: number[]
  target_agency_id?: number
  create_new_agency: boolean
  new_agency_name?: string
  new_agency_description?: string
  merge_strategy: 'fail_on_conflict' | 'auto_prefix'
  feed_name: string
  feed_description?: string
  activate_on_success: boolean
}

export interface FeedEntityCounts {
  feed_id: number
  feed_name: string
  agency_id: number
  agency_name: string
  routes: number
  trips: number
  stops: number
  stop_times: number
  shapes: number
  calendars: number
  calendar_dates: number
  fare_attributes: number
  fare_rules: number
}

export interface AgencyMergeValidationResult {
  valid: boolean
  conflicts: IDConflict[]
  feed_counts: FeedEntityCounts[]
  total_routes: number
  total_trips: number
  total_stops: number
  total_stop_times: number
  total_shapes: number
  total_calendars: number
  total_calendar_dates: number
  total_fare_attributes: number
  total_fare_rules: number
  warnings: string[]
  errors: string[]
}

export interface IDConflict {
  entity_type: string
  conflicting_id: string
  source_agencies: number[]
  count: number
}

export interface AgencyMergeResponse {
  task_id: string
  new_agency_id?: number
  status: string
  message: string
  validation_result: AgencyMergeValidationResult | null
}

export interface AgencySplitRequest {
  feed_id: number
  route_ids: string[]
  new_agency_name: string
  new_agency_description?: string
  new_feed_name: string
  copy_users: boolean
  remove_from_source: boolean
}

export interface AgencySplitDependencies {
  routes: string[]
  trips: number
  stops: number
  stop_times: number
  calendars: number
  calendar_dates: number
  shapes: number
  shared_stops: number
}

export interface AgencySplitResponse {
  task_id: string
  new_agency_id: number
  new_feed_id: number
  status: string
  message: string
  dependencies: AgencySplitDependencies
}

export const agencyOperationsApi = {
  // Merge agencies
  validateMerge: async (request: AgencyMergeRequest): Promise<AgencyMergeValidationResult> => {
    const response = await api.post('/agencies/merge/validate', request)
    return response.data
  },

  executeMerge: async (request: AgencyMergeRequest): Promise<AgencyMergeResponse> => {
    const response = await api.post('/agencies/merge', request)
    return response.data
  },

  // Split agency
  executeSplit: async (agencyId: number, request: AgencySplitRequest): Promise<AgencySplitResponse> => {
    const response = await api.post(`/agencies/${agencyId}/split`, request)
    return response.data
  },
}
