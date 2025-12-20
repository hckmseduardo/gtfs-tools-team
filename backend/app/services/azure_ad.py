"""Microsoft Entra ID (Azure AD) OAuth service"""

import httpx
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from app.core.config import settings


class AzureADService:
    """Service for Microsoft Entra ID OAuth authentication"""

    def __init__(self):
        self.tenant_id = settings.AZURE_AD_TENANT_ID
        self.client_id = settings.AZURE_AD_CLIENT_ID
        self.client_secret = settings.AZURE_AD_CLIENT_SECRET
        self.authority = settings.AZURE_AD_AUTHORITY or f"https://login.microsoftonline.com/{self.tenant_id}"
        self.token_endpoint = f"{self.authority}/oauth2/v2.0/token"
        self.user_info_endpoint = "https://graph.microsoft.com/v1.0/me"

    def is_configured(self) -> bool:
        """Check if Azure AD is properly configured"""
        return bool(
            self.tenant_id
            and self.client_id
            and self.client_secret
            and self.tenant_id != "your-tenant-id"
        )

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from Azure AD
            redirect_uri: Redirect URI used in authorization request

        Returns:
            Token response from Azure AD

        Raises:
            HTTPException: If token exchange fails
        """
        if not self.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Azure AD authentication is not configured",
            )

        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid profile email User.Read",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_endpoint,
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Failed to get access token: {response.text}",
                    )

                return response.json()
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Azure AD: {str(e)}",
            )

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from Microsoft Graph API

        Args:
            access_token: Azure AD access token

        Returns:
            User information from Microsoft Graph

        Raises:
            HTTPException: If user info request fails
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.user_info_endpoint,
                    headers=headers,
                )

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Failed to get user info: {response.text}",
                    )

                return response.json()
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Microsoft Graph: {str(e)}",
            )

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token from Azure AD

        Returns:
            New token response

        Raises:
            HTTPException: If token refresh fails
        """
        if not self.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Azure AD authentication is not configured",
            )

        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "openid profile email User.Read",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_endpoint,
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Failed to refresh token: {response.text}",
                    )

                return response.json()
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to Azure AD: {str(e)}",
            )


# Global instance
azure_ad_service = AzureADService()
