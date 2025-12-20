import api from './api';

export interface Team {
  id: string;
  name: string;
  description?: string;
  memberCount: number;
}

export interface TeamsResponse {
  teams: Team[];
}

/**
 * Fetch teams for the current user with proper error handling
 */
export async function getTeams(): Promise<Team[]> {
  try {
    const response = await api.get<Team[]>('/teams/');
    return response.data;
  } catch (error: any) {
    // Handle specific error cases
    if (error.response?.status === 401) {
      // Token expired or invalid - trigger re-authentication
      window.dispatchEvent(new CustomEvent('auth:expired'));
      throw new Error('Session expired. Please log in again.');
    }
    
    if (error.response?.status === 500) {
      throw new Error('Server error loading teams. Please try again later.');
    }
    
    // Network or other errors
    throw new Error(error.message || 'Failed to load teams');
  }
}