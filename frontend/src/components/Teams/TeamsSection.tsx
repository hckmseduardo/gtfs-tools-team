import React, { useEffect, useState } from 'react';
import { getTeams, Team } from '../../services/teamsService';
import { useAuth } from '../../hooks/useAuth';

export const TeamsSection: React.FC = () => {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { logout, refreshToken } = useAuth();

  useEffect(() => {
    loadTeams();
  }, []);

  const loadTeams = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await getTeams();
      setTeams(data);
    } catch (err: any) {
      if (err.message === 'SESSION_EXPIRED') {
        // Attempt token refresh before forcing logout
        const refreshed = await refreshToken();
        if (refreshed) {
          // Retry after refresh
          return loadTeams();
        }
        logout();
        return;
      }
      setError(err.message || 'Failed to load teams');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="teams-loading">Loading teams...</div>;
  }

  if (error) {
    return (
      <div className="teams-error">
        <p>{error}</p>
        <button onClick={loadTeams}>Retry</button>
      </div>
    );
  }

  return (
    <div className="teams-section">
      <h2>Teams</h2>
      {teams.length === 0 ? (
        <p>No teams found. Create or join a team to get started.</p>
      ) : (
        <ul className="teams-list">
          {teams.map((team) => (
            <li key={team.id} className="team-item">
              <span className="team-name">{team.name}</span>
              <span className="team-members">{team.memberCount} members</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};