# Database Persistence Issue - CRITICAL FIX

## Problem

Users register successfully, but after 30 minutes their account and all data disappear. This happens because:

**Render.com's free tier PostgreSQL database is ephemeral** - it gets reset/deleted periodically or when the service restarts.

## Root Cause

1. Free tier databases on Render.com are **not persistent**
2. When the service restarts or after inactivity, the database is wiped
3. New registrations work initially, but data is lost when the database resets
4. Development account persists because it's in local SQLite (which is also not ideal for production)

## Solution: Use Render's Persistent PostgreSQL

### Step 1: Create a Persistent PostgreSQL Database on Render

1. Go to [render.com](https://render.com)
2. Click **"New +"** → **"PostgreSQL"**
3. Fill in:
   - **Name**: `langgamit-db` (or your choice)
   - **Database**: `langgamit_db`
   - **User**: `langgamit_user`
   - **Region**: Same as your backend service
   - **PostgreSQL Version**: 15 or higher
   - **Plan**: **Standard** (NOT free tier - free tier is ephemeral)

4. Click **"Create Database"**
5. Wait for it to be created (5-10 minutes)
6. Copy the **Internal Database URL** (starts with `postgres://`)

### Step 2: Link Database to Your Backend Service

1. Go to your backend service on Render
2. Click **"Environment"** in the left sidebar
3. Add/Update the environment variable:
   - **Key**: `DATABASE_URL`
   - **Value**: Paste the Internal Database URL from Step 1
4. Click **"Save Changes"**
5. Your service will automatically redeploy

### Step 3: Verify the Connection

After redeployment, check the logs:
```
python manage.py migrate
```

You should see migrations running successfully.

### Step 4: Test Data Persistence

1. Register a new user
2. Set up their financial profile
3. Wait 30+ minutes
4. Try to login again - **the account should still exist**

## Why This Fixes It

- **Persistent Storage**: Standard PostgreSQL on Render persists data permanently
- **Automatic Backups**: Render backs up your database automatically
- **Reliable**: Data survives service restarts and redeployments
- **Production-Ready**: This is the proper setup for a production app

## Cost

- **Free tier PostgreSQL**: Ephemeral, gets deleted
- **Standard PostgreSQL**: ~$15/month (includes backups, persistent storage)
- **This is necessary for a working production app**

## Alternative: Use Supabase (Free Tier with Persistence)

If you want to avoid costs, use Supabase's free tier instead:

1. Go to [supabase.com](https://supabase.com)
2. Create a new project
3. Copy the PostgreSQL connection string
4. Add it as `DATABASE_URL` in Render environment variables
5. Redeploy

Supabase free tier includes:
- Persistent PostgreSQL database
- 500MB storage
- Automatic backups
- No data loss

## Deployment Checklist

- [ ] Created persistent PostgreSQL database (not free tier)
- [ ] Added `DATABASE_URL` to Render environment variables
- [ ] Service redeployed successfully
- [ ] Migrations ran without errors
- [ ] Tested registration and login
- [ ] Waited 30+ minutes and verified data still exists
- [ ] Checked logs for any database connection errors

## Troubleshooting

**Error: "could not connect to server"**
- Verify DATABASE_URL is correct
- Check that database service is running on Render
- Ensure backend service is in the same region as database

**Error: "relation does not exist"**
- Run migrations: `python manage.py migrate`
- Check that migrations completed successfully

**Data still disappearing**
- Verify you're using Standard (persistent) PostgreSQL, not free tier
- Check Render logs for database connection issues
- Confirm DATABASE_URL environment variable is set correctly

## Important Notes

1. **Never use free tier databases for production** - they are ephemeral
2. **Always use persistent storage** for user data
3. **Set up automated backups** (Render does this automatically)
4. **Monitor database usage** to avoid unexpected costs

## Next Steps

1. Create persistent PostgreSQL database
2. Update DATABASE_URL environment variable
3. Redeploy your service
4. Run migrations
5. Test thoroughly before telling users the issue is fixed
