#!/bin/bash
# Enhanced deployment script with PostgreSQL setup

set -e

echo "🚀 Starting RxVerify deployment with PostgreSQL..."

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
BACKEND_APP="rxverify-backend"
FRONTEND_APP="rxverify-frontend"

print_status "Setting up PostgreSQL database..."

# Add PostgreSQL addon to backend app (free tier)
if heroku addons:info postgresql --app $BACKEND_APP &> /dev/null; then
    print_status "PostgreSQL addon already exists for $BACKEND_APP"
else
    print_status "Adding PostgreSQL addon to $BACKEND_APP..."
    heroku addons:create heroku-postgresql:mini --app $BACKEND_APP
    print_status "✅ PostgreSQL addon added successfully"
fi

# Wait for database to be ready
print_status "Waiting for database to be ready..."
sleep 10

# Get database URL
DATABASE_URL=$(heroku config:get DATABASE_URL --app $BACKEND_APP)
if [ -z "$DATABASE_URL" ]; then
    print_error "Failed to get DATABASE_URL from Heroku"
    exit 1
fi

print_status "Database URL obtained: ${DATABASE_URL:0:20}..."

# Update version
print_status "Updating version..."
./update_version.sh

# Deploy backend
print_status "Deploying backend to Heroku..."
git subtree push --prefix=. heroku-backend main

# Deploy frontend
print_status "Deploying frontend to Heroku..."
git subtree push --prefix=frontend heroku-frontend main

# Run database migration on Heroku
print_status "Running database migration on Heroku..."
heroku run python migrate_database.py --app $BACKEND_APP

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
print_status "Database: PostgreSQL (persistent storage enabled)"

# Show recent logs
print_status "Recent backend logs:"
heroku logs --tail --app $BACKEND_APP --num 20
