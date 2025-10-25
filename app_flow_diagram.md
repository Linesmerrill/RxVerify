# RxVerify Application Flow Diagram

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    RxVerify                                     │
│                         Modern Drug Search & Analytics Platform                │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   Database      │
│   (Port 8080)   │◄──►│   (Port 8000)   │◄──►│   MongoDB       │
│                 │    │                 │    │   Atlas         │
│ • React-like JS │    │ • FastAPI       │    │ • 100k+ drugs   │
│ • Dark/Light UI │    │ • WebSockets    │    │ • Vote records  │
│ • Real-time UI  │    │ • Analytics     │    │ • Analytics     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🔍 Drug Search Flow

### 1. User Search Input
```
User types "metformin" in search box
    ↓
Frontend debounces input (300ms delay)
    ↓
Frontend shows skeleton loading
    ↓
GET /drugs/search?query=metformin&limit=10
```

### 2. Backend Search Processing
```
FastAPI receives search request
    ↓
LocalDrugSearchService.search_drugs()
    ↓
DrugDatabaseManager.search_drugs()
    ↓
MongoDB Aggregation Pipeline:
    ├── Match: drugs containing "metformin"
    ├── AddFields: Calculate relevance_score
    │   ├── Base Score: +50 points
    │   ├── Prefix Match: +50 points (if starts with query)
    │   ├── Drug Type: +30 (generic), +20 (brand), +10 (combination)
    │   ├── Vote Boost: rating_score × 25 points
    │   └── Social Proof: +10 points (if 5+ votes)
    ├── Sort: By relevance_score DESC, search_count DESC
    └── Limit: 10 results
    ↓
Return ranked drug results
```

### 3. Frontend Results Display
```
Frontend receives search results
    ↓
createSearchResultElement() for each drug
    ├── Drug name and type
    ├── Vote buttons (Helpful/Not Helpful)
    ├── Vote counts from backend
    └── Apply cached vote states from localStorage
    ↓
Display results with optimistic UI updates
```

## 🗳️ Voting System Flow

### 1. User Clicks Vote Button
```
User clicks "Helpful" on Metformin
    ↓
Frontend: voteOnDrug(drugId, 'upvote')
    ↓
Frontend: verifyVoteStatus(drugId)
    ↓
GET /drugs/vote-status?drug_id=metformin_12345
```

### 2. Backend Vote Verification
```
FastAPI receives vote status check
    ↓
DrugRatingService.check_user_vote_status()
    ↓
Generate anonymous user ID:
    MD5(IP + User Agent) = "a1b2c3d4e5f6..."
    ↓
MongoDB query: Find existing vote
    ↓
Return: {has_voted: false, vote_type: null}
```

### 3. Vote Processing
```
Frontend: Allow voting (when in doubt, allow voting policy)
    ↓
Frontend: Optimistic UI update (immediate button highlight)
    ↓
POST /drugs/vote?drug_id=metformin_12345&vote_type=upvote
    ↓
Backend: DrugRatingService.vote_on_drug()
    ↓
MongoDB Operations:
    ├── Insert vote record:
    │   {drug_id, user_id, vote_type, ip_address, user_agent, created_at}
    └── Update drug document:
        ├── upvotes: 0 → 1
        ├── downvotes: 0 → 0
        ├── total_votes: 0 → 1
        └── rating_score: 0.0 → 1.0
    ↓
Return success response
```

### 4. UI Update & Cache Sync
```
Frontend: Update localStorage vote state
    ↓
Frontend: Refresh search results to show new ranking
    ↓
Drug ranking updated:
    Metformin: Score 100.0 → 125.0 (+25 vote boost)
    ↓
User sees immediate feedback and updated ranking
```

## 📊 Admin Dashboard Flow

### 1. Admin Dashboard Access
```
User clicks "Admin" dropdown
    ↓
Frontend: Load admin dashboard
    ↓
Multiple API calls in parallel:
    ├── GET /admin/stats
    ├── GET /metrics/summary
    ├── GET /metrics/time-series
    ├── GET /feedback/stats
    └── GET /admin/recent-activity
```

### 2. Real-time Updates
```
WebSocket connection: /ws/admin
    ↓
Backend: ConnectionManager manages active connections
    ↓
On new search/vote activity:
    ├── Monitor.record_request() called
    ├── Analytics database updated
    └── WebSocket broadcast to all connected clients
    ↓
Frontend: Receive real-time updates
    ↓
Frontend: Animate number transitions and update charts
```

### 3. Analytics Data Flow
```
AnalyticsDatabaseManager:
    ├── Log all requests to request_logs collection
    ├── Aggregate hourly/daily metrics
    ├── Store system stats and performance data
    └── Provide time-series data for charts
    ↓
Admin dashboard displays:
    ├── Total requests, success rate, avg response time
    ├── Search trends chart with real-time updates
    ├── Feedback analytics with vote ratios
    └── Recent activity with pagination
```

## 🔄 Vote Switching Flow

### 1. User Changes Vote
```
User clicks "Not Helpful" on previously upvoted drug
    ↓
Frontend: Detect vote switching (upvote → downvote)
    ↓
Frontend: Two-step process:
    ├── POST /drugs/vote?is_unvote=true (remove old vote)
    └── POST /drugs/vote?is_unvote=false (add new vote)
```

### 2. Backend Vote Switching
```
Backend: DrugRatingService.vote_on_drug()
    ↓
Detect existing vote of different type
    ↓
Remove old vote:
    ├── DELETE from votes_collection
    └── Update drug: upvotes: 1 → 0, rating_score: 1.0 → 0.0
    ↓
Add new vote:
    ├── INSERT new vote record
    └── Update drug: downvotes: 0 → 1, rating_score: 0.0 → -1.0
    ↓
Return success response
```

## 🚫 Auto-Hiding Flow

### 1. Poor Rating Detection
```
Drug with multiple downvotes:
    ├── rating_score: -1.0 (below -0.5 threshold)
    ├── total_votes: 5 (above 3 minimum)
    └── Status: HIDDEN
    ↓
Search results exclude hidden drugs
    ↓
Drug disappears from search results
```

## 🎯 Key System Features

### **Anonymous User Tracking**
- **Method**: IP + User Agent hash (MD5)
- **Consistency**: Same user gets same ID across sessions
- **Privacy**: No personal data stored, only anonymous hash

### **Vote-Based Ranking**
- **Formula**: Base + Prefix + Type + Vote Boost + Social Proof
- **Impact**: Each vote adds/subtracts 25 points
- **Threshold**: -0.5 rating with 3+ votes triggers hiding

### **Real-time Updates**
- **WebSockets**: Live admin dashboard updates
- **Optimistic UI**: Immediate frontend feedback
- **Error Handling**: Revert UI changes on failure

### **Self-Improving System**
- **User Feedback**: Drives search ranking improvements
- **Social Proof**: Popular drugs get ranking boosts
- **Auto-Hiding**: Poor drugs disappear automatically
- **Dynamic Ranking**: Search results improve over time

## 🔧 Technical Stack

### **Frontend**
- **Vanilla JavaScript**: Modern ES6+ with classes
- **Tailwind CSS**: Utility-first styling
- **WebSocket**: Real-time communication
- **localStorage**: Client-side vote caching

### **Backend**
- **FastAPI**: Modern Python web framework
- **Motor**: Async MongoDB driver
- **WebSockets**: Real-time admin updates
- **Pydantic**: Data validation and serialization

### **Database**
- **MongoDB Atlas**: Cloud-hosted NoSQL database
- **Collections**: drugs, votes, analytics, request_logs
- **Indexes**: Text search, compound indexes for performance
- **Aggregation**: Complex ranking and analytics pipelines

This architecture creates a self-improving drug search system that learns from user feedback and provides real-time analytics for administrators! 🎯
