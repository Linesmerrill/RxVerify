#!/bin/bash
# Script to add PostgreSQL addon to Heroku apps

set -e

echo "🔧 Adding PostgreSQL addon to Heroku apps..."

# App names
BACKEND_APP="rxverify-backend"

# Check if Heroku CLI is installed
if ! command -v heroku &> /dev/null; then
    echo "❌ Heroku CLI is not installed. Please install it first."
    exit 1
fi

# Check if we're logged into Heroku
if ! heroku auth:whoami &> /dev/null; then
    echo "❌ Not logged into Heroku. Please run 'heroku login' first."
    exit 1
fi

echo "📋 Adding PostgreSQL addon to $BACKEND_APP..."

# Add PostgreSQL addon (free tier)
if heroku addons:info postgresql --app $BACKEND_APP &> /dev/null; then
    echo "✅ PostgreSQL addon already exists for $BACKEND_APP"
else
    echo "➕ Adding PostgreSQL addon..."
    heroku addons:create heroku-postgresql:mini --app $BACKEND_APP
    echo "✅ PostgreSQL addon added successfully"
fi

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 15

# Get database URL
echo "🔗 Getting database URL..."
DATABASE_URL=$(heroku config:get DATABASE_URL --app $BACKEND_APP)
if [ -z "$DATABASE_URL" ]; then
    echo "❌ Failed to get DATABASE_URL from Heroku"
    exit 1
fi

echo "✅ Database URL obtained: ${DATABASE_URL:0:30}..."

# Show database info
echo "📊 Database information:"
heroku addons:info postgresql --app $BACKEND_APP

echo "🎉 PostgreSQL setup completed!"
echo "💡 Next steps:"
echo "   1. Run: ./deploy_with_postgres.sh"
echo "   2. Or manually deploy and run: heroku run python migrate_database.py --app $BACKEND_APP"
