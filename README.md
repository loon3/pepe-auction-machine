# Rare Pepe Dutch Auction Machine

A Python Flask application that manages Dutch auctions for Rare Pepe assets (Counterparty assets on Bitcoin) using pre-signed PSBTs with SIGHASH_SINGLE|ANYONECANPAY that are revealed progressively per block.

## What is a Dutch Auction?

A **Dutch auction** is a descending price auction where:
- Seller sets a starting high price
- Price decreases over time (per Bitcoin block)
- First buyer to accept the current price wins
- Price descends until sold or auction ends

This implementation uses **progressive PSBT revelation** - PSBTs are only exposed one per block based on current blockchain height, preventing buyers from seeing the lowest price ahead of time and maintaining auction integrity.

## Features

- ✅ **Dutch Auction Mechanism**: Descending price per block
- 🔒 **Progressive PSBT Revelation**: One PSBT per block (prevents front-running)
- 🔗 **Bitcoin Core Integration**: UTXO validation and transaction monitoring
- 💎 **Counterparty Integration**: Asset verification via REST API
- 🤖 **Background Monitors**: Automatic status updates and UTXO spend detection
- 🌐 **REST API**: Easy marketplace integration
- 🔐 **Security First**: API key auth, single asset enforcement, read-only RPC
- 📊 **Status Tracking**: upcoming → active → sold/closed/finished → expired

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
  "start_price_sats": 100000,
  "end_price_sats": 50000,
  "price_decrement": 5000,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 800000,
      "price_sats": 100000,
      "psbt_data": "cHNidP8BAH..."
    },
    {
      "block_number": 800001,
      "price_sats": 95000,
      "psbt_data": "cHNidP8BAH..."
    }
  ]
}
```

**Field Descriptions:**
- `start_price_sats`: Starting (highest) price in satoshis
- `end_price_sats`: Ending (lowest) price in satoshis  
- `price_decrement`: Price decrease per block in satoshis
- `psbts`: Array of PSBTs, one per block from start to end

### GET /api/auctions
List all auctions with optional status filter.

**Query Parameters:**
- `status` (optional): upcoming, active, sold, closed, finished, expired

**Status Definitions:**
- `upcoming`: Auction hasn't started yet (current block < start_block)
- `active`: Auction is currently running
- `sold`: Asset purchased via PSBT
- `closed`: Asset spent but not via PSBT (seller closed)
- `finished`: Auction ended, not sold, still in cleanup window
- `expired`: Auction ended, cleanup window passed

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

- 🔑 **API Key Authentication**: Protected auction submission
- ✅ **UTXO Validation**: Verifies UTXO exists and contains correct asset
- 1️⃣ **Single Asset Enforcement**: Rejects UTXOs with multiple assets
- 🔒 **Progressive PSBT Revelation**: Never exposes all PSBTs (prevents front-running)
- 👀 **Read-Only RPC**: No transaction broadcasting or private key handling
- 🛡️ **Input Validation**: Comprehensive validation of all submission data

## How It Works

1. **Seller Preparation**: Seller creates range of PSBTs in their wallet (e.g., rarepepewallet) with decreasing prices
2. **Submission**: Seller submits auction with PSBTs to API (authenticated)
3. **Validation**: System validates UTXO, asset, prices, and PSBT format
4. **Storage**: Auction and PSBTs stored securely in database
5. **Revelation**: API only reveals current PSBT based on block height
6. **Purchase**: Buyer gets current PSBT, completes and broadcasts transaction
7. **Monitoring**: Background services detect UTXO spend and update status

## Documentation

- 📖 **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- 📘 **[SETUP.md](SETUP.md)** - Detailed installation guide
- 🔧 **[API.md](API.md)** - Complete API documentation
- 🏗️ **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture
- 📊 **[STATUS_GUIDE.md](STATUS_GUIDE.md)** - Status lifecycle reference

## Quick Start

```bash
# 1. Configure
cp .env.example .env
# Edit .env with your Bitcoin/Counterparty settings

# 2. Deploy with Docker
docker-compose up -d

# 3. Verify
curl http://localhost:5000/api/health
```

## Development

Built with:
- Python 3.11
- Flask (web framework)
- SQLAlchemy (ORM)
- APScheduler (background jobs)
- Bitcoin Core RPC
- Counterparty REST API

## License

MIT License - See LICENSE file for details

