# Deploying Trading Bot to Render (24/7)

## Overview

This guide will help you deploy the trading bot as a 24/7 web service on Render (render.com), which is free and perfect for long-running processes.

## Prerequisites

1. GitHub account (to store code)
2. Render account (free at render.com)
3. API keys:
   - Google Gemini API key
   - Alpaca API keys (for US markets) OR Zerodha API keys (for Indian markets)

## Step 1: Prepare Your Code

### 1.1 Push Code to GitHub

```bash
# Initialize git repo
git init
git add .
git commit -m "Initial trading bot commit"

# Create repo on github.com and push
git remote add origin https://github.com/your-username/trading-bot.git
git branch -M main
git push -u origin main
```

### 1.2 Verify .env is in .gitignore

```bash
cat .gitignore | grep .env
# Should show: .env
```

**Important**: Never commit `.env` to GitHub!

## Step 2: Deploy to Render

### 2.1 Connect Render to GitHub

1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Authorize Render to access your GitHub account

### 2.2 Create New Web Service

1. Click **"New +"** → **"Web Service"**
2. Select your GitHub repository (trading-bot)
3. Fill in the form:

   | Field | Value |
   |-------|-------|
   | Name | `trading-bot` |
   | Environment | `Python 3` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `python app.py` |
   | Plan | `Free` (auto-sleeps after 15 min of inactivity - see note below) |

4. **Important**: For 24/7 operation without sleeping, upgrade to **Paid Plan ($7/month)**

### 2.3 Add Environment Variables

In Render dashboard → Your Service → "Environment":

```
BROKER=alpaca
GEMINI_API_KEY=your_gemini_key_here
ALPACA_API_KEY=your_alpaca_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
SYMBOLS_TO_MONITOR=["AAPL","MSFT","GOOGL","NVDA","TSLA"]
ORDER_QUANTITY=1
MAX_POSITIONS=5
CYCLE_INTERVAL_SECONDS=60
```

Or for Zerodha (Indian markets):

```
BROKER=zerodha
GEMINI_API_KEY=your_gemini_key_here
ZERODHA_API_KEY=your_zerodha_api_key_here
ZERODHA_ACCESS_TOKEN=your_zerodha_access_token_here
SYMBOLS_TO_MONITOR=["RELIANCE","TCS","INFOSYS","WIPRO","BAJAJFINSV"]
```

### 2.4 Deploy

1. Click **"Deploy"**
2. Wait for build to complete (2-3 minutes)
3. Once live, you'll see the service URL: `https://trading-bot.onrender.com`

## Step 3: Monitor Your Bot

### 3.1 API Endpoints

Your bot is now accessible at: `https://trading-bot.onrender.com`

```bash
# Health check
curl https://trading-bot.onrender.com/health

# Bot status
curl https://trading-bot.onrender.com/status

# Current positions
curl https://trading-bot.onrender.com/positions

# Account info
curl https://trading-bot.onrender.com/account

# Get latest logs
curl https://trading-bot.onrender.com/logs/latest

# Start bot
curl -X POST https://trading-bot.onrender.com/start
```

### 3.2 View Logs

In Render dashboard → Your Service → **Logs** tab

```
2024-07-02 10:23:45 - __main__ - INFO - Starting Trading Bot Service (24/7)...
2024-07-02 10:23:46 - __main__ - INFO - ✓ Connected to Alpaca
2024-07-02 10:23:47 - __main__ - INFO - ✓ Connected to Gemini
2024-07-02 10:30:00 - __main__ - INFO - Market closed. Next opening: 2024-07-03 09:30:00 ET
2024-07-03 09:30:05 - __main__ - INFO - CYCLE #1 | Market is now OPEN - trading enabled
```

## Market Hours & Cycles

### How It Works

The bot checks market status **every 10 seconds**:

- **Market CLOSED**: Waits (checks every 10 seconds)
- **Market OPEN**: Runs trading cycle (checks patterns every 1 second)

### Market Hours

**Alpaca (US)**:
- Monday-Friday: 9:30 AM - 4:00 PM ET
- Auto-pauses on weekends/holidays

**Zerodha (India)**:
- Monday-Friday: 9:15 AM - 3:30 PM IST
- Auto-pauses on weekends/holidays

## Handling the Free Tier Sleep

### Problem
Render free tier auto-sleeps after 15 minutes of inactivity (no HTTP requests).

### Solutions

**Option 1: Use Paid Plan ($7/month)**
```
Render Dashboard → Your Service → Billing → Upgrade to Paid
```

**Option 2: Add Uptime Monitor (Keep Alive)**

Use a free uptime monitoring service to ping your bot every 10 minutes:

1. Go to [uptime-robot.com](https://uptime.betterstack.com/)
2. Create new monitor:
   - URL: `https://trading-bot.onrender.com/health`
   - Interval: Every 10 minutes
   - Type: HTTPS
3. Save - your bot will never sleep!

**Option 3: Use GitHub Actions (Keep Alive)**

Create `.github/workflows/keep-alive.yml`:

```yaml
name: Keep Alive

on:
  schedule:
    - cron: '*/10 * * * *'  # Every 10 minutes

jobs:
  keep-alive:
    runs-on: ubuntu-latest
    steps:
      - name: Ping service
        run: curl -f https://trading-bot.onrender.com/health || exit 1
```

## Updating Your Bot

### Deploy Changes

```bash
# Make changes locally
nano main.py

# Commit and push
git add .
git commit -m "Update trading logic"
git push origin main
```

Render automatically redeploys from GitHub when you push!

### Rollback

In Render dashboard → Your Service → Deployments → Select previous version → Click "Deploy"

## Performance Monitoring

### Track Bot Metrics

```bash
# Status overview
curl -s https://trading-bot.onrender.com/status | jq .

# Monitor positions
watch -n 5 'curl -s https://trading-bot.onrender.com/positions | jq .'

# Track cycles per minute
curl -s https://trading-bot.onrender.com/logs/latest | tail -20
```

## Troubleshooting

### Bot Not Starting

**Check logs**:
```
Render Dashboard → Logs
```

**Common issues**:
- Missing environment variables → Add all keys to Environment
- API key invalid → Verify credentials are correct
- Network error → Check internet connection

### Market Status Wrong

Bot uses **automatic timezone detection**:
- Alpaca: Converts to US/Eastern automatically
- Zerodha: Converts to Asia/Kolkata automatically

To verify:
```bash
curl https://trading-bot.onrender.com/status | jq '.market_open'
```

### Too Many Trades

If bot is trading too frequently:

```env
# Increase cycle interval
CYCLE_INTERVAL_SECONDS=10  # Check patterns every 10 seconds instead of 1
```

Redeploy after changing environment variables.

### Getting Throttled

Alpaca/Zerodha might throttle if too many requests:

```env
# Reduce symbols to monitor
SYMBOLS_TO_MONITOR=["AAPL","MSFT","GOOGL"]  # Was 5, now 3
```

## Production Checklist

- ✅ Tested locally with paper trading
- ✅ All environment variables set in Render
- ✅ `.env` file in `.gitignore`
- ✅ Code committed to GitHub
- ✅ Service deployed and running
- ✅ Health checks passing
- ✅ Logs showing "Market CLOSED/OPEN" status
- ✅ Uptime monitor/keep-alive configured (if free tier)
- ✅ Can access `/status` endpoint
- ✅ Can view logs via `/logs/latest`

## Cost Analysis

| Option | Cost | Uptime | Recommendation |
|--------|------|--------|---|
| Free + Uptime Monitor | $0 | 99% | Good for testing |
| Paid Plan | $7/month | 99.9% | Production use |
| AWS EC2 | $5-10/month | 99.9% | More control |

## Auto-Restart on Crash

Render automatically restarts failed services. Logs will show:

```
Service crashed (code 1)
Restarting service...
Service started successfully
```

## Next Steps

1. **Monitor for 1 week** - Watch logs and status
2. **Verify trades** - Check that decisions are being made correctly
3. **Adjust parameters** - Fine-tune based on results
4. **Scale up** - Increase ORDER_QUANTITY once confident

## Support

- **Render Docs**: https://render.com/docs
- **Bot Logs**: `/logs/latest` endpoint
- **Status Dashboard**: Visit `https://trading-bot.onrender.com/`

## Security

- Never commit `.env` to GitHub
- Rotate API keys periodically
- Use environment variables for all secrets
- Monitor logs for unauthorized access attempts

Happy 24/7 trading! 🚀
