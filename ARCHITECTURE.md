# RxVerify Architecture Documentation

> **Comprehensive technical architecture and system design for RxVerify - Post-Discharge Medication Search & Feedback-Driven ML System**

## 🏗️ **System Architecture Overview**

RxVerify is built as a modern, production-ready medication search system designed specifically for post-discharge medication management. It combines real-time API integration, intelligent feedback-driven learning, and comprehensive admin analytics for continuous system optimization.

## 🔄 **High-Level System Flow**

```mermaid
graph TB
    subgraph "Client Layer"
        A[Web Client] 
        B[Mobile App]
        C[API Client]
    end
    
    subgraph "Frontend Layer"
        D[React/Vanilla JS UI]
        E[Dark/Light Mode Toggle]
        F[Admin Dashboard]
        G[Feedback System]
    end
    
    subgraph "API Gateway"
        H[FastAPI Application]
        I[CORS Middleware]
        J[Rate Limiting]
        K[Health Monitoring]
    end
    
    subgraph "Core Services"
        L[Medication Search Service]
        M[Feedback Management]
        N[Admin Analytics]
        O[Cache Management]
    end
    
    subgraph "Real-time Data Sources"
        P[RxNorm API]
        Q[DailyMed SPL]
        R[OpenFDA API]
        S[DrugBank Open Data]
    end
    
    subgraph "ML Pipeline"
        T[Feedback Collection]
        U[Result Ranking]
        V[Performance Analytics]
        W[Continuous Learning]
    end
    
    subgraph "Data Storage"
        X[Medication Cache]
        Y[Feedback Database]
        Z[RxList Database]
        AA[System Metrics]
    end
    
    A --> D
    B --> D
    C --> D
    D --> H
    D --> F
    D --> G
    
    H --> I
    I --> J
    J --> K
    H --> L
    H --> M
    H --> N
    H --> O
    
    L --> P
    L --> Q
    L --> R
    L --> S
    
    M --> T
    T --> U
    U --> V
    V --> W
    
    L --> X
    M --> Y
    O --> Z
    N --> AA
```

## 🧠 **Core Application Architecture**

```mermaid
graph TB
    subgraph "FastAPI Application Layer"
        A[main.py - App Entry Point]
        B[models.py - Data Models]
        C[config.py - Configuration]
        D[logging.py - Logging Setup]
        E[monitoring.py - Health & Metrics]
    end
    
    subgraph "Business Logic Layer"
        F[post_discharge_search.py - Search Engine]
        G[medical_apis.py - API Integration]
        H[medication_cache.py - Cache Management]
        I[rxlist_database.py - Local Database]
    end
    
    subgraph "Feedback & ML Layer"
        J[Feedback Collection]
        K[ML Pipeline Integration]
        L[Result Ranking]
        M[Performance Analytics]
    end
    
    subgraph "Data Access Layer"
        N[SQLite Databases]
        O[In-Memory Cache]
        P[File System Storage]
    end
    
    subgraph "External Services"
        Q[RxNorm API]
        R[DailyMed API]
        S[OpenFDA API]
        T[DrugBank API]
    end
    
    A --> B
    A --> C
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
    
    F --> J
    F --> K
    F --> L
    G --> Q
    G --> R
    G --> S
    G --> T
    
    H --> O
    I --> N
    J --> N
    K --> M
    M --> P
```

## 🔍 **Medication Search Flow**

```mermaid
sequenceDiagram
    participant Client
    participant Frontend
    participant FastAPI
    participant SearchService
    participant MedicalAPIs
    participant Cache
    participant FeedbackDB
    
    Client->>Frontend: Search "metformin"
    Frontend->>FastAPI: POST /search
    FastAPI->>SearchService: search_discharge_medications()
    
    SearchService->>Cache: Check cache
    alt Cache Hit
        Cache-->>SearchService: Return cached results
    else Cache Miss
        SearchService->>MedicalAPIs: Query RxNorm API
        MedicalAPIs-->>SearchService: RxNorm results
        SearchService->>MedicalAPIs: Query DailyMed API
        MedicalAPIs-->>SearchService: DailyMed results
        SearchService->>MedicalAPIs: Query OpenFDA API
        MedicalAPIs-->>SearchService: OpenFDA results
        SearchService->>MedicalAPIs: Query DrugBank API
        MedicalAPIs-->>SearchService: DrugBank results
        
        SearchService->>SearchService: Deduplicate & combine results
        SearchService->>Cache: Store results
    end
    
    SearchService->>FeedbackDB: Get feedback scores
    FeedbackDB-->>SearchService: Vote counts & scores
    SearchService->>SearchService: Apply ML ranking
    
    SearchService-->>FastAPI: Ranked results
    FastAPI-->>Frontend: JSON response
    Frontend-->>Client: Display results with feedback buttons
```

## 🤖 **Feedback System Flow**

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI
    participant FeedbackService
    participant FeedbackDB
    participant MLPipeline
    
    User->>Frontend: Click thumbs up/down
    Frontend->>Frontend: Update UI (localStorage)
    Frontend->>FastAPI: POST /feedback
    FastAPI->>FeedbackService: record_feedback()
    
    FeedbackService->>FeedbackDB: Store/update vote
    FeedbackDB-->>FeedbackService: Confirmation
    
    FeedbackService->>MLPipeline: Update ranking algorithm
    MLPipeline->>MLPipeline: Recalculate drug scores
    
    FeedbackService-->>FastAPI: Success response
    FastAPI-->>Frontend: Feedback recorded
    Frontend-->>User: Visual confirmation
    
    Note over MLPipeline: Continuous learning<br/>improves future results
```

## 📊 **Admin Dashboard & Analytics**

```mermaid
graph TB
    subgraph "Admin Interface"
        A[Admin Dropdown Menu]
        B[Feedback Analytics Tab]
        C[System Dashboard Tab]
    end
    
    subgraph "Analytics Components"
        D[Feedback Trends Chart]
        E[System Health Metrics]
        F[Cache Statistics]
        G[Search Performance]
    end
    
    subgraph "Management Actions"
        H[Clear Feedback Data]
        I[Clear Medication Cache]
        J[Clear RxList Database]
        K[System Health Check]
    end
    
    subgraph "Data Sources"
        L[Feedback Database]
        M[System Metrics]
        N[Cache Statistics]
        O[Performance Logs]
    end
    
    A --> B
    A --> C
    B --> D
    C --> E
    C --> F
    C --> G
    
    B --> H
    C --> I
    C --> J
    C --> K
    
    D --> L
    E --> M
    F --> N
    G --> O
```

## 🔍 **Query Processing Flow**

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant QueryProcessor
    participant Retriever
    participant ChromaDB
    participant CrossChecker
    participant LLM
    participant OpenAI
    
    Client->>FastAPI: POST /query
    FastAPI->>QueryProcessor: Process Query
    QueryProcessor->>Retriever: Retrieve Documents
    
    Retriever->>ChromaDB: Vector Search
    ChromaDB-->>Retriever: Top-K Results
    Retriever->>ChromaDB: Keyword Search
    ChromaDB-->>Retriever: Keyword Results
    
    Retriever-->>QueryProcessor: Combined Results
    QueryProcessor->>CrossChecker: Validate & Unify
    
    CrossChecker->>CrossChecker: Detect Disagreements
    CrossChecker->>CrossChecker: Merge Sources
    CrossChecker-->>QueryProcessor: Unified Context
    
    QueryProcessor->>LLM: Generate Response
    LLM->>OpenAI: API Call
    OpenAI-->>LLM: AI Response
    LLM-->>QueryProcessor: Formatted Answer
    
    QueryProcessor-->>FastAPI: QueryResponse
    FastAPI-->>Client: JSON Response
```

## 🗄️ **Data Architecture & Storage**

```mermaid
graph TB
    subgraph "SQLite Databases"
        A[medication_cache.db]
        B[rxlist_database.db]
        C[feedback_data.db]
    end
    
    subgraph "Database Schemas"
        D[Medication Cache Schema]
        E[RxList Schema]
        F[Feedback Schema]
    end
    
    subgraph "Cache Structure"
        G[In-Memory Cache]
        H[TTL Management]
        I[Cache Statistics]
    end
    
    subgraph "File System Storage"
        J[Log Files]
        K[Configuration Files]
        L[Static Assets]
    end
    
    subgraph "Data Operations"
        M[CRUD Operations]
        N[Query Optimization]
        O[Data Validation]
        P[Backup & Recovery]
    end
    
    A --> D
    B --> E
    C --> F
    
    D --> G
    E --> G
    F --> G
    
    G --> H
    H --> I
    
    J --> M
    K --> M
    L --> M
    
    M --> N
    N --> O
    O --> P
```

## 🔄 **Real-time API Integration Pipeline**

```mermaid
graph TB
    subgraph "API Clients"
        A[RxNorm HTTP Client]
        B[DailyMed HTTP Client]
        C[OpenFDA HTTP Client]
        D[DrugBank HTTP Client]
    end
    
    subgraph "Request Processing"
        E[Query Normalization]
        F[Partial Name Expansion]
        G[Rate Limiting]
        H[Error Handling]
    end
    
    subgraph "Data Processing"
        I[Response Parsing]
        J[Data Validation]
        K[Deduplication Logic]
        L[Result Ranking]
    end
    
    subgraph "Caching Layer"
        M[Medication Cache]
        N[TTL Management]
        O[Cache Invalidation]
        P[Performance Optimization]
    end
    
    subgraph "Output Generation"
        Q[Structured Results]
        R[Feedback Integration]
        S[ML Ranking]
        T[JSON Response]
    end
    
    A --> E
    B --> E
    C --> E
    D --> E
    
    E --> F
    F --> G
    G --> H
    
    H --> I
    I --> J
    J --> K
    K --> L
    
    L --> M
    M --> N
    N --> O
    O --> P
    
    P --> Q
    Q --> R
    R --> S
    S --> T
```

## 🚀 **Deployment Architecture**

```mermaid
graph TB
    subgraph "Development Environment"
        A[Local Development]
        B[Virtual Environment]
        C[Local Databases]
        D[Test Data]
    end
    
    subgraph "Automated Deployment"
        E[deploy.sh Script]
        F[update_version.sh]
        G[Automated Versioning]
        H[Git Integration]
    end
    
    subgraph "Heroku Production"
        I[Frontend App]
        J[Backend App]
        K[Environment Variables]
        L[Buildpacks]
    end
    
    subgraph "Version Management"
        M[Timestamp-based Versions]
        N[Cache-busting]
        O[Auto-commit/Push]
        P[Deployment Tracking]
    end
    
    subgraph "CI/CD Pipeline"
        Q[Git Repository]
        R[Automated Testing]
        S[Version Updates]
        T[Heroku Deployment]
    end
    
    A --> B
    B --> C
    C --> D
    
    E --> F
    F --> G
    G --> H
    
    H --> I
    H --> J
    I --> K
    J --> K
    K --> L
    
    G --> M
    M --> N
    N --> O
    O --> P
    
    Q --> R
    R --> S
    S --> T
    T --> I
    T --> J
```

## 🔐 **Security & Access Control**

```mermaid
graph TB
    subgraph "External Access"
        A[Internet]
        B[VPN/Private Network]
        C[Internal Services]
    end
    
    subgraph "API Security"
        D[Rate Limiting]
        E[CORS Configuration]
        F[Request Validation]
        G[Error Handling]
    end
    
    subgraph "Data Security"
        H[Environment Variables]
        I[API Key Management]
        J[Secure Logging]
        K[Data Encryption]
    end
    
    subgraph "Infrastructure Security"
        L[Docker Security]
        M[Network Isolation]
        N[Resource Limits]
        O[Health Monitoring]
    end
    
    A --> D
    B --> D
    C --> D
    
    D --> E
    E --> F
    F --> G
    
    G --> H
    H --> I
    I --> J
    J --> K
    
    K --> L
    L --> M
    M --> N
    N --> O
```

## 📊 **Monitoring & Observability**

```mermaid
graph TB
    subgraph "Application Metrics"
        A[Request Count]
        B[Response Time]
        C[Error Rate]
        D[Success Rate]
    end
    
    subgraph "System Health"
        E[ChromaDB Status]
        F[OpenAI API Status]
        G[Memory Usage]
        H[Disk Usage]
    end
    
    subgraph "Business Metrics"
        I[Queries per Hour]
        J[Data Source Usage]
        K[Cross-Validation Results]
        L[LLM Response Quality]
    end
    
    subgraph "Logging & Alerts"
        M[Structured Logs]
        N[Error Tracking]
        O[Performance Alerts]
        P[Health Checks]
    end
    
    A --> M
    B --> M
    C --> N
    D --> M
    
    E --> P
    F --> P
    G --> P
    H --> P
    
    I --> M
    J --> M
    K --> M
    L --> M
    
    M --> O
    N --> O
    P --> O
```

## 🚀 **Deployment Architecture**

```mermaid
graph TB
    subgraph "Development Environment"
        A[Local Development]
        B[Virtual Environment]
        C[Local ChromaDB]
        D[Test Data]
    end
    
    subgraph "Production Environment"
        E[Docker Container]
        F[Production ChromaDB]
        G[Environment Variables]
        H[Log Aggregation]
    end
    
    subgraph "Scaling Options"
        I[Load Balancer]
        J[Multiple Instances]
        K[Distributed ChromaDB]
        L[CDN for Static Assets]
    end
    
    subgraph "CI/CD Pipeline"
        M[Git Repository]
        N[Automated Testing]
        O[Docker Build]
        P[Deployment]
    end
    
    A --> B
    B --> C
    C --> D
    
    E --> F
    F --> G
    G --> H
    
    I --> J
    J --> K
    K --> L
    
    M --> N
    N --> O
    O --> P
    P --> E
```

## 🔧 **Component Dependencies**

```mermaid
graph LR
    subgraph "Core Dependencies"
        A[FastAPI]
        B[Pydantic]
        C[Uvicorn]
        D[ChromaDB]
    end
    
    subgraph "AI & ML"
        E[OpenAI]
        F[NumPy]
        G[Pandas]
    end
    
    subgraph "Data Processing"
        H[Requests]
        I[BeautifulSoup]
        J[XML Parsers]
        K[CSV Readers]
    end
    
    subgraph "Utilities"
        L[Python-dotenv]
        M[Logging]
        N[AsyncIO]
        O[Pathlib]
    end
    
    A --> B
    A --> C
    A --> D
    A --> E
    
    E --> F
    E --> G
    
    H --> I
    H --> J
    H --> K
    
    L --> M
    M --> N
    N --> O
```

## 📈 **Performance Characteristics**

```mermaid
graph TB
    subgraph "Response Time Breakdown"
        A[Query Processing: 10-50ms]
        B[API Calls: 200-800ms]
        C[Cache Lookup: 1-5ms]
        D[Deduplication: 5-20ms]
        E[ML Ranking: 10-30ms]
        F[Total: 250-900ms]
    end
    
    subgraph "Throughput Metrics"
        G[Concurrent Requests: 20-100]
        H[Searches per Second: 10-50]
        I[Peak Load: 200 QPS]
    end
    
    subgraph "Resource Usage"
        J[Memory: 200MB-1GB]
        K[CPU: 1-2 cores]
        L[Disk: 100MB-1GB]
        M[Network: 1-5 Mbps]
    end
    
    subgraph "Scalability Factors"
        N[API Rate Limits]
        O[Cache Hit Ratio]
        P[Database Performance]
        Q[Network Latency]
    end
    
    A --> F
    B --> F
    C --> F
    D --> F
    E --> F
    
    G --> H
    H --> I
    
    J --> K
    K --> L
    L --> M
    
    N --> O
    O --> P
    P --> Q
```

## 🔄 **Data Flow Patterns**

```mermaid
graph TB
    subgraph "Read Pattern"
        A[Query Request]
        B[Vector Search]
        C[Result Ranking]
        D[Context Assembly]
        E[Response Generation]
    end
    
    subgraph "Write Pattern"
        F[Data Ingestion]
        G[Text Processing]
        H[Embedding Generation]
        I[Vector Storage]
        J[Metadata Indexing]
    end
    
    subgraph "Update Pattern"
        K[Data Refresh]
        L[Incremental Updates]
        M[Version Management]
        N[Rollback Capability]
    end
    
    subgraph "Delete Pattern"
        O[Data Archival]
        P[Soft Deletes]
        Q[Cleanup Jobs]
        R[Storage Optimization]
    end
    
    A --> B
    B --> C
    C --> D
    D --> E
    
    F --> G
    G --> H
    H --> I
    I --> J
    
    K --> L
    L --> M
    M --> N
    
    O --> P
    P --> Q
    Q --> R
```

## 🎯 **Key Design Principles**

### **1. Real-time Data Integration**
- **Live API Queries**: Direct integration with medical databases for current information
- **Intelligent Caching**: Smart caching strategies to balance freshness and performance
- **Partial Name Support**: Automatic expansion of common drug prefixes for better UX
- **Deduplication Logic**: Combines duplicate results with different dosages

### **2. Feedback-Driven Learning**
- **User Feedback Collection**: Thumbs up/down voting system for continuous improvement
- **ML Pipeline Integration**: Feedback feeds into result ranking and optimization
- **Real-time Analytics**: Admin dashboard with feedback trends and system metrics
- **Performance Tracking**: Comprehensive monitoring of search quality and user satisfaction

### **3. Post-Discharge Focus**
- **Curated Results**: Prioritizes oral medications typically prescribed after hospital stays
- **Clinical Relevance**: Filters out IV medications, formulas, and non-discharge medications
- **RxCUI Integration**: Direct links to authoritative drug information sources
- **Comprehensive Information**: Drug class, common uses, and dosage information

### **4. Modern User Experience**
- **Responsive Design**: Optimized for desktop, tablet, and mobile devices
- **Dark/Light Mode**: System preference detection with manual override
- **Progressive Web App**: PWA capabilities with offline support
- **Real-time Feedback**: Live vote counts and visual feedback on interactions

### **5. Production-Ready Architecture**
- **Automated Deployment**: Scripted deployment with version management
- **Health Monitoring**: Comprehensive system status and performance metrics
- **Error Handling**: Graceful degradation and comprehensive error reporting
- **Scalable Design**: Architecture supports horizontal scaling and load balancing

## 🔮 **Future Architecture Considerations**

### **Scalability Enhancements**
- **Load Balancing**: Multiple API instances behind a load balancer
- **Database Clustering**: Distributed SQLite or PostgreSQL clusters
- **Caching Layer**: Redis for frequently accessed data and session management
- **CDN Integration**: Static asset delivery optimization

### **Advanced Features**
- **Real-time Updates**: WebSocket support for live data updates and notifications
- **Advanced Analytics**: Machine learning for search result optimization
- **Multi-tenant Support**: Isolated data spaces for different organizations
- **API Versioning**: Backward-compatible API evolution

### **Integration Capabilities**
- **EHR Integration**: Direct integration with Electronic Health Records
- **Pharmacy Software**: Integration with pharmacy management systems
- **Mobile SDKs**: Native mobile application support
- **Third-party APIs**: Integration with additional medical data sources

### **AI/ML Enhancements**
- **Natural Language Processing**: Advanced query understanding and intent recognition
- **Predictive Analytics**: Anticipate user needs and suggest relevant medications
- **Personalization**: User-specific result ranking based on history and preferences
- **Automated Quality Assurance**: AI-powered result validation and quality scoring

---

*This architecture document provides a comprehensive view of the RxVerify system design. For implementation details, refer to the individual component documentation and source code.*
