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
┌─────────────────────────────────────────────────────────────┐
│                     Auction Machine                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Flask API (routes.py)                     │  │
│  │  - POST /api/auctions (create auction)                │  │
│  │  - GET  /api/auctions (list auctions)                 │  │
│  │  - GET  /api/auctions/{id} (get details)              │  │
│  │  - GET  /api/auctions/{id}/current-psbt (get PSBT)    │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                  │
│  ┌────────────────────┬────┴────┬──────────────────────┐    │
│  │                    │         │                       │    │
│  │  Validators        │ Models  │  Background Monitors  │    │
│  │  - PSBT format    │  - Auction│  - Block monitor    │    │
│  │  - UTXO exists    │  - PSBT   │  - UTXO monitor     │    │
│  │  - Asset match    │           │                      │    │
│  │  - Price descent  │           │                      │    │
│  └────────┬───────────┴──────────┴──────┬───────────────┘    │
│           │                              │                     │
│  ┌────────┴───────────┐     ┌──────────┴──────────┐         │
│  │  Bitcoin RPC       │     │  Counterparty API   │         │
│  │  - Block height    │     │  - Asset validation │         │
│  │  - UTXO lookup     │     │  - Balance check    │         │
│  │  - TX monitoring   │     │                     │         │
│  └────────┬───────────┘     └──────────┬──────────┘         │
└───────────┼────────────────────────────┼────────────────────┘
            │                            │
      ┌─────┴────────┐          ┌───────┴────────┐
      │ Bitcoin Core │          │ Counterparty   │
      │    (RPC)     │          │  Core (API)    │
      └──────────────┘          └────────────────┘
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
    asset_qty: integer
    utxo_txid: string
    utxo_vout: integer
    start_block: integer
    end_block: integer
    blocks_after_end: integer
    status: enum (upcoming/active/sold/closed/finished)
    purchase_txid: string (nullable)
    closed_txid: string (nullable)
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

**Block Monitor (every 30 seconds):**
- Gets current block height
- Updates auction statuses:
  - `upcoming` → `active` when current_block >= start_block
  - `active` → `finished` when current_block > end_block
  - `finished` → `expired` when current_block >= end_block + blocks_after_end

**UTXO Monitor (every 60 seconds):**
- Checks if auction UTXOs have been spent
- Determines if spent via PSBT or otherwise:
  - Via PSBT → status = `sold`, set purchase_txid
  - Not via PSBT → status = `closed`, set closed_txid

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
           │      │  sold  │  (purchase_txid set, closed_txid null)
           │      └────────┘
           │
           │ UTXO spent not via PSBT
           ↓
      ┌────────┐
      │ closed │  (closed_txid set, purchase_txid null)
      └────────┘
           
      (if end_block passed and still unspent)
           ↓
      ┌──────────┐
      │ finished │  (auction ended, no sale, both txids null)
      └────┬─────┘
           │ cleanup window expires
           ↓
      ┌──────────┐
      │ expired  │  (past cleanup window, both txids null)
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

# Bitcoin Core
BITCOIN_RPC_HOST=bitcoind
BITCOIN_RPC_PORT=8332
BITCOIN_RPC_USER=user
BITCOIN_RPC_PASSWORD=password

# Counterparty Core
COUNTERPARTY_HOST=counterparty
COUNTERPARTY_PORT=4000

# Database
DATABASE_PATH=./data/auctions.db
```

## Performance Considerations

### 1. Database
- SQLite for simplicity
- Indexes on frequently queried fields (status, utxo)
- Cascading deletes for referential integrity

### 2. Monitoring Intervals
- Block monitor: 30 seconds (Bitcoin blocks ~10 minutes)
- UTXO monitor: 60 seconds (slower check is acceptable)

### 3. API Response Times
- Auction listing: Fast (DB query only)
- Current PSBT: Fast (one DB query + RPC call)
- Auction creation: Slower (validation requires external calls)

## Scalability

### Current Limitations
- SQLite (single writer)
- Single instance only
- No caching layer

### Potential Improvements
- PostgreSQL for multiple writers
- Redis caching for block height
- Load balancer for multiple instances
- Message queue for monitoring jobs

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
- UTXO monitoring failures
- Database errors

## Future Enhancements

1. **Webhook Support**: Notify sellers when auction status changes
2. **Batch Operations**: Submit multiple auctions at once
3. **Advanced Filtering**: Search by asset, price range, date
4. **Analytics**: Auction success rates, average prices
5. **WebSocket**: Real-time auction updates
6. **Multi-Asset**: Support for asset bundles (if demand exists)
7. **Auction Extensions**: Allow sellers to extend end_block
8. **Reserve Prices**: Hidden minimum price support

