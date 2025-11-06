# RxVerify Architecture

> **Technical architecture and system design for RxVerify - Modern Drug Search & Self-Improving Analytics Platform**

## 🏗️ System Architecture Overview

RxVerify is a modern, production-ready drug search system featuring intelligent ranking, user-driven feedback, and real-time analytics. It combines a curated MongoDB database of 100,000+ drugs with sophisticated search algorithms and a self-improving voting system that learns from user preferences.

## 🔄 High-Level System Flow

```mermaid
graph TB
    subgraph "Client Layer"
        A[Web Browser]
        B[Mobile App]
    end
    
    subgraph "Frontend Layer"
        C[Vanilla JS UI]
        D[Admin Dashboard]
        E[Voting System]
    end
    
    subgraph "API Gateway"
        F[FastAPI Application]
        G[CORS Middleware]
        H[WebSocket Server]
    end
    
    subgraph "Core Services"
        I[Drug Search Service]
        J[Vote Management]
        K[Analytics Engine]
        L[Cache Management]
    end
    
    subgraph "Data Storage"
        M[MongoDB Atlas]
        N[SQLite Fallback]
        O[Analytics Database]
    end
    
    A --> C
    B --> C
    C --> F
    D --> F
    E --> F
    
    F --> G
    F --> H
    F --> I
    F --> J
    F --> K
    
    I --> L
    J --> M
    K --> O
    I --> M
    I --> N
```

## 🧠 Core Application Architecture

```mermaid
graph TB
    subgraph "FastAPI Application Layer"
        A[main.py - App Entry Point]
        B[models.py - Data Models]
        C[config.py - Configuration]
        D[app_logging.py - Logging]
        E[monitoring.py - Health & Metrics]
    end
    
    subgraph "Business Logic Layer"
        F[local_drug_search_service.py - Search Engine]
        G[medical_apis.py - API Integration]
        H[drug_database_manager.py - Database Manager]
        I[drug_rating_service.py - Rating System]
    end
    
    subgraph "Data Access Layer"
        J[mongodb_config.py - MongoDB Config]
        K[analytics_database.py - Analytics DB]
        L[SQLite Databases]
    end
    
    subgraph "External Services"
        M[RxNorm API]
        N[DailyMed API]
        O[OpenFDA API]
        P[DrugBank API]
    end
    
    A --> B
    A --> C
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
    
    F --> H
    G --> M
    G --> N
    G --> O
    G --> P
    
    H --> J
    H --> L
    I --> J
    E --> K
```

## 🔍 Drug Search Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI
    participant SearchService
    participant Database
    participant RatingService
    
    User->>Frontend: Search "metformin"
    Frontend->>FastAPI: GET /drugs/search?q=metformin
    FastAPI->>SearchService: search_drugs()
    
    SearchService->>Database: Query drug database
    Database-->>SearchService: Drug candidates
    
    SearchService->>RatingService: Get vote scores
    RatingService-->>SearchService: Vote counts & ratings
    
    SearchService->>SearchService: Apply ranking algorithm
    Note over SearchService: Multi-tier scoring:<br/>Prefix matches > Single drugs > Combinations<br/>Vote scores affect ranking
    
    SearchService-->>FastAPI: Ranked results
    FastAPI-->>Frontend: JSON response
    Frontend-->>User: Display results with vote buttons
```

## 🗳️ Voting System Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI
    participant VoteService
    participant Database
    
    User->>Frontend: Click thumbs up/down
    Frontend->>Frontend: Check vote status
    Frontend->>FastAPI: GET /drugs/vote-status
    FastAPI->>VoteService: check_vote_status()
    VoteService->>Database: Query vote records
    Database-->>VoteService: Existing vote (if any)
    VoteService-->>FastAPI: Vote status
    FastAPI-->>Frontend: Current vote state
    
    Frontend->>FastAPI: POST /drugs/vote
    FastAPI->>VoteService: record_vote()
    
    VoteService->>Database: Store/update vote
    Database-->>VoteService: Confirmation
    
    VoteService->>VoteService: Recalculate drug rating
    Note over VoteService: Rating affects future<br/>search rankings
    
    VoteService-->>FastAPI: Success response
    FastAPI-->>Frontend: Vote recorded
    Frontend-->>User: Update UI with new vote
```

## 📊 Database Architecture

```mermaid
erDiagram
    DRUGS ||--o{ VOTES : has
    DRUGS {
        string drug_id PK
        string name
        string type
        string status
        datetime created_at
        datetime updated_at
    }
    
    VOTES {
        string vote_id PK
        string drug_id FK
        string user_hash
        int vote_value
        datetime created_at
        datetime updated_at
    }
    
    ANALYTICS {
        string id PK
        string endpoint
        int request_count
        float avg_response_time
        datetime timestamp
    }
    
    SEARCH_LOGS {
        string id PK
        string query
        int result_count
        float response_time
        datetime timestamp
    }
```

## 🎯 Key Components

### Frontend (Vanilla JavaScript)
- **Drug Search Interface**: Debounced search input with real-time results
- **Voting System**: Thumbs up/down buttons with optimistic updates
- **Admin Dashboard**: Real-time metrics and analytics
- **WebSocket Integration**: Live updates for admin dashboard

### Backend (FastAPI)
- **Drug Search API**: Intelligent ranking with multi-tier scoring
- **Vote Management**: Anonymous tracking with IP + User Agent hash
- **Analytics Engine**: Performance metrics and search analytics
- **WebSocket Server**: Real-time updates for connected clients

### Database Layer
- **MongoDB Atlas** (Primary): 100,000+ drugs, vote records, analytics
- **SQLite** (Fallback): Local development and testing
- **Analytics Database**: Search logs, performance metrics

### Search Algorithm
1. **Prefix Matching**: Drugs starting with query get highest priority
2. **Single Drug Priority**: Single drugs ranked above combinations
3. **Vote Integration**: Vote scores add/subtract ranking points
4. **Auto-Hiding**: Poorly rated drugs (rating ≤ -0.5, 3+ votes) filtered out

## 🔐 Security & Privacy

- **Anonymous Tracking**: IP + User Agent hash (no personal data)
- **CORS Protection**: Configurable allowed origins
- **Rate Limiting**: Built-in FastAPI rate limiting
- **Input Validation**: Pydantic models for all requests

## 📈 Performance Optimizations

- **Database Indexing**: Optimized indexes on drug names and IDs
- **Caching**: In-memory caching for frequently accessed data
- **Debounced Search**: 300ms debounce on frontend search input
- **Lazy Loading**: Results loaded incrementally
- **Connection Pooling**: Efficient database connection management

