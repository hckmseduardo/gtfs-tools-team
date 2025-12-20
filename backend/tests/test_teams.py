import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_teams_unauthorized():
    """Test that unauthenticated requests return 401."""
    response = client.get("/teams/")
    assert response.status_code == 401


def test_get_teams_with_expired_token(expired_token):
    """Test that expired tokens are rejected."""
    response = client.get(
        "/teams/",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_get_teams_success(auth_headers, test_user_with_team):
    """Test successful teams retrieval."""
    response = client.get("/teams/", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)