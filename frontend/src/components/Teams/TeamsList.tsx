import React, { useEffect, useState } from 'react';
import { teamsService } from '../../services/teamsService';
import { Team } from '../../types/team';
import { useAuth } from '../../hooks/useAuth';

export const TeamsList: React.FC = () => {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { logout } = useAuth();

  useEffect(() => {
    const fetchTeams = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await teamsService.getTeams();
        setTeams(data);
      } catch (err: any) {
        setError(err.message);
        // If session expired, redirect to login
        if (err.message.includes('Session expired')) {
          logout();
        }
      } finally {
        setLoading(false);
      }
    };

    fetchTeams();
  }, [logout]);

  if (loading) {
    return <div className="teams-loading">Loading teams...</div>;
  }

  if (error) {
    return (
      <div className="teams-error">
        <p>{error}</p>
        <button onClick={() => window.location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="teams-list">
      {teams.length === 0 ? (
        <p>No teams found. Create or join a team to get started.</p>
      ) : (
        teams.map((team) => (
          <div key={team.id} className="team-card">
            <h3>{team.name}</h3>
            <p>{team.description}</p>
          </div>
        ))
      )}
    </div>
  );
};