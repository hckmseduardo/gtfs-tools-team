"""Application configuration"""

import os
from typing import List, Union, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get secret from Key Vault or environment variable

    This function is used during Settings initialization to fetch secrets.
    It tries Key Vault first (if enabled), then falls back to environment variables.
    """
    # Check if Key Vault is enabled
    use_keyvault = os.getenv("USE_KEY_VAULT", "false").lower() == "true"

    if use_keyvault:
        try:
            from app.services.azure_keyvault import keyvault_service
            return keyvault_service.get_secret(key, default)
        except ImportError:
            # Key Vault service not available, fall back to env vars
            pass

    # Fall back to environment variable
    return os.getenv(key, default)


class Settings(BaseSettings):
    """Application settings with Azure Key Vault support

    Configuration priority:
    1. Azure Key Vault (if USE_KEY_VAULT=true)
    2. Environment variables (.env file or system environment)
    3. Default values
    """

    # Azure Key Vault Configuration
    USE_KEY_VAULT: bool = Field(
        default=False,
        description="Enable Azure Key Vault for secrets management"
    )
    AZURE_KEY_VAULT_URL: str = Field(
        default="",
        description="Azure Key Vault URL (e.g., https://your-vault.vault.azure.net/)"
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://gtfs_user:gtfs_password@localhost:5432/gtfs_editor",
        description="Database connection URL",
    )
    DATABASE_POOL_SIZE: int = Field(default=20, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(
        default=10, description="Maximum overflow connections"
    )

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis URL")

    # Celery
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2", description="Celery result backend URL"
    )
    CELERY_WORKER_CONCURRENCY: int = Field(
        default=4, description="Number of parallel Celery workers (uses solo pool, spawns N processes)"
    )

    # JWT
    SECRET_KEY: str = Field(
        default="your-secret-key-change-this-in-production",
        description="Secret key for JWT tokens",
    )
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access token expiration in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh token expiration in days"
    )

    # Microsoft Entra ID Configuration (unified approach - same as PortfolioInvestments)
    ENTRA_CLIENT_ID: str = Field(default="", description="Microsoft Entra ID client ID")
    ENTRA_CLIENT_SECRET: str = Field(default="", description="Microsoft Entra ID client secret")
    ENTRA_TENANT_ID: str = Field(default="", description="Microsoft Entra ID tenant ID")
    ENTRA_AUTHORITY: str = Field(default="", description="Microsoft Entra ID authority URL (auto-constructed if not provided)")
    ENTRA_REDIRECT_URI: str = Field(
        default="http://localhost:5173/auth/callback",
        description="Default redirect URI for OAuth callback"
    )
    ENTRA_ALLOWED_REDIRECT_URIS: str = Field(
        default="http://localhost:5173/auth/callback,http://localhost:3000/auth/callback,http://localhost:4000/api/v1/auth/entra/callback",
        description="Comma-separated list of allowed redirect URIs for multi-domain support"
    )
    ENTRA_SCOPES: str = Field(
        default="User.Read",
        description="Comma-separated OAuth scopes (openid, profile, email are automatically added by MSAL)"
    )

    # Legacy Azure AD config (for backward compatibility)
    AZURE_AD_TENANT_ID: str = Field(default="", description="Azure AD tenant ID (legacy, use ENTRA_TENANT_ID)")
    AZURE_AD_CLIENT_ID: str = Field(default="", description="Azure AD client ID (legacy, use ENTRA_CLIENT_ID)")
    AZURE_AD_CLIENT_SECRET: str = Field(default="", description="Azure AD client secret (legacy)")
    AZURE_AD_AUTHORITY: str = Field(default="", description="Azure AD authority URL (legacy)")

    # Legacy Azure AD B2C config (kept for backward compatibility)
    AZURE_B2C_TENANT_NAME: str = Field(default="", description="B2C tenant name (legacy)")
    AZURE_B2C_TENANT_ID: str = Field(default="", description="B2C tenant ID (legacy)")
    AZURE_B2C_CLIENT_ID: str = Field(default="", description="B2C client ID (legacy)")
    AZURE_B2C_CLIENT_SECRET: str = Field(default="", description="B2C client secret (legacy)")
    AZURE_B2C_SIGNUP_SIGNIN_FLOW: str = Field(
        default="B2C_1_signupsignin1", description="B2C sign up/sign in user flow name"
    )
    AZURE_B2C_PASSWORD_RESET_FLOW: str = Field(
        default="B2C_1_passwordreset1", description="B2C password reset user flow name"
    )
    AZURE_B2C_ALLOW_COMMON_TENANT: bool = Field(
        default=False, description="Allow any Microsoft account (common tenant)"
    )
    AZURE_B2C_ENDPOINT_TYPE: str = Field(
        default="tenant",
        description="Endpoint type: 'tenant', 'b2clogin', 'ciamlogin', or 'common'"
    )

    # Email Configuration (Microsoft Graph API)
    EMAIL_ENABLED: bool = Field(default=False, description="Enable email sending via Microsoft Graph")
    EMAIL_SENDER_ADDRESS: str = Field(default="", description="Email sender address (M365 mailbox)")
    EMAIL_SENDER_NAME: str = Field(default="GTFS Editor", description="Email sender display name")
    # Optional: Use separate app registration for email (defaults to Azure AD credentials if not set)
    EMAIL_TENANT_ID: str = Field(default="", description="Tenant ID for email (uses AZURE_AD_TENANT_ID if empty)")
    EMAIL_CLIENT_ID: str = Field(default="", description="Client ID for email (uses AZURE_AD_CLIENT_ID if empty)")
    EMAIL_CLIENT_SECRET: str = Field(default="", description="Client secret for email (uses AZURE_AD_CLIENT_SECRET if empty)")

    # Frontend URL for invitation links
    FRONTEND_URL: str = Field(default="http://localhost:5173", description="Frontend URL for links in emails")

    # Cross-Domain SSO (Portal Integration)
    CROSS_DOMAIN_SECRET: str = Field(
        default="",
        description="Shared secret for cross-domain SSO tokens from portal"
    )
    PORTAL_API_URL: str = Field(
        default="",
        description="Portal API URL for fetching user info during SSO"
    )

    # Application
    ENVIRONMENT: str = Field(default="development", description="Environment name")
    DEBUG: bool = Field(default=True, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    ALLOWED_HOSTS: Union[str, List[str]] = Field(
        default=["localhost", "127.0.0.1"], description="Allowed hosts"
    )

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        description="CORS allowed origins",
    )

    @field_validator("ALLOWED_HOSTS", "CORS_ORIGINS", mode="before")
    @classmethod
    def parse_list_from_string(cls, v):
        """Parse comma-separated string into list"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = Field(default=100, description="Maximum upload size in MB")
    UPLOAD_DIRECTORY: str = Field(
        default="/tmp/gtfs-uploads", description="Upload directory path"
    )

    # Entra ID helper properties (matching PortfolioInvestments pattern)
    @property
    def is_entra_configured(self) -> bool:
        """Check if Microsoft Entra ID is properly configured."""
        return all([
            self.ENTRA_CLIENT_ID,
            self.ENTRA_CLIENT_SECRET,
            self.ENTRA_TENANT_ID,
        ])

    @property
    def entra_authority_url(self) -> str:
        """Get the Entra ID authority URL."""
        if self.ENTRA_AUTHORITY:
            return self.ENTRA_AUTHORITY
        if self.ENTRA_TENANT_ID:
            return f"https://login.microsoftonline.com/{self.ENTRA_TENANT_ID}"
        return ""

    @property
    def entra_scopes_list(self) -> List[str]:
        """Get Entra ID scopes as a list."""
        return [scope.strip() for scope in self.ENTRA_SCOPES.split(",") if scope.strip()]

    @property
    def entra_allowed_redirect_uris(self) -> List[str]:
        """Get allowed Entra ID redirect URIs as a list."""
        return [uri.strip() for uri in self.ENTRA_ALLOWED_REDIRECT_URIS.split(",") if uri.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        """Initialize settings with Key Vault support"""
        # If Key Vault is enabled, pre-load secrets
        use_kv = os.getenv("USE_KEY_VAULT", "false").lower() == "true"

        if use_kv:
            try:
                from app.services.azure_keyvault import keyvault_service
                if keyvault_service.is_enabled():
                    print("🔐 Loading secrets from Azure Key Vault...")
                    # Override kwargs with Key Vault secrets
                    kv_secrets = keyvault_service.get_all_secrets()
                    kwargs.update(kv_secrets)
            except Exception as e:
                print(f"⚠️  Could not load secrets from Key Vault: {e}")
                print("   → Falling back to environment variables")

        super().__init__(**kwargs)


settings = Settings()
