"""Email service supporting SMTP and Microsoft Graph API.

Supports two providers:
- SMTP (office365/protonmail/etc): Uses standard SMTP with TLS
- graph: Uses Microsoft Graph API (requires Azure AD app)

Provider selection via EMAIL_PROVIDER env var:
- "smtp" or "office365" -> SMTP
- "graph" -> Microsoft Graph API
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

import httpx
from msal import ConfidentialClientApplication

from app.core.config import settings

logger = logging.getLogger(__name__)

# Provider selection
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp").lower()

# SMTP settings
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Common settings (from env or settings)
EMAIL_FROM_EMAIL = os.getenv("EMAIL_FROM_EMAIL") or os.getenv("EMAIL_SENDER_ADDRESS")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME") or os.getenv("EMAIL_SENDER_NAME", "GTFS Editor")


class EmailService:
    """Service for sending emails via SMTP or Microsoft Graph API"""

    def __init__(self):
        self._access_token: Optional[str] = None
        self._msal_app: Optional[ConfidentialClientApplication] = None

    def _get_tenant_id(self) -> str:
        """Get tenant ID for email (uses EMAIL_TENANT_ID if set, otherwise AZURE_AD_TENANT_ID)"""
        return getattr(settings, 'EMAIL_TENANT_ID', None) or getattr(settings, 'AZURE_AD_TENANT_ID', None)

    def _get_client_id(self) -> str:
        """Get client ID for email (uses EMAIL_CLIENT_ID if set, otherwise AZURE_AD_CLIENT_ID)"""
        return getattr(settings, 'EMAIL_CLIENT_ID', None) or getattr(settings, 'AZURE_AD_CLIENT_ID', None)

    def _get_client_secret(self) -> str:
        """Get client secret for email (uses EMAIL_CLIENT_SECRET if set, otherwise AZURE_AD_CLIENT_SECRET)"""
        return getattr(settings, 'EMAIL_CLIENT_SECRET', None) or getattr(settings, 'AZURE_AD_CLIENT_SECRET', None)

    def _is_smtp_configured(self) -> bool:
        """Check if SMTP is configured"""
        return bool(EMAIL_FROM_EMAIL and SMTP_USERNAME and SMTP_PASSWORD)

    def _is_graph_configured(self) -> bool:
        """Check if Microsoft Graph is configured"""
        sender = getattr(settings, 'EMAIL_SENDER_ADDRESS', None)
        return bool(
            sender
            and self._get_tenant_id()
            and self._get_client_id()
            and self._get_client_secret()
        )

    def is_enabled(self) -> bool:
        """Check if email service is enabled and configured"""
        enabled = getattr(settings, 'EMAIL_ENABLED', True)
        if not enabled:
            return False

        if EMAIL_PROVIDER in ("smtp", "office365"):
            configured = self._is_smtp_configured()
            logger.info(f"Email provider: SMTP, configured: {configured}")
            return configured
        elif EMAIL_PROVIDER == "graph":
            configured = self._is_graph_configured()
            logger.info(f"Email provider: Graph, configured: {configured}")
            return configured
        else:
            # Default: try SMTP first, then Graph
            if self._is_smtp_configured():
                logger.info("Email provider: auto-detected SMTP")
                return True
            if self._is_graph_configured():
                logger.info("Email provider: auto-detected Graph")
                return True
            return False

    def _get_msal_app(self) -> ConfidentialClientApplication:
        """Get or create MSAL confidential client application"""
        if self._msal_app is None:
            tenant_id = self._get_tenant_id()
            client_id = self._get_client_id()
            client_secret = self._get_client_secret()
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            logger.info(f"Creating MSAL app with tenant: {tenant_id}, client_id: {client_id[:8] if client_id else 'N/A'}...")
            self._msal_app = ConfidentialClientApplication(
                client_id=client_id,
                client_credential=client_secret,
                authority=authority,
            )
        return self._msal_app

    def _get_access_token(self) -> str:
        """Get access token for Microsoft Graph API"""
        msal_app = self._get_msal_app()

        # Try to get token from cache first
        result = msal_app.acquire_token_silent(
            scopes=["https://graph.microsoft.com/.default"],
            account=None,
        )

        if not result:
            # No cached token, acquire new one
            result = msal_app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )

        if "access_token" in result:
            return result["access_token"]
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise Exception(f"Failed to acquire token: {error}")

    def _send_with_smtp(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> bool:
        """Send email using SMTP"""
        if not self._is_smtp_configured():
            logger.error("SMTP is not configured")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((EMAIL_FROM_NAME, EMAIL_FROM_EMAIL))
        msg["To"] = to_email

        # Add plain text part
        if body_text:
            msg.attach(MIMEText(body_text, "plain"))

        # Add HTML part
        msg.attach(MIMEText(body_html, "html"))

        try:
            logger.info(f"Sending email via SMTP to {to_email}")
            logger.info(f"SMTP Host: {SMTP_HOST}:{SMTP_PORT}, From: {EMAIL_FROM_EMAIL}")

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(EMAIL_FROM_EMAIL, [to_email], msg.as_string())

            logger.info(f"Email sent successfully via SMTP to {to_email}")
            return True
        except Exception as e:
            logger.error(f"SMTP error sending email to {to_email}: {e}")
            return False

    async def _send_with_graph(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> bool:
        """Send email using Microsoft Graph API"""
        if not self._is_graph_configured():
            logger.error("Microsoft Graph is not configured")
            return False

        try:
            logger.info(f"Attempting to send email via Graph API to {to_email}")
            logger.info(f"Sender address: {settings.EMAIL_SENDER_ADDRESS}")

            access_token = self._get_access_token()
            logger.info("Access token acquired successfully")

            # Build the email message
            message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": body_html,
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": to_email,
                            }
                        }
                    ],
                    "from": {
                        "emailAddress": {
                            "address": settings.EMAIL_SENDER_ADDRESS,
                            "name": getattr(settings, 'EMAIL_SENDER_NAME', 'GTFS Editor'),
                        }
                    },
                },
                "saveToSentItems": "true",
            }

            # Send via Microsoft Graph API
            url = f"https://graph.microsoft.com/v1.0/users/{settings.EMAIL_SENDER_ADDRESS}/sendMail"
            logger.info(f"Calling Graph API: {url}")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=message,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

            logger.info(f"Graph API response status: {response.status_code}")

            if response.status_code == 202:
                logger.info(f"Email sent successfully via Graph API to {to_email}")
                return True
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {}).get("message", response.text)
                except Exception:
                    pass
                logger.error(f"Failed to send email via Graph API: {response.status_code} - {error_detail}")
                return False

        except Exception as e:
            logger.error(f"Error sending email via Graph API to {to_email}: {e}")
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> bool:
        """
        Send an email using configured provider

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            body_text: Optional plain text body (fallback)

        Returns:
            True if email was sent successfully
        """
        if not self.is_enabled():
            logger.warning("Email service is not enabled or configured")
            return False

        # Determine provider
        if EMAIL_PROVIDER in ("smtp", "office365"):
            return self._send_with_smtp(to_email, subject, body_html, body_text)
        elif EMAIL_PROVIDER == "graph":
            return await self._send_with_graph(to_email, subject, body_html, body_text)
        else:
            # Auto-detect: try SMTP first (simpler), then Graph
            if self._is_smtp_configured():
                return self._send_with_smtp(to_email, subject, body_html, body_text)
            elif self._is_graph_configured():
                return await self._send_with_graph(to_email, subject, body_html, body_text)
            else:
                logger.error("No email provider configured")
                return False

    async def send_team_invitation(
        self,
        to_email: str,
        team_name: str,
        inviter_name: str,
        role: str,
        invitation_token: str,
        expires_at: str,
    ) -> bool:
        """
        Send a team invitation email

        Args:
            to_email: Recipient email address
            team_name: Name of the team
            inviter_name: Name of the person who sent the invitation
            role: Role being offered (e.g., "member", "admin")
            invitation_token: The invitation token for accepting
            expires_at: Human-readable expiration date

        Returns:
            True if email was sent successfully
        """
        # Build accept URL - prefer TEAM_SLUG + DOMAIN for multi-tenant setup
        team_slug = os.getenv('TEAM_SLUG')
        domain = os.getenv('DOMAIN')

        if team_slug and domain:
            # Multi-tenant: build URL from team slug and domain
            frontend_url = f"https://{team_slug}.{domain}"
        else:
            # Fallback to FRONTEND_URL from env or settings
            frontend_url = os.getenv('FRONTEND_URL') or getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

        accept_url = f"{frontend_url}/join?token={invitation_token}"

        subject = f"You've been invited to join {team_name} on GTFS Editor"

        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">Team Invitation</h1>
    </div>

    <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
        <p style="font-size: 16px;">Hello,</p>

        <p style="font-size: 16px;">
            <strong>{inviter_name}</strong> has invited you to join <strong>{team_name}</strong>
            as a <strong style="color: #667eea;">{role}</strong> on GTFS Editor.
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{accept_url}"
               style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                      color: white;
                      padding: 14px 30px;
                      text-decoration: none;
                      border-radius: 5px;
                      font-weight: bold;
                      display: inline-block;">
                Accept Invitation
            </a>
        </div>

        <p style="font-size: 14px; color: #666;">
            This invitation will expire on <strong>{expires_at}</strong>.
        </p>

        <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">

        <p style="font-size: 12px; color: #999;">
            If you didn't expect this invitation, you can safely ignore this email.
        </p>

        <p style="font-size: 12px; color: #999;">
            If the button above doesn't work, copy and paste this link into your browser:<br>
            <a href="{accept_url}" style="color: #667eea; word-break: break-all;">{accept_url}</a>
        </p>
    </div>

    <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
        <p>GTFS Editor - Transit Data Management Platform</p>
    </div>
</body>
</html>
"""

        return await self.send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
        )


# Singleton instance
email_service = EmailService()
