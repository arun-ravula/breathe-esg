# Deployment Guide

## Option A: Railway (Recommended — free tier, SQLite ok for prototype)

1. Go to https://railway.app → New Project → Deploy from GitHub repo
2. Select this repo, set **Root Directory** to `backend`
3. Railway auto-detects Python. Add these env vars:
   ```
   SECRET_KEY=<generate a 50+ char random string>
   DEBUG=False
   ALLOWED_HOSTS=*.railway.app
   ```
4. Railway auto-runs `Procfile`:
   - `release`: runs migrations + seed
   - `web`: starts gunicorn
5. Note the deployed URL. Update `ALLOWED_HOSTS` to match.

**For the React frontend:** Either:
- Set `REACT_APP_API_URL=https://your-app.railway.app` and `npm run build` → copy to backend/staticfiles/
- Or deploy frontend separately on Vercel/Netlify pointing to the Railway API

## Option B: Render

1. New Web Service → Connect GitHub repo
2. Build Command: `cd backend && pip install -r requirements.txt`
3. Start Command: `cd backend && gunicorn config.wsgi --bind 0.0.0.0:$PORT`
4. Add env vars same as Railway above
5. Add a job for `python backend/seed_data.py` after first deploy

## Credentials

After deployment, the seed script creates:
- `admin / breathe123` (superuser, Django admin at `/admin/`)
- `analyst / breathe123` (regular user for review workflow)

## Sharing access for review

Share these with reviewers:
- Live URL: `https://your-app.railway.app/`
- GitHub repo (add saurav@breatheesg.com, rahul@breatheesg.com, shivang@breatheesg.com as collaborators)
- Login: `analyst / breathe123`
