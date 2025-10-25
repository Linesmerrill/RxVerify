# RxVerify

A modern drug search and information system featuring intelligent ranking, user-driven feedback, and real-time analytics. Built with a curated MongoDB database of 100,000+ drugs, sophisticated search algorithms, and a self-improving voting system that learns from user preferences.

## 🗄️ Database Setup

RxVerify supports multiple database options for persistent storage:

### Option 1: MongoDB Atlas (Recommended - FREE)
- **Free tier**: 512MB storage, shared clusters
- **Persistent**: Data survives deployments and dyno restarts
- **NoSQL**: Flexible document-based storage
- **Setup**: Automatic via `MONGODB_URI` environment variable

### Option 2: PostgreSQL (Paid)
- **Paid tier**: Heroku PostgreSQL Essential 0 (~$5/month)
- **Persistent**: Data survives deployments and dyno restarts
- **SQL**: Relational database with ACID compliance
- **Setup**: Automatic via `DATABASE_URL` environment variable

### Option 3: SQLite (Local Development)
- **File-based**: `rxverify.db` in project root
- **No setup required**: Automatically created on first run
- **Fast**: Perfect for development and testing
- **Note**: Data lost on Heroku deployments

### Database Migration
When deploying to production, the system automatically:
1. Detects database type from environment variables
2. Creates required tables/collections and indexes
3. Migrates existing SQLite data (if any)

### MongoDB Atlas Setup (FREE)
```bash
# Interactive setup with guided instructions
./setup_mongodb.sh

# Deploy with MongoDB
./deploy_with_mongodb.sh
```

### PostgreSQL Setup (PAID)
```bash
# Add PostgreSQL addon to Heroku
./setup_postgres.sh

# Deploy with PostgreSQL
./deploy_with_postgres.sh
```

## 🚀 Quick Start

### Option 1: Using Makefile (Recommended)
```bash
# Start both backend and frontend
make run

# Stop both servers
make stop

# Check server status
make status

# Open frontend in browser
make open
```

### Option 2: Using Run Script
```bash
# Start both servers
./run.sh

# Press Ctrl+C to stop
```

### Option 3: Manual Start
```bash
# Terminal 1: Start backend
source venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2: Start frontend
cd frontend
python -m http.server 8080
```

## 🛠️ Development Commands

```bash
# View all available commands
make help

# Individual server control
make run-backend     # Start only backend
make run-frontend    # Start only frontend
make stop-backend    # Stop only backend
make stop-frontend   # Stop only frontend

# Utility commands
make install         # Install dependencies
make test           # Run tests
make status         # Check server status
make logs           # Show backend logs
make clean          # Clean up processes and files
make restart        # Restart both servers
make health         # Quick health check
```

## 📋 Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- OpenAI API key

## 🔧 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd RxVerify
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install
   # or manually: pip install -r requirements.txt
   ```

4. **Set environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

## 🌐 Access Points

- **Frontend**: http://localhost:8080
- **Backend API**: http://localhost:8000
- **Health Check**: http://localhost:8000/health
- **API Docs**: http://localhost:8000/docs

## 🔌 API Endpoints

### **Core Drug Search**
- `GET /drugs/search` - Fast local drug search with intelligent ranking
- `GET /drugs/vote-status` - Check if user has voted on a specific drug
- `POST /drugs/vote` - Vote on drugs (upvote/downvote) with anonymous tracking
- `GET /drugs/common-uses` - Get common uses for specific drugs

### **Admin Dashboard**
- `GET /admin/stats` - System overview and database statistics
- `GET /admin/recent-activity` - Recent search activity with pagination
- `GET /metrics/summary` - Performance metrics and analytics
- `GET /metrics/time-series` - Time-series data for charts
- `GET /feedback/stats` - Feedback analytics and trends
- `POST /feedback/remove` - Remove specific feedback entries

### **Real-time Features**
- `WebSocket /ws/admin` - Live updates for admin dashboard
- `GET /status` - Comprehensive system status and health metrics
- `GET /health` - Basic health check
- `GET /` - API information and version

## 🎯 Features

### 🔍 **Intelligent Drug Search**
- **Curated Database**: 100,000+ drugs from Drugs.com with clean, deduplicated names
- **Smart Ranking**: Multi-tier scoring system prioritizing prefix matches, single drugs, then combinations
- **Real-time Search**: Instant results with debounced input and skeleton loading
- **Drug Types**: Generic, brand, and combination drugs with proper categorization
- **Prefix Matching**: "Met" shows drugs starting with "Met" first, then containing "Met"

### 🗳️ **Self-Improving Voting System**
- **Anonymous Tracking**: IP + User Agent hash for consistent user identification
- **Backend Verification**: Frontend checks with backend before voting to prevent false states
- **Vote Switching**: Users can change votes (unvote old, vote new)
- **Dynamic Ranking**: Vote scores significantly impact search ranking (+25/-25 points)
- **Auto-Hiding**: Poorly rated drugs (rating ≤ -0.5, 3+ votes) disappear from results
- **Social Proof**: Drugs with 5+ votes get bonus ranking points

### 📊 **Real-time Analytics**
- **Live Admin Dashboard**: WebSocket-powered real-time updates
- **Search Metrics**: Total requests, success rate, average response time
- **Feedback Analytics**: Vote trends, helpful/unhelpful ratios, drug ratings
- **Recent Activity**: Paginated search history with local time conversion
- **Performance Monitoring**: System health, database stats, and error tracking

### 🎨 **Modern User Experience**
- **Responsive Design**: Works perfectly on desktop, tablet, and mobile
- **Dark/Light Mode**: Automatic theme switching with persistent preferences
- **Optimistic Updates**: Immediate UI feedback with error reversion
- **Skeleton Loading**: Smooth loading states for better perceived performance
- **Toast Notifications**: Real-time feedback for all user actions
- **Keyboard Shortcuts**: Ctrl+Enter to search, Escape to clear

## 🔍 Testing the System

1. **Start the servers**: `make run`
2. **Open frontend**: `make open`
3. **Test intelligent drug search**:
   - Search for "metformin" or "met" (prefix matching)
   - Search for "atorvastatin" or "ator" (generic vs combination)
   - Search for "lisinopril" or "lisi" (single word drugs)
4. **Test voting system**:
   - Vote on search results using thumbs up/down
   - Try vote switching (upvote → downvote → upvote)
   - Check how votes affect search ranking
5. **Test admin dashboard**:
   - Access admin dropdown in top navigation
   - View real-time metrics and analytics
   - Check recent activity with pagination
   - Monitor WebSocket live updates

## 🚀 Deployment

### **Automated Deployment**
```bash
# Deploy to Heroku with automatic versioning
./deploy.sh

# Deploy without version update
./deploy.sh --skip-version

# Update version only
./update_version.sh
```

### **Manual Deployment**
```bash
# Frontend deployment
cd frontend
git subtree push --prefix=frontend heroku-frontend main

# Backend deployment  
git subtree push --prefix=. heroku-backend main
```

### **Version Management**
- **Format**: `v1.0.0-beta.YYYYMMDD-HHMMSS`
- **Auto-generated**: Timestamps in Zulu format
- **Cache-busting**: Automatic frontend cache version updates
- **Git Integration**: Auto-commit and push version changes

## 📚 Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system architecture and data flow diagrams.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
