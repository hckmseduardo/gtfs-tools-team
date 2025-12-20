"""Azure Key Vault service for secure configuration management"""

import os
from typing import Optional, Dict, Any
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential


class AzureKeyVaultService:
    """Service for retrieving secrets from Azure Key Vault"""

    def __init__(self):
        self.vault_url = os.getenv("AZURE_KEY_VAULT_URL")
        self.enabled = os.getenv("USE_KEY_VAULT", "false").lower() == "true"
        self.client: Optional[SecretClient] = None
        self._cache: Dict[str, str] = {}

        if self.enabled and self.vault_url:
            self._initialize_client()

    def _initialize_client(self):
        """Initialize Key Vault client with appropriate authentication"""
        try:
            # Option 1: Use Managed Identity or Azure CLI credentials (recommended for Azure-hosted apps)
            # This automatically works when running in Azure (App Service, Container Apps, AKS, etc.)
            credential = DefaultAzureCredential()

            # Option 2: Use Service Principal (for local development or non-Azure environments)
            # Uncomment if you prefer explicit service principal authentication:
            # tenant_id = os.getenv("AZURE_TENANT_ID")
            # client_id = os.getenv("AZURE_CLIENT_ID")
            # client_secret = os.getenv("AZURE_CLIENT_SECRET")
            # if tenant_id and client_id and client_secret:
            #     credential = ClientSecretCredential(
            #         tenant_id=tenant_id,
            #         client_id=client_id,
            #         client_secret=client_secret,
            #     )

            self.client = SecretClient(vault_url=self.vault_url, credential=credential)
            print(f"✓ Azure Key Vault initialized: {self.vault_url}")
        except Exception as e:
            print(f"✗ Failed to initialize Key Vault: {e}")
            self.enabled = False

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret from Key Vault (or environment variable as fallback)

        Args:
            secret_name: Name of the secret in Key Vault (converts to kebab-case automatically)
            default: Default value if secret not found

        Returns:
            Secret value or default

        Example:
            >>> vault = AzureKeyVaultService()
            >>> vault.get_secret("DATABASE_URL", "postgresql://localhost/db")
        """
        # If Key Vault is disabled, fall back to environment variables
        if not self.enabled:
            return os.getenv(secret_name, default)

        # Check cache first
        if secret_name in self._cache:
            return self._cache[secret_name]

        # Convert environment variable name to Key Vault secret name
        # DATABASE_URL -> database-url
        kv_secret_name = secret_name.lower().replace("_", "-")

        try:
            secret = self.client.get_secret(kv_secret_name)
            self._cache[secret_name] = secret.value
            return secret.value
        except Exception as e:
            print(f"Warning: Could not retrieve secret '{kv_secret_name}' from Key Vault: {e}")
            # Fall back to environment variable
            env_value = os.getenv(secret_name, default)
            if env_value:
                print(f"  → Using environment variable for {secret_name}")
            return env_value

    def get_all_secrets(self, prefix: Optional[str] = None) -> Dict[str, str]:
        """
        Get all secrets from Key Vault (optionally filtered by prefix)

        Args:
            prefix: Optional prefix to filter secrets (e.g., "AZURE_AD_")

        Returns:
            Dictionary of secret names to values
        """
        if not self.enabled:
            return {}

        secrets = {}
        try:
            for secret_properties in self.client.list_properties_of_secrets():
                secret_name = secret_properties.name
                # Convert kebab-case to UPPER_SNAKE_CASE
                env_name = secret_name.upper().replace("-", "_")

                if prefix is None or env_name.startswith(prefix):
                    try:
                        secret = self.client.get_secret(secret_name)
                        secrets[env_name] = secret.value
                        self._cache[env_name] = secret.value
                    except Exception as e:
                        print(f"Warning: Could not retrieve secret '{secret_name}': {e}")
        except Exception as e:
            print(f"Error listing secrets from Key Vault: {e}")

        return secrets

    def is_enabled(self) -> bool:
        """Check if Key Vault is enabled and properly configured"""
        return self.enabled and self.client is not None

    def clear_cache(self):
        """Clear the in-memory secret cache"""
        self._cache.clear()


# Singleton instance
keyvault_service = AzureKeyVaultService()
