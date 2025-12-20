/**
 * GTFS Feed API Client
 */

import { api } from './api'

export interface GTFSFeed {
  id: number
  agency_id: number
  name: string
  description?: string
  version?: string
  imported_at: string
  imported_by?: number
  is_active: boolean
  filename?: string
  total_routes?: number
  total_stops?: number
  total_trips?: number
  created_at: string
  updated_at: string
}

export interface GTFSFeedCreate {
  agency_id: number
  name: string
  description?: string
  version?: string
  filename?: string
}

export interface GTFSFeedUpdate {
  name?: string
  description?: string
  version?: string
  is_active?: boolean
}

export interface GTFSFeedListResponse {
  items: GTFSFeed[]
  feeds: GTFSFeed[]
  total: number
  skip: number
  limit: number
}

export interface GTFSFeedStats {
  feed_id: number
  name: string
  imported_at: string
  is_active: boolean
  stats: {
    routes: number
    stops: number
    trips: number
  }
}

export interface FeedDeletionResponse {
  task_id: number
  celery_task_id: string
  status: string
  message: string
  feed_id: number
  feed_name: string
}

export interface FeedInfo {
  feed_id: number
  feed_publisher_name: string
  feed_publisher_url: string
  feed_lang: string
  default_lang?: string
  feed_start_date?: string
  feed_end_date?: string
  feed_version?: string
  feed_contact_email?: string
  feed_contact_url?: string
  custom_fields?: Record<string, any>
  created_at?: string
  updated_at?: string
}

export interface FeedInfoCreate {
  feed_publisher_name: string
  feed_publisher_url: string
  feed_lang: string
  default_lang?: string
  feed_start_date?: string
  feed_end_date?: string
  feed_version?: string
  feed_contact_email?: string
  feed_contact_url?: string
  custom_fields?: Record<string, any>
}

export interface FeedInfoUpdate {
  feed_publisher_name?: string
  feed_publisher_url?: string
  feed_lang?: string
  default_lang?: string
  feed_start_date?: string
  feed_end_date?: string
  feed_version?: string
  feed_contact_email?: string
  feed_contact_url?: string
  custom_fields?: Record<string, any>
}

export interface FeedCloneResponse {
  task_id: number
  celery_task_id: string
  status: string
  message: string
  source_feed_id: number
  new_name: string
  target_agency_id: number
}

export interface FeedComparisonResult {
  feed1: {
    id: number
    name: string
    imported_at: string
  }
  feed2: {
    id: number
    name: string
    imported_at: string
  }
  comparison: {
    routes: {
      feed1_count: number
      feed2_count: number
      added: number
      removed: number
      common: number
      added_ids: string[]
      removed_ids: string[]
    }
    stops: {
      feed1_count: number
      feed2_count: number
      added: number
      removed: number
      common: number
      added_ids: string[]
      removed_ids: string[]
    }
    trips: {
      feed1_count: number
      feed2_count: number
      added: number
      removed: number
      common: number
    }
    calendars: {
      feed1_count: number
      feed2_count: number
      added: number
      removed: number
      common: number
      added_ids: string[]
      removed_ids: string[]
    }
    shapes: {
      feed1_count: number
      feed2_count: number
      added: number
      removed: number
      common: number
    }
  }
  summary: {
    total_changes: number
    has_changes: boolean
  }
}

export const feedApi = {
  /**
   * Create a new empty GTFS feed from scratch
   */
  async create(data: GTFSFeedCreate): Promise<GTFSFeed> {
    const response = await api.post('/feeds/', data)
    return response.data
  },

  /**
   * List GTFS feeds with optional filtering
   */
  async list(params?: {
    agency_id?: number
    is_active?: boolean
    skip?: number
    limit?: number
  }): Promise<GTFSFeedListResponse> {
    const queryParams = new URLSearchParams()
    if (params?.agency_id) queryParams.append('agency_id', params.agency_id.toString())
    if (params?.is_active !== undefined) queryParams.append('is_active', params.is_active.toString())
    if (params?.skip) queryParams.append('skip', params.skip.toString())
    if (params?.limit) queryParams.append('limit', params.limit.toString())

    const response = await api.get(`/feeds/?${queryParams.toString()}`)
    return response.data
  },

  /**
   * Get a specific feed by ID
   */
  async get(feedId: number): Promise<GTFSFeed> {
    const response = await api.get(`/feeds/${feedId}`)
    return response.data
  },

  /**
   * Update a feed
   */
  async update(feedId: number, data: GTFSFeedUpdate): Promise<GTFSFeed> {
    const response = await api.patch(`/feeds/${feedId}`, data)
    return response.data
  },

  /**
   * Delete a feed (asynchronous operation)
   */
  async delete(feedId: number): Promise<FeedDeletionResponse> {
    const response = await api.delete(`/feeds/${feedId}`)
    return response.data
  },

  /**
   * Activate a feed
   */
  async activate(feedId: number): Promise<GTFSFeed> {
    const response = await api.post(`/feeds/${feedId}/activate`)
    return response.data
  },

  /**
   * Deactivate a feed
   */
  async deactivate(feedId: number): Promise<GTFSFeed> {
    const response = await api.post(`/feeds/${feedId}/deactivate`)
    return response.data
  },

  /**
   * Get feed statistics
   */
  async getStats(feedId: number): Promise<GTFSFeedStats> {
    const response = await api.get(`/feeds/${feedId}/stats`)
    return response.data
  },

  /**
   * Get all feeds for a specific agency
   */
  async getByAgency(agencyId: number, activeOnly: boolean = false): Promise<GTFSFeed[]> {
    const response = await this.list({
      agency_id: agencyId,
      is_active: activeOnly ? true : undefined,
      limit: 1000,
    })
    return response.feeds
  },

  /**
   * Get the active feed for an agency (most recent active feed)
   */
  async getActiveFeed(agencyId: number): Promise<GTFSFeed | null> {
    const feeds = await this.getByAgency(agencyId, true)
    if (feeds.length === 0) return null

    // Return the most recently imported active feed
    return feeds.sort((a, b) =>
      new Date(b.imported_at).getTime() - new Date(a.imported_at).getTime()
    )[0]
  },

  /**
   * Clone a feed (asynchronous operation)
   */
  async clone(feedId: number, newName?: string, targetAgencyId?: number): Promise<FeedCloneResponse> {
    const params = new URLSearchParams()
    if (newName) params.append('new_name', newName)
    if (targetAgencyId) params.append('target_agency_id', targetAgencyId.toString())

    const response = await api.post(`/feeds/${feedId}/clone?${params.toString()}`)
    return response.data
  },

  /**
   * Compare two feeds
   */
  async compare(feedId: number, otherFeedId: number): Promise<FeedComparisonResult> {
    const response = await api.get(`/feeds/${feedId}/compare/${otherFeedId}`)
    return response.data
  },

  /**
   * Get feed info
   */
  async getFeedInfo(feedId: number): Promise<FeedInfo> {
    const response = await api.get(`/feeds/${feedId}/feed-info`)
    return response.data
  },

  /**
   * Create feed info
   */
  async createFeedInfo(feedId: number, data: FeedInfoCreate): Promise<FeedInfo> {
    const response = await api.post(`/feeds/${feedId}/feed-info`, { ...data, feed_id: feedId })
    return response.data
  },

  /**
   * Update feed info
   */
  async updateFeedInfo(feedId: number, data: FeedInfoUpdate): Promise<FeedInfo> {
    const response = await api.patch(`/feeds/${feedId}/feed-info`, { ...data, feed_id: feedId })
    return response.data
  },

  /**
   * Delete feed info
   */
  async deleteFeedInfo(feedId: number): Promise<void> {
    await api.delete(`/feeds/${feedId}/feed-info`)
  },
}
