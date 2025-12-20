from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.team import Team
from app.schemas.team import TeamResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/", response_model=List[TeamResponse])
async def get_teams(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Fetch all teams for the current user."""
    try:
        # Query teams the user belongs to
        teams = db.query(Team).filter(
            Team.members.any(id=current_user.id)
        ).all()
        
        return teams
    except Exception as e:
        logger.error(f"Failed to load teams for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load teams. Please try again later."
        )