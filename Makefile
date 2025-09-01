# RxVerify Makefile
# Simple commands to manage the backend and frontend

.PHONY: help run run-backend run-frontend stop clean install test status logs

# Default target
help:
	@echo "🚀 RxVerify Development Commands"
	@echo ""
		@echo "Main Commands:"
	@echo "  make run          - Start both servers with Python Server Manager"
	@echo "  make start        - Alias for make run"
	@echo "  make stop         - Stop both backend and frontend"
	@echo "  make restart      - Restart both servers"
	@echo ""
	@echo "Individual Commands:"
	@echo "  make run-backend  - Start only the backend (port 8000)"
	@echo "  make run-frontend - Start only the frontend (port 8080)"
	@echo "  make stop-backend - Stop only the backend"
	@echo "  make stop-frontend- Stop only the frontend"
	@echo ""
	@echo "Utility Commands:"
	@echo "  make install      - Install Python dependencies"
	@echo "  make test         - Run backend tests"
	@echo "  make status       - Check server status"
	@echo "  make logs         - Show backend logs"
	@echo "  make clean        - Clean up processes and temporary files"
	@echo "  make open         - Open frontend in browser"
	@echo ""

# Start both servers
run:
	@echo "🚀 Starting RxVerify with Python Server Manager..."
	@python run_servers.py

# Start backend server
run-backend:
	@echo "🚀 Starting RxVerify Backend..."
	@if [ -f "venv/bin/activate.fish" ]; then \
		echo "Using Fish shell virtual environment"; \
		source venv/bin/activate.fish && python -m uvicorn app.main:app --reload --port 8000; \
	else \
		echo "Using standard Python virtual environment"; \
		source venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000; \
	fi

# Start frontend server
run-frontend:
	@echo "🌐 Starting RxVerify Frontend..."
	@cd frontend && python -m http.server 8080

# Stop both servers
stop: stop-backend stop-frontend
	@echo "🛑 Both servers stopped"

# Stop backend server
stop-backend:
	@echo "🛑 Stopping Backend..."
	@-pkill -f "uvicorn app.main:app" || echo "Backend not running"

# Stop frontend server
stop-frontend:
	@echo "🛑 Stopping Frontend..."
	@-pkill -f "python -m http.server 8080" || echo "Frontend not running"

# Restart both servers
restart: stop run

# Install dependencies
install:
	@echo "📦 Installing Python dependencies..."
	@python -m pip install --upgrade pip
	@python -m pip install -r requirements.txt
	@echo "✅ Dependencies installed!"

# Run tests
test:
	@echo "🧪 Running tests..."
	@python -m pytest tests/ -v

# Check server status
status:
	@echo "📊 Checking server status..."
	@echo "Backend Health:"
	@-curl -s "http://localhost:8000/health" | jq '.' 2>/dev/null || echo "Backend not responding"
	@echo ""
	@echo "Frontend Status:"
	@-curl -s "http://localhost:8080" | head -1 2>/dev/null || echo "Frontend not responding"
	@echo ""
	@echo "Running Processes:"
	@ps aux | grep -E "(uvicorn|http.server)" | grep -v grep || echo "No servers running"

# Show backend logs
logs:
	@echo "📝 Backend logs (last 50 lines):"
	@-tail -n 50 logs/app.log 2>/dev/null || echo "No log file found"

# Clean up processes and temporary files
clean:
	@echo "🧹 Cleaning up..."
	@make stop
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type f -name ".DS_Store" -delete
	@echo "✅ Cleanup complete!"

# Open frontend in browser
open:
	@echo "🌐 Opening frontend in browser..."
	@open "http://localhost:8080" 2>/dev/null || \
	xdg-open "http://localhost:8080" 2>/dev/null || \
	echo "Could not open browser automatically. Please visit: http://localhost:8080"

# Development mode with auto-reload
dev: run
	@echo "🔄 Development mode active - files will auto-reload"

# Start with Python server manager
start: run
	@echo "🚀 RxVerify started with Python Server Manager"

# Quick health check
health:
	@echo "🏥 Quick health check..."
	@curl -s "http://localhost:8000/health" | jq '.status' 2>/dev/null || echo "Backend unhealthy"
