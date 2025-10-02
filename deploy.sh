#!/bin/bash

# RxVerify Heroku Deployment Script
# Deploys both frontend and backend to Heroku

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Heroku app names
FRONTEND_APP="rx-verify"
BACKEND_APP="rx-verify-api"

# Deployed URLs
FRONTEND_URL="https://rx-verify-b127ef29a2bd.herokuapp.com"
BACKEND_URL="https://rx-verify-api-e68bdd74c056.herokuapp.com"

echo -e "${BLUE}🚀 RxVerify Heroku Deployment Script${NC}"
echo "=================================="

# Function to check if Heroku CLI is installed
check_heroku_cli() {
    if ! command -v heroku &> /dev/null; then
        echo -e "${RED}❌ Heroku CLI not found. Please install it first:${NC}"
        echo "   https://devcenter.heroku.com/articles/heroku-cli"
        exit 1
    fi
    echo -e "${GREEN}✅ Heroku CLI found${NC}"
}

# Function to check if logged in to Heroku
check_heroku_auth() {
    if ! heroku auth:whoami &> /dev/null; then
        echo -e "${RED}❌ Not logged in to Heroku. Please run:${NC}"
        echo "   heroku login"
        exit 1
    fi
    echo -e "${GREEN}✅ Logged in to Heroku as $(heroku auth:whoami)${NC}"
}

# Function to deploy backend
deploy_backend() {
    echo -e "\n${YELLOW}📦 Deploying Backend (${BACKEND_APP})...${NC}"
    
    # Check if we're in the right directory
    if [ ! -f "app/main.py" ]; then
        echo -e "${RED}❌ Backend files not found. Make sure you're in the project root.${NC}"
        exit 1
    fi
    
    # Add Heroku remote if it doesn't exist
    if ! git remote | grep -q "heroku-backend"; then
        echo "Adding Heroku backend remote..."
        heroku git:remote -a ${BACKEND_APP} -r heroku-backend
    fi
    
    # Deploy to Heroku
    echo "Deploying to Heroku..."
    git push heroku-backend main
    
    echo -e "${GREEN}✅ Backend deployed successfully!${NC}"
    echo -e "${BLUE}   Backend URL: ${BACKEND_URL}${NC}"
}

# Function to deploy frontend
deploy_frontend() {
    echo -e "\n${YELLOW}🌐 Deploying Frontend (${FRONTEND_APP})...${NC}"
    
    # Check if frontend directory exists
    if [ ! -d "frontend" ]; then
        echo -e "${RED}❌ Frontend directory not found.${NC}"
        exit 1
    fi
    
    # Create a temporary directory for frontend deployment
    TEMP_DIR=$(mktemp -d)
    echo "Creating temporary deployment directory: ${TEMP_DIR}"
    
    # Copy frontend files
    cp -r frontend/* ${TEMP_DIR}/
    
    # Copy necessary files to root of temp directory
    cp frontend/Procfile ${TEMP_DIR}/
    cp frontend/runtime.txt ${TEMP_DIR}/
    cp frontend/requirements.txt ${TEMP_DIR}/
    
    # Navigate to temp directory
    cd ${TEMP_DIR}
    
    # Initialize git repository
    git init
    git add .
    git commit -m "Deploy frontend to Heroku"
    
    # Add Heroku remote if it doesn't exist
    if ! git remote | grep -q "heroku"; then
        echo "Adding Heroku frontend remote..."
        heroku git:remote -a ${FRONTEND_APP}
    fi
    
    # Deploy to Heroku
    echo "Deploying frontend to Heroku..."
    git push heroku main --force
    
    # Cleanup
    cd - > /dev/null
    rm -rf ${TEMP_DIR}
    
    echo -e "${GREEN}✅ Frontend deployed successfully!${NC}"
    echo -e "${BLUE}   Frontend URL: ${FRONTEND_URL}${NC}"
}

# Function to set environment variables
set_env_vars() {
    echo -e "\n${YELLOW}🔧 Setting Environment Variables...${NC}"
    
    # Backend environment variables
    echo "Setting backend environment variables..."
    heroku config:set -a ${BACKEND_APP} \
        OPENAI_API_KEY="${OPENAI_API_KEY:-your-openai-api-key}" \
        CHROMA_PERSIST_DIRECTORY="/app/chroma_db" \
        LOG_LEVEL="INFO" \
        ENVIRONMENT="production"
    
    # Frontend environment variables (if needed)
    echo "Setting frontend environment variables..."
    heroku config:set -a ${FRONTEND_APP} \
        BACKEND_URL="${BACKEND_URL}"
    
    echo -e "${GREEN}✅ Environment variables set${NC}"
}

# Function to show deployment status
show_status() {
    echo -e "\n${YELLOW}📊 Deployment Status:${NC}"
    
    echo -e "\n${BLUE}Backend (${BACKEND_APP}):${NC}"
    heroku ps -a ${BACKEND_APP}
    heroku logs --tail -a ${BACKEND_APP} -n 10
    
    echo -e "\n${BLUE}Frontend (${FRONTEND_APP}):${NC}"
    heroku ps -a ${FRONTEND_APP}
    heroku logs --tail -a ${FRONTEND_APP} -n 10
}

# Main deployment function
main() {
    # Parse command line arguments
    DEPLOY_BACKEND=true
    DEPLOY_FRONTEND=true
    SET_ENV=false
    SHOW_STATUS=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backend-only)
                DEPLOY_FRONTEND=false
                shift
                ;;
            --frontend-only)
                DEPLOY_BACKEND=false
                shift
                ;;
            --set-env)
                SET_ENV=true
                shift
                ;;
            --status)
                SHOW_STATUS=true
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --backend-only    Deploy only the backend"
                echo "  --frontend-only   Deploy only the frontend"
                echo "  --set-env         Set environment variables"
                echo "  --status          Show deployment status"
                echo "  --help            Show this help message"
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                exit 1
                ;;
        esac
    done
    
    # Check prerequisites
    check_heroku_cli
    check_heroku_auth
    
    # Set environment variables if requested
    if [ "$SET_ENV" = true ]; then
        set_env_vars
    fi
    
    # Deploy applications
    if [ "$DEPLOY_BACKEND" = true ]; then
        deploy_backend
    fi
    
    if [ "$DEPLOY_FRONTEND" = true ]; then
        deploy_frontend
    fi
    
    # Show status if requested
    if [ "$SHOW_STATUS" = true ]; then
        show_status
    fi
    
    echo -e "\n${GREEN}🎉 Deployment completed successfully!${NC}"
    echo -e "${BLUE}Frontend: ${FRONTEND_URL}${NC}"
    echo -e "${BLUE}Backend:  ${BACKEND_URL}${NC}"
    echo -e "${BLUE}API Docs: ${BACKEND_URL}/docs${NC}"
}

# Run main function with all arguments
main "$@"
