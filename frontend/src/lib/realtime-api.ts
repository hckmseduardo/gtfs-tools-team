import { api } from './api'

// Types for GTFS-Realtime data
export interface VehiclePosition {
  id: string
  vehicle_id: string
  vehicle_label?: string
  license_plate?: string
  latitude: number
  longitude: number
  bearing?: number
  speed?: number
  trip_id?: string
  route_id?: string
  direction_id?: number
  start_time?: string
  start_date?: string
  current_stop_sequence?: number
  stop_id?: string
  current_status?: 'incoming_at' | 'stopped_at' | 'in_transit_to'
  congestion_level?: string
  occupancy_status?: string
  timestamp?: number
  feed_source_id?: number
  feed_source_name?: string
}

export interface TripUpdate {
  id: string
  trip_id: string
  route_id?: string
  direction_id?: number
  start_time?: string
  start_date?: string
  schedule_relationship?: string
  vehicle_id?: string
  vehicle_label?: string
  delay?: number
  timestamp?: number
  stop_time_updates?: StopTimeUpdate[]
  feed_source_id?: number
  feed_source_name?: string
}

export interface StopTimeUpdate {
  stop_sequence?: number
  stop_id?: string
  arrival_delay?: number
  arrival_time?: number
  departure_delay?: number
  departure_time?: number
}

export interface Alert {
  id: string
  active_periods?: { start?: number; end?: number }[]
  informed_entities?: {
    agency_id?: string
    route_id?: string
    route_type?: number
    stop_id?: string
    trip_id?: string
  }[]
  cause?: string
  effect?: string
  header_text?: Record<string, string>
  description_text?: Record<string, string>
  url?: string
  feed_source_id?: number
  feed_source_name?: string
}

export interface TripModification {
  id: string
  modification_id: string
  trip_id?: string
  route_id?: string
  selected_trips?: {
    trip_ids?: string[]
    shape_id?: string
  }[]
  service_dates?: string[]
  modifications?: {
    start_stop?: { stop_sequence?: number; stop_id?: string }
    end_stop?: { stop_sequence?: number; stop_id?: string }
    propagated_delay?: number
    replacement_stops?: { stop_id?: string; travel_time?: number }[]
    service_alert_id?: string
    last_modified_time?: number
  }[]
  affected_stop_ids?: string[]
  replacement_stops?: { stop_id?: string; travel_time?: number }[]
  feed_source_id?: number
  feed_source_name?: string
}

// Real-time shape for detours
export interface RealtimeShape {
  id: string
  shape_id: string
  encoded_polyline?: string
  shape_points?: { lat: number; lon: number; sequence?: number; dist_traveled?: number }[]
  modification_id?: string
  trip_id?: string
  route_id?: string
  timestamp?: number
  feed_source_id?: number
  feed_source_name?: string
}

// Real-time stop for detours (replacement stops)
export interface RealtimeStop {
  id: string
  stop_id: string
  stop_name?: string
  stop_lat?: number
  stop_lon?: number
  stop_code?: string
  stop_desc?: string
  zone_id?: string
  stop_url?: string
  location_type?: number
  parent_station?: string
  wheelchair_boarding?: number
  platform_code?: string
  modification_id?: string
  route_id?: string
  is_replacement?: boolean
  timestamp?: number
  feed_source_id?: number
  feed_source_name?: string
}

export interface VehiclesResponse {
  agency_id: number
  timestamp: string
  vehicles: VehiclePosition[]
  vehicle_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface TripUpdatesResponse {
  agency_id: number
  timestamp: string
  trip_updates: TripUpdate[]
  trip_update_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface AlertsResponse {
  agency_id: number
  timestamp: string
  alerts: Alert[]
  alert_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface TripModificationsResponse {
  agency_id: number
  timestamp: string
  trip_modifications: TripModification[]
  modification_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface ShapesResponse {
  agency_id: number
  timestamp: string
  shapes: RealtimeShape[]
  shape_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface StopsResponse {
  agency_id: number
  timestamp: string
  stops: RealtimeStop[]
  stop_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface AllRealtimeResponse {
  agency_id: number
  timestamp: string
  vehicles: VehiclePosition[]
  vehicle_count: number
  trip_updates: TripUpdate[]
  trip_update_count: number
  alerts: Alert[]
  alert_count: number
  trip_modifications: TripModification[]
  trip_modification_count: number
  shapes: RealtimeShape[]
  shape_count: number
  stops: RealtimeStop[]
  stop_count: number
  errors?: { feed_source_id: number; feed_source_name: string; error: string }[]
  message?: string
}

export interface FeedSourceTestResponse {
  success: boolean
  feed_source_id: number
  feed_timestamp?: number
  gtfs_realtime_version?: string
  entity_count?: number
  vehicle_count?: number
  trip_update_count?: number
  alert_count?: number
  trip_modification_count?: number
  shape_count?: number
  stop_count?: number
  sample_vehicles?: VehiclePosition[]
  sample_trip_updates?: TripUpdate[]
  sample_alerts?: Alert[]
  sample_trip_modifications?: TripModification[]
  sample_shapes?: RealtimeShape[]
  sample_stops?: RealtimeStop[]
  error?: string
}

// API functions
export const realtimeApi = {
  /**
   * Get real-time vehicle positions for an agency.
   * Fetches data directly from configured GTFS-RT feed sources.
   */
  getVehicles: async (agencyId: number): Promise<VehiclesResponse> => {
    const response = await api.get<VehiclesResponse>(`/realtime/agency/${agencyId}/vehicles`)
    return response.data
  },

  /**
   * Get real-time trip updates for an agency.
   * Fetches data directly from configured GTFS-RT feed sources.
   */
  getTripUpdates: async (agencyId: number): Promise<TripUpdatesResponse> => {
    const response = await api.get<TripUpdatesResponse>(`/realtime/agency/${agencyId}/trip-updates`)
    return response.data
  },

  /**
   * Get real-time service alerts for an agency.
   * Fetches data directly from configured GTFS-RT feed sources.
   */
  getAlerts: async (agencyId: number): Promise<AlertsResponse> => {
    const response = await api.get<AlertsResponse>(`/realtime/agency/${agencyId}/alerts`)
    return response.data
  },

  /**
   * Get real-time trip modifications (detours, service changes) for an agency.
   * Fetches data directly from configured GTFS-RT feed sources.
   * Trip modifications is an experimental GTFS-RT extension for communicating
   * about detours, skipped stops, and other service changes.
   */
  getTripModifications: async (agencyId: number): Promise<TripModificationsResponse> => {
    const response = await api.get<TripModificationsResponse>(`/realtime/agency/${agencyId}/trip-modifications`)
    return response.data
  },

  /**
   * Get real-time shapes (modified/detour shapes) for an agency.
   * Fetches data directly from configured GTFS-RT feed sources.
   * Real-time shapes is an experimental GTFS-RT extension for communicating
   * replacement shapes during detours and service modifications.
   */
  getShapes: async (agencyId: number): Promise<ShapesResponse> => {
    const response = await api.get<ShapesResponse>(`/realtime/agency/${agencyId}/shapes`)
    return response.data
  },

  /**
   * Get real-time stops (replacement/temporary stops) for an agency.
   * Fetches data directly from configured GTFS-RT feed sources.
   * Real-time stops is an experimental GTFS-RT extension for communicating
   * temporary stops during detours and service modifications.
   */
  getStops: async (agencyId: number): Promise<StopsResponse> => {
    const response = await api.get<StopsResponse>(`/realtime/agency/${agencyId}/stops`)
    return response.data
  },

  /**
   * Get all real-time data (vehicles, trip updates, alerts, trip modifications, shapes, stops) for an agency in one call.
   * More efficient than making separate requests.
   */
  getAllRealtimeData: async (agencyId: number): Promise<AllRealtimeResponse> => {
    const response = await api.get<AllRealtimeResponse>(`/realtime/agency/${agencyId}/all`)
    return response.data
  },

  /**
   * Test a GTFS-RT feed source connection and return sample data.
   */
  testFeedSource: async (feedSourceId: number): Promise<FeedSourceTestResponse> => {
    const response = await api.get<FeedSourceTestResponse>(`/realtime/feed-source/${feedSourceId}/test`)
    return response.data
  },
}
