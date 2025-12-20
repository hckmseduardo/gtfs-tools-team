/**
 * Route Creator API client
 */

import { api } from './api'

// Types matching backend schemas

export interface RouteExportRoute {
  route_id: string
  route_short_name: string
  route_long_name?: string
  route_type: number
  route_color?: string
  route_text_color?: string
  route_desc?: string
  custom_fields?: Record<string, any>
}

export interface RouteExportStop {
  stop_id: string
  stop_name: string
  stop_lat: number
  stop_lon: number
  stop_code?: string
  stop_desc?: string
  wheelchair_boarding?: number
  custom_fields?: Record<string, any>
}

export interface RouteExportShapePoint {
  lat: number
  lon: number
  sequence: number
  dist_traveled?: number
}

export interface RouteExportTrip {
  trip_id: string
  trip_headsign?: string
  direction_id?: number
  wheelchair_accessible?: number
  bikes_allowed?: number
  custom_fields?: Record<string, any>
}

export interface RouteExportStopTime {
  trip_id: string
  stop_id: string
  stop_sequence: number
  arrival_time: string
  departure_time: string
  stop_headsign?: string
  pickup_type?: number
  drop_off_type?: number
  shape_dist_traveled?: number
  timepoint?: number
}

export interface RouteExportPayload {
  feed_id: number
  service_ids: string[]  // GTFS service_id values from calendar.txt
  route: RouteExportRoute
  new_stops: RouteExportStop[]
  shape_id: string
  shape_points: RouteExportShapePoint[]
  trips: RouteExportTrip[]
  stop_times: RouteExportStopTime[]
}

export interface RouteExportValidation {
  valid: boolean
  errors: string[]
  warnings: string[]
  summary: {
    route_id: string
    route_short_name: string
    new_stops_count: number
    shape_points_count: number
    trip_patterns_count: number
    service_calendars_count: number
    total_trips: number
    stop_times_per_trip: number
    total_stop_times: number
  }
}

export interface RouteExportTaskResponse {
  task_id: number
  celery_task_id: string
  message: string
}

export const routeCreatorApi = {
  /**
   * Validate route export payload before submitting
   */
  validate: async (payload: RouteExportPayload): Promise<RouteExportValidation> => {
    const response = await api.post('/route-creator/validate', payload)
    return response.data
  },

  /**
   * Export a route from Route Creator to a GTFS feed
   * Returns a task ID for tracking progress
   */
  export: async (payload: RouteExportPayload): Promise<RouteExportTaskResponse> => {
    const response = await api.post('/route-creator/export', { payload })
    return response.data
  },
}
