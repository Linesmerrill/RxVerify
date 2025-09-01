# RxVerify

A real-time Retrieval-Augmented Generation system for comprehensive drug information, integrating data from RxNorm, DailyMed, OpenFDA, and DrugBank APIs.

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

## 🎯 Features

- **Real-time Medical Database Integration**: Live queries to RxNorm, DailyMed, OpenFDA, and DrugBank
- **Enhanced DailyMed XML Parsing**: Comprehensive package insert content extraction
- **Zero Hallucinations**: All responses sourced from official medical databases
- **Professional UI**: Modern frontend with progress updates and debug information
- **Cross-Source Validation**: Detects and reports data discrepancies between sources

## 🔍 Testing the System

1. **Start the servers**: `make run`
2. **Open frontend**: `make open`
3. **Test queries**:
   - "What are the side effects of warfarin?"
   - "What are the side effects of ibuprofen?"
   - "What are the side effects of metformin?"

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
