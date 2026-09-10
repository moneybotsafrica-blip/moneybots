#!/usr/bin/env python
"""
Vercel build script for Django deployment.
This script collects static files during the build process.
Database migrations should be run separately against the production database.
"""
import os
import sys
import django

# Set up Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")
django.setup()

def collect_static():
    """Collect static files for production."""
    print("Collecting static files...")
    try:
        from django.core.management import call_command
        call_command("collectstatic", "--noinput", verbosity=1)
        print("✓ Static files collected successfully")
        return True
    except Exception as e:
        print(f"✗ Static files collection error: {e}")
        return False

if __name__ == "__main__":
    # Note: Database migrations are not run during build to avoid failures
    # when database is not available. Run migrations separately:
    # - For Vercel Postgres: Use Vercel's database migration feature
    # - For external Postgres: Run migrate command against production database
    
    print("Build script started (migrations skipped - run separately)")
    
    # Always collect static files
    static_success = collect_static()
    if not static_success:
        sys.exit(1)
    
    print("Build completed successfully")
    print("⚠️  Remember to run database migrations separately against your production database")
    sys.exit(0)
