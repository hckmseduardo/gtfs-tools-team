#!/usr/bin/env python3
"""
Migrate secrets from .env file to Azure Key Vault

Usage:
    python scripts/migrate_to_keyvault.py

Prerequisites:
    1. Set AZURE_KEY_VAULT_URL in .env or environment
    2. Authenticate with Azure (az login or service principal)
    3. Have Key Vault Secrets Officer or Contributor role
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import AzureError


# Secrets to migrate (sensitive values only)
SECRETS_TO_MIGRATE = [
    "DATABASE_URL",
    "SECRET_KEY",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "AZURE_AD_CLIENT_SECRET",
    "AZURE_B2C_CLIENT_SECRET",
]

# Non-sensitive configuration (keep as environment variables)
NON_SENSITIVE_CONFIG = [
    "ENVIRONMENT",
    "DEBUG",
    "LOG_LEVEL",
    "ALLOWED_HOSTS",
    "CORS_ORIGINS",
    "AZURE_AD_TENANT_ID",
    "AZURE_AD_CLIENT_ID",
    "AZURE_AD_AUTHORITY",
    "AZURE_B2C_TENANT_NAME",
    "AZURE_B2C_TENANT_ID",
    "AZURE_B2C_CLIENT_ID",
    "AZURE_B2C_SIGNUP_SIGNIN_FLOW",
    "AZURE_B2C_PASSWORD_RESET_FLOW",
]


def convert_to_keyvault_name(env_var_name: str) -> str:
    """Convert environment variable name to Key Vault secret name

    Example: DATABASE_URL -> database-url
    """
    return env_var_name.lower().replace("_", "-")


def migrate_secrets(dry_run: bool = False):
    """Migrate secrets from .env to Azure Key Vault"""

    # Load .env file
    load_dotenv()

    vault_url = os.getenv("AZURE_KEY_VAULT_URL")
    if not vault_url:
        print("❌ Error: AZURE_KEY_VAULT_URL not set in .env or environment")
        print("   Please set it to your Key Vault URL (e.g., https://my-vault.vault.azure.net/)")
        sys.exit(1)

    print(f"🔐 Migrating secrets to Azure Key Vault")
    print(f"   Vault: {vault_url}")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    # Initialize Key Vault client
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        print("✓ Authenticated with Azure Key Vault\n")
    except AzureError as e:
        print(f"❌ Failed to authenticate with Azure: {e}")
        print("\n💡 Tips:")
        print("   1. Run 'az login' to authenticate")
        print("   2. Ensure you have Key Vault Secrets Officer role")
        print("   3. Check AZURE_KEY_VAULT_URL is correct")
        sys.exit(1)

    # Migrate secrets
    migrated = []
    skipped = []
    failed = []

    for secret_name in SECRETS_TO_MIGRATE:
        value = os.getenv(secret_name)
        kv_name = convert_to_keyvault_name(secret_name)

        if not value or value == f"your-{secret_name.lower()}":
            skipped.append(secret_name)
            print(f"⊘ Skipped {secret_name} → {kv_name} (not set or placeholder)")
            continue

        if dry_run:
            print(f"✓ Would migrate {secret_name} → {kv_name} (value: {'*' * len(value)})")
            migrated.append(secret_name)
        else:
            try:
                client.set_secret(kv_name, value)
                print(f"✓ Migrated {secret_name} → {kv_name}")
                migrated.append(secret_name)
            except AzureError as e:
                print(f"✗ Failed to migrate {secret_name}: {e}")
                failed.append(secret_name)

    # Summary
    print("\n" + "="*60)
    print("Migration Summary:")
    print(f"  ✓ Migrated: {len(migrated)}")
    print(f"  ⊘ Skipped: {len(skipped)}")
    if failed:
        print(f"  ✗ Failed: {len(failed)}")

    if migrated:
        print("\nMigrated secrets:")
        for secret in migrated:
            print(f"  • {secret}")

    if skipped:
        print("\nSkipped (not set):")
        for secret in skipped:
            print(f"  • {secret}")

    if failed:
        print("\nFailed:")
        for secret in failed:
            print(f"  • {secret}")

    # Next steps
    print("\n" + "="*60)
    if not dry_run and migrated:
        print("✅ Migration complete!")
        print("\nNext steps:")
        print("1. Update your .env file:")
        print("   USE_KEY_VAULT=true")
        print(f"   AZURE_KEY_VAULT_URL={vault_url}")
        print("\n2. Keep non-sensitive config in .env:")
        for config in NON_SENSITIVE_CONFIG:
            value = os.getenv(config)
            if value:
                print(f"   {config}={value}")
        print("\n3. Remove migrated secrets from .env (they're now in Key Vault)")
        print("\n4. Restart your application to load secrets from Key Vault")

        # Generate updated .env content
        print("\n" + "="*60)
        print("Recommended .env file content:")
        print("="*60)
        print("# Key Vault Configuration")
        print("USE_KEY_VAULT=true")
        print(f"AZURE_KEY_VAULT_URL={vault_url}")
        print("\n# Azure Authentication (if using Service Principal)")
        print("# AZURE_TENANT_ID=your-tenant-id")
        print("# AZURE_CLIENT_ID=your-client-id")
        print("# AZURE_CLIENT_SECRET=your-client-secret")
        print("\n# Non-sensitive Configuration")
        for config in NON_SENSITIVE_CONFIG:
            value = os.getenv(config)
            if value:
                print(f"{config}={value}")
        print("\n# Secrets are now in Key Vault!")
        print("# DATABASE_URL, SECRET_KEY, etc. will be fetched automatically")
        print("="*60)
    elif dry_run:
        print("💡 This was a dry run. Run again without --dry-run to actually migrate.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate secrets to Azure Key Vault")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually migrating"
    )

    args = parser.parse_args()

    try:
        migrate_secrets(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
