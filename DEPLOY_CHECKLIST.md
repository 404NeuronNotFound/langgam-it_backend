# Deploy Checklist

## Before Deploying

- [ ] Read `YOU_WERE_RIGHT.md`
- [ ] Read `REAL_ISSUE_FOUND.md`
- [ ] Understand the two issues (CORS + Database)
- [ ] Know what needs to be fixed

## Code Changes Made

- [ ] ✓ CORS configuration fixed (removed trailing slash)
- [ ] ✓ CORS_ALLOW_CREDENTIALS added
- [ ] ✓ requirements.txt fixed
- [ ] ✓ settings_render.py updated
- [ ] ✓ Documentation created

## Deploy CORS Fix

- [ ] Commit changes to GitHub
- [ ] Push to main branch
- [ ] Render automatically detects changes
- [ ] Render starts redeployment
- [ ] Wait 2-3 minutes for deployment
- [ ] Check Render logs for any errors
- [ ] Verify service shows "Live" status

## Test CORS Fix (5 minutes)

- [ ] Go to frontend: https://langgam-it-by-keybeen.vercel.app
- [ ] Open DevTools: Press F12
- [ ] Go to Console tab
- [ ] Try to register a user
- [ ] **Check for CORS errors**
  - [ ] No red errors = ✓ CORS fixed!
  - [ ] Red CORS errors = ✗ Still broken
- [ ] Check Network tab
  - [ ] POST /api/auth/register/ should show 201 Created
  - [ ] Should NOT show 0 or blocked status

## If CORS Test Passes

- [ ] ✓ Frontend can connect to backend
- [ ] ✓ Data is being saved
- [ ] ✓ Registration works
- [ ] ✓ Move to database fix

## If CORS Test Fails

- [ ] Check browser console for exact error
- [ ] Check Render logs for errors
- [ ] Verify CORS_ALLOWED_ORIGINS is correct
- [ ] Verify no trailing slash in frontend URL
- [ ] Try clearing browser cache (Ctrl+Shift+Delete)
- [ ] Try in incognito mode
- [ ] Check if service redeployed successfully

## Set Up Persistent Database (15 minutes)

- [ ] Read `QUICK_START_FIX.md`
- [ ] Choose Supabase (free) or Render Standard ($15/month)
- [ ] Create persistent database
- [ ] Copy connection string/URL
- [ ] Go to Render dashboard
- [ ] Click your backend service
- [ ] Click "Environment"
- [ ] Add/Update `DATABASE_URL` variable
- [ ] Paste connection string
- [ ] Click "Save Changes"
- [ ] Wait 2-3 minutes for redeployment
- [ ] Check Render logs for migrations
- [ ] Verify service shows "Live" status

## Test Database Fix (10 minutes)

- [ ] Register a new user
- [ ] Set up financial profile
- [ ] Note the current time
- [ ] Logout
- [ ] Wait 30+ minutes
- [ ] Try to login with the test user
- [ ] **✓ Account should still exist**
- [ ] **✓ Financial profile should still be there**
- [ ] **✓ All data should be intact**

## If Database Test Passes

- [ ] ✓ Data persists permanently
- [ ] ✓ Users won't lose accounts
- [ ] ✓ App works properly
- [ ] ✓ Ready to tell users it's fixed

## If Database Test Fails

- [ ] Check Render logs for errors
- [ ] Verify DATABASE_URL is set correctly
- [ ] Verify database service is running
- [ ] Check for "relation does not exist" errors
- [ ] Run migrations: `python manage.py migrate`
- [ ] Verify migrations completed successfully

## Final Verification

- [ ] ✓ CORS fix deployed and tested
- [ ] ✓ Database fix deployed and tested
- [ ] ✓ Can register new user
- [ ] ✓ Can set up financial profile
- [ ] ✓ Can logout and login again
- [ ] ✓ Data persists after 30+ minutes
- [ ] ✓ No errors in logs
- [ ] ✓ Frontend and backend connected
- [ ] ✓ App works as expected

## Communicate to Users

- [ ] ✓ All tests pass
- [ ] ✓ Tell users the issue is fixed
- [ ] ✓ Explain what was wrong
- [ ] ✓ Ask them to try registering again
- [ ] ✓ Monitor for any issues

## Post-Deployment Monitoring

- [ ] Check Render logs regularly
- [ ] Monitor for any errors
- [ ] Watch for CORS errors
- [ ] Watch for database connection errors
- [ ] Monitor database usage
- [ ] Check user feedback

## Success Criteria

✓ CORS fix deployed
✓ CORS fix tested and working
✓ Database fix deployed
✓ Database fix tested and working
✓ Frontend can connect to backend
✓ Data persists permanently
✓ App works properly
✓ Users can register and login
✓ No errors in logs

---

**Follow this checklist to ensure everything is deployed correctly.**
