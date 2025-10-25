# RxVerify Drug Voting System Flow

## 🎯 How Drug Voting & Ranking Works

### 📊 Search Results Before Voting

```
Search Query: "Metformin"

Ranking Score = Base Score + Prefix Match + Drug Type + Vote Boost + Social Proof

1. Metformin                    Score: 100.0  Rating: 0.00  Votes: 0
   ┌─────────────────────────────────────────────────────────────┐
   │ Generic Drug (Single word)                                  │
   │ ✅ Prefix Match: +50 points                                │
   │ ✅ Generic Type: +30 points                                │
   │ ❌ No votes: +0 points                                      │
   │ Total: 50 + 50 + 30 + 0 = 130 points                      │
   └─────────────────────────────────────────────────────────────┘

2. Metformin ER                 Score: 80.0   Rating: 0.00  Votes: 0
   ┌─────────────────────────────────────────────────────────────┐
   │ Combination Drug (Extended Release)                        │
   │ ✅ Prefix Match: +50 points                                │
   │ ❌ Combination Type: +10 points                            │
   │ ❌ No votes: +0 points                                      │
   │ Total: 50 + 50 + 10 + 0 = 110 points                      │
   └─────────────────────────────────────────────────────────────┘

3. Metformin + Glipizide        Score: 80.0   Rating: 0.00  Votes: 0
   ┌─────────────────────────────────────────────────────────────┐
   │ Combination Drug (Multiple drugs)                          │
   │ ✅ Prefix Match: +50 points                                │
   │ ❌ Combination Type: +10 points                            │
   │ ❌ No votes: +0 points                                      │
   │ Total: 50 + 50 + 10 + 0 = 110 points                      │
   └─────────────────────────────────────────────────────────────┘
```

### 🗳️ User Votes "Helpful" on Metformin

```
User Action: Click "Helpful" on Metformin

Frontend Process:
┌─────────────────────────────────────────────────────────────┐
│ 1. Check localStorage cache                                  │
│ 2. Verify with backend (/drugs/vote-status)                │
│ 3. Backend checks: IP + User Agent → Anonymous User ID    │
│ 4. Database lookup: No existing vote found                  │
│ 5. Allow voting (when in doubt, allow voting policy)       │
└─────────────────────────────────────────────────────────────┘

Backend Process:
┌─────────────────────────────────────────────────────────────┐
│ 1. Generate Anonymous User ID:                              │
│    MD5("127.0.0.1:Mozilla/5.0...") = "a1b2c3d4e5f6..."    │
│ 2. Create vote record in MongoDB:                           │
│    {                                                         │
│      "drug_id": "metformin_DrugType.GENERIC_12345",         │
│      "user_id": "a1b2c3d4e5f6...",                          │
│      "vote_type": "upvote",                                 │
│      "ip_address": "127.0.0.1",                             │
│      "user_agent": "Mozilla/5.0...",                         │
│      "created_at": "2025-10-25T09:05:00Z"                   │
│    }                                                         │
│ 3. Update drug rating:                                      │
│    upvotes: 0 → 1                                           │
│    downvotes: 0 → 0                                          │
│    total_votes: 0 → 1                                        │
│    rating_score: 0.0 → 1.0                                  │
└─────────────────────────────────────────────────────────────┘
```

### 📈 Search Results After Voting

```
Search Query: "Metformin" (After 1 Upvote)

Ranking Score = Base Score + Prefix Match + Drug Type + Vote Boost + Social Proof

1. Metformin                    Score: 155.0  Rating: 1.00  Votes: 1  ⬆️ MOVED UP!
   ┌─────────────────────────────────────────────────────────────┐
   │ Generic Drug (Single word)                                  │
   │ ✅ Prefix Match: +50 points                                │
   │ ✅ Generic Type: +30 points                                │
   │ ✅ Vote Boost: 1.0 × 25 = +25 points                      │
   │ ❌ Social Proof: <5 votes = +0 points                      │
   │ Total: 50 + 50 + 30 + 25 + 0 = 155 points                 │
   └─────────────────────────────────────────────────────────────┘

2. Metformin ER                 Score: 110.0  Rating: 0.00  Votes: 0  ⬇️ MOVED DOWN!
   ┌─────────────────────────────────────────────────────────────┐
   │ Combination Drug (Extended Release)                        │
   │ ✅ Prefix Match: +50 points                                │
   │ ❌ Combination Type: +10 points                            │
   │ ❌ No votes: +0 points                                      │
   │ Total: 50 + 50 + 10 + 0 = 110 points                      │
   └─────────────────────────────────────────────────────────────┘

3. Metformin + Glipizide        Score: 110.0  Rating: 0.00  Votes: 0  ⬇️ MOVED DOWN!
   ┌─────────────────────────────────────────────────────────────┐
   │ Combination Drug (Multiple drugs)                          │
   │ ✅ Prefix Match: +50 points                                │
   │ ❌ Combination Type: +10 points                            │
   │ ❌ No votes: +0 points                                      │
   │ Total: 50 + 50 + 10 + 0 = 110 points                      │
   └─────────────────────────────────────────────────────────────┘
```

### 🗳️ User Votes "Not Helpful" on Metformin ER

```
User Action: Click "Not Helpful" on Metformin ER

Backend Process:
┌─────────────────────────────────────────────────────────────┐
│ 1. Generate Anonymous User ID:                              │
│    MD5("127.0.0.1:Mozilla/5.0...") = "a1b2c3d4e5f6..."    │
│ 2. Create vote record in MongoDB:                           │
│    {                                                         │
│      "drug_id": "metformin_er_DrugType.COMBINATION_67890",   │
│      "user_id": "a1b2c3d4e5f6...",                          │
│      "vote_type": "downvote",                               │
│      "ip_address": "127.0.0.1",                             │
│      "user_agent": "Mozilla/5.0...",                         │
│      "created_at": "2025-10-25T09:05:30Z"                   │
│    }                                                         │
│ 3. Update drug rating:                                      │
│    upvotes: 0 → 0                                           │
│    downvotes: 0 → 1                                          │
│    total_votes: 0 → 1                                        │
│    rating_score: 0.0 → -1.0                                 │
└─────────────────────────────────────────────────────────────┘
```

### 📉 Search Results After Downvote

```
Search Query: "Metformin" (After 1 Upvote + 1 Downvote)

Ranking Score = Base Score + Prefix Match + Drug Type + Vote Boost + Social Proof

1. Metformin                    Score: 155.0  Rating: 1.00  Votes: 1  🥇 STAYS #1
   ┌─────────────────────────────────────────────────────────────┐
   │ Generic Drug (Single word)                                  │
   │ ✅ Prefix Match: +50 points                                │
   │ ✅ Generic Type: +30 points                                │
   │ ✅ Vote Boost: 1.0 × 25 = +25 points                      │
   │ Total: 50 + 50 + 30 + 25 = 155 points                     │
   └─────────────────────────────────────────────────────────────┘

2. Metformin + Glipizide        Score: 110.0  Rating: 0.00  Votes: 0  ⬆️ MOVED UP!
   ┌─────────────────────────────────────────────────────────────┐
   │ Combination Drug (Multiple drugs)                          │
   │ ✅ Prefix Match: +50 points                                │
   │ ❌ Combination Type: +10 points                            │
   │ ❌ No votes: +0 points                                      │
   │ Total: 50 + 50 + 10 + 0 = 110 points                      │
   └─────────────────────────────────────────────────────────────┘

3. Metformin ER                 Score: 85.0   Rating: -1.00  Votes: 1  ⬇️ MOVED DOWN!
   ┌─────────────────────────────────────────────────────────────┐
   │ Combination Drug (Extended Release)                        │
   │ ✅ Prefix Match: +50 points                                │
   │ ❌ Combination Type: +10 points                            │
   │ ❌ Vote Penalty: -1.0 × 25 = -25 points                   │
   │ Total: 50 + 50 + 10 - 25 = 85 points                      │
   └─────────────────────────────────────────────────────────────┘
```

### 🔄 Vote Switching Example

```
User Action: Click "Helpful" on Metformin ER (switching from "Not Helpful")

Backend Process:
┌─────────────────────────────────────────────────────────────┐
│ 1. Detect existing downvote for same user                    │
│ 2. Remove old vote: DELETE from votes_collection            │
│ 3. Update drug: downvotes: 1 → 0, rating_score: -1.0 → 0.0 │
│ 4. Create new vote: INSERT upvote record                    │
│ 5. Update drug: upvotes: 0 → 1, rating_score: 0.0 → 1.0   │
└─────────────────────────────────────────────────────────────┘

Result: Metformin ER moves from position #3 to position #2
```

### 🚫 Hiding Poorly Rated Drugs

```
After Multiple Downvotes:

Metformin ER                 Score: 25.0   Rating: -1.00  Votes: 5
┌─────────────────────────────────────────────────────────────┐
│ ❌ Vote Penalty: -1.0 × 25 = -25 points                    │
│ ❌ Low total score: 50 + 50 + 10 - 25 = 85 points           │
│ ❌ Rating below threshold: -1.0 < -0.5                      │
│ ❌ Enough votes: 5 ≥ 3 (minimum for hiding)                 │
│ 🚫 RESULT: Drug is HIDDEN from search results               │
└─────────────────────────────────────────────────────────────┘
```

### 🎯 Key Features

1. **Anonymous User Tracking**: IP + User Agent hash for consistent identification
2. **Backend Verification**: Frontend checks with backend before voting
3. **"When in Doubt, Allow Voting"**: If verification fails, allow the vote
4. **Vote Switching**: Users can change their vote (unvote old, vote new)
5. **Dynamic Ranking**: Vote scores significantly impact search ranking
6. **Social Proof**: Drugs with 5+ votes get bonus points
7. **Auto-Hiding**: Poorly rated drugs disappear from results
8. **Real-time Updates**: UI updates immediately with optimistic updates

### 📊 Scoring Formula

```
Total Score = Base Score + Prefix Match + Drug Type + Vote Boost + Social Proof

Where:
- Base Score: 50 points (for any match)
- Prefix Match: +50 points (drug starts with query)
- Drug Type: +30 (generic), +20 (brand), +10 (combination)
- Vote Boost: rating_score × 25 points
- Social Proof: +10 points (if total_votes ≥ 5)
```

This system ensures that helpful drugs rise to the top while unhelpful drugs sink to the bottom, creating a self-improving search experience! 🎯
