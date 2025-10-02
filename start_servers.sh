#!/bin/bash

# RxVerify Server Startup Script
# Starts both backend and frontend servers with proper signal handling

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to cleanup processes
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down servers...${NC}"
    
    if [ ! -z "$BACKEND_PID" ]; then
        echo -e "${BLUE}   Stopping backend (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
        echo -e "${GREEN}   ✅ Backend stopped${NC}"
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        echo -e "${BLUE}   Stopping frontend (PID: $FRONTEND_PID)...${NC}"
        kill $FRONTEND_PID 2>/dev/null || true
        wait $FRONTEND_PID 2>/dev/null || true
        echo -e "${GREEN}   ✅ Frontend stopped${NC}"
    fi
    
    echo -e "${GREEN}✅ All servers stopped${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo -e "${BLUE}🚀 RxVerify Server Manager${NC}"
echo -e "${BLUE}==========================${NC}"

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${RED}❌ Virtual environment not detected!${NC}"
    echo -e "${YELLOW}Please activate your virtual environment first:${NC}"
    echo -e "  source venv/bin/activate"
    echo -e "  # or for fish shell:"
    echo -e "  source venv/bin/activate.fish"
    exit 1
fi

# Check if required packages are installed
if ! python -c "import uvicorn, fastapi" 2>/dev/null; then
    echo -e "${RED}❌ Required packages not installed!${NC}"
    echo -e "${YELLOW}Please install dependencies first:${NC}"
    echo -e "  pip install -r requirements.txt"
    exit 1
fi

# Start backend server
echo -e "${BLUE}🚀 Starting RxVerify Backend...${NC}"
python -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo -e "${YELLOW}⏳ Waiting for backend to be ready...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready!${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Backend failed to start within timeout${NC}"
        cleanup
        exit 1
    fi
    sleep 1
    if [ $((i % 5)) -eq 0 ]; then
        echo -e "${YELLOW}   Still waiting... ($i/30)${NC}"
    fi
done

# Start frontend server
echo -e "${BLUE}🌐 Starting RxVerify Frontend...${NC}"
cd frontend
python -m http.server 8080 &
FRONTEND_PID=$!
cd ..

# Wait for frontend to be ready
echo -e "${YELLOW}⏳ Waiting for frontend to be ready...${NC}"
for i in {1..10}; do
    if curl -s http://localhost:8080 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Frontend is ready!${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}❌ Frontend failed to start within timeout${NC}"
        cleanup
        exit 1
    fi
    sleep 1
done

# Show status
echo -e "\n${GREEN}🎉 Both servers are running successfully!${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}Backend API:  ${NC}http://localhost:8000"
echo -e "${GREEN}Frontend UI:  ${NC}http://localhost:8080"
echo -e "${GREEN}Health Check: ${NC}http://localhost:8000/health"
echo -e "${GREEN}API Docs:     ${NC}http://localhost:8000/docs"
echo -e "${BLUE}==================================================${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop both servers${NC}"
echo ""

# Monitor processes
while true; do
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Backend process died unexpectedly${NC}"
        cleanup
        exit 1
    fi
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Frontend process died unexpectedly${NC}"
        cleanup
        exit 1
    fi
    sleep 1
done
