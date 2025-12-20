"""Authentication endpoints"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_password,
    get_password_hash,
)
from app.db.base import User
from app.models.audit import AuditAction
from app.schemas.auth import (
    Token,
    LoginRequest,
    RegisterRequest,
    EntraIDUserResponse,
    AzureADAuthRequest,
    RefreshTokenRequest,
    UserInfo,
)
from app.services.azure_ad import azure_ad_service
from app.services.microsoft_graph import microsoft_graph_service
from app.services.azure_ad_b2c import azure_b2c_service
from app.services.demo_agency_service import create_demo_agency_for_user
from app.utils.audit import create_audit_log
from app.core.config import settings
from jose import jwt, JWTError

router = APIRouter()


@router.post("/register", response_model=dict, status_code=status.HTTP_200_OK, deprecated=True)
async def register(
    register_data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    [DEPRECATED] User registration - Use Azure AD B2C instead

    For public applications, users should register through Azure AD B2C:
    1. Call GET /api/v1/auth/b2c/authorize to get authorization URL
    2. Redirect user to B2C login/registration page
    3. User self-registers with any email domain
    4. B2C redirects back to your callback with authorization code
    5. Call POST /api/v1/auth/b2c/callback to exchange code for tokens

    This endpoint is deprecated and will be removed in future versions.
    """
    # Return B2C authorization URL instead
    if azure_b2c_service.is_configured():
        auth_url = azure_b2c_service.get_authorization_url(
            redirect_uri="http://localhost:4000/api/v1/auth/b2c/callback"
        )
        return {
            "message": "Please use Azure AD B2C for registration",
            "authorization_url": auth_url,
            "instructions": "Redirect users to this URL for registration and login",
        }

    # Fallback to old behavior if B2C not configured
    if not microsoft_graph_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neither Azure AD B2C nor Microsoft Graph API is configured.",
        )

    # Check if user already exists in local database
    result = await db.execute(select(User).where(User.email == register_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    try:
        # Create user in Azure AD using Microsoft Graph API
        azure_user = await microsoft_graph_service.create_user(
            email=register_data.email,
            display_name=register_data.display_name,
            password=register_data.password,
            force_change_password=register_data.force_change_password,
            account_enabled=True,
        )

        # Create user record in local database
        new_user = User(
            email=register_data.email,
            full_name=register_data.display_name,
            azure_ad_object_id=azure_user["id"],
            azure_ad_tenant_id=microsoft_graph_service.tenant_id,
            is_active=True,
            is_superuser=False,
            hashed_password=None,  # No local password - auth through Entra ID only
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Create demo agency with sample GTFS data for new user
        try:
            await create_demo_agency_for_user(db, new_user)
        except Exception as e:
            # Log but don't fail registration if demo creation fails
            print(f"Warning: Failed to create demo agency for user {new_user.email}: {e}")

        return EntraIDUserResponse(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            azure_ad_object_id=new_user.azure_ad_object_id,
            is_active=new_user.is_active,
            message=f"User created successfully in Microsoft Entra ID. User must log in through Azure AD OAuth.",
        )

    except httpx.HTTPStatusError as e:
        # Handle Graph API errors
        error_detail = "Failed to create user in Microsoft Entra ID"
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", error_detail)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )


@router.post("/login", response_model=Token, deprecated=True)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    [DEPRECATED] Local password login

    This endpoint is deprecated. Users should authenticate through Microsoft Entra ID OAuth.
    Use the /azure-ad/callback endpoint after OAuth flow.

    This endpoint only works for users created before Entra ID migration.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Verify password
    if not user.hashed_password or not verify_password(
        login_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Create JWT tokens
    access_token = create_access_token(subject=user.id)
    refresh_token_str = create_refresh_token(subject=user.id)

    # Create audit log for login
    await create_audit_log(
        db=db,
        user=user,
        action=AuditAction.LOGIN,
        entity_type="auth",
        entity_id=str(user.id),
        description=f"User {user.email} logged in (local)",
        request=request,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer",
    )


@router.post("/azure-ad/callback", response_model=Token)
async def azure_ad_callback(
    auth_request: AzureADAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Handle Azure AD OAuth callback

    Exchange authorization code for access token, get user info,
    and create or update user in the database.
    """
    # Exchange code for token
    token_response = await azure_ad_service.exchange_code_for_token(
        auth_request.code, auth_request.redirect_uri
    )

    # Get user info from Microsoft Graph
    user_info = await azure_ad_service.get_user_info(token_response["access_token"])

    # Get or create user
    azure_object_id = user_info.get("id")
    email = user_info.get("mail") or user_info.get("userPrincipalName")
    display_name = user_info.get("displayName", email)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not retrieve email from Azure AD",
        )

    # Check if user exists
    result = await db.execute(
        select(User).where(User.azure_ad_object_id == azure_object_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Check if user exists with this email
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        is_new_user = False
        if user:
            # Update existing user with Azure AD info
            user.azure_ad_object_id = azure_object_id
            user.azure_ad_tenant_id = azure_ad_service.tenant_id
        else:
            # Create new user
            is_new_user = True
            user = User(
                email=email,
                full_name=display_name,
                azure_ad_object_id=azure_object_id,
                azure_ad_tenant_id=azure_ad_service.tenant_id,
                is_active=True,
                is_superuser=False,
            )
            db.add(user)

        await db.commit()
        await db.refresh(user)

        # Create demo agency with sample GTFS data for new users
        if is_new_user:
            try:
                await create_demo_agency_for_user(db, user)
            except Exception as e:
                print(f"Warning: Failed to create demo agency for user {user.email}: {e}")

    # Create JWT tokens
    access_token = create_access_token(subject=user.id)
    refresh_token_str = create_refresh_token(subject=user.id)

    # Create audit log for Azure AD login
    await create_audit_log(
        db=db,
        user=user,
        action=AuditAction.LOGIN,
        entity_type="auth",
        entity_id=str(user.id),
        description=f"User {user.email} logged in (Azure AD)",
        request=request,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer",
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Refresh access token using refresh token
    """
    # Verify refresh token
    payload = verify_token(refresh_request.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Get user ID
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Verify user exists
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new tokens
    access_token = create_access_token(subject=user.id)
    new_refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserInfo:
    """
    Get current user information
    """
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        azure_ad_object_id=current_user.azure_ad_object_id,
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Logout endpoint (for client-side token deletion)

    Note: JWT tokens are stateless, so logout is handled client-side
    by deleting the token. In a production environment, you might want
    to implement token blacklisting using Redis.
    """
    # Create audit log for logout
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.LOGOUT,
        entity_type="auth",
        entity_id=str(current_user.id),
        description=f"User {current_user.email} logged out",
        request=request,
    )

    return {"message": "Successfully logged out"}


@router.get("/config")
async def get_auth_config() -> dict:
    """
    Get authentication configuration for frontend

    Returns Azure AD and/or B2C configuration if available
    """
    config = {}

    # Azure AD (for admin users)
    if azure_ad_service.is_configured():
        config["azure_ad"] = {
            "enabled": True,
            "tenant_id": azure_ad_service.tenant_id,
            "client_id": azure_ad_service.client_id,
            "authority": azure_ad_service.authority,
        }

    # Azure AD B2C (for public users)
    if azure_b2c_service.is_configured():
        config["azure_b2c"] = {
            "enabled": True,
            "tenant_name": azure_b2c_service.tenant_name,
            "client_id": azure_b2c_service.client_id,
            "authority": azure_b2c_service.authority,
            "signup_signin_flow": azure_b2c_service.signup_signin_flow,
        }

    if not config:
        return {
            "message": "No authentication providers configured",
        }

    return config


# ============================================================================
# Azure AD B2C Endpoints (for public users with any email domain)
# ============================================================================


@router.get("/b2c/authorize")
async def b2c_get_authorization_url(
    redirect_uri: str = "http://localhost:4000/api/v1/auth/b2c/callback",
    state: str = None,
) -> dict:
    """
    Get Azure AD B2C authorization URL for user login/registration

    Frontend should redirect users to this URL for authentication.
    Users can register with any email domain (gmail.com, yahoo.com, etc.)

    Args:
        redirect_uri: Where to redirect after authentication
        state: Optional state parameter for CSRF protection

    Returns:
        Dictionary with authorization URL and instructions
    """
    if not azure_b2c_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure AD B2C is not configured. Please check your settings.",
        )

    try:
        auth_url = azure_b2c_service.get_authorization_url(
            redirect_uri=redirect_uri, state=state
        )

        return {
            "authorization_url": auth_url,
            "redirect_uri": redirect_uri,
            "state": state,
            "instructions": (
                "1. Redirect user to authorization_url\n"
                "2. User registers/logs in with any email\n"
                "3. B2C redirects to your redirect_uri with authorization code\n"
                "4. Call POST /b2c/callback with the code"
            ),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating authorization URL: {str(e)}",
        )


@router.post("/b2c/callback", response_model=Token)
async def b2c_callback(
    auth_request: AzureADAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Handle Azure AD B2C OAuth callback

    Exchange authorization code for tokens and create/update user.
    Users are automatically registered on first login.

    Args:
        auth_request: Contains authorization code and redirect URI

    Returns:
        JWT tokens for your application
    """
    if not azure_b2c_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure AD B2C is not configured",
        )

    try:
        # Exchange code for tokens
        token_response = await azure_b2c_service.exchange_code_for_token(
            auth_request.code, auth_request.redirect_uri
        )

        # Get user info from ID token
        user_info = azure_b2c_service.get_user_info_from_token(
            token_response["id_token"]
        )

        # Get or create user in local database
        azure_object_id = user_info["id"]
        email = user_info["email"]
        display_name = user_info["name"]

        # If email is not in ID token, try UserInfo endpoint
        if not email:
            print("DEBUG: Email not in ID token, trying UserInfo endpoint...")
            try:
                userinfo_data = await azure_b2c_service.get_user_info_from_userinfo_endpoint(
                    token_response["access_token"]
                )
                print(f"DEBUG: UserInfo endpoint response: {userinfo_data}")
                email = (
                    userinfo_data.get("email")
                    or userinfo_data.get("emails", [None])[0]
                    or userinfo_data.get("preferred_username")
                )
            except Exception as e:
                print(f"DEBUG: Failed to get UserInfo: {e}")

        if not email:
            # Fallback: create synthetic email from username or object ID
            # This allows login even if email wasn't collected during External ID registration
            print(f"DEBUG: No email found, creating synthetic email from name or OID")
            username = display_name or azure_object_id
            email = f"{username}@external-id-user.local"
            print(f"DEBUG: Using synthetic email: {email}")
            print(f"WARN: External ID user flow should be configured to collect 'Email Address' in User attributes")

        # Check if user exists by B2C object ID
        result = await db.execute(
            select(User).where(User.azure_ad_object_id == azure_object_id)
        )
        user = result.scalar_one_or_none()

        is_new_user = False
        if user is None:
            # Check if user exists by email
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if user:
                # Link existing user to B2C account
                user.azure_ad_object_id = azure_object_id
                user.azure_ad_tenant_id = azure_b2c_service.tenant_id
            else:
                # Create new user
                is_new_user = True
                user = User(
                    email=email,
                    full_name=display_name,
                    azure_ad_object_id=azure_object_id,
                    azure_ad_tenant_id=azure_b2c_service.tenant_id,
                    is_active=True,
                    is_superuser=False,
                    hashed_password=None,  # No local password - B2C handles auth
                )
                db.add(user)

            await db.commit()
            await db.refresh(user)

            # Create demo agency with sample GTFS data for new users
            if is_new_user:
                try:
                    await create_demo_agency_for_user(db, user)
                except Exception as e:
                    print(f"Warning: Failed to create demo agency for user {user.email}: {e}")

        # Create JWT tokens for your application
        access_token = create_access_token(subject=user.id)
        refresh_token_str = create_refresh_token(subject=user.id)

        # Create audit log for B2C login
        await create_audit_log(
            db=db,
            user=user,
            action=AuditAction.LOGIN,
            entity_type="auth",
            entity_id=str(user.id),
            description=f"User {user.email} logged in (Azure AD B2C)",
            request=request,
        )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
        )

    except httpx.HTTPStatusError as e:
        error_detail = "Failed to authenticate with Azure AD B2C"
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error_description", error_detail)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )


# ============================================================================
# Test Authentication Endpoint (Development/Test only)
# ============================================================================


@router.post("/test-token", response_model=Token)
async def get_test_token(
    email: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Get a test token for automated testing.

    This endpoint is ONLY available in development/test environments.
    It creates or retrieves a test user and returns valid JWT tokens.

    Args:
        email: Email address of the test user

    Returns:
        JWT tokens for the test user
    """
    from app.core.config import settings

    # Only allow in development/test environments
    if settings.ENVIRONMENT not in ("development", "test", "staging"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test authentication is only available in development/test environments",
        )

    # Check if user exists
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    is_new_user = False
    if user is None:
        # Create test user
        is_new_user = True
        user = User(
            email=email,
            full_name=f"Test User ({email.split('@')[0]})",
            is_active=True,
            is_superuser=False,
            hashed_password=None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Create demo agency for new test user
        try:
            await create_demo_agency_for_user(db, user)
        except Exception as e:
            print(f"Warning: Failed to create demo agency for test user {email}: {e}")

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test user account is inactive",
        )

    # Create JWT tokens
    access_token = create_access_token(subject=user.id)
    refresh_token_str = create_refresh_token(subject=user.id)

    # Create audit log for test login
    await create_audit_log(
        db=db,
        user=user,
        action=AuditAction.LOGIN,
        entity_type="auth",
        entity_id=str(user.id),
        description=f"Test user {user.email} logged in (test-token endpoint)",
        request=request,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer",
    )


# ============================================================================
# Cross-Domain SSO Endpoint (Portal Integration)
# ============================================================================


@router.post("/sso", response_model=Token)
async def sso_login(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    SSO login from portal.

    Exchange a cross-domain token from the portal for team-specific JWT tokens.
    This endpoint verifies the token using the shared CROSS_DOMAIN_SECRET,
    creates/syncs the user in the team database, and returns valid tokens.

    Args:
        token: Cross-domain JWT token from portal

    Returns:
        JWT tokens for the team instance
    """
    cross_domain_secret = getattr(settings, 'CROSS_DOMAIN_SECRET', None)
    if not cross_domain_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSO not configured for this team",
        )

    try:
        # Verify the cross-domain token
        payload = jwt.decode(
            token,
            cross_domain_secret,
            algorithms=["HS256"]
        )

        # Validate token type
        if payload.get("type") != "cross_domain":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired SSO token: {str(e)}",
        )

    # Fetch user info from portal
    portal_api_url = getattr(settings, 'PORTAL_API_URL', None)
    if portal_api_url:
        try:
            async with httpx.AsyncClient() as client:
                # Use the cross-domain token to get user info from portal
                response = await client.post(
                    f"{portal_api_url.rstrip('/')}/auth/exchange",
                    params={"token": token}
                )
                if response.status_code == 200:
                    portal_data = response.json()
                    user_info = portal_data.get("user", {})
                    email = user_info.get("email")
                    display_name = user_info.get("display_name", email)
                else:
                    email = None
                    display_name = None
        except Exception as e:
            print(f"Warning: Failed to fetch user info from portal: {e}")
            email = None
            display_name = None
    else:
        email = None
        display_name = None

    if not email:
        # Fallback: use user_id as identifier
        email = f"sso-user-{user_id}@portal.local"
        display_name = f"SSO User ({user_id[:8]})"

    # Check if user exists by portal user ID (stored in azure_ad_object_id field)
    result = await db.execute(
        select(User).where(User.azure_ad_object_id == user_id)
    )
    user = result.scalar_one_or_none()

    is_new_user = False
    if user is None:
        # Check if user exists by email
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            # Link existing user to portal account
            user.azure_ad_object_id = user_id
        else:
            # Create new user
            is_new_user = True
            user = User(
                email=email,
                full_name=display_name,
                azure_ad_object_id=user_id,  # Store portal user ID
                is_active=True,
                is_superuser=False,
                hashed_password=None,
            )
            db.add(user)

        await db.commit()
        await db.refresh(user)

        # Create demo agency for new users
        if is_new_user:
            try:
                await create_demo_agency_for_user(db, user)
            except Exception as e:
                print(f"Warning: Failed to create demo agency for SSO user {email}: {e}")

    # Create JWT tokens for the team
    access_token = create_access_token(subject=user.id)
    refresh_token_str = create_refresh_token(subject=user.id)

    # Create audit log for SSO login
    await create_audit_log(
        db=db,
        user=user,
        action=AuditAction.LOGIN,
        entity_type="auth",
        entity_id=str(user.id),
        description=f"User {user.email} logged in (Portal SSO)",
        request=request,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer",
    )
