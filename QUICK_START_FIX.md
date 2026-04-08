# Quick Start: Fix Data Loss in 15 Minutes

## The Problem
Users lose their account after 30 minutes. **Cause: Free tier database is ephemeral.**

## The Fix (Pick One)

### ⚡ FASTEST: Supabase (Free)

1. Go to https://supabase.com → Sign up
2. Create new project
3. Go to **Settings** → **Database** → Copy connection string
4. Go to Render dashboard → Your backend service
5. Click **Environment** → Add variable:
   - Key: `DATABASE_URL`
   - Value: Paste Supabase connection string
6. Click **Save Changes** (service redeploys automatically)
7. Wait 2-3 minutes for redeployment
8. **Done!** Test by registering a user

### 💰 RECOMMENDED: Render Standard PostgreSQL

1. Go to https://render.com → Click **New +** → **PostgreSQL**
2. Fill in:
   - Name: `langgamit-db`
   - Database: `langgamit_db`
   - User: `langgamit_user`
   - Region: Same as backend
   - **Plan: Standard** (NOT free!)
3. Click **Create Database**
4. Wait 5-10 minutes
5. Copy **Internal Database URL**
6. Go to Render backend → **Environment**
7. Update `DATABASE_URL` with the URL
8. Click **Save Changes**
9. Wait for redeployment
10. **Done!** Test by registering a user

## Test It Works

1. Register new user
2. Set up financial profile
3. Wait 30+ minutes
4. Try to login
5. **✓ Account should still exist**

## If It Doesn't Work

Check these:
- [ ] DATABASE_URL is set in environment variables
- [ ] Service redeployed after changing DATABASE_URL
- [ ] No errors in Render logs
- [ ] Database service is running (check Render dashboard)

## That's It!

Your data will now persist permanently. Users won't lose their accounts anymore.

---

**Choose Supabase if you want free. Choose Render if you want reliability.**
**Either way, your app will work properly.**
