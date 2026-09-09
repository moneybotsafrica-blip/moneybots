# Vercel Deployment Setup

## Required Environment Variables

Set these in your Vercel project settings (Settings → Environment Variables):

### Required for Deployment
- `SECRET_KEY` - Generate a secure random string: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `ALLOWED_HOSTS` - `moneybots.vercel.app,.vercel.app`
- `DATABASE_URL` - Your Postgres connection string (see Database Setup below)
- `DEBUG` - `False`

### Deriv API Configuration
- `DERIV_APP_ID` - `1089` (or your own app ID)
- `DERIV_API_TOKEN` - Leave empty for public access, or add your token
- `DERIV_WS_URL` - `wss://ws.derivws.com/websockets/v3?app_id=1089`

### Optional Features
- `ANTHROPIC_API_KEY` - For AI chat features (get from https://console.anthropic.com)
- `GROQ_API_KEY` - Alternative AI provider (get from https://console.groq.com)
- `GOOGLE_OAUTH_CLIENT_ID` - For Google OAuth login
- `GOOGLE_OAUTH_CLIENT_SECRET` - For Google OAuth login
- `SITE_DOMAIN` - `moneybots.vercel.app`

## Database Setup

### Option 1: Vercel Postgres (Recommended)
1. Go to your Vercel project → Storage → Create Database
2. Choose "Postgres" and follow the setup
3. Vercel will automatically set `DATABASE_URL` environment variable
4. Run migrations: `vercel exec python manage.py migrate`

### Option 2: Neon Postgres
1. Create a free account at https://neon.tech
2. Create a new project
3. Copy the connection string (Connection Details → Connection string)
4. Add as `DATABASE_URL` in Vercel environment variables
5. Run migrations: `vercel exec python manage.py migrate`

### Option 3: Supabase Postgres
1. Create a free account at https://supabase.com
2. Create a new project
3. Go to Settings → Database → Connection string
4. Copy the URI connection string
5. Add as `DATABASE_URL` in Vercel environment variables
6. Run migrations: `vercel exec python manage.py migrate`

## Post-Deployment Steps

After deployment, run database migrations:

```bash
# Install Vercel CLI if needed
npm i -g vercel

# Login to Vercel
vercel login

# Run migrations
vercel exec python manage.py migrate
```

## Notes

- The app now uses Python 3.12 for Django 5.0+ compatibility
- Background analysis loop is disabled on Vercel (serverless environment)
- ML features are disabled on Vercel (libraries removed for size limits)
- MT5 trading is disabled on Vercel (Windows-only)
- Static files are automatically collected during build
