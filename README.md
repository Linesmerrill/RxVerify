# RxVerify

A real-time medication search and drug information system designed for post-discharge medication management. Features live API integration with RxNorm, DailyMed, OpenFDA, and DrugBank, plus intelligent feedback-driven ML pipeline optimization.

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

### **Core Search Endpoints**
- `POST /search` - Enhanced medication search with post-discharge focus
- `POST /query` - General drug information queries (Ask Questions - coming soon)

### **Feedback System**
- `POST /feedback` - Submit thumbs up/down feedback on search results
- `GET /feedback/stats` - Get feedback analytics and trends
- `POST /feedback/remove` - Remove specific feedback entries
- `POST /feedback/clear` - Clear all feedback data

### **Admin & Management**
- `GET /status` - Comprehensive system status and health metrics
- `GET /cache/stats` - Medication cache statistics
- `POST /cache/clear` - Clear medication cache
- `GET /rxlist/stats` - RxList database statistics
- `POST /rxlist/clear` - Clear RxList database
- `POST /rxlist/ingest` - Ingest new RxList data

### **System Health**
- `GET /health` - Basic health check
- `GET /` - API information and version

## 🎯 Features

### 🔍 **Core Search Features**
- **Real-time Medication Search**: Live API queries to RxNorm, DailyMed, OpenFDA, and DrugBank
- **Post-Discharge Focus**: Curated results for oral medications typically prescribed after hospital stays
- **Intelligent Deduplication**: Combines duplicate drugs with different dosages into single results
- **RxCUI Integration**: Direct links to RxNav for detailed drug information
- **Partial Name Expansion**: Smart expansion of common drug prefixes (e.g., "metf" → "metformin")

### 🤖 **AI & ML Features**
- **Feedback-Driven Learning**: Thumbs up/down voting system for continuous improvement
- **ML Pipeline Integration**: User feedback feeds into result ranking and optimization
- **Real-time Analytics**: Admin dashboard with feedback trends and system metrics
- **Zero Hallucinations**: All responses sourced from official medical databases

### 🎨 **User Experience**
- **Modern UI**: Clean, responsive design with dark/light mode toggle
- **Real-time Feedback**: Live vote counts and visual feedback on search results
- **Admin Dashboard**: Comprehensive analytics and system management tools
- **Mobile Responsive**: Optimized for all device sizes
- **Progressive Web App**: PWA capabilities with offline support

### 🔧 **System Features**
- **Automated Versioning**: Dynamic version numbers with deployment timestamps
- **Health Monitoring**: Comprehensive system status and performance metrics
- **Cache Management**: Intelligent caching for improved performance
- **Cross-Source Validation**: Detects and reports data discrepancies between sources

## 🔍 Testing the System

1. **Start the servers**: `make run`
2. **Open frontend**: `make open`
3. **Test medication search**:
   - Search for "metformin" or "metf"
   - Search for "atorvastatin" or "ator"
   - Search for "lisinopril" or "lisi"
4. **Test feedback system**:
   - Vote on search results using thumbs up/down
   - Check admin dashboard for feedback analytics
5. **Test admin features**:
   - Access admin dropdown in top navigation
   - View feedback analytics and system metrics
   - Clear caches and manage system data

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
