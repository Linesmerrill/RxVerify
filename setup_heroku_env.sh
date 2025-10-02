#!/bin/bash

# RxVerify Heroku Environment Setup Script
# Sets up environment variables for both frontend and backend

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

echo -e "${BLUE}🔧 RxVerify Heroku Environment Setup${NC}"
echo "====================================="

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

# Function to prompt for environment variables
prompt_for_env_vars() {
    echo -e "\n${YELLOW}📝 Environment Variables Setup${NC}"
    echo "Please provide the following environment variables:"
    echo
    
    # OpenAI API Key
    if [ -z "$OPENAI_API_KEY" ]; then
        read -p "OpenAI API Key: " OPENAI_API_KEY
    else
        echo -e "${GREEN}✅ OpenAI API Key already set${NC}"
    fi
    
    # Optional: Additional environment variables
    read -p "Log Level (default: INFO): " LOG_LEVEL
    LOG_LEVEL=${LOG_LEVEL:-INFO}
    
    read -p "Environment (default: production): " ENVIRONMENT
    ENVIRONMENT=${ENVIRONMENT:-production}
}

# Function to set backend environment variables
set_backend_env() {
    echo -e "\n${YELLOW}🔧 Setting Backend Environment Variables (${BACKEND_APP})...${NC}"
    
    # Check if app exists
    if ! heroku apps:info -a ${BACKEND_APP} &> /dev/null; then
        echo -e "${RED}❌ Backend app '${BACKEND_APP}' not found. Please create it first.${NC}"
        exit 1
    fi
    
    # Set environment variables
    heroku config:set -a ${BACKEND_APP} \
        OPENAI_API_KEY="${OPENAI_API_KEY}" \
        CHROMA_PERSIST_DIRECTORY="/tmp/chroma_db" \
        LOG_LEVEL="${LOG_LEVEL}" \
        ENVIRONMENT="${ENVIRONMENT}" \
        PYTHONPATH="/app" \
        PORT="8000" \
        CHROMA_SERVER_HOST="0.0.0.0" \
        CHROMA_SERVER_HTTP_PORT="8001"
    
    echo -e "${GREEN}✅ Backend environment variables set${NC}"
    
    # Show current config
    echo -e "\n${BLUE}Current Backend Config:${NC}"
    heroku config -a ${BACKEND_APP}
}

# Function to set frontend environment variables
set_frontend_env() {
    echo -e "\n${YELLOW}🌐 Setting Frontend Environment Variables (${FRONTEND_APP})...${NC}"
    
    # Check if app exists
    if ! heroku apps:info -a ${FRONTEND_APP} &> /dev/null; then
        echo -e "${RED}❌ Frontend app '${FRONTEND_APP}' not found. Please create it first.${NC}"
        exit 1
    fi
    
    # Set environment variables
    heroku config:set -a ${FRONTEND_APP} \
        BACKEND_URL="${BACKEND_URL}" \
        PORT="8080"
    
    echo -e "${GREEN}✅ Frontend environment variables set${NC}"
    
    # Show current config
    echo -e "\n${BLUE}Current Frontend Config:${NC}"
    heroku config -a ${FRONTEND_APP}
}

# Function to update frontend to use backend URL
update_frontend_config() {
    echo -e "\n${YELLOW}🔄 Updating Frontend Configuration...${NC}"
    
    # Update the frontend JavaScript to use the backend URL
    if [ -f "frontend/app.js" ]; then
        # Create a backup
        cp frontend/app.js frontend/app.js.backup
        
        # Update the API base URL
        sed -i.bak "s|http://localhost:8000|${BACKEND_URL}|g" frontend/app.js
        
        echo -e "${GREEN}✅ Frontend configuration updated${NC}"
        echo -e "${BLUE}   API Base URL: ${BACKEND_URL}${NC}"
    else
        echo -e "${YELLOW}⚠️  frontend/app.js not found, skipping configuration update${NC}"
    fi
}

# Function to show all environment variables
show_all_config() {
    echo -e "\n${YELLOW}📊 All Environment Variables:${NC}"
    
    echo -e "\n${BLUE}Backend (${BACKEND_APP}):${NC}"
    heroku config -a ${BACKEND_APP}
    
    echo -e "\n${BLUE}Frontend (${FRONTEND_APP}):${NC}"
    heroku config -a ${FRONTEND_APP}
}

# Main function
main() {
    # Parse command line arguments
    SHOW_CONFIG=false
    UPDATE_FRONTEND=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --show-config)
                SHOW_CONFIG=true
                shift
                ;;
            --update-frontend)
                UPDATE_FRONTEND=true
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --show-config      Show current environment variables"
                echo "  --update-frontend  Update frontend to use backend URL"
                echo "  --help             Show this help message"
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
    
    # Show config if requested
    if [ "$SHOW_CONFIG" = true ]; then
        show_all_config
        exit 0
    fi
    
    # Update frontend if requested
    if [ "$UPDATE_FRONTEND" = true ]; then
        update_frontend_config
        exit 0
    fi
    
    # Prompt for environment variables
    prompt_for_env_vars
    
    # Set environment variables
    set_backend_env
    set_frontend_env
    
    # Update frontend configuration
    update_frontend_config
    
    echo -e "\n${GREEN}🎉 Environment setup completed successfully!${NC}"
    echo -e "${BLUE}Frontend: ${FRONTEND_URL}${NC}"
    echo -e "${BLUE}Backend:  ${BACKEND_URL}${NC}"
    echo -e "${BLUE}API Docs: ${BACKEND_URL}/docs${NC}"
    
    echo -e "\n${YELLOW}Next steps:${NC}"
    echo "1. Run './deploy.sh' to deploy both applications"
    echo "2. Check deployment status with './deploy.sh --status'"
}

# Run main function with all arguments
main "$@"
