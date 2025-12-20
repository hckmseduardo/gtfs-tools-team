"""
Microsoft Entra ID Authentication Service

Handles OAuth 2.0 authentication flow with Microsoft Entra ID (formerly Azure AD)
using the Microsoft Authentication Library (MSAL).

This is the recommended authentication approach, matching the PortfolioInvestments pattern.
"""
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
import msal
import requests
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.base import User

logger = logging.getLogger(__name__)


class EntraAuthService:
    """Service for handling Microsoft Entra ID authentication."""

    def __init__(self):
        """Initialize the Entra Auth Service."""
        self.client_id = settings.ENTRA_CLIENT_ID
        self.client_secret = settings.ENTRA_CLIENT_SECRET
        self.tenant_id = settings.ENTRA_TENANT_ID
        self.authority = settings.entra_authority_url
        self.redirect_uri = settings.ENTRA_REDIRECT_URI
        self.scopes = settings.entra_scopes_list

    def _get_msal_app(self) -> msal.ConfidentialClientApplication:
        """
        Create and return an MSAL Confidential Client Application.

        Returns:
            MSAL application instance

        Raises:
            ValueError: If Entra ID is not properly configured
        """
        if not settings.is_entra_configured:
            raise ValueError(
                "Microsoft Entra ID is not properly configured. "
                "Please set ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, and ENTRA_TENANT_ID."
            )

        return msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
        )

    def get_authorization_url(
        self,
        state: Optional[str] = None,
        prompt: Optional[str] = None,
        redirect_uri: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Generate the authorization URL for Entra ID login.

        Args:
            state: Optional state parameter for CSRF protection
            prompt: Optional prompt parameter (select_account, consent, login, none)
                   - select_account: Forces account selection even if user is signed in
                   - consent: Forces user to grant consent
                   - login: Forces user to enter credentials
                   - none: No interaction (SSO)
            redirect_uri: Optional dynamic redirect URI (defaults to configured value)

        Returns:
            Tuple of (authorization_url, state)
        """
        app = self._get_msal_app()

        # Use provided redirect_uri or fall back to default
        effective_redirect_uri = redirect_uri or self.redirect_uri

        # Build authorization request parameters
        auth_params = {
            "scopes": self.scopes,
            "state": state,
            "redirect_uri": effective_redirect_uri,
        }

        # Add prompt parameter if specified
        if prompt:
            auth_params["prompt"] = prompt

        auth_url = app.get_authorization_request_url(**auth_params)

        logger.info(f"Generated authorization URL for Entra ID login (prompt={prompt}, redirect_uri={effective_redirect_uri})")
        return auth_url, state or ""

    def exchange_code_for_token(self, code: str, redirect_uri: Optional[str] = None) -> Optional[Dict]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from the OAuth callback
            redirect_uri: Optional dynamic redirect URI (must match the one used in authorization)

        Returns:
            Token response dict or None if failed
        """
        app = self._get_msal_app()

        # Use provided redirect_uri or fall back to default
        effective_redirect_uri = redirect_uri or self.redirect_uri

        try:
            result = app.acquire_token_by_authorization_code(
                code,
                scopes=self.scopes,
                redirect_uri=effective_redirect_uri,
            )

            if "error" in result:
                logger.error(
                    f"Error exchanging code for token: {result.get('error')} - "
                    f"{result.get('error_description')}"
                )
                return None

            logger.info(f"Successfully exchanged authorization code for token (redirect_uri={effective_redirect_uri})")
            return result

        except Exception as e:
            logger.error(f"Exception exchanging code for token: {str(e)}")
            return None

    def get_user_info_from_token(self, access_token: str) -> Optional[Dict]:
        """
        Fetch user information from Microsoft Graph API.

        Args:
            access_token: Access token from Entra ID

        Returns:
            User info dict or None if failed
        """
        graph_endpoint = "https://graph.microsoft.com/v1.0/me"

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(graph_endpoint, headers=headers)
            response.raise_for_status()

            user_info = response.json()
            logger.info(f"Retrieved user info from Graph API: {user_info.get('mail') or user_info.get('userPrincipalName')}")
            return user_info

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching user info from Graph API: {str(e)}")
            return None

    def parse_id_token(self, token_response: Dict) -> Dict:
        """
        Parse and extract claims from the ID token.
        If email is not in ID token, fetches it from Microsoft Graph API.

        Args:
            token_response: Token response from MSAL

        Returns:
            Dict with parsed claims
        """
        id_token_claims = token_response.get("id_token_claims", {})

        # Log all available claims for debugging
        logger.info(f"Available ID token claims: {list(id_token_claims.keys())}")
        logger.debug(f"Full ID token claims: {id_token_claims}")

        # Microsoft Entra External ID (CIAM) uses different claim names
        # Try multiple possible claim names for each field
        entra_id = id_token_claims.get("oid") or id_token_claims.get("sub")
        email = (
            id_token_claims.get("email") or
            id_token_claims.get("preferred_username") or
            id_token_claims.get("emails", [None])[0] if isinstance(id_token_claims.get("emails"), list) else None
        )

        # If email is not in ID token, try to get it from Graph API
        if not email and token_response.get("access_token"):
            logger.warning("Email not found in ID token, attempting to fetch from Graph API")
            user_info = self.get_user_info_from_token(token_response["access_token"])
            if user_info:
                email = user_info.get("mail") or user_info.get("userPrincipalName")
                logger.info(f"Successfully fetched email from Graph API: {email}")
            else:
                logger.error("Failed to fetch email from Graph API")

        parsed_claims = {
            "entra_id": entra_id,
            "email": email,
            "name": id_token_claims.get("name"),
            "given_name": id_token_claims.get("given_name"),
            "family_name": id_token_claims.get("family_name"),
            "tenant_id": id_token_claims.get("tid"),
            "email_verified": id_token_claims.get("email_verified", False),
        }

        logger.info(f"Parsed claims - entra_id: {entra_id}, email: {email}")
        return parsed_claims

    async def find_user_by_entra_id(self, db: AsyncSession, entra_id: str) -> Optional[User]:
        """
        Find a user by their Entra ID.

        Args:
            db: Database session
            entra_id: Microsoft Entra ID (Object ID)

        Returns:
            User object or None
        """
        result = await db.execute(
            select(User).where(User.azure_ad_object_id == entra_id)
        )
        return result.scalar_one_or_none()

    async def find_user_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """
        Find a user by their email address.

        Args:
            db: Database session
            email: Email address

        Returns:
            User object or None
        """
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def link_entra_to_existing_user(
        self,
        db: AsyncSession,
        user: User,
        entra_claims: Dict,
    ) -> User:
        """
        Link Entra ID to an existing user account.

        Args:
            db: Database session
            user: Existing user object
            entra_claims: Claims from Entra ID token

        Returns:
            Updated user object
        """
        user.azure_ad_object_id = entra_claims["entra_id"]
        user.azure_ad_tenant_id = entra_claims["tenant_id"]

        await db.commit()
        await db.refresh(user)

        logger.info(f"Linked Entra ID to existing user: {user.email}")
        return user

    async def create_entra_user(
        self,
        db: AsyncSession,
        entra_claims: Dict,
    ) -> User:
        """
        Create a new user from Entra ID authentication.

        Args:
            db: Database session
            entra_claims: Claims from Entra ID token

        Returns:
            New user object
        """
        email = entra_claims["email"]
        if email:
            email = email.lower()

        new_user = User(
            email=email,
            full_name=entra_claims.get("name") or email,
            hashed_password=None,  # No local password
            azure_ad_object_id=entra_claims["entra_id"],
            azure_ad_tenant_id=entra_claims["tenant_id"],
            is_active=True,
            is_superuser=False,
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        logger.info(f"Created new Entra ID user: {new_user.email}")
        return new_user


# Singleton instance
entra_auth_service = EntraAuthService()
