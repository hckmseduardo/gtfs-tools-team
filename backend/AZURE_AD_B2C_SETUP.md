# Azure AD B2C Setup Guide

Azure AD B2C (Business to Consumer) is Microsoft's customer identity and access management solution for public-facing applications.

## Why Azure AD B2C?

✅ **Accepts any email domain** - Users can register with any email (gmail.com, yahoo.com, etc.)
✅ **Social identity providers** - Google, Facebook, Microsoft Account, Apple, etc.
✅ **Custom branding** - Customize login pages with your brand
✅ **Scalable** - Handles millions of users
✅ **Self-service** - Password reset, profile editing
✅ **MFA support** - Multi-factor authentication built-in

## Key Differences: Azure AD vs Azure AD B2C

| Feature | Azure AD | Azure AD B2C |
|---------|----------|--------------|
| **Target** | Employees/Organizations | Customers/Public |
| **Email Domains** | Verified domains only | Any email domain |
| **User Creation** | Via Graph API | Self-service registration |
| **Social Providers** | No | Yes (Google, Facebook, etc.) |
| **Branding** | Limited | Full customization |
| **Pricing** | Per user/month | Per authentication |

## Setup Steps

### 1. Create Azure AD B2C Tenant

1. Go to [Azure Portal](https://portal.azure.com)
2. Search for "Azure AD B2C" in the top search bar
3. Click **Create Azure AD B2C Tenant**
4. Choose **Create a new Azure AD B2C Tenant**
5. Fill in:
   - **Organization name**: Your company name (e.g., "GTFS Editor")
   - **Initial domain name**: Choose a unique name (e.g., "gtfseditor")
   - **Country/Region**: Select your region
6. Click **Create** (takes 1-2 minutes)
7. Click **Switch to this directory** after creation

> **Important**: B2C tenant is separate from your existing Azure AD tenant!

### 2. Register Your Application

In your B2C tenant:

1. Go to **App registrations** > **New registration**
2. Fill in:
   - **Name**: `GTFS Editor API`
   - **Supported account types**:
     - Select: "Accounts in any identity provider or organizational directory (for authenticating users with user flows)"
   - **Redirect URI**:
     - Platform: `Web`
     - URI: `http://localhost:4000/api/v1/auth/b2c/callback`
3. Click **Register**

### 3. Configure Application

#### 3.1 Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Description: `API Secret`
4. Expires: 24 months
5. Click **Add**
6. **Copy the secret value** immediately!

#### 3.2 Configure Authentication

1. Go to **Authentication**
2. Under **Implicit grant and hybrid flows**, check:
   - ✅ **ID tokens** (used for implicit and hybrid flows)
3. Click **Save**

#### 3.3 Expose API (Optional - for API access)

1. Go to **Expose an API**
2. Click **Set** next to Application ID URI
3. Use default: `https://{tenant}.onmicrosoft.com/{appId}`
4. Click **Save**

### 4. Create User Flows

User flows define the authentication experience (sign-up, sign-in, password reset).

#### 4.1 Create Sign-Up and Sign-In Flow

1. In B2C tenant, go to **User flows**
2. Click **New user flow**
3. Select **Sign up and sign in**
4. Choose version: **Recommended**
5. Fill in:
   - **Name**: `signupsignin1` (becomes `B2C_1_signupsignin1`)
   - **Identity providers**:
     - ✅ **Email signup**
     - Optional: Enable Google, Facebook, Microsoft Account
   - **User attributes and token claims**:
     - Collect during sign-up:
       - ✅ Display Name
       - ✅ Email Address
       - ✅ Given Name (optional)
       - ✅ Surname (optional)
     - Return in token:
       - ✅ Display Name
       - ✅ Email Addresses
       - ✅ User's Object ID
6. Click **Create**

#### 4.2 Create Password Reset Flow (Optional)

1. Click **New user flow**
2. Select **Password reset**
3. Name: `passwordreset1`
4. Identity providers: **Email**
5. User attributes: Email Address
6. Click **Create**

#### 4.3 Create Profile Editing Flow (Optional)

1. Click **New user flow**
2. Select **Profile editing**
3. Name: `profileediting1`
4. Configure attributes users can edit
5. Click **Create**

### 5. Configure Social Identity Providers (Optional)

#### Google

1. Create OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/)
2. In B2C: **Identity providers** > **New OpenID Connect provider**
3. Select **Google**
4. Enter Client ID and Secret from Google
5. Click **Save**

#### Facebook

1. Create app in [Facebook Developers](https://developers.facebook.com/)
2. In B2C: **Identity providers** > **Facebook**
3. Enter App ID and Secret
4. Click **Save**

### 6. Gather Configuration Values

You'll need these values for your application:

```bash
# B2C Tenant Information
B2C_TENANT_NAME=gtfseditor  # Your B2C tenant name (without .onmicrosoft.com)
B2C_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Application Information
B2C_CLIENT_ID=yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
B2C_CLIENT_SECRET=your-client-secret-value

# User Flow Names
B2C_SIGNUP_SIGNIN_FLOW=B2C_1_signupsignin1
B2C_PASSWORD_RESET_FLOW=B2C_1_passwordreset1
B2C_PROFILE_EDIT_FLOW=B2C_1_profileediting1

# Redirect URIs
B2C_REDIRECT_URI=http://localhost:4000/api/v1/auth/b2c/callback
```

**Find these values:**
- **Tenant Name**: `{name}.onmicrosoft.com` (your B2C domain)
- **Tenant ID**: B2C Home > Overview > Tenant ID
- **Client ID**: App registrations > Your app > Application (client) ID
- **Client Secret**: The value you copied earlier

### 7. Update Environment Variables

Update `backend/.env`:

```env
# Azure AD B2C Configuration
AZURE_B2C_TENANT_NAME=gtfseditor
AZURE_B2C_TENANT_ID=your-b2c-tenant-id
AZURE_B2C_CLIENT_ID=your-b2c-client-id
AZURE_B2C_CLIENT_SECRET=your-b2c-client-secret
AZURE_B2C_SIGNUP_SIGNIN_FLOW=B2C_1_signupsignin1
AZURE_B2C_PASSWORD_RESET_FLOW=B2C_1_passwordreset1

# Keep existing Azure AD config for admin users (optional)
AZURE_AD_TENANT_ID=your-existing-tenant-id
AZURE_AD_CLIENT_ID=your-existing-client-id
AZURE_AD_CLIENT_SECRET=your-existing-client-secret
```

## Authentication Flow with B2C

### User Registration/Login

1. **Frontend**: Redirect user to B2C login page
   ```
   https://gtfseditor.b2clogin.com/gtfseditor.onmicrosoft.com/B2C_1_signupsignin1/oauth2/v2.0/authorize
   ```

2. **User**: Enters email and password (or signs in with Google/Facebook)

3. **B2C**: Creates user account automatically on first sign-up

4. **B2C**: Redirects to your callback with authorization code

5. **Backend**: Exchanges code for tokens

6. **Backend**: Gets user info from token claims

7. **Backend**: Creates/updates user in local database

8. **Backend**: Returns JWT tokens for your app

### Key Benefits

- ✅ **No manual user creation** - Users self-register
- ✅ **Any email domain** - No domain restrictions
- ✅ **Password management** - B2C handles password resets
- ✅ **Social login** - Users can use Google, Facebook, etc.
- ✅ **Custom branding** - Add your logo and styling

## Testing B2C Setup

### Test User Flow

1. Go to **User flows** > **B2C_1_signupsignin1**
2. Click **Run user flow**
3. Reply URL: Select your redirect URI
4. Click **Run user flow**
5. You'll see the login page
6. Click **Sign up now** and create a test account
7. After sign-up, you'll be redirected with an authorization code

### Test with API

```bash
# Registration happens through B2C UI flow (not API)
# Users self-register at B2C login page

# After OAuth callback, verify user was created:
curl http://localhost:4000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

## Pricing

Azure AD B2C pricing (as of 2024):
- **Free tier**: 50,000 authentications/month
- **Pay-as-you-go**: $0.00325 per authentication after free tier
- **MFA**: $0.03 per authentication

Example: 100,000 users logging in once per month = $162.50/month

[Azure AD B2C Pricing Details](https://azure.microsoft.com/pricing/details/active-directory-b2c/)

## Security Best Practices

1. **Enable MFA** - Require multi-factor authentication
2. **Configure Conditional Access** - Block suspicious sign-ins
3. **Enable Identity Protection** - Detect risky users and sign-ins
4. **Use HTTPS** - Always use secure connections in production
5. **Rotate secrets** - Change client secrets before expiration
6. **Monitor logs** - Review sign-in logs regularly
7. **Configure CORS** - Only allow your frontend domain

## Migration from Azure AD

If you have existing Azure AD users:

1. **Keep both** - Azure AD for internal/admin, B2C for customers
2. **Or migrate** - Export Azure AD users and import to B2C
3. **Or use B2B** - Invite Azure AD users as guests in B2C

For this project, we recommend **keeping both**:
- Azure AD: Admin users (agency managers)
- Azure AD B2C: Public users (GTFS editors)

## Troubleshooting

### Error: "AADB2C90037: An error occurred while processing the request"

**Solution**: Check user flow configuration and client ID match

### Error: "Invalid redirect URI"

**Solution**: Ensure redirect URI is registered in app authentication settings

### Error: "Invalid client secret"

**Solution**: Verify secret hasn't expired and is correct

### Users can't sign up

**Solution**: Check "Email signup" is enabled in user flow identity providers

## Next Steps

After B2C setup:
1. Update backend code to use B2C endpoints
2. Update frontend to redirect to B2C login
3. Test authentication flow
4. Customize B2C branding (optional)
5. Enable social providers (optional)
6. Deploy to production with production redirect URIs

## Resources

- [Azure AD B2C Documentation](https://learn.microsoft.com/azure/active-directory-b2c/)
- [B2C User Flow Customization](https://learn.microsoft.com/azure/active-directory-b2c/custom-policy-overview)
- [MSAL Python with B2C](https://learn.microsoft.com/azure/active-directory-b2c/enable-authentication-python-web-app)
- [B2C Best Practices](https://learn.microsoft.com/azure/active-directory-b2c/best-practices)
