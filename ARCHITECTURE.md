# Rare Pepe Auction Machine - Architecture Documentation

## System Overview

The Rare Pepe Auction Machine is a Python Flask application that implements a Dutch auction system for Rare Pepe assets on Bitcoin using Counterparty. The system uses pre-signed PSBTs (Partially Signed Bitcoin Transactions) with SIGHASH_SINGLE|ANYONECANPAY, which are progressively revealed one per block to implement a descending price auction.

## Key Concepts

### Dutch Auction
A Dutch auction is a descending price auction where:
1. Seller sets a starting high price
2. Price decreases over time (per block)
3. First buyer to accept the current price wins
4. Unsold items may reach a minimum price

### SIGHASH_SINGLE|ANYONECANPAY PSBTs
- **SIGHASH_SINGLE**: Signs only the corresponding output
- **ANYONECANPAY**: Allows others to add inputs
- This combination lets buyers add their own inputs to pay the seller's specified price
- Seller pre-signs multiple PSBTs at different price points

### Progressive Revelation
- PSBTs are revealed one per block based on current block height
- Prevents buyers from seeing the lowest price ahead of time
- Maintains auction integrity and prevents front-running

## Architecture Components

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Auction Machine                               │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                   Flask API (routes.py)                         │  │
│  │  - POST /api/auctions (create auction)                         │  │
│  │  - GET  /api/auctions (list auctions)                          │  │
│  │  - GET  /api/auctions/{id} (get details)                       │  │
│  │  - GET  /api/auctions/{id}/current-psbt (get PSBT)             │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                │                                      │
│  ┌─────────────────────────────┼─────────────────────────────────┐   │
│  │                             │                                  │   │
│  │  ┌──────────────┐  ┌───────┴───────┐  ┌────────────────────┐ │   │
│  │  │  Validators  │  │    Models     │  │  Background Monitors│ │   │
│  │  │  - PSBT fmt  │  │  - Auction    │  │  - Block (5m poll) │ │   │
│  │  │  - UTXO      │  │  - PSBT       │  │  - UTXO (5m poll)  │ │   │
│  │  │  - Asset     │  │               │  │                    │ │   │
│  │  └──────────────┘  └───────────────┘  └─────────┬──────────┘ │   │
│  │                                                  │            │   │
│  │  ┌───────────────────────────────────────────────┴──────────┐│   │
│  │  │              ZMQ Listener (zmq_listener.py)              ││   │
│  │  │  - rawblock subscription → instant block detection       ││   │
│  │  │  - rawtx subscription → instant UTXO spend detection     ││   │
│  │  │  - Triggers monitors immediately on events               ││   │
│  │  └──────────────────────────────────────────────────────────┘│   │
│  └───────────────────────────────────────────────────────────────┘   │
│                    │                              │                   │
│  ┌─────────────────┴──────────┐     ┌────────────┴────────────┐     │
│  │       Bitcoin RPC          │     │    Counterparty API     │     │
│  │  - Block height            │     │    - Asset validation   │     │
│  │  - UTXO lookup             │     │    - Balance check      │     │
│  │  - TX monitoring           │     │                         │     │
│  └─────────────────┬──────────┘     └────────────┬────────────┘     │
└────────────────────┼─────────────────────────────┼──────────────────┘
                     │                             │
       ┌─────────────┴─────────────┐     ┌────────┴────────┐
       │       Bitcoin Core        │     │   Counterparty  │
       │  - RPC (port 8332)        │     │   Core (API)    │
       │  - ZMQ (ports 9332/9333)  │     │                 │
       └───────────────────────────┘     └─────────────────┘
```

## Component Details

### 1. Flask API (`routes.py`)

**Endpoints:**
- `POST /api/auctions`: Create new auction (authenticated)
- `GET /api/auctions`: List all auctions with optional status filter
- `GET /api/auctions/{id}`: Get auction metadata (no PSBTs)
- `GET /api/auctions/{id}/current-psbt`: Get current PSBT only
- `GET /api/health`: Health check

**Security:**
- API key authentication for auction creation
- Never exposes all PSBTs (only current one)
- Validates all inputs before processing

### 2. Database Models (`models.py`)

**Auction Model:**
```python
{
    id: integer (primary key)
    asset_name: string
    asset_qty: float  # Supports divisible assets (up to 8 decimals)
    utxo_txid: string
    utxo_vout: integer
    start_block: integer
    end_block: integer
    blocks_after_end: integer
    status: enum (upcoming/active/sold/closed/finished/expired)
    spent_txid: string (nullable)  # Transaction that spent the UTXO
    spent_block: integer (nullable)  # Block height when spent
    spent_at: timestamp (nullable)  # Timestamp when spent
    recipient: string (nullable)  # Recipient address
    seller: string (nullable)  # Seller address
    created_at: timestamp
}
```

**PSBT Model:**
```python
{
    id: integer (primary key)
    auction_id: foreign key
    block_number: integer
    price_sats: integer
    psbt_data: text (base64)
}
```

### 3. Validators (`validators.py`)

**Validation Chain:**
1. Format validation (JSON structure, data types)
2. PSBT format validation (magic bytes, base64 encoding)
3. UTXO existence check (via Bitcoin RPC)
4. Asset validation (via Counterparty API)
   - Single asset only
   - Correct asset name
   - Correct quantity
5. Price progression validation (descending order)
6. Block range validation (start to end, no gaps)

### 4. Bitcoin RPC Client (`bitcoin_rpc.py`)

**Methods:**
- `get_current_block_height()`: Get current blockchain height
- `get_utxo(txid, vout)`: Check if UTXO exists and is unspent
- `is_utxo_spent(txid, vout)`: Check if UTXO is spent
- `get_transaction(txid)`: Get transaction details
- `find_spending_transaction(txid, vout)`: Find TX that spent UTXO

### 5. Counterparty API Client (`counterparty_api.py`)

**Methods:**
- `get_utxo_balances(txid, vout)`: Get assets attached to UTXO
- `validate_utxo_asset(...)`: Validate asset name and quantity

**Endpoint:**
```
GET http://{counterparty_host}:4000/v2/utxos/{txid}:{vout}/balances
```

### 6. Background Monitors (`monitors.py`)

The system uses a dual notification strategy:
1. **ZMQ (primary)**: Real-time push notifications from Bitcoin Core
2. **Polling (fallback)**: Periodic checks every 5 minutes to catch any missed events

**Block Monitor (5 minute fallback polling):**
- Gets current block height
- Updates auction statuses:
  - `upcoming` → `active` when current_block >= start_block
  - `active` → `finished` when current_block > end_block
  - `finished` → `expired` when current_block >= end_block + blocks_after_end

**UTXO Monitor (5 minute fallback polling):**
- Checks if auction UTXOs have been spent
- Determines if spent via PSBT or otherwise:
  - Via PSBT → status = `sold`, set spent_txid, recipient, spent_block, spent_at
  - Not via PSBT → status = `closed`, set spent_txid, recipient, spent_block, spent_at

**ZMQ Trigger Methods:**
- `trigger_block_check()`: Called by ZMQ on new block for immediate status update
- `trigger_utxo_check()`: Called by ZMQ when monitored UTXO is spent
- `check_transaction_for_utxos()`: Parses raw tx to detect UTXO spends

### 7. ZMQ Listener (`zmq_listener.py`)

Real-time notification service that subscribes to Bitcoin Core's ZMQ endpoints.

**Subscriptions:**
- `rawblock` (port 9333): New block notifications → triggers immediate block check
- `rawtx` (port 9332): New transaction notifications → checks if any monitored UTXO is spent

**Features:**
- Runs in separate daemon threads
- Graceful shutdown with timeouts
- Automatic reconnection handling
- Raw transaction parsing to extract inputs
- Thread-safe coordination with polling monitors

**Performance:**
- Block detection: < 1 second (vs 30 seconds with polling only)
- UTXO spend detection: < 1 second (vs 60 seconds with polling only)

## Data Flow

### 1. Auction Submission Flow

```
Seller's Wallet → POST /api/auctions → Validator → Bitcoin RPC → Counterparty API
                                           ↓
                                      Valid? ──→ Save to DB
                                           ↓
                                      Return auction_id
```

**Steps:**
1. Seller creates PSBTs in their wallet (rarepepewallet)
2. Wallet sends JSON payload with PSBTs to API
3. System validates:
   - UTXO exists and is unspent
   - Asset matches expected (single asset only)
   - PSBTs cover full range
   - Prices descend correctly
4. If valid, store in database
5. Return auction ID to seller

### 2. PSBT Revelation Flow

```
Marketplace → GET /api/auctions/{id}/current-psbt
                        ↓
                  Get current block height
                        ↓
                  Calculate which PSBT to reveal
                        ↓
                  Return ONLY that PSBT
                        ↓
              Buyer sees current price
```

**Rules:**
- Before start_block: Return null (not started)
- During auction: Return PSBT for current block
- After end_block: Return final (lowest) PSBT if unsold
- After end_block + blocks_after_end: Return null (cleanup)
- If sold/closed: Return null with status

### 3. Purchase Detection Flow

**Primary Path (ZMQ - Real-time):**
```
New Transaction (Bitcoin Core)
         │
         ▼
    ZMQ rawtx notification
         │
         ▼
    Parse transaction inputs
         │
         ▼
    Check against monitored UTXOs ──── No match ──→ Ignore
         │
         │ Match found
         ▼
    Trigger immediate UTXO check
         │
         ▼
    Get spending TX details → Compare with PSBT prices
         │
         ▼
    Match? → sold : closed
         │
         ▼
    Update status in DB (< 1 second total)
```

**Fallback Path (Polling - Every 5 minutes):**
```
UTXO Monitor → Check if spent → Get spending TX
                    ↓
              Compare with PSBT prices
                    ↓
         Match? → sold : closed
                    ↓
              Update status in DB
```

## Status State Machine

```
       ┌──────────┐
       │ upcoming │  (current_block < start_block)
       └────┬─────┘
            │ start_block reached
            ↓
       ┌────────┐
       │ active │  (start_block ≤ current_block ≤ end_block, unspent)
       └───┬─┬──┘
           │ │
           │ └─────────┐ UTXO spent via PSBT
           │           ↓
           │      ┌────────┐
           │      │  sold  │  (spent_txid set, status indicates PSBT match)
           │      └────────┘
           │
           │ UTXO spent not via PSBT
           ↓
      ┌────────┐
      │ closed │  (spent_txid set, status indicates non-PSBT spend)
      └────────┘
           
      (if end_block passed and still unspent)
           ↓
      ┌──────────┐
      │ finished │  (auction ended, no sale, spent_txid null)
      └────┬─────┘
           │ cleanup window expires
           ↓
      ┌──────────┐
      │ expired  │  (past cleanup window, spent_txid null)
      └──────────┘
```

## Security Features

### 1. PSBT Privacy
- **Never reveal all PSBTs at once**
- Only current PSBT is accessible via API
- Prevents front-running (buying at lowest price)
- Maintains auction integrity

### 2. UTXO Validation
- Verifies UTXO exists before accepting auction
- Checks asset name and quantity match
- Rejects multiple-asset UTXOs
- Ensures UTXO is unspent

### 3. Authentication
- API key required for auction creation
- Read-only endpoints are public
- API key stored in .env file

### 4. Read-Only Bitcoin Operations
- System never modifies blockchain
- No transaction broadcasting
- No private key handling
- Only queries Bitcoin Core

### 5. Input Validation
- Comprehensive validation of all inputs
- Type checking, range checking
- SQL injection prevention (SQLAlchemy ORM)
- Base64 validation for PSBTs

## Deployment

### Docker Network Configuration

```yaml
networks:
  counterparty-core_default:
    external: true
```

The application connects to the existing `counterparty-core_default` network, which already has:
- Bitcoin Core (bitcoind)
- Counterparty Core

### Environment Variables

```bash
# API
API_KEY=secret-key-here

# Bitcoin Core RPC
BITCOIN_RPC_HOST=bitcoind
BITCOIN_RPC_PORT=8332
BITCOIN_RPC_USER=user
BITCOIN_RPC_PASSWORD=password

# Bitcoin Core ZMQ (real-time notifications)
ZMQ_ENABLED=true
ZMQ_BLOCK_URL=tcp://bitcoind:9333   # rawblock notifications
ZMQ_TX_URL=tcp://bitcoind:9332      # rawtx notifications

# Counterparty Core
COUNTERPARTY_HOST=counterparty
COUNTERPARTY_PORT=4000

# Database
DATABASE_PATH=./data/auctions.db

# Monitoring (fallback polling intervals - ZMQ provides real-time)
BLOCK_MONITOR_INTERVAL=300   # 5 minutes
UTXO_MONITOR_INTERVAL=300    # 5 minutes
```

**Bitcoin Core ZMQ Configuration** (in `bitcoin.conf`):
```ini
zmqpubrawtx=tcp://0.0.0.0:9332
zmqpubhashtx=tcp://0.0.0.0:9332
zmqpubsequence=tcp://0.0.0.0:9332
zmqpubrawblock=tcp://0.0.0.0:9333
```

## Performance Considerations

### 1. Database
- SQLite for simplicity with WAL mode enabled for better concurrency
- Indexes on frequently queried fields (status, utxo)
- Cascading deletes for referential integrity
- 5-second busy timeout for lock contention handling

### 2. Real-Time Notifications (ZMQ)
- Block detection: < 1 second via ZMQ `rawblock` subscription
- UTXO spend detection: < 1 second via ZMQ `rawtx` subscription
- Fallback polling: Every 5 minutes (catches missed ZMQ messages)

### 3. API Response Times
- Auction listing: Fast (DB query only)
- Current PSBT: Fast (one DB query + RPC call)
- Auction creation: Slower (validation requires external calls)

## Scalability

### Current Architecture
- SQLite with WAL mode (concurrent reads, single writer with retry)
- Single instance deployment
- ZMQ for real-time event-driven updates (reduces polling overhead 10x)
- Handles 100-200 requests/minute comfortably

### Potential Improvements for Higher Scale
- PostgreSQL for multiple writers and horizontal scaling
- Redis caching for auction listings and block height
- Load balancer for multiple API instances
- Shared ZMQ listener service for multi-instance deployments

## Testing Strategy

### 1. Unit Tests
Test individual components:
- Validators
- Bitcoin RPC client
- Counterparty API client
- Status transitions

### 2. Integration Tests
Test component interactions:
- Auction submission flow
- PSBT revelation logic
- Status updates

### 3. End-to-End Tests
Test complete flows:
- Create auction → verify storage
- Query current PSBT → verify correct one returned
- Simulate block progression → verify status changes

### 4. Manual Testing
Use provided `test_api.sh` script to:
- Check health
- List auctions
- Create test auction
- Get current PSBT

## Monitoring and Observability

### Logs
- Application logs to stdout
- Docker captures logs
- View with: `docker-compose logs -f`

### Health Check
- `/api/health` endpoint
- Checks Bitcoin RPC connectivity
- Returns current block height

### Metrics to Monitor
- Auction creation rate
- PSBT revelation requests
- Bitcoin RPC response times
- ZMQ connection status and message rates
- UTXO monitoring failures
- Database errors

## Future Enhancements

1. **Webhook Support**: Notify sellers when auction status changes
2. **Batch Operations**: Submit multiple auctions at once
3. **Advanced Filtering**: Search by asset, price range, date
4. **Analytics**: Auction success rates, average prices
5. **WebSocket API**: Real-time auction updates for frontend clients
6. **Multi-Asset**: Support for asset bundles (if demand exists)
7. **Auction Extensions**: Allow sellers to extend end_block
8. **Reserve Prices**: Hidden minimum price support

