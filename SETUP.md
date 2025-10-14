# Setup Guide

## Quick Start with Docker

### 1. Configure Environment

Copy the example environment file and edit with your settings:

```bash
cp .env.example .env
```

Edit `.env` and set:
- `API_KEY`: Generate a secure random API key
- `BITCOIN_RPC_USER`: Your Bitcoin Core RPC username
- `BITCOIN_RPC_PASSWORD`: Your Bitcoin Core RPC password
- `BITCOIN_RPC_HOST`: Usually `bitcoind` for Docker
- `COUNTERPARTY_HOST`: Usually `counterparty` for Docker

Example `.env`:
```bash
API_KEY=$(openssl rand -hex 32)
BITCOIN_RPC_HOST=bitcoind
BITCOIN_RPC_PORT=8332
BITCOIN_RPC_USER=your_rpc_user
BITCOIN_RPC_PASSWORD=your_rpc_password
COUNTERPARTY_HOST=counterparty
```

### 2. Build and Run

```bash
# Build the Docker image
docker-compose build

# Start the service
docker-compose up -d

# Check logs
docker-compose logs -f
```

### 3. Verify Installation

Check the health endpoint:
```bash
curl http://localhost:5000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "bitcoin_rpc": "connected",
  "current_block": 850000
}
```

## Local Development Setup

### 1. Install Python 3.11

```bash
pyenv install 3.11.0
pyenv local 3.11.0
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 5. Run Locally

```bash
python run.py
```

## API Usage Examples

### Submit an Auction

```bash
curl -X POST http://localhost:5000/api/auctions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
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
        "psbt_data": "cHNidP8BAH..."
      },
      {
        "block_number": 850001,
        "price_sats": 95000,
        "psbt_data": "cHNidP8BAH..."
      }
    ]
  }'
```

### List All Auctions

```bash
curl http://localhost:5000/api/auctions
```

### List Active Auctions Only

```bash
curl http://localhost:5000/api/auctions?status=active
```

### Get Auction Details

```bash
curl http://localhost:5000/api/auctions/1
```

### Get Current PSBT for Auction

```bash
curl http://localhost:5000/api/auctions/1/current-psbt
```

## Troubleshooting

### Can't connect to Bitcoin Core

Check that:
1. Bitcoin Core is running
2. RPC credentials are correct in `.env`
3. Docker network `counterparty-core_default` exists
4. Bitcoin Core is on the same network

### Can't connect to Counterparty Core

Check that:
1. Counterparty Core is running
2. REST API is enabled (port 4000)
3. Host name in `.env` matches container name

### Database issues

Delete the database and restart:
```bash
rm -rf data/auctions.db
docker-compose restart
```

### View logs

```bash
docker-compose logs -f auction-machine
```

## Network Configuration

The application connects to the `counterparty-core_default` network. Make sure this network exists:

```bash
docker network ls | grep counterparty
```

If it doesn't exist, you need to start Counterparty Core first, or create it manually:

```bash
docker network create counterparty-core_default
```

## Security Notes

1. **API Key**: Keep your API key secret. Regenerate if compromised.
2. **Database**: The SQLite database is stored in `./data/` and persisted between restarts.
3. **PSBT Security**: The system never reveals future PSBTs, only the current one based on block height.
4. **Read-Only RPC**: The app only performs read-only Bitcoin RPC operations.

