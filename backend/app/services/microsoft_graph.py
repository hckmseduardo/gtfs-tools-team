"""Microsoft Graph API service for user management"""

from typing import Dict, Any, Optional
import httpx
from msal import ConfidentialClientApplication

from app.core.config import settings


class MicrosoftGraphService:
    """Service for interacting with Microsoft Graph API"""

    def __init__(self):
        self.client_id = settings.AZURE_AD_CLIENT_ID
        self.client_secret = settings.AZURE_AD_CLIENT_SECRET
        self.tenant_id = settings.AZURE_AD_TENANT_ID
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"

        # MSAL confidential client for app-only authentication
        self.app = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority,
        ) if self.is_configured() else None

    def is_configured(self) -> bool:
        """Check if Microsoft Graph is properly configured"""
        return bool(
            self.client_id
            and self.client_secret
            and self.tenant_id
            and self.client_id != "your-client-id"
        )

    async def get_app_token(self) -> str:
        """
        Get app-only access token for Microsoft Graph API

        Requires application permissions (not delegated):
        - User.ReadWrite.All
        - Directory.ReadWrite.All

        Returns:
            Access token string
        """
        if not self.is_configured():
            raise ValueError("Microsoft Graph API is not configured")

        # Request token with application permissions
        result = self.app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" in result:
            return result["access_token"]
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise ValueError(f"Failed to acquire token: {error}")

    async def create_user(
        self,
        email: str,
        display_name: str,
        password: str,
        force_change_password: bool = True,
        account_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new user in Azure AD

        Args:
            email: User's email address (will be used as userPrincipalName)
            display_name: User's display name
            password: Initial password for the user
            force_change_password: Whether user must change password on first login
            account_enabled: Whether the account is enabled

        Returns:
            Created user object from Graph API

        Raises:
            httpx.HTTPStatusError: If the API request fails
        """
        token = await self.get_app_token()

        # Extract domain from tenant or use default
        # Note: userPrincipalName must include domain (e.g., user@domain.com)
        if "@" not in email:
            raise ValueError("Email must include domain (e.g., user@yourdomain.com)")

        user_data = {
            "accountEnabled": account_enabled,
            "displayName": display_name,
            "mailNickname": email.split("@")[0],  # Part before @
            "userPrincipalName": email,
            "passwordProfile": {
                "forceChangePasswordNextSignIn": force_change_password,
                "password": password,
            },
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.graph_endpoint}/users",
                json=user_data,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email address

        Args:
            email: User's email address

        Returns:
            User object if found, None otherwise
        """
        token = await self.get_app_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            # Use $filter to find user by userPrincipalName
            response = await client.get(
                f"{self.graph_endpoint}/users",
                params={"$filter": f"userPrincipalName eq '{email}'"},
                headers=headers,
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                users = data.get("value", [])
                return users[0] if users else None

            return None

    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user from Azure AD

        Args:
            user_id: Azure AD user object ID

        Returns:
            True if successful, False otherwise
        """
        token = await self.get_app_token()

        headers = {
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.graph_endpoint}/users/{user_id}",
                headers=headers,
                timeout=30.0,
            )
            return response.status_code == 204

    async def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update user properties in Azure AD

        Args:
            user_id: Azure AD user object ID
            updates: Dictionary of properties to update

        Returns:
            Updated user object
        """
        token = await self.get_app_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.graph_endpoint}/users/{user_id}",
                json=updates,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()

            # PATCH returns 204 No Content on success, so fetch updated user
            if response.status_code == 204:
                get_response = await client.get(
                    f"{self.graph_endpoint}/users/{user_id}",
                    headers=headers,
                    timeout=30.0,
                )
                get_response.raise_for_status()
                return get_response.json()

            return response.json()


# Singleton instance
microsoft_graph_service = MicrosoftGraphService()
