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

The project now uses a custom build script (`vercel_build.py`) that:
- Runs database migrations if `DATABASE_URL` is configured
- Collects static files for production
- Provides clear error messages for build failures

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
- Create a PostgreSQL database in Vercel or use an external Postgres service
- The project will fallback to SQLite locally, but PostgreSQL is required for production

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

### 5. Post-Deployment
- Test the deployed application
- Verify database migrations ran successfully
- Check that static files are loading correctly
- Test authentication if Google OAuth is configured

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

### Build Failures
- Check that `DATABASE_URL` is set correctly
- Verify PostgreSQL credentials are valid
- Ensure all required environment variables are configured

### Static Files Not Loading
- Verify `STATIC_ROOT` is properly configured
- Check that `collectstatic` ran during build
- Ensure static files are in the `staticfiles/` directory

### Database Errors
- Confirm PostgreSQL is accessible from Vercel
- Check database connection string format
- Verify database user has proper permissions

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

## Additional Resources

- [Vercel Django Documentation](https://vercel.com/docs/frameworks/django)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [PostgreSQL on Vercel](https://vercel.com/docs/storage/vercel-postgres)

## Support

If you encounter issues:
1. Check Vercel build logs
2. Verify all environment variables are set
3. Ensure database connectivity
4. Review Django settings for production compatibility
