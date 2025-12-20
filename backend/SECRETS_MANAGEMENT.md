# Secrets Management Guide

## Overview

The GTFS Editor supports two methods for managing secrets:

1. **Environment Variables** (`.env` file) - Simple, good for development
2. **Azure Key Vault** - Secure, recommended for production

## Quick Start

### Development (Using .env)

```bash
# Copy the example
cp .env.example .env

# Edit with your values
nano .env

# Run the application
docker-compose up
```

### Production (Using Key Vault)

```bash
# 1. Create Key Vault
az keyvault create --name gtfs-kv --resource-group gtfs-rg --location eastus

# 2. Migrate secrets
python scripts/migrate_to_keyvault.py

# 3. Enable Key Vault in .env
USE_KEY_VAULT=true
AZURE_KEY_VAULT_URL=https://gtfs-kv.vault.azure.net/

# 4. Deploy with Key Vault enabled
docker-compose up
```

## Security Comparison

| Feature | .env Files | Azure Key Vault |
|---------|-----------|----------------|
| **Security** | ⚠️ Low (plaintext) | ✅ High (encrypted) |
| **Rotation** | ❌ Manual | ✅ Automated |
| **Audit Logs** | ❌ No | ✅ Yes |
| **Access Control** | ⚠️ File permissions | ✅ Azure RBAC |
| **Cost** | ✅ Free | 💰 ~$0.03/10k operations |
| **Setup** | ✅ Simple | ⚠️ Moderate |
| **Best For** | Development | Production |

## What Should Go in Key Vault?

### ✅ Store in Key Vault:
- Database passwords
- JWT secret keys
- Azure AD client secrets
- API keys
- Connection strings with credentials

### ❌ Keep in .env:
- Non-sensitive IDs (tenant IDs, client IDs)
- Configuration flags (DEBUG, ENVIRONMENT)
- URLs (API endpoints, authority URLs)
- Feature flags
- Port numbers

## Secret Naming Convention

| Environment Variable | Key Vault Secret |
|---------------------|------------------|
| `DATABASE_URL` | `database-url` |
| `SECRET_KEY` | `secret-key` |
| `AZURE_AD_CLIENT_SECRET` | `azure-ad-client-secret` |
| `REDIS_URL` | `redis-url` |

The application automatically converts underscore-separated names to kebab-case for Key Vault.

## Authentication Methods

### Managed Identity (Recommended for Azure)

When running in Azure (App Service, Container Apps, AKS):

```bash
# Enable managed identity
az webapp identity assign --name your-app --resource-group your-rg

# Grant access to Key Vault
az keyvault set-policy --name your-kv \
  --object-id $(az webapp identity show --name your-app --resource-group your-rg --query principalId -o tsv) \
  --secret-permissions get list
```

No credentials needed in `.env` - it just works!

### Service Principal (For local development)

```bash
# Create service principal
az ad sp create-for-rbac --name "gtfs-dev-sp" \
  --role "Key Vault Secrets User" \
  --scopes /subscriptions/<sub-id>/resourceGroups/your-rg/providers/Microsoft.KeyVault/vaults/your-kv

# Add to .env
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

## Migration Process

### Step 1: Dry Run

```bash
python scripts/migrate_to_keyvault.py --dry-run
```

This shows what will be migrated without making changes.

### Step 2: Migrate

```bash
python scripts/migrate_to_keyvault.py
```

### Step 3: Update .env

```bash
# Enable Key Vault
USE_KEY_VAULT=true
AZURE_KEY_VAULT_URL=https://your-vault.vault.azure.net/

# Remove sensitive values (now in Key Vault)
# DATABASE_URL=(removed - in Key Vault)
# SECRET_KEY=(removed - in Key Vault)
# AZURE_AD_CLIENT_SECRET=(removed - in Key Vault)

# Keep non-sensitive config
ENVIRONMENT=production
DEBUG=false
AZURE_AD_TENANT_ID=your-tenant-id
AZURE_AD_CLIENT_ID=your-client-id
```

### Step 4: Test

```bash
# Verify Key Vault is working
docker-compose up backend

# Look for:
# 🔐 Loading secrets from Azure Key Vault...
# ✓ Azure Key Vault initialized
```

## Troubleshooting

### "Authentication failed"

**Problem**: Can't connect to Key Vault

**Solutions**:
```bash
# Check Azure login
az login
az account show

# Verify Key Vault URL
echo $AZURE_KEY_VAULT_URL

# Check permissions
az keyvault show --name your-kv --query properties.accessPolicies
```

### "Secret not found"

**Problem**: Secret doesn't exist in Key Vault

**Solutions**:
```bash
# List all secrets
az keyvault secret list --vault-name your-kv --query "[].name"

# Check secret name format (should be kebab-case)
# DATABASE_URL → database-url
# SECRET_KEY → secret-key

# Add missing secret
az keyvault secret set --vault-name your-kv --name database-url --value "postgresql://..."
```

### "Falls back to environment variables"

**Problem**: Key Vault is enabled but not working

**Check**:
1. Is `USE_KEY_VAULT=true`?
2. Is `AZURE_KEY_VAULT_URL` set correctly?
3. Are you authenticated (`az login`)?
4. Do you have permissions on the Key Vault?

## Best Practices

### DO:
- ✅ Use Key Vault for production
- ✅ Enable soft-delete and purge protection
- ✅ Rotate secrets regularly
- ✅ Use Managed Identity when in Azure
- ✅ Monitor access logs
- ✅ Use different Key Vaults for dev/staging/prod

### DON'T:
- ❌ Commit .env with real secrets
- ❌ Share Key Vault credentials
- ❌ Use same secrets across environments
- ❌ Disable audit logging
- ❌ Grant excessive permissions

## Performance

Key Vault integration includes:
- **Caching**: Secrets are cached in memory after first fetch
- **Fallback**: Falls back to .env if Key Vault is unavailable
- **Lazy Loading**: Only fetches secrets when needed
- **Batch Loading**: Fetches all secrets at startup if enabled

Typical overhead: ~100-200ms at startup, then cached.

## Cost Estimation

Azure Key Vault pricing (as of 2024):
- **Storage**: $0.03 per 10,000 transactions
- **Secrets**: No additional cost
- **Managed HSM**: Premium tier available

For a typical application:
- Startup: 5-10 secret reads
- Runtime: Cached (no additional reads)
- **Estimated cost**: < $1/month for most applications

## References

- [Full Setup Guide](AZURE_KEY_VAULT_SETUP.md)
- [Azure Key Vault Documentation](https://docs.microsoft.com/azure/key-vault/)
- [Best Practices](https://docs.microsoft.com/azure/key-vault/general/best-practices)

## Support

Questions? Check:
1. [AZURE_KEY_VAULT_SETUP.md](AZURE_KEY_VAULT_SETUP.md) - Detailed setup guide
2. [Azure Key Vault troubleshooting](https://docs.microsoft.com/azure/key-vault/general/troubleshooting)
3. Project issues on GitHub
