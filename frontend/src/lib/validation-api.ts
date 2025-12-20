import { api } from './api'

// Types for validation preferences
export interface ValidationPreferences {
  id: number
  agency_id: number
  // Routes validations
  validate_route_agency: boolean
  validate_route_duplicates: boolean
  validate_route_mandatory: boolean
  // Shapes validations
  validate_shape_dist_traveled: boolean
  validate_shape_dist_accuracy: boolean
  validate_shape_sequence: boolean
  validate_shape_mandatory: boolean
  // Calendar validations
  validate_calendar_mandatory: boolean
  // Calendar dates validations
  validate_calendar_date_mandatory: boolean
  // Fare attributes validations
  validate_fare_attribute_mandatory: boolean
  // Feed info validations
  validate_feed_info_mandatory: boolean
  // Stops validations
  validate_stop_duplicates: boolean
  validate_stop_mandatory: boolean
  // Trips validations
  validate_trip_service: boolean
  validate_trip_duplicates: boolean
  validate_trip_shape: boolean
  validate_trip_mandatory: boolean
  // Stop times validations
  validate_stop_time_trip: boolean
  validate_stop_time_stop: boolean
  validate_stop_time_sequence: boolean
  validate_stop_time_mandatory: boolean
  // Custom settings
  custom_settings?: Record<string, any>
}

export interface ValidationPreferencesUpdate {
  validate_route_agency?: boolean
  validate_route_duplicates?: boolean
  validate_route_mandatory?: boolean
  validate_shape_dist_traveled?: boolean
  validate_shape_dist_accuracy?: boolean
  validate_shape_sequence?: boolean
  validate_shape_mandatory?: boolean
  validate_calendar_mandatory?: boolean
  validate_calendar_date_mandatory?: boolean
  validate_fare_attribute_mandatory?: boolean
  validate_feed_info_mandatory?: boolean
  validate_stop_duplicates?: boolean
  validate_stop_mandatory?: boolean
  validate_trip_service?: boolean
  validate_trip_duplicates?: boolean
  validate_trip_shape?: boolean
  validate_trip_mandatory?: boolean
  validate_stop_time_trip?: boolean
  validate_stop_time_stop?: boolean
  validate_stop_time_sequence?: boolean
  validate_stop_time_mandatory?: boolean
  custom_settings?: Record<string, any>
}

export interface EnabledValidations {
  agency_id: number
  enabled_rules: {
    routes: Record<string, boolean>
    shapes: Record<string, boolean>
    calendar: Record<string, boolean>
    calendar_dates: Record<string, boolean>
    fare_attributes: Record<string, boolean>
    feed_info: Record<string, boolean>
    stops: Record<string, boolean>
    trips: Record<string, boolean>
    stop_times: Record<string, boolean>
  }
  total_enabled: number
  total_rules: number
}

export interface FeedValidationResult {
  valid: boolean
  error_count: number
  warning_count: number
  info_count: number
  issues: ValidationIssue[]
  summary: string
}

// Response when validation is queued as async task
export interface ValidationTaskResponse {
  task_id: number
  celery_task_id: string
  status: 'queued'
  message: string
  feed_id: number
  feed_name: string
  validator?: 'internal' | 'mobilitydata'
}

// MobilityData validation result (from task result_data)
export interface MobilityDataValidationResult {
  success: boolean
  valid: boolean
  feed_id: number
  feed_name: string
  validation_id: string
  error_count: number
  warning_count: number
  info_count: number
  total_notices: number
  duration_seconds: number
  report_html_path?: string
  report_json?: MobilityDataReport
  validator: 'mobilitydata'
}

export interface MobilityDataReport {
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

export interface MobilityDataNotice {
  code: string
  severity: 'ERROR' | 'WARNING' | 'INFO'
  totalNotices?: number
  [key: string]: any
}

export interface ValidationIssue {
  severity: 'error' | 'warning' | 'info'
  category: string
  message: string
  entity_type?: string
  entity_id?: string
  field?: string
  details?: Record<string, any>
}

// Validation preferences API
export const validationApi = {
  // Get validation preferences for an agency
  getPreferences: async (agencyId: number): Promise<ValidationPreferences> => {
    const response = await api.get(`/agencies/${agencyId}/validation-preferences`)
    return response.data
  },

  // Update validation preferences for an agency
  updatePreferences: async (agencyId: number, preferences: ValidationPreferencesUpdate): Promise<ValidationPreferences> => {
    const response = await api.put(`/agencies/${agencyId}/validation-preferences`, preferences)
    return response.data
  },

  // Get enabled validations summary for an agency
  getEnabledValidations: async (agencyId: number): Promise<EnabledValidations> => {
    const response = await api.get(`/agencies/${agencyId}/validation-preferences/enabled`)
    return response.data
  },

  // Queue feed validation (async task) - internal validator
  validateFeed: async (feedId: number): Promise<ValidationTaskResponse> => {
    const response = await api.post(`/feeds/${feedId}/validate`)
    return response.data
  },

  // Queue feed validation using MobilityData GTFS Validator
  validateFeedMobilityData: async (feedId: number, countryCode?: string): Promise<ValidationTaskResponse> => {
    const params = new URLSearchParams()
    if (countryCode) {
      params.append('country_code', countryCode)
    }
    const response = await api.post(`/feeds/${feedId}/validate-mobilitydata?${params.toString()}`)
    return response.data
  },

  // Get validation report (HTML or JSON)
  getValidationReport: async (feedId: number, validationId: string, reportType: 'branded' | 'original' | 'json' = 'branded') => {
    const params = new URLSearchParams({ report_type: reportType })

    if (reportType === 'json') {
      const response = await api.get(`/feeds/${feedId}/validation-report/${validationId}?${params.toString()}`)
      return response.data
    } else {
      // For HTML reports, we need to open in a new window
      const baseUrl = api.defaults.baseURL || ''
      const url = `${baseUrl}/feeds/${feedId}/validation-report/${validationId}?${params.toString()}`
      window.open(url, '_blank')
      return null
    }
  },

  // Open validation report in new window
  openValidationReport: (feedId: number, validationId: string, reportType: 'branded' | 'original' = 'branded') => {
    const baseUrl = api.defaults.baseURL || '/api/v1'
    const params = new URLSearchParams({ report_type: reportType })
    const url = `${baseUrl}/feeds/${feedId}/validation-report/${validationId}?${params.toString()}`
    window.open(url, '_blank')
  },
}

// Validation rule categories for UI organization
export const VALIDATION_CATEGORIES = {
  routes: {
    key: 'routes',
    rules: [
      { key: 'validate_route_agency', labelKey: 'validationSettings.rules.routeAgency' },
      { key: 'validate_route_duplicates', labelKey: 'validationSettings.rules.routeDuplicates' },
      { key: 'validate_route_mandatory', labelKey: 'validationSettings.rules.routeMandatory' },
    ],
  },
  shapes: {
    key: 'shapes',
    rules: [
      { key: 'validate_shape_dist_traveled', labelKey: 'validationSettings.rules.shapeDistTraveled' },
      { key: 'validate_shape_dist_accuracy', labelKey: 'validationSettings.rules.shapeDistAccuracy' },
      { key: 'validate_shape_sequence', labelKey: 'validationSettings.rules.shapeSequence' },
      { key: 'validate_shape_mandatory', labelKey: 'validationSettings.rules.shapeMandatory' },
    ],
  },
  calendar: {
    key: 'calendar',
    rules: [
      { key: 'validate_calendar_mandatory', labelKey: 'validationSettings.rules.calendarMandatory' },
    ],
  },
  calendar_dates: {
    key: 'calendar_dates',
    rules: [
      { key: 'validate_calendar_date_mandatory', labelKey: 'validationSettings.rules.calendarDateMandatory' },
    ],
  },
  fare_attributes: {
    key: 'fare_attributes',
    rules: [
      { key: 'validate_fare_attribute_mandatory', labelKey: 'validationSettings.rules.fareAttributeMandatory' },
    ],
  },
  feed_info: {
    key: 'feed_info',
    rules: [
      { key: 'validate_feed_info_mandatory', labelKey: 'validationSettings.rules.feedInfoMandatory' },
    ],
  },
  stops: {
    key: 'stops',
    rules: [
      { key: 'validate_stop_duplicates', labelKey: 'validationSettings.rules.stopDuplicates' },
      { key: 'validate_stop_mandatory', labelKey: 'validationSettings.rules.stopMandatory' },
    ],
  },
  trips: {
    key: 'trips',
    rules: [
      { key: 'validate_trip_service', labelKey: 'validationSettings.rules.tripService' },
      { key: 'validate_trip_duplicates', labelKey: 'validationSettings.rules.tripDuplicates' },
      { key: 'validate_trip_shape', labelKey: 'validationSettings.rules.tripShape' },
      { key: 'validate_trip_mandatory', labelKey: 'validationSettings.rules.tripMandatory' },
    ],
  },
  stop_times: {
    key: 'stop_times',
    rules: [
      { key: 'validate_stop_time_trip', labelKey: 'validationSettings.rules.stopTimeTrip' },
      { key: 'validate_stop_time_stop', labelKey: 'validationSettings.rules.stopTimeStop' },
      { key: 'validate_stop_time_sequence', labelKey: 'validationSettings.rules.stopTimeSequence' },
      { key: 'validate_stop_time_mandatory', labelKey: 'validationSettings.rules.stopTimeMandatory' },
    ],
  },
}
