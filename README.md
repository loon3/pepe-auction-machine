# Rare Pepe Dutch Auction Machine

A Python Flask application that manages Dutch auctions for Rare Pepe assets using pre-signed PSBTs that are revealed progressively per block.

## Features

- Accept pre-signed PSBTs from sellers for Dutch auction style sales
- Progressive PSBT revelation (one per block) to prevent front-running
- Bitcoin Core integration for UTXO validation and monitoring
- Counterparty Core integration for asset verification
- Automatic status updates via background monitors
- REST API for marketplace integration

## Local Development Setup

### Prerequisites

- pyenv installed
- Bitcoin Core running (accessible via RPC)
- Counterparty Core running (accessible via REST API)

### Setup Steps

1. **Install Python 3.11 using pyenv:**
```bash
pyenv install 3.11.0
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Run the application:**
```bash
python run.py
```

## Docker Deployment

### Build and run with Docker Compose:

```bash
docker-compose up -d
```

This will connect to the existing `counterparty-core_default` network and access Bitcoin Core.

## API Endpoints

### POST /api/auctions
Submit a new auction with pre-signed PSBTs.

**Authentication:** Requires `X-API-Key` header

**Request Body:**
```json
{
  "asset_name": "RAREPEPE",
  "asset_qty": 1,
  "utxo_txid": "abc123...",
  "utxo_vout": 0,
  "start_block": 800000,
  "end_block": 800010,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 800000,
      "price_sats": 100000,
      "psbt_data": "cHNidP8BAH..."
    }
  ]
}
```

### GET /api/auctions
List all auctions with optional status filter.

**Query Parameters:**
- `status` (optional): upcoming, active, sold, closed, finished

### GET /api/auctions/{id}
Get auction details (metadata only, no PSBTs).

### GET /api/auctions/{id}/current-psbt
Get the currently active PSBT for an auction.

**Security Note:** Only returns the PSBT for the current block height to prevent revealing future prices.

## Architecture

- **Flask**: Web framework
- **SQLAlchemy**: Database ORM
- **APScheduler**: Background monitoring tasks
- **Bitcoin Core RPC**: UTXO validation and transaction monitoring
- **Counterparty API**: Asset verification

## Security Features

- API key authentication
- UTXO existence validation before accepting auctions
- Single asset per UTXO enforcement
- Progressive PSBT revelation (never expose all PSBTs)
- Read-only Bitcoin RPC operations

