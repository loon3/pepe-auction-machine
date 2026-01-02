# Rare Pepe Auction Machine API Documentation

## Overview

The Rare Pepe Auction Machine provides a REST API for managing Dutch auctions and fixed-price listings of Rare Pepe assets on Bitcoin using pre-signed PSBTs.

**Supported Listing Types:**
- **Dutch Auctions**: Price decreases over multiple blocks until sold or expired
- **Fixed-Price Listings**: "Buy it now" style listings at a fixed price for a single block

Base URL: `http://localhost:5000/api`

## Authentication

Most endpoints are public (read-only), but creating auctions requires API key authentication.

**Header:** `X-API-Key: your-api-key`

## Endpoints

### Quick Reference

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/health` | Health check | No |
| GET | `/listings` | List all listings | No |
| POST | `/listings` | Create new listing | Yes |
| GET | `/listings/{id}` | Get listing details | No |
| GET | `/address/{address}` | Get all listings by seller or recipient address | No |

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

### Create Listing (Detailed Documentation)

Submit a new listing with pre-signed PSBTs.

**POST** `/listings`

**Authentication Required:** Yes (X-API-Key header)

**Request Body (Indivisible Asset Example):**
```json
{
  "asset_name": "RAREPEPE",
  "asset_qty": 1,
  "utxo_txid": "abc123...",
  "utxo_vout": 0,
  "start_block": 850000,
  "end_block": 850010,
  "start_price_sats": 100000,
  "end_price_sats": 75000,
  "price_decrement": 2500,
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

**Request Body (Divisible Asset Example):**
```json
{
  "asset_name": "MYTOKEN",
  "asset_qty": 2.5,
  "utxo_txid": "def456...",
  "utxo_vout": 1,
  "start_block": 850000,
  "end_block": 850100,
  "start_price_sats": 500000,
  "end_price_sats": 100000,
  "price_decrement": 4000,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 850000,
      "price_sats": 500000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    }
  ]
}
```

**Request Body (Fixed-Price Listing Example):**

For a fixed-price "buy it now" listing (not a Dutch auction), use these special values:
- `start_block` = `end_block` (single block)
- `start_price_sats` = `end_price_sats` (fixed price)
- `price_decrement` = `0` (no price change)
- Single PSBT with matching block and price

```json
{
  "asset_name": "RAREPEPE",
  "asset_qty": 1,
  "utxo_txid": "abc123...",
  "utxo_vout": 0,
  "start_block": 850000,
  "end_block": 850000,
  "start_price_sats": 50000,
  "end_price_sats": 50000,
  "price_decrement": 0,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 850000,
      "price_sats": 50000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    }
  ]
}
```

**Field Descriptions:**
- `asset_name` (string, required): Counterparty asset name
- `asset_qty` (number, required): Asset quantity (must be > 0)
  - **Indivisible assets**: Integer (e.g., `1`, `100`)
  - **Divisible assets**: Float with up to 8 decimal places (e.g., `0.5`, `1.25`, `100.12345678`)
- `utxo_txid` (string, required): Transaction ID of UTXO containing asset
- `utxo_vout` (integer, required): Output index of UTXO
- `start_block` (integer, required): Block height when auction starts
- `end_block` (integer, required): Block height when auction ends
- `start_price_sats` (integer, required): Starting (highest) price in satoshis
  - For fixed-price listings: set equal to `end_price_sats`
- `end_price_sats` (integer, required): Ending (lowest) price in satoshis
  - For fixed-price listings: set equal to `start_price_sats`
- `price_decrement` (integer, required): Price decrease per block in satoshis
  - For fixed-price listings: set to `0`
  - For Dutch auctions: must be positive
- `blocks_after_end` (integer, required): Grace period for cleanup (typically 144 = 1 day)
  - Set to `0` for immediate expiration after end_block (no cleanup window)
  - When `0`: auction goes directly from `active` → `expired` (skips `finished` state)
- `psbts` (array, required): Array of PSBTs, one per block from start to end
  - For fixed-price listings: single PSBT with block_number = start_block = end_block

**PSBT Object:**
- `block_number` (integer): Block height when this PSBT becomes available
- `price_sats` (integer): Asking price in satoshis
- `psbt_data` (string): Base64 encoded PSBT

**Validation:**

**General Rules (all listings):**
- UTXO must exist and be unspent
- **UTXO transaction must be confirmed** (at least 1 confirmation required)
- UTXO must not have an existing auction (unless the existing auction is `expired`)
- UTXO must contain exactly one asset (multiple assets not supported)
- Asset name and quantity must match
- Asset quantity must be positive; for divisible assets, maximum 8 decimal places
- **`start_block` must be in the future** (after current block height)
- `end_block` must be greater than or equal to `start_block`
- PSBTs must cover entire block range (start to end, inclusive)
- First PSBT price must match `start_price_sats`
- Last PSBT price must match `end_price_sats`
- All PSBTs must be valid format

**Fixed-Price Listings (when start_block = end_block, start_price = end_price, decrement = 0):**
- All three conditions must be true: `start_block == end_block`, `start_price_sats == end_price_sats`, `price_decrement == 0`
- Single PSBT required with matching block and price
- Acts as a "buy it now" listing at a fixed price

**Dutch Auctions (standard multi-block auctions):**
- `end_block` must be greater than `start_block`
- `end_price_sats` must be less than `start_price_sats`
- `price_decrement` must be positive
- Prices must be descending (never increase)
- `price_decrement` must be consistent with price range and block count

**Note on UTXO Reuse:** 
- A UTXO can only have **one active listing** at a time (status: `upcoming`, `active`, or `finished`)
- Once a listing reaches `expired` status, you can create a new listing for the same UTXO
  - `expired`: UTXO still unspent, listing completely over → **Can reuse**
  - `sold`/`closed`: UTXO already spent → **Cannot reuse** (UTXO doesn't exist)
- **Historical records are preserved** - old listings remain in the database for historical queries
- This allows re-listing assets that didn't sell

**Response (Success):**
```json
{
  "success": true,
  "listing_id": 1,
  "message": "Listing created successfully",
  "listing": {
    "id": 1,
    "asset_name": "RAREPEPE",
    "asset_qty": 1,
    "utxo_txid": "abc123...",
    "utxo_vout": 0,
    "start_block": 850000,
    "end_block": 850010,
    "start_price_sats": 100000,
    "end_price_sats": 75000,
    "price_decrement": 2500,
    "blocks_after_end": 144,
    "status": "upcoming",
    "spent_txid": null,
    "spent_block": null,
    "spent_at": null,
    "recipient": null,
    "seller": "bc1q...",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

**Response (Error):**
```json
{
  "error": "Error validating UTXO: UTXO transaction is not yet confirmed. Please wait for at least 1 confirmation before creating a listing."
}
```

**Common Error Messages:**
- `"start_block (X) must be after current block (Y). Listings cannot start in the past or present."` - Listing must start in the future
- `"UTXO transaction is not yet confirmed. Please wait for at least 1 confirmation before creating a listing."` - Transaction is in mempool, needs confirmation
- `"UTXO {txid}:{vout} does not exist or is already spent"` - UTXO not found or already used
- `"Transaction not found. Please verify the transaction ID is correct and has been broadcast."` - Invalid transaction ID
- `"Asset mismatch. Expected 'X', found 'Y'"` - Wrong asset on UTXO
- `"UTXO has N assets attached. Only single asset UTXOs are supported."` - Multiple assets not allowed
- `"Invalid price progression: price increases from X to Y at block Z"` - Prices must decrease
- `"price_decrement (X) doesn't match expected value (~Y based on price range and block count)"` - Inconsistent price decrement
- `"Active listing already exists for UTXO {txid}:{vout} with status 'X'. Wait for it to expire before creating a new listing."` - UTXO has an active/upcoming/finished listing (cannot create concurrent listings)

### List Listings

Get a list of all listings with optional status filter.

**GET** `/listings`

**Query Parameters:**
- `status` (optional): Filter by status (can be comma-separated for multiple statuses)
  - `upcoming`: Auction hasn't started yet
  - `active`: Auction is currently active
  - `sold`: Asset was purchased via PSBT
  - `closed`: Asset was spent but not via PSBT
  - `finished`: Auction ended, not sold, still in cleanup window (if `blocks_after_end` > 0)
  - `expired`: Auction ended, not sold, cleanup window passed (or `blocks_after_end` = 0)
  - Examples: `status=active`, `status=active,sold`, `status=active,upcoming,sold`

**Response:**
```json
{
  "success": true,
  "current_block": 850005,
  "count": 2,
  "listings": [
    {
      "id": 1,
      "asset_name": "RAREPEPE",
      "asset_qty": 1,
      "utxo_txid": "abc123...",
      "utxo_vout": 0,
      "start_block": 850000,
      "end_block": 850010,
      "start_price_sats": 100000,
      "end_price_sats": 75000,
      "price_decrement": 2500,
      "blocks_after_end": 144,
      "status": "active",
      "spent_txid": null,
      "spent_block": null,
      "spent_at": null,
      "recipient": null,
      "seller": "bc1q...",
      "created_at": "2024-01-01T12:00:00",
      "current_price_sats": 87500,
      "current_psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    }
  ]
}
```

**Notes:**
- Returns all listings ordered by creation date (most recent first)
- Supports optional status filtering via query parameter
- Multiple statuses can be specified as comma-separated values (e.g., `status=active,sold`)
- When multiple statuses are provided, returns listings matching ANY of the specified statuses (OR logic)

### Get Listing Details

Get detailed information about a specific listing.

**GET** `/listings/{id}`

**Security Note:** This endpoint returns listing metadata only. PSBT data is never returned to prevent revealing future prices.

**Response:**
```json
{
  "success": true,
  "listing": {
    "id": 1,
    "asset_name": "RAREPEPE",
    "asset_qty": 1,
    "utxo_txid": "abc123...",
    "utxo_vout": 0,
    "start_block": 850000,
    "end_block": 850010,
    "start_price_sats": 100000,
    "end_price_sats": 75000,
    "price_decrement": 2500,
    "blocks_after_end": 144,
    "status": "active",
    "spent_txid": null,
    "spent_block": null,
    "spent_at": null,
    "recipient": null,
    "seller": "bc1q...",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

**Notes:**
- Returns listing metadata only (no PSBT data for security)
- Shows all key listing information including status and pricing

### Create Listing

Submit a new listing with pre-signed PSBTs.

**POST** `/listings`

**Authentication Required:** Yes (X-API-Key header)

**Request Body:** Accepts the same JSON format as the detailed documentation section.

See the [Create Listing (Detailed Documentation)](#create-listing-detailed-documentation) section above for complete details on request format, validation rules, and examples.

**Response (Success):**
```json
{
  "success": true,
  "listing_id": 1,
  "message": "Listing created successfully",
  "listing": {
    "id": 1,
    "asset_name": "RAREPEPE",
    "asset_qty": 1,
    "utxo_txid": "abc123...",
    "utxo_vout": 0,
    "start_block": 850000,
    "end_block": 850010,
    "start_price_sats": 100000,
    "end_price_sats": 75000,
    "price_decrement": 2500,
    "blocks_after_end": 144,
    "status": "upcoming",
    "spent_txid": null,
    "spent_block": null,
    "spent_at": null,
    "recipient": null,
    "seller": "bc1q...",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

**Notes:**
- Returns `listing_id` and `listing` in response
- All validation rules and error messages apply (see [Create Listing (Detailed Documentation)](#create-listing-detailed-documentation) section)
- Error message for existing UTXO will say "Active listing already exists"

### Get Listings by Address

Get all listings where the specified address is either the seller or recipient.

**GET** `/address/{address}`

**Query Parameters:**
- `status` (optional): Filter by status (can be comma-separated for multiple statuses)
  - `upcoming`: Auction hasn't started yet
  - `active`: Auction is currently active
  - `sold`: Asset was purchased via PSBT
  - `closed`: Asset was spent but not via PSBT
  - `finished`: Auction ended, not sold, still in cleanup window
  - `expired`: Auction ended, not sold, cleanup window passed
  - Examples: `status=active`, `status=active,sold`, `status=upcoming,active`
- `role` (optional): Filter by address role
  - `seller`: Only show listings where the address is the seller
  - `buyer`: Only show listings where the address is the recipient (buyer)
  - If not specified: Show both seller and buyer listings

**Response:**
```json
{
  "success": true,
  "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
  "current_block": 850005,
  "count": 3,
  "listings": [
    {
      "id": 1,
      "asset_name": "RAREPEPE",
      "asset_qty": 1,
      "utxo_txid": "abc123...",
      "utxo_vout": 0,
      "start_block": 850000,
      "end_block": 850010,
      "start_price_sats": 100000,
      "end_price_sats": 75000,
      "price_decrement": 2500,
      "blocks_after_end": 144,
      "status": "active",
      "spent_txid": null,
      "spent_block": null,
      "spent_at": null,
      "recipient": null,
      "seller": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
      "created_at": "2024-01-01T12:00:00",
      "current_price_sats": 87500,
      "current_psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "id": 5,
      "asset_name": "NAKAMOTO",
      "asset_qty": 1,
      "utxo_txid": "def456...",
      "utxo_vout": 0,
      "start_block": 849900,
      "end_block": 849950,
      "start_price_sats": 50000,
      "end_price_sats": 25000,
      "price_decrement": 500,
      "blocks_after_end": 144,
      "status": "sold",
      "spent_txid": "xyz789...",
      "spent_block": 849920,
      "spent_at": "2024-01-01T11:00:00",
      "recipient": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
      "seller": "bc1qanotheraddress...",
      "created_at": "2024-01-01T10:00:00",
      "current_price_sats": 40000,
      "current_psbt_data": null
    }
  ]
}
```

**Response (with role filter):**
```json
{
  "success": true,
  "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
  "role": "seller",
  "current_block": 850005,
  "count": 2,
  "listings": [
    {
      "id": 1,
      "asset_name": "RAREPEPE",
      "seller": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
      ...
    }
  ]
}
```

**Notes:**
- Returns all listings where `address` matches either the `seller` or `recipient` field (when no role specified)
- When `role` parameter is provided, only listings matching that role are returned
- Response includes `role` field when a role filter is applied
- Multiple statuses can be specified as comma-separated values (e.g., `status=active,sold`)
- When multiple statuses are provided, returns listings matching ANY of the specified statuses (OR logic)
- Useful for viewing:
  - All auctions created by an address (as seller)
  - All purchases made by an address (as recipient/buyer)
  - Combined view of all activity for an address
- Same listing format and behavior as `/listings` endpoint
- Address validation performs basic format check (minimum length)

**Example Use Cases:**
- View all activity for an address (both buyer and seller): `/api/address/bc1q...`
- View only listings created by a seller: `/api/address/bc1q...?role=seller`
- View only purchases made by a buyer: `/api/address/bc1q...?role=buyer`
- View active seller listings: `/api/address/bc1q...?role=seller&status=active`
- View sold purchases as buyer: `/api/address/bc1q...?role=buyer&status=sold`
- View active and upcoming seller listings: `/api/address/bc1q...?role=seller&status=active,upcoming`
- View sold and closed history: `/api/address/bc1q...?status=sold,closed`

## Auction Status Flow

```
upcoming → active → sold/closed/finished → expired
   ↓          ↓           ↓                   ↓
(before)  (during)    (after)            (cleanup)
```

**Status Definitions:**
- `upcoming`: current_block < start_block
- `active`: start_block ≤ current_block ≤ end_block, UTXO unspent
  - **Note:** Auction is purchasable THROUGH end_block (inclusive)
- `sold`: UTXO spent via one of the PSBTs (spent_txid set, status determined by PSBT match)
- `closed`: UTXO spent but not via PSBT (spent_txid set, status determined by non-PSBT spend)
- `finished`: current_block > end_block, UTXO still unspent, within cleanup window (spent_txid null)
  - Only occurs when `blocks_after_end` > 0
  - Transition happens at end_block + 1
- `expired`: current_block > end_block + blocks_after_end, UTXO still unspent (spent_txid null)
  - If `blocks_after_end` = 0, transition happens at end_block + 1 (skips `finished`)

## Auction Lifecycle

### Normal Flow (with cleanup window)
```
Block X:     upcoming
Block 1000:  active (start_block)
Block 1100:  active (end_block - still purchasable!)
Block 1101:  finished (if blocks_after_end > 0)
Block 1245:  expired (1101 + 144 blocks)
```

**Status transitions:**
```
upcoming → active → finished → expired
           ↓          ↓
          sold      sold
           ↓          ↓
        closed    closed
```

### Fast Expiration (blocks_after_end = 0)
```
Block X:     upcoming
Block 1000:  active (start_block)
Block 1100:  active (end_block - still purchasable!)
Block 1101:  expired (immediate expiration)
```

**Status transitions:**
```
upcoming → active → expired
           ↓
          sold
           ↓
        closed
```

**Important:** Auction is purchasable THROUGH `end_block` (inclusive). Transition happens at `end_block + 1`.

**When to use `blocks_after_end = 0`:**
- Auctions that should expire immediately after end_block
- No grace period needed for late purchases
- Seller wants UTXO available for new auction ASAP

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


