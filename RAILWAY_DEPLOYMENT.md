# Railway Deployment Guide - Multi-Agent System

## Architecture Overview

This application uses a **Claude-powered agent system with MCP (Model Context Protocol)** architecture:
- **Claude 3.5 Haiku** - Intelligent orchestrator that makes routing decisions
- **SQL Agent** - MCP server for database queries
- **Graph Agent** - MCP server for data visualization
- **RAG Agent** - MCP server for semantic search and budget context

All agents run as MCP subprocesses within the same Railway container, with Claude coordinating tool calls.

---

## Pre-Deployment Checklist

### 1. Ensure Database Files Exist
Make sure these files are in your repository:
- `/db/vendor.db`
- `/db/budget.db`

### 2. Commit All Code
```bash
git add .
git commit -m "Multi-agent system ready for Railway deployment"
git push origin main
```

---

## Railway Deployment Steps

### Step 1: Create New Project on Railway

1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository: `SEC`
5. Railway will auto-detect the Python project

### Step 2: Configure Environment Variables

In Railway dashboard, go to **Variables** tab and add:

| Variable | Value | Notes |
|----------|-------|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | **REQUIRED** - Get from console.anthropic.com |
| `GROQ_KEY` | `your_groq_api_key` | **REQUIRED** - Get from groq.com (for conversation summarization) |
| `BACKEND_API_KEY` | `your_secure_random_key` | **REQUIRED** - Generate a secure random string |
| `FRONTEND_URL` | `https://your-frontend.railway.app` | Your Next.js frontend URL (or comma-separated list) |

**To generate BACKEND_API_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 3: Configure Build & Start Command

Railway should auto-detect from `railway.toml`, but verify:

**Start Command:**
```
uvicorn chat.api:app --host 0.0.0.0 --port $PORT
```

**Build Command:** (auto-detected)
```
pip install -r requirements.txt
```

### Step 4: Deploy

1. Click "Deploy" in Railway dashboard
2. Wait for build to complete (~2-3 minutes)
3. Railway will assign a public URL like: `https://sec-production-xxxx.up.railway.app`

### Step 5: Test the Deployment

**Health Check:**
```bash
curl https://your-app.railway.app/
```

Expected response:
```json
{
  "message": "API is running",
  "active_sessions": 0
}
```

**Test Chat Endpoint:**
```bash
curl -X POST https://your-app.railway.app/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_backend_api_key" \
  -d '{
    "message": "What are the top 5 agencies by spending?",
    "session_id": "test-session"
  }'
```

---

## Verify Multi-Agent System

Check Railway logs to confirm Claude system and agents started:

```
[SYSTEM] Starting agents...
[SYSTEM] ✓ SQL Agent started
[SYSTEM] ✓ Graph Agent started
[SYSTEM] ✓ RAG Agent started
[SYSTEM] All agents running
✅ System started successfully
```

---

## Frontend Deployment (Next.js)

### Step 1: Create Frontend Service on Railway

1. In same Railway project, click "New Service"
2. Select your repository again
3. Choose the `/frontend` directory as root
4. Railway will detect Next.js automatically

### Step 2: Configure Frontend Environment Variables

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://your-backend.railway.app` |
| `NEXT_PUBLIC_API_KEY` | Same as `BACKEND_API_KEY` from backend |

### Step 3: Deploy Frontend

Railway will build and deploy Next.js automatically.

### Step 4: Update Backend CORS

Go back to **backend service** and update `FRONTEND_URL`:
```
FRONTEND_URL=https://your-frontend.railway.app
```

Redeploy backend for CORS changes to take effect.

---

## Troubleshooting

### Issue: Agents Not Starting

**Check logs for:**
```
[SYSTEM] ✓ SQL Agent started
[SYSTEM] ✓ Graph Agent started
[SYSTEM] ✓ RAG Agent started
[SYSTEM] All agents running
```

If missing, agents failed to spawn.

**Common causes:**
- Missing `ANTHROPIC_API_KEY` environment variable
- Missing `GROQ_KEY` environment variable
- Missing dependencies (check requirements.txt)
- File permissions
- Path issues

**Fix:**
Make sure all agent files are in the repo:
```
/chat/agents/sql_agent.py
/chat/agents/graph_agent.py
/chat/agents/rag_agent.py
/chat/agents/agent_client.py
/chat/claude_main.py
```

And set required environment variables in Railway dashboard.

### Issue: Database Not Found

**Error:** `no such table: vendor_payments`

**Fix:** Ensure `/db/vendor.db` and `/db/budget.db` are committed to git:
```bash
git add db/vendor.db db/budget.db
git commit -m "Add database files"
git push
```

### Issue: CORS Errors

**Error:** `Access to fetch blocked by CORS policy`

**Fix:** Update `FRONTEND_URL` in Railway backend environment variables:
```
FRONTEND_URL=https://your-exact-frontend-url.railway.app
```

Redeploy backend.

### Issue: 403 Invalid API Key

**Error:** `{"detail":"Invalid API key"}`

**Fix:** Make sure frontend is sending the correct API key:
- Frontend env: `NEXT_PUBLIC_API_KEY=same_as_backend_key`
- Backend env: `BACKEND_API_KEY=same_key`

### Issue: 500 Internal Server Error

**Check Railway logs:**
```bash
# In Railway dashboard, go to "Deployments" -> "View Logs"
```

Common errors:
- Missing `GROQ_KEY`
- Database file missing
- Agent subprocess failed to start

---

## Monitoring

### Check Agent Status

Railway logs will show Claude using agents:
```
[SYSTEM] Starting agents...
[SYSTEM] ✓ SQL Agent started
[SYSTEM] ✓ Graph Agent started
[SYSTEM] ✓ RAG Agent started
[CLAUDE] Using tool: query_database
[CLAUDE] Using tool: create_visualization
```

### Check Active Sessions

```bash
curl https://your-app.railway.app/
```

Response includes `active_sessions` count.

### Performance

- **Cold start:** ~5-10 seconds (first request after inactivity)
- **Warm requests:** ~1-3 seconds (SQL + Graph pipeline)
- **SQL only:** ~500ms-1s

---

## Scaling Considerations

### Current Setup (Single Container)
- All agents run as subprocesses in one container
- Good for: Development, small-to-medium traffic
- Limits: Single container CPU/memory

### Future Scaling Options
1. **Horizontal scaling** - Run multiple containers
   - Railway auto-balances requests
   - Each container has its own agent processes

2. **Dedicated agent services** - Deploy agents as separate Railway services
   - More complex but better isolation
   - Can scale SQL and Graph agents independently

---

## Cost Estimation

**Railway Resources:**
- Starter Plan: $5/month
- Pro Plan: $20/month (recommended for production)

**Groq API:**
- Free tier: Generous limits
- Pay-as-you-go: ~$0.10-$0.50 per 1M tokens

**Estimated monthly cost:**
- Low traffic: ~$5-10/month
- Medium traffic: ~$20-30/month
- High traffic: ~$50-100/month

---

## Maintenance

### Update Dependencies

```bash
pip install --upgrade groq fastapi uvicorn
pip freeze > requirements.txt
git commit -am "Update dependencies"
git push
```

Railway will auto-deploy on push.

### Update Agents

Modify agent files locally, then:
```bash
git add chat/agents/
git commit -m "Update agent logic"
git push
```

Railway redeploys automatically.

### Monitor Logs

Railway dashboard → Deployments → View Logs

Look for:
- ✅ `Multi-agent system started`
- ⚠️ Error messages
- 📊 Request patterns

---

## Security Checklist

- ✅ `BACKEND_API_KEY` is strong and random
- ✅ `GROQ_KEY` is kept secret
- ✅ CORS configured correctly (only your frontend domain)
- ✅ Rate limiting enabled (slowapi)
- ✅ No secrets in git repository

---

## Support

**Railway Issues:**
- Railway Discord: discord.gg/railway
- Railway Docs: docs.railway.app

**Multi-Agent Issues:**
- Check logs for agent startup messages
- Verify all environment variables set
- Test agents individually (see agent_client.py)

---

## Quick Reference

**Backend URL:** `https://your-backend.railway.app`
**Frontend URL:** `https://your-frontend.railway.app`

**Key Endpoints:**
- `GET /` - Health check
- `POST /chat` - Main chat endpoint (requires `X-API-Key` header)
- `DELETE /session/{id}` - Delete session

**Environment Variables:**
- `GROQ_KEY` - Groq API key
- `BACKEND_API_KEY` - API authentication
- `FRONTEND_URL` - CORS whitelist
- `MODEL_NAME` - LLM model name

---

✅ **Deployment Complete!**

Your Claude-powered MCP agent system is now live on Railway with:
- Claude 3.5 Haiku (intelligent orchestration)
- SQL Agent (MCP server for database queries)
- Graph Agent (MCP server for visualizations)
- RAG Agent (MCP server for semantic search)
