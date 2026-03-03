#!/bin/bash

# RxVerify Run Script
# Simple script to start both backend and frontend

set -e

echo "🚀 RxVerify Development Server"
echo "================================"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down servers..."
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "python -m http.server 8080" 2>/dev/null || true
    echo "✅ Servers stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

# Check if virtual environment exists
if [ -f "venv/bin/activate" ]; then
    echo "📦 Activating Python virtual environment..."
    source venv/bin/activate
elif [ -f "venv/bin/activate.fish" ]; then
    echo "🐟 Fish shell detected - please run: source venv/bin/activate.fish"
    echo "Then run this script again or use: make run"
    exit 1
else
    echo "❌ Virtual environment not found. Please create one first:"
    echo "   python -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Check if required packages are installed
if ! python -c "import uvicorn, fastapi" 2>/dev/null; then
    echo "❌ Required packages not installed. Installing now..."
    pip install -r requirements.txt
fi

echo ""
echo "🚀 Starting Backend Server (port 8000)..."
echo "🌐 Starting Frontend Server (port 8080)..."
echo ""

# Start backend in background
echo "Starting backend..."
python -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

# Fix any incorrect drug class assignments in the database
echo "Fixing drug class assignments..."
python scripts/fix_drug_classes.py --api-url http://localhost:8000 || echo "Warning: Drug class fix script failed (non-fatal)"
echo ""

# Start frontend in background
echo "Starting frontend..."
cd frontend
python -m http.server 8080 &
FRONTEND_PID=$!

# Go back to root directory
cd ..

echo ""
echo "🎉 Both servers started successfully!"
echo "====================================="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:8080"
echo "Health:   http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for user interrupt
wait
