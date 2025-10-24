#!/bin/bash
# Script to set up MongoDB Atlas for Heroku apps

set -e

echo "🔧 Setting up MongoDB Atlas for Heroku apps..."

# App names
BACKEND_APP="rx-verify-api"

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

echo "📋 Setting up MongoDB Atlas for $BACKEND_APP..."

# Instructions for MongoDB Atlas setup
echo "🌐 MongoDB Atlas Setup Instructions:"
echo "=================================="
echo ""
echo "1. Go to https://www.mongodb.com/atlas/database"
echo "2. Sign up for a free account (if you don't have one)"
echo "3. Create a new project"
echo "4. Build a free cluster (M0 Sandbox - FREE)"
echo "5. Choose a cloud provider and region"
echo "6. Create cluster (takes 3-5 minutes)"
echo ""
echo "7. Set up database access:"
echo "   - Go to 'Database Access'"
echo "   - Click 'Add New Database User'"
echo "   - Choose 'Password' authentication"
echo "   - Create username and password"
echo "   - Set privileges to 'Read and write to any database'"
echo ""
echo "8. Set up network access:"
echo "   - Go to 'Network Access'"
echo "   - Click 'Add IP Address'"
echo "   - Choose 'Allow access from anywhere' (0.0.0.0/0)"
echo "   - Or add specific IP addresses"
echo ""
echo "9. Get connection string:"
echo "   - Go to 'Database'"
echo "   - Click 'Connect' on your cluster"
echo "   - Choose 'Connect your application'"
echo "   - Copy the connection string"
echo "   - Replace <password> with your database user password"
echo ""

# Prompt for MongoDB URI
echo "📝 Please enter your MongoDB Atlas connection string:"
echo "   (Format: mongodb+srv://username:password@cluster.mongodb.net/database)"
read -p "MongoDB URI: " MONGODB_URI

if [ -z "$MONGODB_URI" ]; then
    echo "❌ MongoDB URI is required"
    exit 1
fi

# Set MongoDB URI as Heroku config var
echo "🔗 Setting MongoDB URI as Heroku config var..."
heroku config:set MONGODB_URI="$MONGODB_URI" --app $BACKEND_APP

# Verify the config var was set
echo "✅ MongoDB URI set successfully"
echo "📊 Current config vars:"
heroku config --app $BACKEND_APP | grep MONGODB

echo ""
echo "🎉 MongoDB Atlas setup completed!"
echo "💡 Next steps:"
echo "   1. Run: ./deploy_with_mongodb.sh"
echo "   2. Or manually deploy and run: heroku run python migrate_to_mongodb.py --app $BACKEND_APP"
echo ""
echo "🔍 To verify your MongoDB connection:"
echo "   heroku run python -c \"from app.mongodb_config import mongodb_config; import asyncio; print(asyncio.run(mongodb_config.test_connection()))\" --app $BACKEND_APP"
