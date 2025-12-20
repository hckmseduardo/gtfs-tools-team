"""
Microsoft Entra ID Authentication API Endpoints

Handles OAuth 2.0 authentication flow with Microsoft Entra ID,
using GET-based redirects (matching PortfolioInvestments pattern).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import timedelta
import secrets
import logging

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.api.deps import get_db
from app.services.entra_auth import entra_auth_service
from app.services.demo_agency_service import create_demo_agency_for_user
from app.models.audit import AuditAction
from app.utils.audit import create_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/entra", tags=["entra-authentication"])


# In-memory state storage (use Redis in production for multi-instance deployments)
_auth_states = {}


def _build_redirect_uri(request: Request) -> str:
    """
    Build the OAuth redirect URI based on the incoming request.

    This allows the app to work with multiple domains.
    """
    # Get the scheme (http/https) - check X-Forwarded-Proto first (from reverse proxy)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)

    # Get the host - check X-Forwarded-Host first, then Host header
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    redirect_uri = f"{scheme}://{host}/api/v1/auth/entra/callback"

    # Validate against allowed redirect URIs
    allowed_uris = settings.entra_allowed_redirect_uris
    if redirect_uri not in allowed_uris:
        logger.warning(f"Redirect URI {redirect_uri} not in allowed list: {allowed_uris}")
        # Fall back to default
        redirect_uri = settings.ENTRA_REDIRECT_URI

    return redirect_uri


@router.get("/login")
async def entra_login(
    request: Request,
    prompt: Optional[str] = Query("select_account", description="Prompt type: select_account, login, consent, or none"),
    redirect_to: Optional[str] = Query(None, description="Frontend URL to redirect after login"),
):
    """
    Initiate Microsoft Entra ID OAuth login flow.

    This endpoint redirects the user directly to Microsoft for authentication.

    Args:
        request: FastAPI request object
        prompt: Controls the authentication experience:
                - select_account: Show account picker (default, recommended)
                - login: Force user to re-enter credentials
                - consent: Force user to grant consent again
                - none: SSO if possible (no prompts)
        redirect_to: Optional frontend URL to redirect after successful login

    Returns:
        Redirect to Microsoft login page
    """
    if not settings.is_entra_configured:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Microsoft Entra ID is not properly configured. Please set ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, and ENTRA_TENANT_ID."
        )

    # Build dynamic redirect URI based on request origin
    redirect_uri = _build_redirect_uri(request)
    logger.info(f"Using redirect URI: {redirect_uri}")

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    _auth_states[state] = {
        "redirect_uri": redirect_uri,
        "redirect_to": redirect_to or "/auth/callback",  # Default to /auth/callback for frontend
        "created_at": timedelta(minutes=10)  # State expires in 10 minutes
    }

    try:
        # Get authorization URL with prompt parameter and dynamic redirect URI
        auth_url, _ = entra_auth_service.get_authorization_url(
            state=state,
            prompt=prompt,
            redirect_uri=redirect_uri
        )

        logger.info(f"Redirecting to Entra ID login (prompt={prompt})")
        return RedirectResponse(url=auth_url)

    except ValueError as e:
        logger.error(f"Error generating auth URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/callback")
async def entra_callback(
    request: Request,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from Microsoft Entra ID.

    This endpoint receives the authorization code from Microsoft and exchanges it
    for tokens, then redirects to the frontend with the JWT token.

    Args:
        request: FastAPI request object
        code: Authorization code from Entra ID
        state: State parameter for CSRF validation
        error: Error code if authentication failed
        error_description: Human-readable error description
        db: Database session

    Returns:
        Redirect to frontend with JWT token, or JSON with token
    """
    # Check for OAuth errors
    if error:
        logger.error(f"Entra ID OAuth error: {error} - {error_description}")
        # Redirect to frontend with error
        return RedirectResponse(url=f"/login?error={error_description or error}")

    # Validate state (CSRF protection)
    state_data = _auth_states.pop(state, None)
    if state_data is None:
        logger.error(f"Invalid or expired state parameter: {state}")
        return RedirectResponse(url="/login?error=Invalid+or+expired+session")

    redirect_uri = state_data.get("redirect_uri", settings.ENTRA_REDIRECT_URI)
    redirect_to = state_data.get("redirect_to", "/auth/callback")

    # Exchange code for token using the same redirect_uri
    logger.info(f"Attempting to exchange authorization code for token with redirect_uri: {redirect_uri}")
    token_response = entra_auth_service.exchange_code_for_token(code, redirect_uri=redirect_uri)

    if not token_response:
        logger.error("Failed to exchange authorization code for token")
        return RedirectResponse(url="/login?error=Failed+to+exchange+code+for+token")

    logger.info("Successfully exchanged code for token, parsing ID token claims")

    # Parse ID token claims
    entra_claims = entra_auth_service.parse_id_token(token_response)

    logger.info(f"Checking required claims - entra_id: {entra_claims.get('entra_id')}, email: {entra_claims.get('email')}")
    if not entra_claims.get("entra_id") or not entra_claims.get("email"):
        logger.error(f"Missing required claims. Available claims: {entra_claims}")
        return RedirectResponse(url="/login?error=Missing+required+claims+from+Entra+ID")

    # Check if user already exists with this Entra ID
    existing_user = await entra_auth_service.find_user_by_entra_id(db, entra_claims["entra_id"])

    if existing_user:
        # User already linked - just log them in
        user = existing_user
        logger.info(f"Existing Entra user logged in: {user.email}")
    else:
        # Check if email already exists (legacy local auth user)
        email_user = await entra_auth_service.find_user_by_email(db, entra_claims["email"])

        if email_user:
            # Link Entra ID to existing user
            if not email_user.azure_ad_object_id:
                logger.info(f"Found existing user with email {email_user.email}, linking Entra ID")
                user = await entra_auth_service.link_entra_to_existing_user(db, email_user, entra_claims)
            else:
                user = email_user
        else:
            # Create new user with Entra ID
            user = await entra_auth_service.create_entra_user(db, entra_claims)
            logger.info(f"New Entra user created: {user.email}")

            # Create demo agency with sample GTFS data for new users
            try:
                await create_demo_agency_for_user(db, user)
            except Exception as e:
                logger.warning(f"Failed to create demo agency for user {user.email}: {e}")

    # Create JWT tokens for our application
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Create audit log for login
    try:
        await create_audit_log(
            db=db,
            user=user,
            action=AuditAction.LOGIN,
            entity_type="auth",
            entity_id=str(user.id),
            description=f"User {user.email} logged in (Entra ID)",
            request=request,
        )
    except Exception as e:
        logger.warning(f"Failed to create audit log: {e}")

    logger.info(f"User {user.email} authenticated successfully")

    # Check Accept header to determine response type
    accept_header = request.headers.get("accept", "")

    if "application/json" in accept_header:
        # Return JSON response for API clients
        return JSONResponse(content={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        })
    else:
        # Redirect to frontend with token in query params
        # Frontend will extract and store the token
        redirect_url = f"{redirect_to}?token={access_token}&refresh_token={refresh_token}"
        return RedirectResponse(url=redirect_url)


@router.get("/config")
async def get_entra_config():
    """
    Get public Entra ID configuration for frontend.

    Returns:
        Public configuration (no secrets)
    """
    return {
        "enabled": settings.is_entra_configured,
        "configured": settings.is_entra_configured,
        "tenant_id": settings.ENTRA_TENANT_ID if settings.is_entra_configured else None,
        "login_url": "/api/v1/auth/entra/login" if settings.is_entra_configured else None,
    }
