# RxVerify: Multi-Database Drug Assistant

> **Production-Ready Retrieval-Augmented Generation (RAG) backend** that ingests RxNorm, DailyMed, OpenFDA, and DrugBank data, normalizes to RxCUI, cross-checks fields, and answers questions with intelligent AI responses and proper citations.

## 🚀 **System Overview**

RxVerify is a comprehensive drug information system that combines:
- **Vector Database**: ChromaDB for semantic search and retrieval
- **AI Integration**: OpenAI GPT-4o-mini for intelligent responses
- **Multi-Source Data**: RxNorm, DailyMed, OpenFDA, and DrugBank
- **Cross-Validation**: Detects disagreements between sources
- **Production Ready**: Monitoring, logging, and health checks

## 🏗️ **Architecture**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App  │    │   ChromaDB      │    │   OpenAI API    │
│   (Port 8000)  │◄──►│   Vector Store  │◄──►│   GPT-4o-mini   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ETL Pipeline │    │   Cross-Check   │    │   Response      │
│   (4 Sources)  │    │   & Unification │    │   Generation    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 **Project Structure**

```
RxVerify/
├── app/                    # Main application
│   ├── main.py           # FastAPI app with endpoints
│   ├── models.py         # Pydantic data models
│   ├── db.py             # ChromaDB integration
│   ├── embeddings.py     # Vector embedding service
│   ├── retriever.py      # Hybrid search (vector + keyword)
│   ├── crosscheck.py     # Source validation & unification
│   ├── llm.py            # OpenAI integration
│   ├── config.py         # Configuration management
│   ├── logging.py        # Logging setup
│   └── monitoring.py     # Health checks & monitoring
├── etl/                   # Data ingestion pipeline
│   ├── common.py         # Shared ETL utilities
│   ├── rxnorm.py         # RxNorm drug nomenclature
│   ├── dailymed.py       # FDA drug labeling
│   ├── openfda.py        # Drug safety & adverse events
│   └── drugbank.py       # Drug interactions & mechanisms
├── scripts/               # Utility scripts
│   ├── run_etl.py        # Master ETL pipeline
│   ├── start_production.py # Production server startup
│   └── test_chromadb.py  # Database testing
├── tests/                 # Test suite
├── logs/                  # Application logs
├── chroma_db/            # ChromaDB data storage
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container configuration
└── .env.example          # Environment variables template
```

## 🚀 **Quick Start**

### 1. **Environment Setup**

```bash
# Clone the repository
git clone <your-repo-url>
cd RxVerify

# Create virtual environment
python3 -m venv venv
source venv/bin/activate.fish  # For fish shell
# OR source venv/bin/activate   # For bash/zsh

# Install dependencies
pip install -r requirements.txt
```

### 2. **Configuration**

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your OpenAI API key
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 3. **Data Ingestion**

```bash
# Run the complete ETL pipeline
python scripts/run_etl.py

# Or run individual sources
python scripts/run_etl.py --source rxnorm
python scripts/run_etl.py --source dailymed
python scripts/run_etl.py --source openfda
python scripts/run_etl.py --source drugbank
```

### 4. **Start the Server**

```bash
# Development mode
python -m uvicorn app.main:app --reload --port 8000

# Production mode
python scripts/start_production.py
```

## 🔍 **API Endpoints**

### **Core Endpoints**

- `GET /` - API information and documentation links
- `GET /health` - Basic health check
- `GET /status` - Comprehensive system status
- `POST /query` - Main drug information query endpoint

### **Query Endpoint**

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the drug interactions for atorvastatin?",
    "top_k": 5
  }'
```

**Response includes:**
- Intelligent AI-generated answer
- Source citations and context
- Processing time
- Sources consulted
- Cross-validated information

## 📊 **Data Sources**

| Source | Content | Records | Update Frequency |
|--------|---------|---------|------------------|
| **RxNorm** | Drug nomenclature, relationships | 4 | Monthly |
| **DailyMed** | FDA-approved labeling (SPL) | 3 | Real-time |
| **OpenFDA** | Drug safety, adverse events | 5 | Weekly |
| **DrugBank** | Mechanisms, interactions | 3 | Quarterly |

## 🛠️ **Production Deployment**

### **Docker Deployment**

```bash
# Build the image
docker build -t rxverify .

# Run the container
docker run -d \
  -p 8000:8000 \
  -e OPENAI_API_KEY=your-key \
  -v $(pwd)/chroma_db:/app/chroma_db \
  -v $(pwd)/logs:/app/logs \
  rxverify
```

### **Environment Variables**

```bash
# Required
OPENAI_API_KEY=sk-your-api-key

# Optional (with defaults)
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=1000
OPENAI_TEMPERATURE=0.1
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1
LOG_LEVEL=INFO
CHROMADB_PATH=./chroma_db
RATE_LIMIT_PER_MINUTE=60
```

### **Monitoring & Health Checks**

- **Health Endpoint**: `/health` for basic status
- **Status Endpoint**: `/status` for detailed system metrics
- **Logging**: Structured logs in `logs/` directory
- **Metrics**: Request count, success rate, uptime
- **Performance**: Processing time headers

## 🔧 **Development & Testing**

### **Running Tests**

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_crosscheck.py
```

### **Database Testing**

```bash
# Test ChromaDB functionality
python scripts/test_chromadb.py

# Check database contents
python scripts/check_chromadb.py
```

### **ETL Development**

```bash
# Test individual ETL sources
python etl/rxnorm.py
python etl/dailymed.py
python etl/openfda.py
python etl/drugbank.py
```

## 📈 **Performance & Scaling**

### **Current Performance**
- **Query Response Time**: ~500-2000ms (depending on complexity)
- **Vector Search**: ChromaDB with 384-dimensional embeddings
- **Concurrent Requests**: Configurable worker processes
- **Memory Usage**: ~500MB for current drug dataset

### **Scaling Considerations**
- **ChromaDB**: Can be scaled to distributed instances
- **Embeddings**: Can switch to production embedding services
- **API**: Can be load-balanced behind nginx
- **Data**: ETL pipeline can be scheduled and automated

## 🚨 **Troubleshooting**

### **Common Issues**

1. **ChromaDB Connection Errors**
   - Check `chroma_db/` directory permissions
   - Ensure sufficient disk space

2. **OpenAI API Errors**
   - Verify API key in `.env` file
   - Check API quota and billing

3. **ETL Pipeline Failures**
   - Check network connectivity for data sources
   - Verify source data availability

### **Logs & Debugging**

```bash
# View application logs
tail -f logs/rxverify_*.log

# Check system status
curl http://localhost:8000/status

# Test individual components
python scripts/test_chromadb.py
```

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 **Support**

For questions or issues:
- Check the [troubleshooting section](#-troubleshooting)
- Review the logs in `logs/` directory
- Test individual components with provided scripts
- Open an issue with detailed error information

---

**⚠️ Medical Disclaimer**: This system provides drug information for educational purposes only. It is not a substitute for professional medical advice. Always consult healthcare professionals for medical decisions.
