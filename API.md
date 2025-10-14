# Rare Pepe Auction Machine API Documentation

## Overview

The Rare Pepe Auction Machine provides a REST API for managing Dutch auctions of Rare Pepe assets on Bitcoin using pre-signed PSBTs.

Base URL: `http://localhost:5000/api`

## Authentication

Most endpoints are public (read-only), but creating auctions requires API key authentication.

**Header:** `X-API-Key: your-api-key`

## Endpoints

### Health Check

Check if the service is running and can connect to Bitcoin Core.

**GET** `/health`

**Response:**
```json
{
  "status": "healthy",
  "bitcoin_rpc": "connected",
  "current_block": 850000
}
```

### List Auctions

Get a list of all auctions with optional status filter.

**GET** `/auctions`

**Query Parameters:**
- `status` (optional): Filter by status
  - `upcoming`: Auction hasn't started yet
  - `active`: Auction is currently active
  - `sold`: Asset was purchased via PSBT
  - `closed`: Asset was spent but not via PSBT
  - `finished`: Auction ended, not sold, still in cleanup window
  - `expired`: Auction ended, not sold, cleanup window passed

**Response:**
```json
{
  "success": true,
  "count": 2,
  "auctions": [
    {
      "id": 1,
      "asset_name": "RAREPEPE",
      "asset_qty": 1,
      "utxo_txid": "abc123...",
      "utxo_vout": 0,
      "start_block": 850000,
      "end_block": 850010,
      "blocks_after_end": 144,
      "status": "active",
      "purchase_txid": null,
      "closed_txid": null,
      "created_at": "2024-01-01T12:00:00"
    }
  ]
}
```

### Get Auction Details

Get detailed information about a specific auction.

**GET** `/auctions/{id}`

**Security Note:** This endpoint returns auction metadata only. PSBT data is never returned to prevent revealing future prices.

**Response:**
```json
{
  "success": true,
  "auction": {
    "id": 1,
    "asset_name": "RAREPEPE",
    "asset_qty": 1,
    "utxo_txid": "abc123...",
    "utxo_vout": 0,
    "start_block": 850000,
    "end_block": 850010,
    "blocks_after_end": 144,
    "status": "active",
    "purchase_txid": null,
    "closed_txid": null,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

### Get Current PSBT

Get the currently available PSBT for an auction based on current block height.

**GET** `/auctions/{id}/current-psbt`

**Security:** Only returns the PSBT for the current block. Never returns future PSBTs to prevent front-running.

**Behavior:**
- Before `start_block`: Returns null with message
- During auction (`start_block` to `end_block`): Returns PSBT for current block
- After `end_block`: Returns final (lowest price) PSBT if not sold/closed
- After `end_block + blocks_after_end`: Returns null (cleanup period)

**Response (Active):**
```json
{
  "success": true,
  "current_block": 850005,
  "auction_id": 1,
  "auction_status": "active",
  "psbt": {
    "id": 5,
    "auction_id": 1,
    "block_number": 850005,
    "price_sats": 75000,
    "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
  }
}
```

**Response (Not Started):**
```json
{
  "success": true,
  "current_block": 849990,
  "auction_id": 1,
  "psbt": null,
  "message": "Auction has not started yet",
  "starts_at_block": 850000
}
```

**Response (Sold):**
```json
{
  "success": true,
  "current_block": 850005,
  "auction_id": 1,
  "psbt": null,
  "status": "sold",
  "message": "Auction is sold"
}
```

### Create Auction

Submit a new auction with pre-signed PSBTs.

**POST** `/auctions`

**Authentication Required:** Yes (X-API-Key header)

**Request Body:**
```json
{
  "asset_name": "RAREPEPE",
  "asset_qty": 1,
  "utxo_txid": "abc123...",
  "utxo_vout": 0,
  "start_block": 850000,
  "end_block": 850010,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 850000,
      "price_sats": 100000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 850001,
      "price_sats": 95000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    }
  ]
}
```

**Field Descriptions:**
- `asset_name` (string, required): Counterparty asset name
- `asset_qty` (integer, required): Asset quantity (must be > 0)
- `utxo_txid` (string, required): Transaction ID of UTXO containing asset
- `utxo_vout` (integer, required): Output index of UTXO
- `start_block` (integer, required): Block height when auction starts
- `end_block` (integer, required): Block height when auction ends
- `blocks_after_end` (integer, required): Grace period for cleanup (typically 144 = 1 day)
- `psbts` (array, required): Array of PSBTs, one per block from start to end

**PSBT Object:**
- `block_number` (integer): Block height when this PSBT becomes available
- `price_sats` (integer): Asking price in satoshis
- `psbt_data` (string): Base64 encoded PSBT

**Validation:**
- UTXO must exist and be unspent
- UTXO must contain exactly one asset (multiple assets not supported)
- Asset name and quantity must match
- PSBTs must cover entire block range (start to end, inclusive)
- Prices must be descending (Dutch auction)
- All PSBTs must be valid format

**Response (Success):**
```json
{
  "success": true,
  "auction_id": 1,
  "message": "Auction created successfully",
  "auction": {
    "id": 1,
    "asset_name": "RAREPEPE",
    "asset_qty": 1,
    "utxo_txid": "abc123...",
    "utxo_vout": 0,
    "start_block": 850000,
    "end_block": 850010,
    "blocks_after_end": 144,
    "status": "upcoming",
    "purchase_txid": null,
    "closed_txid": null,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

**Response (Error):**
```json
{
  "error": "UTXO does not exist or is already spent"
}
```

## Auction Status Flow

```
upcoming → active → sold/closed/finished → expired
   ↓          ↓           ↓                   ↓
(before)  (during)    (after)            (cleanup)
```

**Status Definitions:**
- `upcoming`: Current block < start_block
- `active`: start_block ≤ current_block ≤ end_block, UTXO unspent
- `sold`: UTXO spent via one of the PSBTs (purchase_txid set, closed_txid null)
- `closed`: UTXO spent but not via PSBT (closed_txid set, purchase_txid null)
- `finished`: current_block > end_block, UTXO still unspent, within cleanup window (both txids null)
- `expired`: current_block ≥ end_block + blocks_after_end, UTXO still unspent (both txids null)

## Error Codes

- `200 OK`: Request successful
- `201 Created`: Auction created successfully
- `400 Bad Request`: Invalid request data or validation failed
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Auction not found
- `409 Conflict`: Auction already exists for this UTXO
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Cannot connect to Bitcoin Core

## Rate Limiting

No rate limiting is currently implemented. Use responsibly.

## Security Notes

1. **PSBT Privacy**: The API never reveals all PSBTs at once. Only the current PSBT is returned based on block height.
2. **Read-Only Bitcoin RPC**: The system only performs read operations on Bitcoin Core.
3. **No Broadcasting**: The API does not broadcast transactions. Buyers must broadcast themselves.
4. **UTXO Validation**: All UTXOs are validated before accepting auctions.
5. **Single Asset**: Only single-asset UTXOs are supported (multiple assets rejected).

## Background Monitoring

The system runs two background monitors:

1. **Block Monitor** (every 30 seconds):
   - Updates auction statuses based on current block height
   - Transitions: upcoming → active → finished

2. **UTXO Monitor** (every 60 seconds):
   - Checks if auction UTXOs have been spent
   - Determines if spent via PSBT (sold) or otherwise (closed)

## Integration Example

```javascript
// Example: Get current PSBT and display to user
async function getCurrentPrice(auctionId) {
  const response = await fetch(
    `http://localhost:5000/api/auctions/${auctionId}/current-psbt`
  );
  const data = await response.json();
  
  if (data.success && data.psbt) {
    return {
      price: data.psbt.price_sats,
      psbt: data.psbt.psbt_data,
      block: data.current_block
    };
  }
  
  return null;
}
```

