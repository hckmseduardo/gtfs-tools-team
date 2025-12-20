import { api } from './api'

// Types
export interface Agency {
  id: number
  name: string
  slug: string
  is_active: boolean
  // GTFS agency.txt fields
  agency_id?: string
  agency_url?: string
  agency_timezone?: string
  agency_lang?: string
  agency_phone?: string
  agency_fare_url?: string
  agency_email?: string
  // Legacy fields (kept for backwards compatibility)
  contact_email?: string
  contact_phone?: string
  website?: string
  created_at: string
  updated_at: string
}

export interface Route {
  feed_id: number
  agency_id: number
  route_id: string
  route_short_name: string
  route_long_name?: string
  route_desc?: string
  route_type: number
  route_url?: string
  route_color?: string
  route_text_color?: string
  route_sort_order?: number
  continuous_pickup?: number
  continuous_drop_off?: number
  network_id?: string
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface Stop {
  feed_id: number
  agency_id: number
  stop_id: string
  stop_code?: string
  stop_name: string
  tts_stop_name?: string
  stop_desc?: string
  stop_lat: number
  stop_lon: number
  zone_id?: string
  stop_url?: string
  location_type?: number
  parent_station?: string
  stop_timezone?: string
  wheelchair_boarding?: number
  level_id?: string
  platform_code?: string
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface Trip {
  feed_id: number
  agency_id: number
  route_id: string
  service_id: string
  trip_id: string
  trip_headsign?: string
  trip_short_name?: string
  direction_id?: number
  block_id?: string
  shape_id?: string
  wheelchair_accessible?: number
  bikes_allowed?: number
  cars_allowed?: number
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface TripWithRoute extends Trip {
  route_short_name: string
  route_long_name?: string
  route_type: number
  route_color?: string
}

export interface TripWithDetails extends TripWithRoute {
  stop_count: number
  first_departure?: string
  last_arrival?: string
}

export interface Calendar {
  feed_id: number
  service_id: string
  monday: boolean
  tuesday: boolean
  wednesday: boolean
  thursday: boolean
  friday: boolean
  saturday: boolean
  sunday: boolean
  start_date: string
  end_date: string
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface CalendarDate {
  feed_id: number
  service_id: string
  date: string
  exception_type: 1 | 2 // 1=service added, 2=service removed
  created_at: string
  updated_at: string
}

export interface FareAttribute {
  feed_id: number
  fare_id: string
  price: number
  currency_type: string
  payment_method: number // 0=on board, 1=before boarding
  transfers?: number | null // 0=no, 1=once, 2=twice, null=unlimited
  agency_id?: string
  transfer_duration?: number // seconds
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface FareRule {
  feed_id: number
  fare_id: string
  route_id: string // empty string = all routes
  origin_id: string // zone ID, empty = any origin
  destination_id: string // zone ID, empty = any destination
  contains_id: string // zone ID that must be passed through
  custom_fields?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface GTFSValidationIssue {
  severity: 'error' | 'warning' | 'info'
  file?: string
  field?: string
  line?: number
  message: string
}

export interface GTFSValidationResult {
  valid: boolean
  error_count: number
  warning_count: number
  info_count: number
  issues: GTFSValidationIssue[]
  files_checked: string[]
  summary: string
}

export interface GTFSFileStats {
  filename: string
  imported: number
  updated: number
  skipped: number
  errors: number
}

export interface GTFSImportResult {
  success: boolean
  agency_id: number
  files_processed: GTFSFileStats[]
  total_imported?: number
  total_updated?: number
  total_skipped?: number
  total_errors?: number
  validation_errors: string[]
  validation_warnings: string[]
  started_at: string
  completed_at: string
  duration_seconds: number
}

export interface GTFSExportStats {
  success: boolean
  agency_id: number
  route_count: number
  stop_count: number
  trip_count: number
  stop_time_count: number
  calendar_count: number
  calendar_date_count: number
  shape_count: number
  file_size_bytes: number
}

// Feed Source types
export type FeedSourceStatus = 'active' | 'inactive' | 'error' | 'checking'
export type FeedSourceType = 'gtfs_static' | 'gtfs_realtime' | 'gtfs_rt_trip_updates' | 'gtfs_rt_vehicle_positions' | 'gtfs_rt_alerts' | 'gtfs_rt_trip_modifications'
export type CheckFrequency = 'hourly' | 'daily' | 'weekly'

export interface FeedSource {
  id: number
  agency_id: number
  name: string
  description?: string
  source_type: FeedSourceType
  url: string
  auth_type?: string
  auth_header?: string
  auth_value?: string
  check_frequency: CheckFrequency
  is_enabled: boolean
  auto_import: boolean
  import_options?: Record<string, any>
  status: FeedSourceStatus
  last_checked_at?: string
  last_successful_check?: string
  last_import_at?: string
  error_count: number
  last_error?: string
  created_feed_id?: number
  created_at: string
  updated_at: string
}

export interface FeedSourceCheckLog {
  id: number
  feed_source_id: number
  checked_at: string
  success: boolean
  http_status?: number
  content_changed: boolean
  content_size?: number
  import_triggered: boolean
  import_task_id?: string
  error_message?: string
  created_at: string
}

// Agency API
export const agencyApi = {
  list: async (params?: { skip?: number; limit?: number; search?: string }) => {
    const response = await api.get('/agencies/', { params })
    return response.data
  },

  get: async (id: number) => {
    const response = await api.get(`/agencies/${id}`)
    return response.data
  },

  create: async (data: Partial<Agency>) => {
    const response = await api.post('/agencies/', data)
    return response.data
  },

  update: async (id: number, data: Partial<Agency>) => {
    const response = await api.patch(`/agencies/${id}`, data)
    return response.data
  },

  delete: async (id: number) => {
    const response = await api.delete(`/agencies/${id}`)
    return response.data
  },
}

// Routes API
export const routesApi = {
  list: async (feed_id: number, params?: { skip?: number; limit?: number; search?: string }) => {
    const response = await api.get(`/feeds/${feed_id}/routes`, { params })
    return response.data
  },

  get: async (feed_id: number, route_id: string) => {
    const response = await api.get(`/feeds/${feed_id}/routes/${route_id}`)
    return response.data
  },

  create: async (feed_id: number, data: Partial<Route>) => {
    const response = await api.post(`/feeds/${feed_id}/routes`, data)
    return response.data
  },

  update: async (feed_id: number, route_id: string, data: Partial<Route>) => {
    const response = await api.patch(`/feeds/${feed_id}/routes/${route_id}`, data)
    return response.data
  },

  delete: async (feed_id: number, route_id: string) => {
    await api.delete(`/feeds/${feed_id}/routes/${route_id}`)
  },

  // Get mapping of route_ids to stop_ids for filtering stops by routes
  getRouteStopsMap: async (feed_id: number): Promise<Record<string, string[]>> => {
    const response = await api.get(`/feeds/${feed_id}/routes/route-stops-map`)
    return response.data
  },
}

// Stops API
export const stopsApi = {
  list: async (feed_id: number, params?: { skip?: number; limit?: number; search?: string; wheelchair_accessible?: boolean; location_type?: number }) => {
    const response = await api.get(`/feeds/${feed_id}/stops`, { params })
    return response.data
  },

  get: async (feed_id: number, stop_id: string) => {
    const response = await api.get(`/feeds/${feed_id}/stops/${stop_id}`)
    return response.data
  },

  create: async (feed_id: number, data: Partial<Stop>) => {
    const response = await api.post(`/feeds/${feed_id}/stops`, data)
    return response.data
  },

  update: async (feed_id: number, stop_id: string, data: Partial<Stop>) => {
    const response = await api.patch(`/feeds/${feed_id}/stops/${stop_id}`, data)
    return response.data
  },

  delete: async (feed_id: number, stop_id: string) => {
    await api.delete(`/feeds/${feed_id}/stops/${stop_id}`)
  },

  nearby: async (feed_id: number, lat: number, lon: number, radius: number) => {
    const response = await api.post(`/feeds/${feed_id}/stops/nearby`, {
      latitude: lat,
      longitude: lon,
      radius_meters: radius,
    })
    return response.data
  },
}

// Trips API
export const tripsApi = {
  list: async (feed_id: number, params?: {
    skip?: number
    limit?: number
    route_id?: string
    service_id?: string
    direction_id?: number
    search?: string
  }) => {
    // Trailing slash avoids 307 redirect that can drop auth headers
    const response = await api.get(`/feeds/${feed_id}/trips/`, { params })
    return response.data
  },

  listWithRoutes: async (feed_id: number, params?: {
    skip?: number
    limit?: number
    route_id?: string
  }) => {
    const response = await api.get(`/feeds/${feed_id}/trips/with-routes`, { params })
    return response.data
  },

  listWithDetails: async (feed_id: number, params?: {
    skip?: number
    limit?: number
    route_id?: string
  }) => {
    const response = await api.get(`/feeds/${feed_id}/trips/with-details`, { params })
    return response.data
  },

  get: async (feed_id: number, trip_id: string) => {
    const response = await api.get(`/feeds/${feed_id}/trips/${trip_id}`)
    return response.data
  },

  getWithStopTimes: async (feed_id: number, trip_id: string) => {
    const response = await api.get(`/feeds/${feed_id}/trips/${trip_id}/with-stop-times`)
    return response.data
  },

  create: async (feed_id: number, data: Partial<Trip>) => {
    // Trailing slash avoids 307 redirect that can cause mixed content issues
    const response = await api.post(`/feeds/${feed_id}/trips/`, data)
    return response.data
  },

  update: async (feed_id: number, trip_id: string, data: Partial<Trip>) => {
    const response = await api.patch(`/feeds/${feed_id}/trips/${trip_id}`, data)
    return response.data
  },

  delete: async (feed_id: number, trip_id: string) => {
    await api.delete(`/feeds/${feed_id}/trips/${trip_id}`)
  },

  copy: async (feed_id: number, trip_id: string, newTripId: string, copyStopTimes: boolean = true) => {
    const response = await api.post(`/feeds/${feed_id}/trips/${trip_id}/copy`, {
      new_trip_id: newTripId,
      copy_stop_times: copyStopTimes,
    })
    return response.data
  },
}

// Calendars API
export const calendarsApi = {
  list: async (feed_id: number, params?: { skip?: number; limit?: number; search?: string }) => {
    // Trailing slash avoids 307 redirect that can drop auth headers in some setups
    const response = await api.get(`/feeds/${feed_id}/calendars/`, { params })
    return response.data
  },

  get: async (feed_id: number, service_id: string) => {
    const response = await api.get(`/feeds/${feed_id}/calendars/${service_id}`)
    return response.data
  },

  create: async (feed_id: number, data: Partial<Calendar>) => {
    // Trailing slash avoids 307 redirect that can cause mixed content issues
    const response = await api.post(`/feeds/${feed_id}/calendars/`, { ...data, feed_id })
    return response.data
  },

  update: async (feed_id: number, service_id: string, data: Partial<Calendar>) => {
    const response = await api.patch(`/feeds/${feed_id}/calendars/${service_id}`, data)
    return response.data
  },

  delete: async (feed_id: number, service_id: string) => {
    await api.delete(`/feeds/${feed_id}/calendars/${service_id}`)
  },

  // Calendar Dates (Exceptions) API
  listExceptions: async (feed_id: number, service_id: string): Promise<{ items: CalendarDate[]; total: number }> => {
    const response = await api.get(`/feeds/${feed_id}/calendars/${service_id}/exceptions`)
    return response.data
  },

  createException: async (feed_id: number, service_id: string, data: { date: string; exception_type: 1 | 2 }): Promise<CalendarDate> => {
    const response = await api.post(`/feeds/${feed_id}/calendars/${service_id}/exceptions`, data)
    return response.data
  },

  updateException: async (
    feed_id: number,
    service_id: string,
    date: string,
    data: { exception_type?: 1 | 2 }
  ): Promise<CalendarDate> => {
    const response = await api.patch(`/feeds/${feed_id}/calendars/${service_id}/exceptions/${date}`, data)
    return response.data
  },

  deleteException: async (feed_id: number, service_id: string, date: string): Promise<void> => {
    await api.delete(`/feeds/${feed_id}/calendars/${service_id}/exceptions/${date}`)
  },
}

// MobilityData validation response types
export interface MobilityDataValidationTaskResponse {
  task_id: number
  celery_task_id: string
  status: string
  message: string
  filename: string
  validator: string
}

export interface MobilityDataNotice {
  code: string
  severity: 'ERROR' | 'WARNING' | 'INFO'
  totalNotices?: number
  sampleNotices?: Array<{
    filename?: string
    fieldName?: string
    [key: string]: any
  }>
  [key: string]: any
}

export interface MobilityDataValidationResult {
  success: boolean
  valid: boolean
  filename?: string
  feed_id?: number
  feed_name?: string
  validation_id?: string
  error_count: number
  warning_count: number
  info_count: number
  total_notices: number
  duration_seconds?: number
  report_html_path?: string
  report_json?: {
    notices?: MobilityDataNotice[]
    gtfsFeatures?: string[]
    agencies?: Array<{ name: string }>
    feedInfo?: {
      feedPublisherName?: string
      feedLang?: string
      feedStartDate?: string
      feedEndDate?: string
    }
  }
  validator: string
  pre_import?: boolean
}

// GTFS Analysis types (for 4-step import wizard)
export interface GTFSAgencyInfo {
  agency_id?: string
  agency_name: string
  agency_url?: string
  agency_timezone?: string
  agency_lang?: string
  agency_phone?: string
  agency_fare_url?: string
  agency_email?: string
}

export interface GTFSFileSummary {
  filename: string
  row_count: number
  columns: string[]
}

export interface AgencyMatch {
  id: number
  name: string
  slug: string
  agency_id?: string
  match_score: number
  match_reason: string
}

export interface GTFSAnalysisResult {
  upload_id: string
  filename: string
  file_size_bytes: number
  agencies_in_file: GTFSAgencyInfo[]
  matching_agencies: AgencyMatch[]
  files_summary: GTFSFileSummary[]
  has_required_files: boolean
  missing_files: string[]
  extra_files: string[]
}

// GTFS Import/Export API
export const gtfsApi = {
  // Validate GTFS file (internal validator)
  validate: async (file: File): Promise<GTFSValidationResult> => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post('/gtfs/validate', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  // Validate GTFS file with MobilityData validator (queues async task)
  validateMobilityData: async (file: File, countryCode?: string): Promise<MobilityDataValidationTaskResponse> => {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams()
    if (countryCode) {
      params.append('country_code', countryCode)
    }

    const response = await api.post(`/gtfs/validate-mobilitydata?${params}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  // Analyze GTFS file to extract agency info (Step 2 of import wizard)
  analyze: async (file: File): Promise<GTFSAnalysisResult> => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post('/gtfs/analyze', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  // Import from previously uploaded file (Step 4 of import wizard)
  importFromUpload: async (
    uploadId: string,
    agencyId: number,
    options?: {
      create_agency?: boolean
      agency_name?: string
      agency_timezone?: string
      replace_existing?: boolean
      skip_shapes?: boolean
      stop_on_error?: boolean
      feed_name?: string
      feed_description?: string
      feed_version?: string
    }
  ) => {
    const params = new URLSearchParams({
      upload_id: uploadId,
      agency_id: agencyId.toString(),
      create_agency: (options?.create_agency ?? false).toString(),
      replace_existing: (options?.replace_existing ?? false).toString(),
      skip_shapes: (options?.skip_shapes ?? false).toString(),
      stop_on_error: (options?.stop_on_error ?? false).toString(),
    })

    if (options?.agency_name) {
      params.append('agency_name', options.agency_name)
    }
    if (options?.agency_timezone) {
      params.append('agency_timezone', options.agency_timezone)
    }
    if (options?.feed_name) {
      params.append('feed_name', options.feed_name)
    }
    if (options?.feed_description) {
      params.append('feed_description', options.feed_description)
    }
    if (options?.feed_version) {
      params.append('feed_version', options.feed_version)
    }

    const response = await api.post(`/gtfs/import-from-upload?${params}`)
    return response.data
  },

  // Validate uploaded file with MobilityData (using upload_id)
  validateUploadedFile: async (uploadId: string, countryCode?: string): Promise<MobilityDataValidationTaskResponse> => {
    const params = new URLSearchParams({ upload_id: uploadId })
    if (countryCode) {
      params.append('country_code', countryCode)
    }

    const response = await api.post(`/gtfs/validate-upload?${params}`)
    return response.data
  },

  // Get validation report URL for pre-import validation (requires auth token in URL)
  getValidationReportUrl: (validationId: string, reportType: 'branded' | 'original' | 'json' = 'branded'): string => {
    const baseUrl = api.defaults.baseURL || ''
    const token = localStorage.getItem('token') || ''
    return `${baseUrl}/gtfs/validation-report/${validationId}?report_type=${reportType}&token=${token}`
  },

  // Fetch validation report as blob (for download/view with authentication)
  fetchValidationReport: async (validationId: string, reportType: 'branded' | 'original' | 'json' = 'branded'): Promise<Blob> => {
    const response = await api.get(`/gtfs/validation-report/${validationId}`, {
      params: { report_type: reportType },
      responseType: 'blob',
    })
    return response.data
  },

  // Open validation report in new tab (handles authentication)
  openValidationReport: async (validationId: string, reportType: 'branded' | 'original' = 'branded'): Promise<void> => {
    const blob = await gtfsApi.fetchValidationReport(validationId, reportType)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    // Clean up the URL after a delay
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  },

  // Download validation report
  downloadValidationReport: async (validationId: string, reportType: 'branded' | 'original' = 'branded'): Promise<void> => {
    const blob = await gtfsApi.fetchValidationReport(validationId, reportType)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `validation_report_${validationId}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  },

  // =========== EXPORT WIZARD API ===========

  // Generate GTFS export (Step 1 of export wizard - queues async task)
  generateExport: async (feedId: number): Promise<{
    task_id: number
    celery_task_id: string
    export_id: string
    status: string
    message: string
    feed_id: number
    feed_name: string
  }> => {
    const params = new URLSearchParams({ feed_id: feedId.toString() })
    const response = await api.post(`/gtfs/export-generate?${params}`)
    return response.data
  },

  // Fetch export validation report (Step 2 of export wizard)
  fetchExportReport: async (exportId: string, reportType: 'branded' | 'original' | 'json' = 'branded'): Promise<Blob> => {
    const response = await api.get(`/gtfs/export-report/${exportId}`, {
      params: { report_type: reportType },
      responseType: 'blob',
    })
    return response.data
  },

  // Open export validation report in new tab
  openExportReport: async (exportId: string, reportType: 'branded' | 'original' = 'branded'): Promise<void> => {
    const blob = await gtfsApi.fetchExportReport(exportId, reportType)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  },

  // Download export validation report
  downloadExportReport: async (exportId: string, reportType: 'branded' | 'original' = 'branded'): Promise<void> => {
    const blob = await gtfsApi.fetchExportReport(exportId, reportType)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `validation_report_${exportId}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  },

  // Download GTFS ZIP from export (Step 3 of export wizard)
  downloadExportGtfs: async (exportId: string, filename?: string): Promise<void> => {
    const response = await api.get(`/gtfs/export-download/${exportId}`, {
      responseType: 'blob',
    })

    // Extract filename from content-disposition header if available
    const contentDisposition = response.headers['content-disposition']
    let downloadFilename = filename || `gtfs_export_${exportId}.zip`
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?([^"]+)"?/)
      if (match) {
        downloadFilename = match[1]
      }
    }

    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = downloadFilename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  },

  // Fetch GTFS file from validation (returns blob)
  fetchValidationGtfsFile: async (validationId: string): Promise<Blob> => {
    const response = await api.get(`/gtfs/validation-file/${validationId}`, {
      responseType: 'blob',
    })
    return response.data
  },

  // Download GTFS file from validation
  downloadValidationGtfsFile: async (validationId: string, filename?: string): Promise<void> => {
    const blob = await gtfsApi.fetchValidationGtfsFile(validationId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename || `gtfs_${validationId}.zip`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  },

  // Import GTFS file (queues async task)
  import: async (
    file: File,
    agencyId: number,
    options?: {
      replace_existing?: boolean
      validate_only?: boolean
      skip_shapes?: boolean
      stop_on_error?: boolean
      feed_name?: string
      feed_description?: string
      feed_version?: string
    }
  ) => {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams({
      agency_id: agencyId.toString(),
      replace_existing: (options?.replace_existing ?? false).toString(),
      validate_only: (options?.validate_only ?? false).toString(),
      skip_shapes: (options?.skip_shapes ?? false).toString(),
      stop_on_error: (options?.stop_on_error ?? false).toString(),
    })

    // Add feed metadata if provided
    if (options?.feed_name) {
      params.append('feed_name', options.feed_name)
    }
    if (options?.feed_description) {
      params.append('feed_description', options.feed_description)
    }
    if (options?.feed_version) {
      params.append('feed_version', options.feed_version)
    }

    const response = await api.post(`/gtfs/import?${params}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    // Returns a Task object with task_id, status, etc.
    return response.data
  },

  // Get export statistics
  getExportStats: async (agencyId: number, feedId?: number): Promise<GTFSExportStats> => {
    const params: any = {}

    if (feedId) {
      params.feed_id = feedId
    } else {
      params.agency_id = agencyId
    }

    const response = await api.get('/gtfs/export/stats', { params })
    return response.data
  },

  // Export GTFS file (downloads file)
  export: async (
    agencyId: number,
    options?: {
      feed_id?: number
      include_shapes?: boolean
      include_calendar_dates?: boolean
      date_filter_start?: string
      date_filter_end?: string
    }
  ) => {
    const params = new URLSearchParams({
      include_shapes: (options?.include_shapes ?? true).toString(),
      include_calendar_dates: (options?.include_calendar_dates ?? true).toString(),
    })

    // Use feed_id if provided, otherwise use agency_id
    if (options?.feed_id) {
      params.append('feed_id', options.feed_id.toString())
    } else {
      params.append('agency_id', agencyId.toString())
    }

    if (options?.date_filter_start) {
      params.append('date_filter_start', options.date_filter_start)
    }
    if (options?.date_filter_end) {
      params.append('date_filter_end', options.date_filter_end)
    }

    const response = await api.get(`/gtfs/export?${params}`, {
      responseType: 'blob',
    })

    // Create download link
    const filename = options?.feed_id ? `gtfs_feed_${options.feed_id}.zip` : `gtfs_agency_${agencyId}.zip`
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}

// Shape types
export interface ShapePoint {
  lat: number
  lon: number
  sequence: number
}

export interface ShapeWithPoints {
  shape_id: string
  points: ShapePoint[]
  total_points: number
}

export interface ShapeResponse {
  feed_id: number
  shape_id: string
  shape_pt_lat: number
  shape_pt_lon: number
  shape_pt_sequence: number
  shape_dist_traveled?: number
}

export interface ShapeBulkCreatePoint {
  lat: number
  lon: number
  sequence: number
  dist_traveled?: number
}

// Shapes API
export const shapesApi = {
  // Get shapes grouped by shape_id with all points
  getByShapeId: async (params: {
    feed_id: number
    agency_id?: number
    shape_ids?: string
  }): Promise<{ items: ShapeWithPoints[]; total: number }> => {
    const { feed_id, ...queryParams } = params
    const response = await api.get(`/feeds/${feed_id}/shapes/by-shape-id`, { params: queryParams })
    return response.data
  },

  // List unique shape IDs for a feed
  listShapeIds: async (feed_id: number): Promise<string[]> => {
    const response = await api.get(`/feeds/${feed_id}/shapes/by-shape-id`)
    return response.data.items.map((s: ShapeWithPoints) => s.shape_id)
  },

  // Create a single shape point
  create: async (data: {
    feed_id: number
    shape_id: string
    shape_pt_lat: number
    shape_pt_lon: number
    shape_pt_sequence: number
    shape_dist_traveled?: number
  }): Promise<ShapeResponse> => {
    const response = await api.post(`/feeds/${data.feed_id}/shapes/`, data)
    return response.data
  },

  // Update a shape point
  update: async (
    feed_id: number,
    shape_id: string,
    shape_pt_sequence: number,
    data: {
      shape_pt_lat?: number
      shape_pt_lon?: number
      shape_dist_traveled?: number
    }
  ): Promise<ShapeResponse> => {
    const response = await api.patch(`/feeds/${feed_id}/shapes/${shape_id}/${shape_pt_sequence}`, data)
    return response.data
  },

  // Delete a single shape point
  delete: async (feed_id: number, shape_id: string, shape_pt_sequence: number): Promise<void> => {
    await api.delete(`/feeds/${feed_id}/shapes/${shape_id}/${shape_pt_sequence}`)
  },

  // Bulk create shape points (optionally replacing existing)
  bulkCreate: async (
    data: {
      feed_id: number
      shape_id: string
      points: ShapeBulkCreatePoint[]
    },
    replaceExisting: boolean = false
  ): Promise<ShapeResponse[]> => {
    const response = await api.post(`/feeds/${data.feed_id}/shapes/bulk?replace_existing=${replaceExisting}`, data)
    return response.data
  },

  // Delete all points for a shape_id
  deleteByShapeId: async (shapeId: string, feedId: number): Promise<void> => {
    await api.delete(`/feeds/${feedId}/shapes/by-shape-id/${shapeId}`)
  },
}

// Stop Times types
export interface StopTime {
  feed_id: number
  trip_id: string
  stop_id: string
  arrival_time: string
  departure_time: string
  stop_sequence: number
  stop_headsign?: string
  pickup_type: number
  drop_off_type: number
  // Extended fields from with-details endpoint
  stop_name?: string
  stop_code?: string
  trip_headsign?: string
  route_short_name?: string
  route_long_name?: string
  route_color?: string
  gtfs_trip_id?: string
  gtfs_route_id?: string
}

// Stop Times API
export const stopTimesApi = {
  listForStop: async (feed_id: number, stop_id: string, limit: number = 100): Promise<{ items: StopTime[]; total: number }> => {
    const params = { limit }
    const response = await api.get(`/feeds/${feed_id}/stop-times/stop/${stop_id}`, { params })
    return response.data
  },

  listForTrip: async (feed_id: number, trip_id: string): Promise<{ items: StopTime[]; total: number }> => {
    const response = await api.get(`/feeds/${feed_id}/stop-times/trip/${trip_id}`)
    return response.data
  },

  create: async (feed_id: number, trip_id: string, data: {
    stop_id: string
    stop_sequence: number
    arrival_time: string
    departure_time: string
    stop_headsign?: string
    pickup_type?: number
    drop_off_type?: number
  }): Promise<StopTime> => {
    const response = await api.post(`/feeds/${feed_id}/stop-times/`, {
      feed_id,
      trip_id,
      ...data,
    })
    return response.data
  },

  update: async (feed_id: number, trip_id: string, stop_sequence: number, data: {
    stop_id?: string
    stop_sequence?: number
    arrival_time?: string
    departure_time?: string
    stop_headsign?: string
    pickup_type?: number
    drop_off_type?: number
  }): Promise<StopTime> => {
    const response = await api.patch(`/feeds/${feed_id}/stop-times/${trip_id}/${stop_sequence}`, data)
    return response.data
  },

  delete: async (feed_id: number, trip_id: string, stop_sequence: number): Promise<void> => {
    await api.delete(`/feeds/${feed_id}/stop-times/${trip_id}/${stop_sequence}`)
  },
}

// Feed Sources API
export const feedSourcesApi = {
  list: async (params?: { skip?: number; limit?: number; agency_id?: number; is_enabled?: boolean }) => {
    const response = await api.get('/feed-sources/', { params })
    return response.data
  },

  get: async (id: number) => {
    const response = await api.get(`/feed-sources/${id}`)
    return response.data
  },

  create: async (data: {
    agency_id: number
    name: string
    description?: string
    source_type?: FeedSourceType
    url: string
    auth_type?: string
    auth_header?: string
    auth_value?: string
    check_frequency?: CheckFrequency
    is_enabled?: boolean
    auto_import?: boolean
    import_options?: Record<string, any>
  }) => {
    const response = await api.post('/feed-sources/', data)
    return response.data
  },

  update: async (id: number, data: Partial<FeedSource>) => {
    const response = await api.patch(`/feed-sources/${id}`, data)
    return response.data
  },

  delete: async (id: number) => {
    await api.delete(`/feed-sources/${id}`)
  },

  check: async (id: number, forceImport: boolean = false) => {
    const response = await api.post(`/feed-sources/${id}/check`, { force_import: forceImport })
    return response.data
  },

  enable: async (id: number) => {
    const response = await api.post(`/feed-sources/${id}/enable`)
    return response.data
  },

  disable: async (id: number) => {
    const response = await api.post(`/feed-sources/${id}/disable`)
    return response.data
  },

  getLogs: async (id: number, params?: { skip?: number; limit?: number }) => {
    const response = await api.get(`/feed-sources/${id}/logs`, { params })
    return response.data
  },
}

// Routing types for OSM-based shape improvements
export type TransitMode = 'bus' | 'rail' | 'tram' | 'ferry'

export interface RoutingPoint {
  lat: number
  lon: number
  sequence: number
}

export interface RoutingResult {
  success: boolean
  shape_id: string
  points: RoutingPoint[]
  point_count: number
  distance_meters: number
  message?: string
  confidence?: number
}

export interface RoutingHealthResponse {
  available: boolean
  message: string
}

// Routing API for OSM-based shape improvements
export const routingApi = {
  // Check if routing service (Valhalla) is available
  checkHealth: async (): Promise<RoutingHealthResponse> => {
    const response = await api.get('/routing/health')
    return response.data
  },

  // Snap existing shape to road/rail network
  snapToRoad: async (params: {
    feed_id: number
    shape_id: string
    mode?: TransitMode
  }): Promise<RoutingResult> => {
    const response = await api.post('/routing/snap-to-road', {
      feed_id: params.feed_id,
      shape_id: params.shape_id,
      mode: params.mode || 'bus',
    })
    return response.data
  },

  // Generate route from waypoints following road network
  autoRoute: async (params: {
    feed_id: number
    shape_id: string
    waypoints: { lat: number; lon: number }[]
    mode?: TransitMode
  }): Promise<RoutingResult> => {
    const response = await api.post('/routing/auto-route', {
      feed_id: params.feed_id,
      shape_id: params.shape_id,
      waypoints: params.waypoints,
      mode: params.mode || 'bus',
    })
    return response.data
  },
}

// Fare Attributes API
export const fareAttributesApi = {
  list: async (feed_id: number, params?: { skip?: number; limit?: number }): Promise<{ items: FareAttribute[]; total: number; skip: number; limit: number }> => {
    const response = await api.get(`/feeds/${feed_id}/fare-attributes/`, { params })
    return response.data
  },

  get: async (feed_id: number, fare_id: string): Promise<FareAttribute> => {
    const response = await api.get(`/feeds/${feed_id}/fare-attributes/${fare_id}`)
    return response.data
  },

  create: async (feed_id: number, data: Partial<FareAttribute>): Promise<FareAttribute> => {
    const response = await api.post(`/feeds/${feed_id}/fare-attributes/`, { ...data, feed_id })
    return response.data
  },

  update: async (feed_id: number, fare_id: string, data: Partial<FareAttribute>): Promise<FareAttribute> => {
    const response = await api.patch(`/feeds/${feed_id}/fare-attributes/${fare_id}`, data)
    return response.data
  },

  delete: async (feed_id: number, fare_id: string): Promise<void> => {
    await api.delete(`/feeds/${feed_id}/fare-attributes/${fare_id}`)
  },
}

// Fare Rules API
export interface FareRuleIdentifier {
  fare_id: string
  route_id?: string
  origin_id?: string
  destination_id?: string
  contains_id?: string
}

export const fareRulesApi = {
  list: async (feed_id: number, params?: {
    skip?: number
    limit?: number
    fare_id?: string
    route_id?: string
  }): Promise<{ items: FareRule[]; total: number; skip: number; limit: number }> => {
    const response = await api.get(`/feeds/${feed_id}/fare-rules/`, { params })
    return response.data
  },

  listByFare: async (feed_id: number, fare_id: string): Promise<{ items: FareRule[]; total: number; skip: number; limit: number }> => {
    const response = await api.get(`/feeds/${feed_id}/fare-rules/by-fare/${fare_id}`)
    return response.data
  },

  get: async (feed_id: number, identifier: FareRuleIdentifier): Promise<FareRule> => {
    const body = {
      fare_id: identifier.fare_id,
      route_id: identifier.route_id || '',
      origin_id: identifier.origin_id || '',
      destination_id: identifier.destination_id || '',
      contains_id: identifier.contains_id || '',
    }
    const response = await api.post(`/feeds/${feed_id}/fare-rules/get`, body)
    return response.data
  },

  create: async (feed_id: number, data: Partial<FareRule>): Promise<FareRule> => {
    const response = await api.post(`/feeds/${feed_id}/fare-rules/`, { ...data, feed_id })
    return response.data
  },

  update: async (feed_id: number, identifier: FareRuleIdentifier, data: Partial<FareRule>): Promise<FareRule> => {
    const body = {
      identifier: {
        fare_id: identifier.fare_id,
        route_id: identifier.route_id || '',
        origin_id: identifier.origin_id || '',
        destination_id: identifier.destination_id || '',
        contains_id: identifier.contains_id || '',
      },
      update: data,
    }
    const response = await api.patch(`/feeds/${feed_id}/fare-rules/`, body)
    return response.data
  },

  delete: async (feed_id: number, identifier: FareRuleIdentifier): Promise<void> => {
    const body = {
      fare_id: identifier.fare_id,
      route_id: identifier.route_id || '',
      origin_id: identifier.origin_id || '',
      destination_id: identifier.destination_id || '',
      contains_id: identifier.contains_id || '',
    }
    await api.delete(`/feeds/${feed_id}/fare-rules/`, { data: body })
  },

  deleteByFare: async (feed_id: number, fare_id: string): Promise<void> => {
    await api.delete(`/feeds/${feed_id}/fare-rules/by-fare/${fare_id}`)
  },
}

// Geocoding API for address lookup
export interface ReverseGeocodeResponse {
  success: boolean
  display_name: string
  suggested_stop_name: string
  name?: string
  road?: string
  house_number?: string
  neighbourhood?: string
  suburb?: string
  city?: string
  state?: string
  country?: string
  postcode?: string
}

export interface GeocodingHealthResponse {
  available: boolean
  message: string
}

export interface SearchResultItem {
  place_id: number
  display_name: string
  lat: number
  lon: number
  type?: string
  importance?: number
  boundingbox?: number[]  // [south, north, west, east]
}

export interface SearchResponse {
  success: boolean
  results: SearchResultItem[]
}

export const geocodingApi = {
  // Check if geocoding service is available
  checkHealth: async (): Promise<GeocodingHealthResponse> => {
    const response = await api.get('/geocoding/health')
    return response.data
  },

  // Reverse geocode lat/lon to address
  reverseGeocode: async (params: {
    lat: number
    lon: number
    lang?: string
  }): Promise<ReverseGeocodeResponse> => {
    const response = await api.post('/geocoding/reverse', {
      lat: params.lat,
      lon: params.lon,
      lang: params.lang || 'en',
    })
    return response.data
  },

  // Forward geocode: search for addresses/places
  search: async (params: {
    query: string
    limit?: number
    lang?: string
    viewbox?: number[]  // [minLon, minLat, maxLon, maxLat]
    bounded?: boolean
  }): Promise<SearchResponse> => {
    const response = await api.post('/geocoding/search', {
      query: params.query,
      limit: params.limit || 5,
      lang: params.lang || 'en',
      viewbox: params.viewbox,
      bounded: params.bounded || false,
    })
    return response.data
  },
}
