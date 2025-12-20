"""Azure AD B2C service for customer authentication"""

from typing import Dict, Any, Optional
import httpx
from msal import ConfidentialClientApplication

from app.core.config import settings


class AzureADB2CService:
    """Service for Azure AD B2C authentication"""

    def __init__(self):
        # B2C Configuration
        self.tenant_name = getattr(settings, "AZURE_B2C_TENANT_NAME", None)
        self.tenant_id = getattr(settings, "AZURE_B2C_TENANT_ID", None)
        self.client_id = getattr(settings, "AZURE_B2C_CLIENT_ID", None)
        self.client_secret = getattr(settings, "AZURE_B2C_CLIENT_SECRET", None)
        self.signup_signin_flow = getattr(
            settings, "AZURE_B2C_SIGNUP_SIGNIN_FLOW", "B2C_1_signupsignin1"
        )
        self.allow_common_tenant = getattr(
            settings, "AZURE_B2C_ALLOW_COMMON_TENANT", False
        )
        # Endpoint type: 'b2clogin' (traditional B2C), 'ciamlogin' (External ID), 'common' (Microsoft accounts)
        self.endpoint_type = getattr(
            settings, "AZURE_B2C_ENDPOINT_TYPE", "b2clogin"
        )

        # Determine endpoint type (allow_common_tenant overrides endpoint_type for backwards compatibility)
        if self.allow_common_tenant or self.endpoint_type == "common":
            # Common tenant: allows any Microsoft account (personal + work/school)
            # Uses standard Azure AD endpoints with /common - NO local email/password
            self.authority = "https://login.microsoftonline.com/common"
            self.token_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            self.authorize_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            self.use_graph_api = True  # Use Graph API for user info with common tenant
            self.use_user_flow = False
        elif self.endpoint_type == "ciamlogin" and self.tenant_name and self.tenant_id:
            # Microsoft Entra External ID (ciamlogin.com)
            # External ID uses tenant_id in the path after the domain
            self.authority = f"https://{self.tenant_name}.ciamlogin.com/{self.tenant_id}"
            self.token_endpoint = (
                f"https://{self.tenant_name}.ciamlogin.com/{self.tenant_id}/oauth2/v2.0/token"
            )
            self.authorize_endpoint = (
                f"https://{self.tenant_name}.ciamlogin.com/{self.tenant_id}/oauth2/v2.0/authorize"
            )
            self.use_graph_api = True  # Use Graph API for user info
            self.use_user_flow = False  # External ID doesn't use the 'p' parameter
        elif self.endpoint_type == "tenant" and self.tenant_id:
            # Tenant-specific Azure AD (login.microsoftonline.com/{tenant_id})
            # Supports external identities and self-service sign-up when configured in Azure
            self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            self.token_endpoint = (
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            )
            self.authorize_endpoint = (
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/authorize"
            )
            self.use_graph_api = True
            self.use_user_flow = False
        elif self.tenant_name:
            # Traditional Azure AD B2C (b2clogin.com) - supports email/password local accounts
            self.authority = f"https://{self.tenant_name}.b2clogin.com/{self.tenant_name}.onmicrosoft.com/{self.signup_signin_flow}"
            self.token_endpoint = (
                f"https://{self.tenant_name}.b2clogin.com/{self.tenant_name}.onmicrosoft.com/{self.signup_signin_flow}/oauth2/v2.0/token"
            )
            self.authorize_endpoint = (
                f"https://{self.tenant_name}.b2clogin.com/{self.tenant_name}.onmicrosoft.com/{self.signup_signin_flow}/oauth2/v2.0/authorize"
            )
            self.use_graph_api = False
            self.use_user_flow = False  # User flow is already in the URL path
        else:
            self.use_graph_api = False
            self.use_user_flow = False

        # MSAL app for B2C
        # Initialize if configuration is present
        self.app = None
        can_init = (self.allow_common_tenant or self.tenant_name) and self.client_id and self.client_secret and self.client_id != "your-client-id"
        if can_init:
            try:
                self.app = ConfidentialClientApplication(
                    client_id=self.client_id,
                    client_credential=self.client_secret,
                    authority=self.authority,
                )
            except Exception as e:
                # B2C tenant or user flow might not be fully configured yet
                print(f"Warning: Could not initialize Azure AD B2C client: {e}")
                print("B2C authentication will not be available until properly configured.")

    def is_configured(self) -> bool:
        """Check if B2C is properly configured and MSAL app is initialized"""
        return self.app is not None

    def get_authorization_url(
        self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[list] = None
    ) -> str:
        """
        Get B2C authorization URL for user login/registration

        Args:
            redirect_uri: Where to redirect after authentication
            state: Optional state parameter for CSRF protection
            scopes: Optional list of scopes (defaults to openid and profile)

        Returns:
            Full authorization URL to redirect users to
        """
        if not self.is_configured():
            raise ValueError("Azure AD B2C is not configured")

        if scopes is None:
            if self.allow_common_tenant:
                # For common tenant, we need User.Read to access Graph API for user info
                scopes = ["openid", "profile", "email", "User.Read"]
            else:
                scopes = ["openid", "profile", "email"]

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "prompt": "select_account",  # Force account selection on every login
        }

        # Only add user flow parameter for External ID (ciamlogin) - not for common tenant or traditional B2C
        # Traditional B2C has the user flow in the URL path already
        if self.use_user_flow:
            params["p"] = self.signup_signin_flow  # User flow parameter for External ID

        if state:
            params["state"] = state

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.authorize_endpoint}?{query_string}"

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from B2C
            redirect_uri: Same redirect URI used in authorization request

        Returns:
            Token response with access_token, id_token, etc.

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        if not self.is_configured():
            raise ValueError("Azure AD B2C is not configured")

        # Include User.Read scope for common tenant to access Graph API
        scope = "openid profile email User.Read" if self.allow_common_tenant else "openid profile email"

        token_data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": scope,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    def decode_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Decode B2C ID token to get user information

        B2C returns user information in the ID token claims.
        No need for separate Graph API call.

        Args:
            id_token: JWT ID token from B2C

        Returns:
            Dictionary with user claims (sub, email, name, etc.)
        """
        import jwt

        # B2C tokens can be decoded without validation for reading claims
        # In production, you should validate the signature
        decoded = jwt.decode(id_token, options={"verify_signature": False})
        return decoded

    def get_user_info_from_token(self, id_token: str) -> Dict[str, Any]:
        """
        Extract user information from B2C ID token

        Args:
            id_token: JWT ID token from B2C

        Returns:
            Normalized user info dictionary
        """
        claims = self.decode_id_token(id_token)

        # B2C claim names can vary based on user flow configuration
        # Common claim names: sub, oid, email, name, given_name, family_name
        return {
            "id": claims.get("oid") or claims.get("sub"),  # Object ID
            "email": (
                claims.get("email")
                or claims.get("emails", [None])[0]
                or claims.get("signInNames.emailAddress")
            ),
            "name": claims.get("name") or claims.get("displayName", ""),
            "given_name": claims.get("given_name", ""),
            "family_name": claims.get("family_name", ""),
            "claims": claims,  # Full claims for reference
        }

    async def get_user_info_from_userinfo_endpoint(
        self, access_token: str
    ) -> Dict[str, Any]:
        """
        Get user info from the UserInfo endpoint or Graph API

        For common tenant, uses Microsoft Graph API.
        For External ID, uses the tenant-specific userinfo endpoint.

        Args:
            access_token: Access token from token response

        Returns:
            User information from UserInfo endpoint or Graph API
        """
        if not self.is_configured():
            raise ValueError("Azure AD B2C is not configured")

        if self.allow_common_tenant or self.use_graph_api:
            # Use Microsoft Graph API for common tenant
            userinfo_endpoint = "https://graph.microsoft.com/v1.0/me"
        else:
            userinfo_endpoint = f"https://{self.tenant_name}.ciamlogin.com/{self.tenant_id}/openid/v2.0/userinfo"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            # Normalize Graph API response to match expected format
            if self.allow_common_tenant or self.use_graph_api:
                return {
                    "id": data.get("id"),
                    "email": data.get("mail") or data.get("userPrincipalName"),
                    "name": data.get("displayName", ""),
                    "given_name": data.get("givenName", ""),
                    "family_name": data.get("surname", ""),
                    "raw": data,
                }
            return data

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New token response

        Raises:
            httpx.HTTPStatusError: If refresh fails
        """
        if not self.is_configured():
            raise ValueError("Azure AD B2C is not configured")

        token_data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "scope": "openid profile email offline_access",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()


# Singleton instance
azure_b2c_service = AzureADB2CService()
