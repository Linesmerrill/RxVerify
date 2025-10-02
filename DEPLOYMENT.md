# RxVerify Heroku Deployment Guide

This guide explains how to deploy RxVerify to Heroku with both frontend and backend applications.

## Prerequisites

1. **Heroku CLI**: Install from [https://devcenter.heroku.com/articles/heroku-cli](https://devcenter.heroku.com/articles/heroku-cli)
2. **Git**: Ensure git is installed and configured
3. **Heroku Account**: Create an account at [https://heroku.com](https://heroku.com)

## Heroku Apps

- **Frontend**: `rx-verify` (deployed at: https://rx-verify-b127ef29a2bd.herokuapp.com)
- **Backend**: `rx-verify-api` (deployed at: https://rx-verify-api-e68bdd74c056.herokuapp.com)

## Quick Deployment

### 1. Login to Heroku
```bash
heroku login
```

### 2. Set Environment Variables
```bash
./setup_heroku_env.sh
```

### 3. Deploy Both Applications
```bash
./deploy.sh
```

## Detailed Steps

### Step 1: Environment Setup

Run the environment setup script to configure environment variables:

```bash
./setup_heroku_env.sh
```

This script will:
- Prompt for your OpenAI API key
- Set backend environment variables
- Set frontend environment variables
- Update frontend configuration to use backend URL

### Step 2: Deploy Applications

Deploy both frontend and backend:

```bash
./deploy.sh
```

Or deploy individually:

```bash
# Deploy backend only
./deploy.sh --backend-only

# Deploy frontend only
./deploy.sh --frontend-only
```

### Step 3: Check Deployment Status

```bash
./deploy.sh --status
```

## Environment Variables

### Backend (`rx-verify-api`)
- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `CHROMA_PERSIST_DIRECTORY`: ChromaDB storage directory (`/tmp/chroma_db` for Heroku)
- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)
- `ENVIRONMENT`: Environment (production, development)
- `PYTHONPATH`: Python path for imports
- `PORT`: Port number (set by Heroku)
- `CHROMA_SERVER_HOST`: ChromaDB server host
- `CHROMA_SERVER_HTTP_PORT`: ChromaDB server port

### Frontend (`rx-verify`)
- `BACKEND_URL`: Backend API URL (https://rx-verify-api-e68bdd74c056.herokuapp.com)
- `PORT`: Port number (set by Heroku)

## Manual Deployment

If you prefer to deploy manually:

### Backend Deployment
```bash
# Add Heroku remote
heroku git:remote -a rx-verify-api -r heroku-backend

# Deploy
git push heroku-backend main
```

### Frontend Deployment
```bash
# Navigate to frontend directory
cd frontend

# Initialize git repository
git init
git add .
git commit -m "Deploy frontend"

# Add Heroku remote
heroku git:remote -a rx-verify

# Deploy
git push heroku main --force
```

## Troubleshooting

### Common Issues

1. **Build Failures**
   - Check `requirements.txt` for correct package versions
   - Ensure all dependencies are listed
   - Check Python version compatibility

2. **Environment Variables**
   - Verify all required environment variables are set
   - Check for typos in variable names
   - Ensure OpenAI API key is valid

3. **Frontend Not Connecting to Backend**
   - Verify `BACKEND_URL` is set correctly
   - Check CORS settings in backend
   - Ensure backend is deployed and running

### Checking Logs

```bash
# Backend logs
heroku logs --tail -a rx-verify-api

# Frontend logs
heroku logs --tail -a rx-verify
```

### Restarting Applications

```bash
# Restart backend
heroku restart -a rx-verify-api

# Restart frontend
heroku restart -a rx-verify
```

## URLs

After successful deployment:

- **Frontend**: https://rx-verify-b127ef29a2bd.herokuapp.com
- **Backend**: https://rx-verify-api-e68bdd74c056.herokuapp.com
- **API Documentation**: https://rx-verify-api-e68bdd74c056.herokuapp.com/docs
- **Health Check**: https://rx-verify-api-e68bdd74c056.herokuapp.com/health

## Development vs Production

### Development
- Uses local database files
- Debug logging enabled
- Local API endpoints

### Production
- Uses Heroku's ephemeral filesystem
- Production logging
- Heroku API endpoints
- Environment variables from Heroku config

## Maintenance

### Updating Applications
1. Make changes to your code
2. Commit changes to git
3. Run `./deploy.sh` to deploy updates

### Monitoring
- Use Heroku dashboard to monitor app performance
- Check logs regularly for errors
- Monitor API usage and response times

### Scaling
- Use Heroku dashboard to scale dynos
- Monitor memory and CPU usage
- Consider upgrading dyno types for better performance

## Security Notes

- Never commit API keys to git
- Use Heroku config vars for sensitive data
- Enable HTTPS (automatic with Heroku)
- Regularly update dependencies
- Monitor for security vulnerabilities

## Support

For issues with deployment:
1. Check Heroku logs
2. Verify environment variables
3. Test locally first
4. Check Heroku status page
5. Review this documentation
