# Microsoft Entra ID Setup for User Management

This application uses Microsoft Entra ID (Azure AD) for user authentication and management.

## Required Azure AD Application Permissions

To enable user creation through the API, you need to grant the following **Application Permissions** (not delegated):

### Microsoft Graph API Permissions

1. **User.ReadWrite.All**
   - Required for: Creating and managing users
   - Risk level: High
   - Admin consent: Required

2. **Directory.ReadWrite.All** (Optional but recommended)
   - Required for: Full directory access
   - Risk level: High
   - Admin consent: Required

## Setup Steps

### 1. Register Application in Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Click **New registration**
4. Fill in:
   - Name: `GTFS Editor API`
   - Supported account types: Choose based on your needs
   - Redirect URI: `http://localhost:4000/api/v1/auth/azure-ad/callback` (for development)
5. Click **Register**

### 2. Configure Application Permissions

1. In your app registration, go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph**
4. Select **Application permissions** (NOT Delegated permissions)
5. Search and add:
   - `User.ReadWrite.All`
   - `Directory.ReadWrite.All` (optional)
6. Click **Add permissions**
7. **IMPORTANT**: Click **Grant admin consent** for your organization
   - This requires Global Administrator or Privileged Role Administrator

### 3. Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Add description: `API Secret`
4. Select expiration period (recommend: 24 months)
5. Click **Add**
6. **IMPORTANT**: Copy the secret value immediately (you won't be able to see it again)

### 4. Configure Environment Variables

Update your `.env` file with the following values:

```env
# Azure AD Configuration
AZURE_AD_TENANT_ID=<your-tenant-id>
AZURE_AD_CLIENT_ID=<your-client-id>
AZURE_AD_CLIENT_SECRET=<your-client-secret>
```

Find these values:
- **Tenant ID**: App registration > Overview > Directory (tenant) ID
- **Client ID**: App registration > Overview > Application (client) ID
- **Client Secret**: The value you copied in step 3

### 5. Verify Domain Configuration

Users created through the API must have email addresses with valid domains:
- Example: `user@yourdomain.com` or `user@yourcompany.onmicrosoft.com`
- The domain must be verified in your Azure AD tenant

## Testing User Creation

### Using the API Endpoint

```bash
curl -X POST http://localhost:4000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@yourdomain.com",
    "display_name": "New User",
    "password": "TempPassword123!",
    "force_change_password": true
  }'
```

### Expected Response

```json
{
  "id": 1,
  "email": "newuser@yourdomain.com",
  "full_name": "New User",
  "azure_ad_object_id": "abc123-...",
  "is_active": true,
  "message": "User created successfully in Microsoft Entra ID. User must log in through Azure AD OAuth."
}
```

## Authentication Flow

After user creation:

1. **User Registration**: Created in Azure AD with temporary password
2. **First Login**: User must authenticate through Azure AD OAuth:
   - Frontend redirects to Azure AD login
   - User enters email and temporary password
   - Azure AD forces password change (if `force_change_password: true`)
   - User redirected back with authorization code
3. **Token Exchange**: Backend calls `/api/v1/auth/azure-ad/callback` to exchange code for JWT
4. **Subsequent Logins**: User always authenticates through Azure AD OAuth

## Security Considerations

### High-Privilege Permissions

The `User.ReadWrite.All` permission is highly privileged:
- Allows creating, updating, and deleting users
- Should only be granted after security review
- Consider using Conditional Access policies

### Client Secret Protection

- Never commit client secrets to version control
- Rotate secrets regularly (before expiration)
- Use Azure Key Vault in production
- Monitor secret usage in Azure AD audit logs

### Password Policy

Default Azure AD password policy requires:
- Minimum 8 characters
- Mix of uppercase, lowercase, numbers, and symbols
- Cannot contain user's name or email

Customize in: **Azure AD** > **Password reset** > **Authentication methods**

## Troubleshooting

### Error: "Insufficient privileges to complete the operation"

**Solution**: Admin consent not granted. Go to **API permissions** and click **Grant admin consent**.

### Error: "Invalid domain"

**Solution**: The email domain is not verified in Azure AD. Either:
- Verify the domain in Azure AD
- Use `@yourcompany.onmicrosoft.com` domain

### Error: "Application authentication failed"

**Solution**: Check that:
- Client secret is correct and not expired
- Tenant ID is correct
- Client ID is correct

### Error: "Password does not meet complexity requirements"

**Solution**: Ensure password:
- Is at least 8 characters
- Contains uppercase and lowercase letters
- Contains numbers and symbols

## Monitoring

Monitor user creation and authentication in:
- **Azure AD** > **Audit logs**
- **Azure AD** > **Sign-in logs**
- Application logs in your backend

## Production Recommendations

1. **Use Azure Key Vault** for storing secrets
2. **Enable Conditional Access** policies
3. **Configure MFA** for all users
4. **Enable Azure AD Identity Protection**
5. **Set up alerting** for suspicious activities
6. **Regularly review** application permissions
7. **Implement** proper error handling and logging
8. **Use separate** Azure AD app registrations for dev/staging/production

## Resources

- [Microsoft Graph API - Create User](https://learn.microsoft.com/en-us/graph/api/user-post-users)
- [Azure AD App Permissions](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-permissions-and-consent)
- [Secure Application Best Practices](https://learn.microsoft.com/en-us/azure/active-directory/develop/identity-platform-integration-checklist)
