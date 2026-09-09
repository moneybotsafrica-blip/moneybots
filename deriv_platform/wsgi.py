import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

application = get_wsgi_application()

# Run migrations on first startup for serverless environments
# This handles database setup without requiring terminal access
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    try:
        from django.core.management import call_command
        from django.db import connection
        
        # Only run if database is accessible
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        print("Running automatic database migrations...")
        call_command('migrate', '--noinput', verbosity=0)
        print("Migrations completed")
    except Exception as e:
        print(f"Migration notice: {e}")
        # Continue anyway - migrations may have already run
