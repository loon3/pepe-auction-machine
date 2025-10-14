# Quick Start Guide

Get the Rare Pepe Auction Machine up and running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Bitcoin Core running (with RPC enabled)
- Counterparty Core running (with REST API on port 4000)
- Both on the `counterparty-core_default` Docker network

## Step 1: Clone and Configure

```bash
cd /path/to/auction-machine

# Create environment file
cp .env.example .env
```

## Step 2: Edit Configuration

Edit `.env` with your settings:

```bash
# Generate a secure API key
API_KEY=$(openssl rand -hex 32)

# Bitcoin Core settings (update these)
BITCOIN_RPC_HOST=bitcoind
BITCOIN_RPC_PORT=8332
BITCOIN_RPC_USER=your_rpc_username
BITCOIN_RPC_PASSWORD=your_rpc_password

# Counterparty settings
COUNTERPARTY_HOST=counterparty
COUNTERPARTY_PORT=4000
```

## Step 3: Start the Service

```bash
# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f auction-machine
```

## Step 4: Verify It's Working

```bash
# Health check
curl http://localhost:5000/api/health

# Expected response:
# {
#   "status": "healthy",
#   "bitcoin_rpc": "connected",
#   "current_block": 850000
# }
```

## Step 5: Test the API

```bash
# List all auctions
curl http://localhost:5000/api/auctions

# Expected response:
# {
#   "success": true,
#   "count": 0,
#   "auctions": []
# }
```

## Done! 🎉

Your Auction Machine is now running and ready to accept auction submissions from your wallet.

## Next Steps

1. **Integrate with your wallet**: Use the API key to submit auctions from rarepepewallet
2. **Read the docs**: Check out `API.md` for complete API documentation
3. **Monitor auctions**: Use `GET /api/auctions?status=active` to see active auctions

## Common Issues

### Can't connect to Bitcoin Core

```bash
# Check if Bitcoin Core is running
docker ps | grep bitcoin

# Check if network exists
docker network ls | grep counterparty

# Test RPC connection manually
curl --user your_user:your_password \
  --data-binary '{"jsonrpc":"1.0","id":"test","method":"getblockcount","params":[]}' \
  -H 'content-type: text/plain;' \
  http://bitcoind:8332/
```

### Can't connect to Counterparty Core

```bash
# Check if Counterparty is running
docker ps | grep counterparty

# Test API connection
curl http://counterparty:4000/v2/blocks/latest
```

### Port 5000 already in use

Edit `docker-compose.yml` and change the port mapping:

```yaml
ports:
  - "5001:5000"  # Use port 5001 instead
```

## Stopping the Service

```bash
# Stop
docker-compose stop

# Stop and remove
docker-compose down

# Stop, remove, and delete database
docker-compose down -v
rm -rf data/
```

## Viewing Logs

```bash
# Follow logs
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100

# View logs for specific time
docker-compose logs --since 30m
```

## Updating

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d
```

## Support

For detailed documentation, see:
- `README.md` - Overview
- `SETUP.md` - Detailed setup guide
- `API.md` - Complete API reference
- `ARCHITECTURE.md` - Technical architecture

