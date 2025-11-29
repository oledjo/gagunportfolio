# Deployment Guide

This guide covers how to deploy your Portfolio API to various hosting platforms.

## Prerequisites

1. **GitHub Repository**: Your code should be pushed to GitHub (already done ✅)
2. **OpenRouter API Key**: Get one from https://openrouter.ai/keys
3. **Account**: Sign up for one of the hosting platforms below

---

## 🚀 Quick Deploy Options

### Option 1: Railway (Recommended - Easiest)

**Railway** is the easiest option with a free tier and automatic deployments.

#### Steps:

1. **Sign up**: Go to https://railway.app and sign up with GitHub
2. **New Project**: Click "New Project" → "Deploy from GitHub repo"
3. **Select Repository**: Choose `gagunportfolio`
4. **Configure Environment Variables**:
   - Click on your service → Variables
   - Add: `OPENROUTER_API_KEY` = `your_api_key_here`
5. **Deploy**: Railway will automatically detect Python and deploy
6. **Get URL**: Your app will be live at `https://your-app-name.railway.app`

**Cost**: Free tier includes $5/month credit (enough for small apps)

---

### Option 2: Render (Free Tier Available)

**Render** offers a free tier with automatic SSL.

#### Steps:

1. **Sign up**: Go to https://render.com and sign up with GitHub
2. **New Web Service**: Click "New" → "Web Service"
3. **Connect Repository**: Select `gagunportfolio`
4. **Configure**:
   - **Name**: `gagun-portfolio` (or your choice)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api:app --host 0.0.0.0 --port $PORT`
5. **Environment Variables**:
   - Add: `OPENROUTER_API_KEY` = `your_api_key_here`
6. **Deploy**: Click "Create Web Service"

**Cost**: Free tier available (spins down after 15 min inactivity)

---

### Option 3: Fly.io (Great for Global Distribution)

**Fly.io** offers global deployment with a generous free tier.

#### Steps:

1. **Install Fly CLI**: 
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Sign up**: 
   ```bash
   fly auth signup
   ```

3. **Launch App**:
   ```bash
   fly launch
   ```
   - Follow prompts
   - Choose app name
   - Select region

4. **Set Environment Variable**:
   ```bash
   fly secrets set OPENROUTER_API_KEY=your_api_key_here
   ```

5. **Deploy**:
   ```bash
   fly deploy
   ```

**Cost**: Free tier includes 3 shared-cpu VMs

---

### Option 4: Heroku (Classic, Paid)

**Heroku** is reliable but no longer has a free tier.

#### Steps:

1. **Install Heroku CLI**: https://devcenter.heroku.com/articles/heroku-cli
2. **Login**:
   ```bash
   heroku login
   ```
3. **Create App**:
   ```bash
   heroku create gagun-portfolio
   ```
4. **Set Environment Variable**:
   ```bash
   heroku config:set OPENROUTER_API_KEY=your_api_key_here
   ```
5. **Deploy**:
   ```bash
   git push heroku master
   ```

**Cost**: Starting at $5/month (Eco Dyno)

---

### Option 5: DigitalOcean App Platform

**DigitalOcean** offers simple deployment with good performance.

#### Steps:

1. **Sign up**: Go to https://cloud.digitalocean.com
2. **Create App**: Click "Create" → "Apps" → "GitHub"
3. **Select Repository**: Choose `gagunportfolio`
4. **Configure**:
   - **Type**: Web Service
   - **Build Command**: `pip install -r requirements.txt`
   - **Run Command**: `uvicorn api:app --host 0.0.0.0 --port $PORT`
5. **Environment Variables**: Add `OPENROUTER_API_KEY`
6. **Deploy**: Click "Create Resources"

**Cost**: Starting at $5/month

---

### Option 6: PythonAnywhere (Simple Python Hosting)

**PythonAnywhere** is great for Python apps, especially for beginners.

#### Steps:

1. **Sign up**: Go to https://www.pythonanywhere.com (free tier available)
2. **Open Bash Console**: Click "Consoles" → "Bash"
3. **Clone Repository**:
   ```bash
   git clone https://github.com/oledjo/gagunportfolio.git
   cd gagunportfolio
   ```
4. **Create Virtual Environment**:
   ```bash
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
5. **Create Web App**:
   - Go to "Web" tab
   - Click "Add a new web app"
   - Choose "Manual configuration" → Python 3.10
6. **Configure WSGI**:
   - Edit WSGI file: `/var/www/yourusername_pythonanywhere_com_wsgi.py`
   - Add:
   ```python
   import sys
   path = '/home/yourusername/gagunportfolio'
   if path not in sys.path:
       sys.path.append(path)
   
   from api import app
   application = app
   ```
7. **Set Environment Variables**:
   - In Web tab → "Environment variables"
   - Add: `OPENROUTER_API_KEY` = `your_api_key_here`
8. **Reload**: Click "Reload" button

**Cost**: Free tier available (limited), $5/month for better plan

---

## 🐳 Docker Deployment

If you prefer Docker, you can deploy to any platform that supports Docker:

### Build and Run Locally:
```bash
docker build -t gagun-portfolio .
docker run -p 8000:8000 -e OPENROUTER_API_KEY=your_key_here gagun-portfolio
```

### Deploy to Docker Platforms:
- **Fly.io**: Supports Docker (see Option 3)
- **Railway**: Supports Docker
- **Render**: Supports Docker
- **DigitalOcean**: Supports Docker
- **AWS ECS/Fargate**: Enterprise option
- **Google Cloud Run**: Serverless containers

---

## 🔧 Post-Deployment Checklist

After deploying, verify:

1. ✅ **API is accessible**: Visit `https://your-app-url.com/api`
2. ✅ **Static files work**: Visit `https://your-app-url.com/`
3. ✅ **Database works**: Try syncing a portfolio
4. ✅ **Environment variables**: Check that `OPENROUTER_API_KEY` is set
5. ✅ **File uploads**: Test uploading an Excel file
6. ✅ **HTTPS**: Ensure SSL certificate is active

---

## 📝 Important Notes

### Database Persistence

**SQLite files are ephemeral** on most platforms. For production:

1. **Use persistent storage** (if platform supports):
   - Railway: Persistent volumes
   - Fly.io: Volumes
   - Render: Disk storage (paid)

2. **Or migrate to PostgreSQL** (recommended for production):
   - Most platforms offer managed PostgreSQL
   - Update `database.py` to use PostgreSQL connection string

### Environment Variables

Always set these in your hosting platform:
- `OPENROUTER_API_KEY`: Your OpenRouter API key (required)
- `OPENROUTER_MODEL`: Optional, defaults to `meta-llama/llama-3.2-3b-instruct:free` (free model)
  - Other free options: `google/gemini-flash-1.5:free`, `microsoft/phi-3-mini-128k-instruct:free`
  - Paid options: `openai/gpt-4o-mini`, `anthropic/claude-3-haiku`, etc.
- `DATABASE_PATH`: Optional, defaults to `portfolio.db`

**Note**: The app uses a **free AI model by default** (`meta-llama/llama-3.2-3b-instruct:free`). Free models have rate limits (50 requests/day, or 1000/day if you add $10 credit). You can upgrade to a paid model by setting `OPENROUTER_MODEL`.

### CORS (if needed)

If you're accessing the API from a different domain, you may need to configure CORS in `api.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🆘 Troubleshooting

### App won't start
- Check logs in your hosting platform
- Verify environment variables are set
- Ensure `requirements.txt` is correct

### Database errors
- Check file permissions for SQLite
- Consider using PostgreSQL for production

### API key errors
- Verify `OPENROUTER_API_KEY` is set correctly
- Check for typos in environment variable name

### Static files not loading
- Verify `static/` directory is included in deployment
- Check FastAPI static file mounting in `api.py`

---

## 🎯 Recommended for Your Use Case

**Best for beginners**: **Railway** or **Render**
- Easiest setup
- Free tier available
- Automatic deployments from GitHub

**Best for production**: **Fly.io** or **DigitalOcean**
- Better performance
- More control
- Global distribution (Fly.io)

Choose based on your needs and budget!

