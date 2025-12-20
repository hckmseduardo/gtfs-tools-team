# Azure Key Vault Setup Guide

This guide explains how to set up and use Azure Key Vault for secure secrets management in the GTFS Editor application.

## Why Use Azure Key Vault?

Azure Key Vault provides:
- ✅ Centralized secrets management
- ✅ Encryption at rest and in transit
- ✅ Access control and audit logs
- ✅ Automatic secret rotation
- ✅ Secure credential storage (no secrets in code or .env files)
- ✅ Integration with Azure Managed Identity

## Prerequisites

- Azure subscription
- Azure CLI installed (`az --version`)
- Permissions to create Key Vault and assign roles

## Step 1: Create Azure Key Vault

### Using Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Search for "Key vaults" and click **Create**
3. Fill in the details:
   - **Resource group**: Create new or select existing
   - **Key vault name**: `gtfs-tools-keyvault` (must be globally unique)
   - **Region**: Choose your region
   - **Pricing tier**: Standard (or Premium for HSM-backed keys)
4. Go to **Access configuration**:
   - **Permission model**: Select "Vault access policy" or "Azure role-based access control" (RBAC recommended)
5. Click **Review + create** → **Create**

### Using Azure CLI

```bash
# Set variables
RESOURCE_GROUP="gtfs-tools-rg"
LOCATION="eastus"
KEY_VAULT_NAME="gtfs-tools-kv-$(date +%s)"  # Unique name

# Create resource group (if not exists)
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Key Vault
az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --enable-rbac-authorization true  # Use RBAC for access control
```

## Step 2: Add Secrets to Key Vault

### Secret Naming Convention

Azure Key Vault secret names must be:
- Alphanumeric and hyphens only (no underscores)
- Between 1-127 characters

The application automatically converts:
- `DATABASE_URL` → `database-url`
- `SECRET_KEY` → `secret-key`
- `AZURE_AD_CLIENT_SECRET` → `azure-ad-client-secret`

### Add Secrets via Azure Portal

1. Go to your Key Vault → **Secrets**
2. Click **Generate/Import**
3. Add each secret:

| Secret Name | Value Example | Description |
|------------|--------------|-------------|
| `database-url` | `postgresql+asyncpg://user:pass@host:5432/db` | Database connection string |
| `secret-key` | `your-jwt-secret-key-min-32-chars` | JWT signing key |
| `redis-url` | `redis://host:6379/0` | Redis connection string |
| `azure-ad-client-secret` | `abc123...` | Azure AD client secret |
| `azure-b2c-client-secret` | `def456...` | Azure AD B2C client secret |

### Add Secrets via Azure CLI

```bash
KEY_VAULT_NAME="your-keyvault-name"

# Database credentials
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "database-url" \
  --value "postgresql+asyncpg://gtfs_user:gtfs_password@postgres:5432/gtfs_editor"

# JWT secret
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "secret-key" \
  --value "$(openssl rand -base64 32)"

# Azure AD secrets
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "azure-ad-client-secret" \
  --value "your-client-secret"

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "azure-b2c-client-secret" \
  --value "your-b2c-client-secret"

# Redis URL
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "redis-url" \
  --value "redis://redis:6379/0"
```

## Step 3: Configure Access

### Option A: Managed Identity (Recommended for Azure-hosted apps)

If running on Azure App Service, Container Apps, AKS, or Azure VMs:

```bash
# Enable managed identity on your app
az webapp identity assign --name your-app-name --resource-group your-rg

# Grant Key Vault access
az keyvault set-policy \
  --name $KEY_VAULT_NAME \
  --object-id $(az webapp identity show --name your-app-name --resource-group your-rg --query principalId -o tsv) \
  --secret-permissions get list
```

Or with RBAC:
```bash
# Get managed identity principal ID
PRINCIPAL_ID=$(az webapp identity show --name your-app-name --resource-group your-rg --query principalId -o tsv)

# Assign Key Vault Secrets User role
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $PRINCIPAL_ID \
  --scope /subscriptions/<subscription-id>/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME
```

### Option B: Service Principal (For local development or non-Azure)

```bash
# Create service principal
SP_OUTPUT=$(az ad sp create-for-rbac --name "gtfs-tools-sp" --role "Key Vault Secrets User" --scopes /subscriptions/<subscription-id>/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEY_VAULT_NAME)

# Extract values
CLIENT_ID=$(echo $SP_OUTPUT | jq -r '.appId')
CLIENT_SECRET=$(echo $SP_OUTPUT | jq -r '.password')
TENANT_ID=$(echo $SP_OUTPUT | jq -r '.tenant')

echo "Save these credentials securely:"
echo "AZURE_CLIENT_ID=$CLIENT_ID"
echo "AZURE_CLIENT_SECRET=$CLIENT_SECRET"
echo "AZURE_TENANT_ID=$TENANT_ID"
```

## Step 4: Configure Application

### Environment Variables

Update your `.env` file:

```bash
# Enable Key Vault
USE_KEY_VAULT=true
AZURE_KEY_VAULT_URL=https://your-keyvault-name.vault.azure.net/

# Option A: Managed Identity (no credentials needed when running in Azure)
# (No additional variables required)

# Option B: Service Principal (for local development)
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
```

### Docker Compose

Update `docker-compose.yml`:

```yaml
services:
  backend:
    environment:
      # Key Vault configuration
      - USE_KEY_VAULT=true
      - AZURE_KEY_VAULT_URL=https://your-keyvault-name.vault.azure.net/

      # Service Principal auth (for local development)
      - AZURE_TENANT_ID=${AZURE_TENANT_ID}
      - AZURE_CLIENT_ID=${AZURE_CLIENT_ID}
      - AZURE_CLIENT_SECRET=${AZURE_CLIENT_SECRET}

      # Other non-sensitive configs can remain as env vars
      - ENVIRONMENT=development
      - DEBUG=true
```

## Step 5: Migrate Existing Secrets

### Migration Script

Create a script to migrate secrets from `.env` to Key Vault:

```python
# scripts/migrate_to_keyvault.py
import os
from dotenv import load_dotenv
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

load_dotenv()

# Secrets to migrate
SECRETS = [
    "DATABASE_URL",
    "SECRET_KEY",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "AZURE_AD_CLIENT_SECRET",
    "AZURE_B2C_CLIENT_SECRET",
]

vault_url = os.getenv("AZURE_KEY_VAULT_URL")
credential = DefaultAzureCredential()
client = SecretClient(vault_url=vault_url, credential=credential)

for secret_name in SECRETS:
    value = os.getenv(secret_name)
    if value:
        kv_name = secret_name.lower().replace("_", "-")
        client.set_secret(kv_name, value)
        print(f"✓ Migrated {secret_name} → {kv_name}")
    else:
        print(f"✗ Skipped {secret_name} (not found)")

print("\n✅ Migration complete!")
```

Run the migration:
```bash
cd backend
python scripts/migrate_to_keyvault.py
```

## Testing

### Test Key Vault Connection

```python
from app.services.azure_keyvault import keyvault_service

# Check if Key Vault is enabled
print(f"Key Vault enabled: {keyvault_service.is_enabled()}")

# Test retrieving a secret
database_url = keyvault_service.get_secret("DATABASE_URL")
print(f"Database URL: {database_url[:20]}...")  # Print first 20 chars

# List all secrets
secrets = keyvault_service.get_all_secrets()
print(f"Loaded {len(secrets)} secrets from Key Vault")
```

### Verify Application Startup

```bash
# With Key Vault enabled
USE_KEY_VAULT=true python -m app.main

# Should see:
# 🔐 Loading secrets from Azure Key Vault...
# ✓ Azure Key Vault initialized: https://your-vault.vault.azure.net/
```

## Best Practices

1. **Rotation**: Regularly rotate secrets in Key Vault
2. **Audit**: Enable diagnostic logs for Key Vault access
3. **Least Privilege**: Grant only necessary permissions (Secrets User, not Contributor)
4. **Backup**: Enable soft-delete and purge protection
5. **Monitoring**: Set up alerts for secret access and changes

## Troubleshooting

### "Authentication failed"
- Verify managed identity is enabled and has permissions
- Check service principal credentials are correct
- Ensure correct RBAC role assignment

### "Secret not found"
- Verify secret name follows kebab-case convention
- Check secret exists in Key Vault
- Verify permissions to read secrets

### "Connection timeout"
- Check network connectivity to Azure
- Verify Key Vault URL is correct
- Check firewall rules if using private endpoint

## Security Considerations

### DO:
- ✅ Use Managed Identity when running in Azure
- ✅ Enable Key Vault firewall for production
- ✅ Use RBAC instead of access policies
- ✅ Enable soft-delete and purge protection
- ✅ Audit secret access regularly

### DON'T:
- ❌ Store Key Vault credentials in code
- ❌ Use the same service principal for multiple apps
- ❌ Disable audit logging
- ❌ Grant excessive permissions
- ❌ Hardcode Key Vault URLs

## Production Deployment

For production:

1. **Enable Key Vault firewall**: Restrict access to your Azure services only
2. **Use Managed Identity**: No credentials needed when running in Azure
3. **Enable private endpoint**: For enhanced security
4. **Set up alerts**: Monitor for secret access anomalies
5. **Implement rotation**: Automate secret rotation

## References

- [Azure Key Vault Documentation](https://docs.microsoft.com/azure/key-vault/)
- [Managed Identity Overview](https://docs.microsoft.com/azure/active-directory/managed-identities-azure-resources/overview)
- [Key Vault Best Practices](https://docs.microsoft.com/azure/key-vault/general/best-practices)
