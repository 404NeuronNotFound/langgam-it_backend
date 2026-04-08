#!/usr/bin/env python
"""
Diagnostic script to check database configuration and persistence.
Run this to verify your database setup is correct.

Usage:
    python manage.py shell < check_database.py
    
Or in Django shell:
    exec(open('check_database.py').read())
"""

import os
from django.conf import settings
from django.db import connection
from django.contrib.auth.models import User
from api.models import FinancialProfile

print("\n" + "="*70)
print("DATABASE CONFIGURATION CHECK")
print("="*70)

# 1. Check DATABASE_URL
print("\n1. Environment Variables:")
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Hide password for security
    masked_url = db_url.split("@")[0] + "@***@" + db_url.split("@")[1] if "@" in db_url else "***"
    print(f"   ✓ DATABASE_URL is set: {masked_url}")
else:
    print("   ✗ DATABASE_URL is NOT set (using SQLite)")

# 2. Check current database
print("\n2. Current Database:")
db_engine = settings.DATABASES['default']['ENGINE']
db_name = settings.DATABASES['default'].get('NAME', 'N/A')
print(f"   Engine: {db_engine}")
print(f"   Name: {db_name}")

if 'postgresql' in db_engine:
    print("   ✓ Using PostgreSQL (good for production)")
elif 'sqlite3' in db_engine:
    print("   ⚠ Using SQLite (not recommended for production)")

# 3. Test database connection
print("\n3. Database Connection:")
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    print("   ✓ Database connection successful")
except Exception as e:
    print(f"   ✗ Database connection failed: {e}")
    exit(1)

# 4. Check if tables exist
print("\n4. Database Tables:")
try:
    user_count = User.objects.count()
    profile_count = FinancialProfile.objects.count()
    print(f"   ✓ Users table exists: {user_count} users")
    print(f"   ✓ FinancialProfile table exists: {profile_count} profiles")
except Exception as e:
    print(f"   ✗ Error checking tables: {e}")

# 5. Check session configuration
print("\n5. Session Configuration:")
session_engine = settings.SESSION_ENGINE
print(f"   Session Engine: {session_engine}")
if 'db' in session_engine:
    print("   ✓ Sessions stored in database (good)")
else:
    print("   ⚠ Sessions not stored in database")

# 6. Check JWT configuration
print("\n6. JWT Configuration:")
jwt_config = settings.SIMPLE_JWT
print(f"   Access Token Lifetime: {jwt_config.get('ACCESS_TOKEN_LIFETIME')}")
print(f"   Refresh Token Lifetime: {jwt_config.get('REFRESH_TOKEN_LIFETIME')}")
print(f"   Rotate Refresh Tokens: {jwt_config.get('ROTATE_REFRESH_TOKENS')}")

# 7. Check DEBUG mode
print("\n7. Debug Mode:")
print(f"   DEBUG: {settings.DEBUG}")
if not settings.DEBUG:
    print("   ✓ DEBUG is False (production mode)")
else:
    print("   ⚠ DEBUG is True (development mode)")

# 8. Check ALLOWED_HOSTS
print("\n8. Allowed Hosts:")
for host in settings.ALLOWED_HOSTS:
    print(f"   - {host}")

# 9. Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)

issues = []

if not db_url and 'sqlite3' in db_engine:
    issues.append("❌ Using SQLite in production - data will be lost!")
    issues.append("   → Set DATABASE_URL to a persistent PostgreSQL database")

if 'sqlite3' in db_engine and not settings.DEBUG:
    issues.append("❌ Using SQLite with DEBUG=False - this is a problem")

if settings.DEBUG:
    issues.append("⚠ DEBUG=True - should be False in production")

if not issues:
    print("✓ Database configuration looks good!")
else:
    print("\nIssues found:")
    for issue in issues:
        print(f"  {issue}")

print("\n" + "="*70)
