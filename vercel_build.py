#!/usr/bin/env python
"""
Vercel build script for Django deployment.
This script runs database migrations and collects static files during the build process.
"""
import os
import sys
import django

# Set up Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")
django.setup()

def run_migrations():
    """Run Django database migrations."""
    print("Running database migrations...")
    try:
        from django.core.management import call_command
        from django.db import connection
        
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        # Run migrations
        call_command("migrate", "--noinput", verbosity=1)
        print("✓ Migrations completed successfully")
        return True
    except Exception as e:
        print(f"✗ Migration error: {e}")
        return False

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
    # Only run migrations if DATABASE_URL is configured
    if os.getenv("DATABASE_URL"):
        migration_success = run_migrations()
        if not migration_success:
            sys.exit(1)
    else:
        print("Skipping migrations (DATABASE_URL not set)")
    
    # Always collect static files
    static_success = collect_static()
    if not static_success:
        sys.exit(1)
    
    print("Build completed successfully")
    sys.exit(0)
