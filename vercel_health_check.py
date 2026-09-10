#!/usr/bin/env python
"""
Vercel health check script to validate configuration before deployment.
This script checks that all required environment variables are set correctly.
Note: Vercel now uses zero-configuration Django support, so no custom build scripts are needed.
"""
import os
import sys

def check_environment():
    """Check if required environment variables are set."""
    print("=== Vercel Environment Health Check ===\n")
    
    required_vars = {
        'SECRET_KEY': 'Django secret key (generate with: python -c "import secrets; print(secrets.token_urlsafe(50))")',
        'DATABASE_URL': 'PostgreSQL connection string (postgresql://user:password@host:5432/database)',
        'ALLOWED_HOSTS': 'Allowed hosts (e.g., .vercel.app,your-domain.com)',
    }
    
    optional_vars = {
        'DEBUG': 'Debug mode (should be False in production)',
        'DERIV_APP_ID': 'Deriv API app ID',
        'ANTHROPIC_API_KEY': 'Anthropic API key (optional)',
        'GROQ_API_KEY': 'Groq API key (optional)',
    }
    
    all_good = True
    
    print("Required Environment Variables:")
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'SECRET' in var or 'PASSWORD' in var or 'TOKEN' in var or 'KEY' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"✓ {var}: {display_value}")
        else:
            print(f"✗ {var}: NOT SET - {description}")
            all_good = False
    
    print("\nOptional Environment Variables:")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            if 'SECRET' in var or 'PASSWORD' in var or 'TOKEN' in var or 'KEY' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"✓ {var}: {display_value}")
        else:
            print(f"○ {var}: Not set (optional) - {description}")
    
    print("\n=== Configuration Checks ===")
    
    # Check DEBUG setting
    debug = os.getenv('DEBUG', 'False')
    if debug.lower() in ('false', '0', ''):
        print("✓ DEBUG is properly set to False for production")
    else:
        print("✗ WARNING: DEBUG is set to True in production!")
        all_good = False
    
    # Check ALLOWED_HOSTS
    allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
    if '.vercel.app' in allowed_hosts or 'localhost' in allowed_hosts:
        print(f"✓ ALLOWED_HOSTS includes Vercel domains: {allowed_hosts}")
    else:
        print(f"✗ WARNING: ALLOWED_HOSTS may not include Vercel domains: {allowed_hosts}")
        all_good = False
    
    # Check SECRET_KEY strength
    secret_key = os.getenv('SECRET_KEY', '')
    if secret_key and secret_key != 'insecure-dev-key-change-me':
        if len(secret_key) >= 32:
            print("✓ SECRET_KEY appears to be sufficiently long")
        else:
            print("✗ WARNING: SECRET_KEY may be too short")
            all_good = False
    elif secret_key == 'insecure-dev-key-change-me':
        print("✗ CRITICAL: Using default insecure SECRET_KEY!")
        all_good = False
    else:
        print("✗ SECRET_KEY is not set")
        all_good = False
    
    print("\n=== File Checks ===")
    
    # Check if wsgi.py exists and has proper configuration
    wsgi_path = os.path.join(os.path.dirname(__file__), 'deriv_platform', 'wsgi.py')
    if os.path.exists(wsgi_path):
        try:
            with open(wsgi_path, 'r') as f:
                wsgi_content = f.read()
                if 'app = get_wsgi_application()' in wsgi_content and 'application = app' in wsgi_content:
                    print("✓ wsgi.py properly exposes WSGI variables for Vercel")
                else:
                    print("✗ WARNING: wsgi.py may not expose 'app' variable for Vercel")
                    all_good = False
        except Exception as e:
            print(f"⚠ Could not check wsgi.py: {e}")
    else:
        print("✗ wsgi.py not found")
        all_good = False
    
    # Check if vercel.json exists (should not exist for zero-config)
    vercel_json_path = os.path.join(os.path.dirname(__file__), 'vercel.json')
    if os.path.exists(vercel_json_path):
        print("⚠ WARNING: vercel.json exists - Vercel zero-config Django support doesn't need custom build config")
    else:
        print("✓ No custom vercel.json (using Vercel zero-config Django support)")
    
    print("\n=== Summary ===")
    if all_good:
        print("✓ All critical checks passed. Configuration looks good!")
        print("Vercel will automatically detect Django and configure the deployment.")
        return 0
    else:
        print("✗ Some critical issues found. Please fix them before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(check_environment())
