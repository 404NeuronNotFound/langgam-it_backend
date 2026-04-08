# Test Frontend-Backend Connection

## Quick Test (2 minutes)

### Step 1: Open Your Frontend
Go to: https://langgam-it-by-keybeen.vercel.app

### Step 2: Open Browser Console
Press: **F12** (or right-click → Inspect → Console tab)

### Step 3: Try to Register
1. Click "Register"
2. Fill in form:
   - Username: `testuser123`
   - Email: `test@example.com`
   - Password: `TestPass123!`
   - Confirm: `TestPass123!`
   - First Name: `Test`
   - Last Name: `User`
3. Click "Register"

### Step 4: Check Console for Errors

**Look for red errors like:**
```
Access to XMLHttpRequest at 'https://...' from origin 'https://...' 
has been blocked by CORS policy
```

**If you see this:**
- ❌ Frontend-backend connection is broken
- ✓ The fix I made should resolve it

**If you don't see this:**
- ✓ Frontend-backend connection is working
- Check Network tab for other errors

## Detailed Test (5 minutes)

### Step 1: Check Network Requests

1. Open DevTools (F12)
2. Go to **Network** tab
3. Try to register
4. Look for requests to your backend

**Expected requests:**
- `POST /api/auth/register/` → Status 201 (Created)
- `POST /api/auth/token/` → Status 200 (OK)

**If you see:**
- ❌ Status 0 or blocked = CORS issue
- ❌ Status 403 = CORS issue
- ✓ Status 201 = Working!

### Step 2: Check Response Headers

1. Click on the failed request
2. Go to **Response Headers** tab
3. Look for:
   ```
   Access-Control-Allow-Origin: https://langgam-it-by-keybeen.vercel.app
   ```

**If missing:**
- ❌ CORS not configured
- ✓ The fix should add it

### Step 3: Check Request Headers

1. Click on the request
2. Go to **Request Headers** tab
3. Look for:
   ```
   Origin: https://langgam-it-by-keybeen.vercel.app
   ```

**This should be there automatically.**

## Test Backend Directly

### Using curl

```bash
# Test if backend is running
curl https://your-backend.onrender.com/api/auth/register/

# Should return 405 Method Not Allowed (because we're using GET, not POST)
# This means backend is responding
```

### Using Postman

1. Open Postman
2. Create new request:
   - Method: POST
   - URL: `https://your-backend.onrender.com/api/auth/register/`
   - Headers: `Content-Type: application/json`
   - Body:
     ```json
     {
       "username": "testuser",
       "email": "test@example.com",
       "password": "TestPass123!",
       "confirm_password": "TestPass123!",
       "first_name": "Test",
       "last_name": "User"
     }
     ```
3. Click Send

**Expected response:**
```json
{
  "message": "Account created successfully.",
  "user": {
    "id": 1,
    "username": "testuser",
    "email": "test@example.com",
    ...
  }
}
```

## Verify Data Was Saved

### Check Backend Logs

1. Go to Render dashboard
2. Click your backend service
3. Check logs for:
   - `POST /api/auth/register/` → 201 Created
   - No errors

### Check Database

SSH into Render and run:
```bash
python manage.py shell
```

Then:
```python
from django.contrib.auth.models import User
print(f"Total users: {User.objects.count()}")
for user in User.objects.all():
    print(f"- {user.username}")
```

## Common Issues and Fixes

### Issue: CORS Error in Console

**Error:**
```
Access to XMLHttpRequest blocked by CORS policy
```

**Fix:**
1. Check `CORS_ALLOWED_ORIGINS` in settings
2. Verify frontend URL has no trailing slash
3. Redeploy backend
4. Clear browser cache (Ctrl+Shift+Delete)
5. Try again

### Issue: 404 Not Found

**Error:**
```
POST /api/auth/register/ 404 Not Found
```

**Fix:**
1. Check backend is running
2. Verify API URL is correct
3. Check `api/urls.py` for correct paths
4. Redeploy backend

### Issue: 500 Internal Server Error

**Error:**
```
POST /api/auth/register/ 500 Internal Server Error
```

**Fix:**
1. Check backend logs for error details
2. Verify database is connected
3. Run migrations: `python manage.py migrate`
4. Redeploy backend

### Issue: Network Request Blocked

**Error:**
```
net::ERR_BLOCKED_BY_CLIENT
```

**Fix:**
1. Check browser extensions (ad blockers, etc.)
2. Try in incognito mode
3. Try in different browser
4. Check firewall settings

## Success Criteria

✓ Frontend loads without errors
✓ Can click "Register" button
✓ Form submits without CORS errors
✓ Backend returns 201 Created
✓ User appears in database
✓ Can login with new user
✓ Financial profile can be set up
✓ Data persists after 30+ minutes

## If Everything Works

1. ✓ Frontend-backend connection is working
2. ✓ Data is being saved
3. ✓ The "data loss" issue was CORS-related
4. ✓ The fix I made should resolve it

## If Something Still Doesn't Work

1. Check the error message carefully
2. Look at backend logs
3. Try the detailed test steps above
4. Check `CORS_CONNECTION_FIX.md` for more info

---

**Run this test after deploying the CORS fix.**
