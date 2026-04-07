# Production Authentication Issue - Root Cause & Fix

## Problem Summary

Users were able to register successfully but would lose their credentials after ~30 minutes and get logged out in production.

## Root Cause

The production environment was missing proper **session configuration** for the PostgreSQL database:

1. **Registration worked** because it only writes to the database
2. **But authentication failed after token expiry** because:
   - Django's session middleware wasn't properly configured for PostgreSQL
   - Session data wasn't being persisted to the database
   - When the JWT token expired (30 min), the system couldn't find the user session to refresh it

## The Fix

Added proper session configuration to `settings_render.py`:

```python
# Store sessions in the database (PostgreSQL in production)
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS only in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
```

## What This Does

- **SESSION_ENGINE**: Tells Django to store sessions in the database instead of memory
- **SESSION_COOKIE_AGE**: Sessions last 24 hours before requiring re-authentication
- **SESSION_COOKIE_SECURE**: Only sends cookies over HTTPS in production (security)
- **SESSION_COOKIE_HTTPONLY**: Prevents JavaScript from accessing the session cookie (security)
- **SESSION_COOKIE_SAMESITE**: Prevents CSRF attacks by restricting cross-site cookie access

## Deployment Steps

### 1. Pull the latest code with the fix
```bash
git pull origin main
```

### 2. Run migrations on production database
On Render.com, SSH into your service:
```bash
python manage.py migrate
```

This creates the `django_session` table in PostgreSQL.

### 3. Restart your service
On Render.com, redeploy or restart the service from the dashboard.

## Verification

After deployment, test the fix:

1. **Register a new user**
   ```bash
   curl -X POST https://your-api.onrender.com/api/auth/register/ \
     -H "Content-Type: application/json" \
     -d '{
       "username": "testuser",
       "email": "test@example.com",
       "password": "TestPass123!",
       "confirm_password": "TestPass123!",
       "first_name": "Test",
       "last_name": "User"
     }'
   ```

2. **Get JWT tokens**
   ```bash
   curl -X POST https://your-api.onrender.com/api/auth/token/ \
     -H "Content-Type: application/json" \
     -d '{
       "username": "testuser",
       "password": "TestPass123!"
     }'
   ```

3. **Use the access token to make authenticated requests**
   ```bash
   curl -H "Authorization: Bearer <access_token>" \
     https://your-api.onrender.com/api/me/
   ```

4. **Wait 30+ minutes and try again** - the token should still work because the session is now persisted

## Why This Wasn't Caught Earlier

- **Local development** uses SQLite which handles sessions differently
- **Production** uses PostgreSQL which requires explicit session configuration
- The difference only manifests after token expiry (30 minutes)

## Additional Security Notes

The fix also includes security improvements:
- Sessions are now HTTPS-only in production
- Cookies are protected from JavaScript access
- CSRF protection is enabled via SameSite cookies
