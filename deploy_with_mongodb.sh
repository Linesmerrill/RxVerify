#!/bin/bash
# Enhanced deployment script with MongoDB Atlas setup

set -e

echo "🚀 Starting RxVerify deployment with MongoDB Atlas..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Heroku CLI is installed
if ! command -v heroku &> /dev/null; then
    print_error "Heroku CLI is not installed. Please install it first."
    exit 1
fi

# Check if we're logged into Heroku
if ! heroku auth:whoami &> /dev/null; then
    print_error "Not logged into Heroku. Please run 'heroku login' first."
    exit 1
fi

# App names
BACKEND_APP="rx-verify-api"
FRONTEND_APP="rx-verify"

print_status "Checking MongoDB Atlas configuration..."

# Check if MongoDB URI is set
MONGODB_URI=$(heroku config:get MONGODB_URI --app $BACKEND_APP 2>/dev/null || echo "")
if [ -z "$MONGODB_URI" ]; then
    print_warning "MongoDB URI not found. Please run ./setup_mongodb.sh first."
    echo ""
    echo "Quick MongoDB Atlas setup:"
    echo "1. Go to https://www.mongodb.com/atlas/database"
    echo "2. Create free cluster (M0 Sandbox)"
    echo "3. Get connection string"
    echo "4. Run: ./setup_mongodb.sh"
    echo ""
    read -p "Do you want to continue without MongoDB? (y/N): " continue_without_mongo
    
    if [[ ! $continue_without_mongo =~ ^[Yy]$ ]]; then
        print_error "Deployment cancelled. Please set up MongoDB Atlas first."
        exit 1
    fi
    
    print_warning "Continuing deployment without MongoDB (will use SQLite)"
else
    print_status "MongoDB URI found: ${MONGODB_URI:0:30}..."
fi

# Update version
print_status "Updating version..."
./update_version.sh

# Deploy backend
print_status "Deploying backend to Heroku..."
git subtree push --prefix=. heroku-backend main

# Deploy frontend
print_status "Deploying frontend to Heroku..."
git subtree push --prefix=frontend heroku-frontend main

# Run database migration on Heroku (if MongoDB is configured)
if [ -n "$MONGODB_URI" ]; then
    print_status "Running MongoDB migration on Heroku..."
    heroku run python migrate_to_mongodb.py --app $BACKEND_APP
else
    print_warning "Skipping MongoDB migration (no MongoDB URI configured)"
fi

# Check deployment status
print_status "Checking deployment status..."

# Backend health check
BACKEND_URL="https://$BACKEND_APP.herokuapp.com"
if curl -s "$BACKEND_URL/status" > /dev/null; then
    print_status "✅ Backend deployment successful"
else
    print_warning "Backend health check failed - may still be starting up"
fi

# Frontend health check
FRONTEND_URL="https://$FRONTEND_APP.herokuapp.com"
if curl -s "$FRONTEND_URL" > /dev/null; then
    print_status "✅ Frontend deployment successful"
else
    print_warning "Frontend health check failed - may still be starting up"
fi

print_status "🎉 Deployment completed!"
print_status "Backend: $BACKEND_URL"
print_status "Frontend: $FRONTEND_URL"

if [ -n "$MONGODB_URI" ]; then
    print_status "Database: MongoDB Atlas (persistent storage enabled)"
else
    print_warning "Database: SQLite (data will be lost on deployment)"
fi

# Show recent logs
print_status "Recent backend logs:"
heroku logs --tail --app $BACKEND_APP --num 20
