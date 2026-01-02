# Auction Status Guide

## Complete Status Flow

```
upcoming → active → finished → expired
              ↓
           sold/closed
```

## Status Definitions

| Status | Description | spent_txid | When |
|--------|-------------|------------|------|
| **upcoming** | Auction not started yet | `null` | current_block < start_block |
| **active** | Auction in progress | `null` | start_block ≤ current_block ≤ end_block |
| **sold** | UTXO spent via PSBT | **set** | UTXO spent matching PSBT price |
| **closed** | UTXO spent not via PSBT | **set** | UTXO spent, doesn't match PSBT |
| **finished** | Auction ended, not sold | `null` | end_block < current_block < end_block + blocks_after_end |
| **expired** | Cleanup window passed | `null` | current_block ≥ end_block + blocks_after_end |

**Note:** Both `sold` and `closed` statuses use `spent_txid` to store the transaction that spent the UTXO. The status itself indicates whether it was a PSBT purchase (`sold`) or other spend (`closed`).

## Status Transitions

### Normal Flow (No Sale)

```
upcoming (spent_txid null)
    ↓
active (spent_txid null)
    ↓
finished (spent_txid null)  ← Still showing final PSBT
    ↓
expired (spent_txid null)   ← No longer showing PSBT
```

### Sold During Auction

```
upcoming (spent_txid null)
    ↓
active (spent_txid null)
    ↓
sold (spent_txid set, status='sold' indicates PSBT match)
```

### Seller Closes Manually

```
upcoming (spent_txid null)
    ↓
active (spent_txid null)
    ↓
closed (spent_txid set, status='closed' indicates non-PSBT spend)
```

### Sold After Auction Ends

```
upcoming (spent_txid null)
    ↓
active (spent_txid null)
    ↓
finished (spent_txid null)
    ↓
sold (spent_txid set)
```

## Identifying Auction Outcomes

### How to Query

```sql
-- Unsold auctions still available
SELECT * FROM auctions WHERE status = 'finished' AND spent_txid IS NULL;

-- Unsold auctions past cleanup
SELECT * FROM auctions WHERE status = 'expired' AND spent_txid IS NULL;

-- Sold auctions
SELECT * FROM auctions WHERE status = 'sold';

-- Seller-closed auctions
SELECT * FROM auctions WHERE status = 'closed';

-- Active auctions available now
SELECT * FROM auctions WHERE status = 'active';

-- Upcoming auctions
SELECT * FROM auctions WHERE status = 'upcoming';
```

## API Endpoint Behavior

### GET /api/listings/{id}

Returns listing metadata. The `status` field indicates the current state, and `spent_txid` is populated when the UTXO has been spent.

| Status | spent_txid | Notes |
|--------|------------|-------|
| upcoming | null | Auction has not started yet |
| active | null | Auction in progress, PSBT available |
| sold | set | Purchased via PSBT |
| closed | set | Spent but not via PSBT |
| finished | null | Ended but still in cleanup window |
| expired | null | Past cleanup window |

## Background Monitor Behavior

### Block Monitor (every 30 seconds)

Checks current block height and updates statuses:

1. **upcoming → active**
   - Condition: `current_block >= start_block`
   - Additional check: UTXO still unspent
   
2. **active → finished**
   - Condition: `current_block > end_block`
   - Additional check: UTXO still unspent
   
3. **finished → expired**
   - Condition: `current_block >= end_block + blocks_after_end`
   - Additional check: UTXO still unspent

### UTXO Monitor (every 60 seconds)

Checks if auction UTXOs have been spent:

1. Queries all auctions with status: `upcoming`, `active`, `finished`
2. For each auction, checks if UTXO is spent
3. If spent:
   - Gets spending transaction
   - Checks if transaction output value matches any PSBT price
   - If matches: status → `sold`, set `spent_txid`, `spent_block`, `spent_at`, `recipient`
   - If doesn't match: status → `closed`, set `spent_txid`, `spent_block`, `spent_at`, `recipient`

## Use Cases

### Marketplace Display

**Active Auctions:**
```javascript
// Show auctions currently accepting bids
GET /api/auctions?status=active
```

**Upcoming Auctions:**
```javascript
// Show auctions starting soon
GET /api/auctions?status=upcoming
```

**Recently Ended (Still Available):**
```javascript
// Show auctions that ended but final price still available
GET /api/auctions?status=finished
```

### Analytics

**Sales Rate:**
```sql
SELECT 
  COUNT(*) FILTER (WHERE status = 'sold') as sold_count,
  COUNT(*) FILTER (WHERE status IN ('expired', 'closed')) as not_sold_count,
  COUNT(*) as total_auctions
FROM auctions;
```

**Average Time to Sale:**
```sql
SELECT AVG(sale_block - start_block) as avg_blocks_to_sale
FROM auctions
WHERE status = 'sold';
```

### Seller Dashboard

**My Active Auctions:**
```sql
SELECT * FROM auctions 
WHERE status IN ('upcoming', 'active', 'finished')
ORDER BY start_block DESC;
```

**My Sales:**
```sql
SELECT * FROM auctions 
WHERE status = 'sold' 
ORDER BY created_at DESC;
```

**Expired Listings:**
```sql
SELECT * FROM auctions 
WHERE status = 'expired'
ORDER BY end_block DESC;
```

## Cleanup Strategy

### Old Expired Auctions

You may want to periodically archive or delete expired auctions:

```python
# Example: Delete expired auctions older than 1 month (4320 blocks)
current_block = bitcoin_rpc.get_current_block_height()
cutoff_block = current_block - 4320

old_expired = Auction.query.filter(
    Auction.status == 'expired',
    Auction.end_block < cutoff_block
).delete()

db.session.commit()
```

### Considerations

- Keep `sold` auctions indefinitely (transaction history)
- Keep `closed` auctions for seller reference
- Archive `expired` after reasonable period
- Consider keeping for analytics/reporting

