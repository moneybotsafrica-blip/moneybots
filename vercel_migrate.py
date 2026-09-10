#!/usr/bin/env python
"""
Vercel migration script for running Django migrations against production database.
This script is designed to be run after deployment to apply database schema changes.
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
    
    # Check if DATABASE_URL is configured
    if not os.getenv("DATABASE_URL"):
        print("❌ ERROR: DATABASE_URL environment variable is not set")
        print("Please set DATABASE_URL before running migrations")
        print("For Vercel: vercel env add DATABASE_URL")
        sys.exit(1)
    
    try:
        from django.core.management import call_command
        from django.db import connection
        
        # Test database connection
        print("Testing database connection...")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✓ Database connection successful")
        
        # Run migrations
        print("Applying migrations...")
        call_command("migrate", "--noinput", verbosity=1)
        print("✓ Migrations completed successfully")
        return True
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False

if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
