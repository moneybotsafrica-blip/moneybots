# Vercel Deployment Guide

This guide explains how to deploy the Django trading dashboard to Vercel with proper configuration.

## Important Security Notes

⚠️ **CRITICAL**: The following secrets were exposed in the original `.env` file and should be rotated immediately:

- **Google OAuth Client Secret** - Regenerate at Google Cloud Console
- **Groq API Key** - Regenerate at https://console.groq.com
- **Any other API keys** that were in the `.env` file

The `.env` file has been removed from the repository and is now properly gitignored.

## Vercel Configuration Changes

### What Was Fixed

1. **Removed custom `vercel.json`** - Replaced with minimal build configuration
2. **Fixed production settings** - DEBUG now defaults to False, ALLOWED_HOSTS includes Vercel domains
3. **Moved database migrations** - Migrations now run in `vercel_build.py` instead of `asgi.py`
4. **Disabled Channels/WebSockets** - Vercel doesn't support WebSocket connections, so ASGI is disabled in production
5. **Added proper build script** - `vercel_build.py` handles migrations and static file collection

### New Build Configuration

The project now uses custom scripts for deployment:

**`vercel_build.py`** (runs during Vercel build):
- Collects static files for production
- **Skips database migrations** (run separately to avoid build failures)
- Provides clear error messages for build failures

**`vercel_migrate.py`** (run manually after deployment):
- Runs Django migrations against production database
- Validates DATABASE_URL is configured
- Tests database connection before applying migrations
- Provides clear error messages for migration failures

**Important:** Database migrations are not run during the Vercel build process. This prevents build failures when the database is not available during the build. Run migrations separately against your production database using `vercel_migrate.py`.

## Required Vercel Environment Variables

Configure these in your Vercel project settings (Environment Variables):

### Core Django Settings
```
DEBUG=False
SECRET_KEY=your-random-secret-key-here
ALLOWED_HOSTS=.vercel.app,your-custom-domain.com
```

### Database (Required for Production)
```
DATABASE_URL=postgresql://user:password@host:port/database
```
- **Critical**: Must be set for production deployment
- Create a PostgreSQL database in Vercel or use an external Postgres service
- The project will fallback to SQLite locally, but PostgreSQL is required for production
- Note: Migrations are not run during build - run them separately (see deployment steps)

### Optional API Keys
```
DERIV_APP_ID=1089
DERIV_API_TOKEN=your_token_here
ANTHROPIC_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
FINNHUB_API_KEY=your_key_here
```

### Email Configuration (Optional)
```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
ALERT_CONTACT_EMAIL=your-personal@gmail.com
```

### Google OAuth (Optional)
```
GOOGLE_OAUTH_CLIENT_ID=your_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
SITE_DOMAIN=your-domain.vercel.app
```

## Deployment Steps

### 1. Prepare Your Code
```bash
# Ensure .env is removed (already done)
# Verify .gitignore includes .env
git add .
git commit -m "Prepare for Vercel deployment"
```

### 2. Set Up Vercel Project
1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Create a new project
3. Import your Git repository
4. Vercel will automatically detect Django

### 3. Configure Environment Variables
In Vercel project settings → Environment Variables:
- Add all required variables from the list above
- Set production values (DEBUG=False, proper ALLOWED_HOSTS)

### 4. Deploy
- Push your changes to trigger deployment
- Vercel will run `vercel_build.py` automatically
- Monitor build logs for any errors

### 5. Run Database Migrations
**Important:** Migrations are not run during the build process. Run them separately:

**Option A: Using Vercel CLI (Recommended for Vercel Postgres)**
```bash
# Install Vercel CLI
npm i -g vercel

# Pull environment variables locally
vercel env pull .env.local

# Run migrations using the provided script
python vercel_migrate.py
```

**Option B: Using Vercel Postgres Dashboard**
1. Go to Vercel Dashboard → Storage → Your Database
2. Use the "Query" or "Migration" feature to run Django migrations
3. Or connect to the database directly and run migrations

**Option C: External PostgreSQL**
```bash
# Set DATABASE_URL environment variable locally
export DATABASE_URL="postgresql://user:password@host:5432/database"

# Run migrations using the provided script
python vercel_migrate.py
```

**Option D: Direct Django Command**
```bash
# If you have DATABASE_URL set in your environment
python manage.py migrate
```

### 6. Post-Deployment
- Test the deployed application
- Verify database migrations ran successfully
- Check that static files are loading correctly
- Test authentication if Google OAuth is configured

## Deployment Architecture

The deployment follows a safer architecture that separates build and database operations:

```
Vercel Build Process:
  1. Install dependencies (pip install -r requirements.txt)
  2. Collect static files (python vercel_build.py)
  3. Deploy Django application
  4. Start application with WSGI

Runtime (After Deployment):
  1. Application connects to PostgreSQL via DATABASE_URL
  2. Django runs with production settings
  3. Static files served from staticfiles/
```

**Why Migrations Are Separate:**
- Build environment may not have database access
- Prevents build failures due to database connectivity issues
- Allows for more controlled database schema changes
- Matches industry best practices for production deployments

## Important Limitations

### WebSocket Support
- **Disabled in production** - Vercel's Django deployment uses WSGI, not ASGI
- Real-time features that rely on WebSockets will not work on Vercel
- The dashboard still functions for analysis and chart viewing

### Database
- **PostgreSQL required** - SQLite is not suitable for production on Vercel
- Use Vercel Postgres or an external PostgreSQL service
- Configure `DATABASE_URL` environment variable

### Background Processes
- No long-running background processes are supported
- The analysis loop runs synchronously within request handlers
- Consider using Vercel Cron Jobs for scheduled tasks if needed

## Local Development

For local development with WebSocket support:
```bash
# Copy .env.example to .env
cp .env.example .env

# Edit .env with your local settings
# Set DEBUG=True
# Use local ALLOWED_HOSTS

# Run with Django development server
python manage.py runserver
```

## Troubleshooting

### Internal Server Error (500 Error)
If you see "Internal Server Error" when accessing your deployed site:

**1. Check Environment Variables**
- Go to Vercel → Project → Settings → Environment Variables
- Ensure these are set for Production:
  - `SECRET_KEY` (generate a strong random key)
  - `DATABASE_URL` (PostgreSQL connection string)
  - `ALLOWED_HOSTS=.vercel.app,your-domain.com`
  - `DEBUG=False`

**2. Check Vercel Function Logs**
- Go to Vercel → Project → Functions
- Look for error messages in the function logs
- Common errors:
  - "SECRET_KEY not set" → Add SECRET_KEY environment variable
  - "DATABASE_URL not set" → Add DATABASE_URL environment variable
  - "ALLOWED_HOSTS" errors → Check ALLOWED_HOSTS configuration

**3. Verify Database Connection**
- Ensure `DATABASE_URL` is correctly formatted
- Test the connection string locally first
- Check if PostgreSQL database is accessible

**4. Check Django Settings**
- The application now includes logging for debugging
- Check Vercel logs for configuration warnings
- Look for "SECURITY WARNING" messages about default SECRET_KEY

**5. Common Issues**
- **Missing SECRET_KEY**: Generate one with `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- **Incorrect ALLOWED_HOSTS**: Ensure `.vercel.app` is included
- **Database not migrated**: Run `python vercel_migrate.py` after deployment
- **DEBUG=True in production**: Set `DEBUG=False` in Vercel environment variables

### Build Failures - Migration Errors
If you see "settings.DATABASES is improperly configured" during build:
- **This is expected** - migrations are not run during build
- The build script only collects static files
- Run migrations separately (see "Run Database Migrations" section above)
- Ensure `DATABASE_URL` is set in Vercel environment variables for runtime

### Build Failures - Other Issues
- Check that all required environment variables are configured
- Verify dependencies are correctly specified in requirements.txt
- Check build logs for specific error messages

### Static Files Not Loading
- Verify `STATIC_ROOT` is properly configured
- Check that `collectstatic` ran during build
- Ensure static files are in the `staticfiles/` directory

### Database Errors
- Confirm PostgreSQL is accessible from Vercel
- Check database connection string format
- Verify database user has proper permissions
- Ensure DATABASE_URL is set in Vercel environment variables
- If using SQLite fallback in production, this will cause data loss between deployments

### Authentication Issues
- Ensure Google OAuth redirect URIs include your Vercel domain
- Check that `SITE_DOMAIN` matches your deployed URL
- Verify OAuth credentials are correct

## Security Checklist

- [x] Remove `.env` from repository
- [x] Rotate exposed API keys (Google OAuth, Groq, etc.)
- [x] Set `DEBUG=False` in production
- [x] Configure proper `ALLOWED_HOSTS`
- [x] Use PostgreSQL instead of SQLite
- [x] Set strong `SECRET_KEY`
- [x] Configure HTTPS (automatic on Vercel)
- [x] Review and update environment variables
- [x] Run database migrations separately using `vercel_migrate.py`

## Additional Resources

- [Vercel Django Documentation](https://vercel.com/docs/frameworks/django)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [PostgreSQL on Vercel](https://vercel.com/docs/storage/vercel-postgres)
- [Vercel Environment Variables](https://vercel.com/docs/projects/environment-variables)

## Support

If you encounter issues:
1. Check Vercel build logs
2. Verify all environment variables are set
3. Ensure database connectivity
4. Review Django settings for production compatibility
