# Production Data Loss Issue - Complete Fix Guide

## Executive Summary

**Problem**: Users lose their accounts and data after 30 minutes in production.

**Root Cause**: Using Render.com's free tier PostgreSQL database, which is ephemeral (temporary).

**Solution**: Switch to a persistent database (Render Standard or Supabase).

**Time to Fix**: 15 minutes

**Cost**: $0 (Supabase) or ~$15/month (Render Standard)

---

## The Issue Explained

### What's Happening

1. User registers → Data saved to database ✓
2. User sets up financial profile → Data saved ✓
3. After 30 minutes → User tries to login ✗
4. Account is gone, all data is gone ✗

### Why It Happens

**Free tier PostgreSQL on Render is ephemeral:**
- It's designed for testing, not production
- Gets deleted/reset periodically
- When service restarts, database is wiped
- All user data disappears

### Why Development Works

- Uses local SQLite (`db.sqlite3`)
- SQLite is a file on your computer
- Persists between sessions
- But not suitable for production

---

## The Fix

### Step 1: Choose Your Database

#### Option A: Supabase (Recommended for Free)
- **Cost**: Free (includes 500MB storage)
- **Persistence**: ✓ Permanent
- **Backups**: ✓ Automatic
- **Setup Time**: 10 minutes

#### Option B: Render Standard PostgreSQL
- **Cost**: ~$15/month
- **Persistence**: ✓ Permanent
- **Backups**: ✓ Automatic
- **Setup Time**: 15 minutes

### Step 2: Set Up Your Database

#### Using Supabase

1. Go to https://supabase.com
2. Click **"Sign Up"** and create account
3. Click **"New Project"**
4. Fill in project details
5. Wait for project to be created (2-3 minutes)
6. Go to **Settings** → **Database**
7. Copy the **PostgreSQL Connection String**
8. Go to Render dashboard
9. Click your backend service
10. Click **"Environment"** in left sidebar
11. Click **"Add Environment Variable"**
12. Key: `DATABASE_URL`
13. Value: Paste the Supabase connection string
14. Click **"Save Changes"**
15. Wait for service to redeploy (2-3 minutes)
16. Done!

#### Using Render Standard PostgreSQL

1. Go to https://render.com/dashboard
2. Click **"New +"** → **"PostgreSQL"**
3. Fill in:
   - **Name**: `langgamit-db`
   - **Database**: `langgamit_db`
   - **User**: `langgamit_user`
   - **Region**: Same as your backend service
   - **PostgreSQL Version**: 15 or higher
   - **Plan**: **Standard** (NOT free tier!)
4. Click **"Create Database"**
5. Wait 5-10 minutes for creation
6. Once created, copy the **Internal Database URL**
7. Go to your backend service
8. Click **"Environment"**
9. Add/Update `DATABASE_URL` with the URL
10. Click **"Save Changes"**
11. Wait for redeployment (2-3 minutes)
12. Done!

### Step 3: Verify It Works

1. Go to your app
2. Register a new user
3. Set up their financial profile
4. Note the time
5. Wait 30+ minutes
6. Try to login with that user
7. **✓ Account should still exist with all data**

---

## What Changed in Your Code

I've updated these files to support persistent databases:

### 1. `settings_render.py`
- Added proper PostgreSQL connection handling
- Added connection pooling and health checks
- Added session configuration for database
- Added logging for debugging database issues
- Added fallback to SQLite for local development

### 2. `requirements.txt`
- Fixed corrupted file format

### 3. New Documentation Files
- `URGENT_FIX_INSTRUCTIONS.md` - Quick fix steps
- `DATABASE_PERSISTENCE_FIX.md` - Detailed explanation
- `QUICK_START_FIX.md` - 15-minute quick start
- `check_database.py` - Diagnostic tool

---

## Troubleshooting

### Error: "could not connect to server"

**Cause**: Database URL is incorrect or database isn't running

**Fix**:
1. Verify DATABASE_URL is correct
2. Check that database service is running on Render/Supabase
3. Ensure backend service is in same region as database
4. Check Render logs for connection errors

### Error: "relation does not exist"

**Cause**: Migrations haven't run

**Fix**:
1. Check Render logs - should see "Running migrations"
2. If not, manually run: `python manage.py migrate`
3. Redeploy service

### Data Still Disappearing

**Cause**: Still using free tier database

**Fix**:
1. Verify you're using Standard PostgreSQL (not free tier)
2. Check that DATABASE_URL environment variable is actually set
3. Verify service redeployed after changing DATABASE_URL
4. Check Render logs for any errors

### Service Won't Start After Changing DATABASE_URL

**Cause**: Invalid connection string

**Fix**:
1. Double-check DATABASE_URL is correct
2. Make sure there are no extra spaces or characters
3. Verify database service is running
4. Check Render logs for specific error message

---

## Verification Checklist

After implementing the fix:

- [ ] Persistent database created (Supabase or Render Standard)
- [ ] DATABASE_URL environment variable set in Render
- [ ] Backend service redeployed successfully
- [ ] Render logs show migrations completed
- [ ] Can register a new user
- [ ] Can login with new user
- [ ] Can set up financial profile
- [ ] Waited 30+ minutes
- [ ] Can still login and see all data
- [ ] No database connection errors in logs

---

## Why This Wasn't Caught Earlier

1. **Local development** uses SQLite which persists
2. **Production** was using free tier PostgreSQL which doesn't persist
3. The issue only manifests after 30 minutes (when JWT token expires)
4. Development account was created before this issue, so it persists

---

## Cost Analysis

| Option | Cost | Persistence | Setup Time |
|--------|------|-------------|-----------|
| Render Free | $0 | ✗ Ephemeral | 5 min |
| Supabase Free | $0 | ✓ Permanent | 10 min |
| Render Standard | $15/mo | ✓ Permanent | 15 min |

**Recommendation**: Use Supabase Free tier - it's free and persistent.

---

## Next Steps

1. **Read**: `QUICK_START_FIX.md` (5 minutes)
2. **Choose**: Supabase or Render Standard
3. **Implement**: Follow the setup steps (10-15 minutes)
4. **Test**: Verify data persists after 30+ minutes
5. **Deploy**: Push code changes to production
6. **Communicate**: Tell users the issue is fixed

---

## Important Notes

1. **Never use free tier databases for production** - they are ephemeral
2. **Always use persistent storage** for user data
3. **Set up automated backups** (both Supabase and Render do this)
4. **Monitor database usage** to avoid unexpected costs
5. **Test thoroughly** before telling users the issue is fixed

---

## Support Resources

- Supabase Docs: https://supabase.com/docs
- Render Docs: https://render.com/docs
- Django Database: https://docs.djangoproject.com/en/6.0/ref/settings/#databases

---

**Your app is currently broken. This fix is critical and must be implemented immediately.**

**Users are losing their data. Fix this now.**
