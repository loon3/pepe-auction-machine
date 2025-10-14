#!/bin/bash
# Test script for Rare Pepe Auction Machine API
# This script demonstrates how to interact with the API

# Configuration
API_URL="http://localhost:5000/api"
API_KEY="your-api-key-here"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "======================================"
echo "Rare Pepe Auction Machine API Tests"
echo "======================================"
echo ""

# Test 1: Health Check
echo "1. Testing health endpoint..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/health")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Health check failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 2: List all auctions
echo "2. Listing all auctions..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/auctions")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ List auctions passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ List auctions failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 3: List active auctions only
echo "3. Listing active auctions..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/auctions?status=active")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ List active auctions passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ List active auctions failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 4: Create auction (requires valid data)
echo "4. Testing auction creation (will fail without valid UTXO)..."
PAYLOAD='{
  "asset_name": "TESTPEPE",
  "asset_qty": 1,
  "utxo_txid": "0000000000000000000000000000000000000000000000000000000000000000",
  "utxo_vout": 0,
  "start_block": 900000,
  "end_block": 900005,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 900000,
      "price_sats": 100000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900001,
      "price_sats": 95000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900002,
      "price_sats": 90000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900003,
      "price_sats": 85000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900004,
      "price_sats": 80000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900005,
      "price_sats": 75000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    }
  ]
}'

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/auctions" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d "$PAYLOAD")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 201 ]; then
    echo -e "${GREEN}✓ Auction creation passed${NC}"
    echo "$BODY" | jq .
    AUCTION_ID=$(echo "$BODY" | jq -r '.auction_id')
    
    # Test 5: Get auction details
    if [ -n "$AUCTION_ID" ] && [ "$AUCTION_ID" != "null" ]; then
        echo ""
        echo "5. Getting auction details..."
        RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/auctions/${AUCTION_ID}")
        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
        BODY=$(echo "$RESPONSE" | head -n-1)
        
        if [ "$HTTP_CODE" -eq 200 ]; then
            echo -e "${GREEN}✓ Get auction details passed${NC}"
            echo "$BODY" | jq .
        else
            echo -e "${RED}✗ Get auction details failed (HTTP $HTTP_CODE)${NC}"
            echo "$BODY"
        fi
        echo ""
        
        # Test 6: Get current PSBT
        echo "6. Getting current PSBT..."
        RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/auctions/${AUCTION_ID}/current-psbt")
        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
        BODY=$(echo "$RESPONSE" | head -n-1)
        
        if [ "$HTTP_CODE" -eq 200 ]; then
            echo -e "${GREEN}✓ Get current PSBT passed${NC}"
            echo "$BODY" | jq .
        else
            echo -e "${RED}✗ Get current PSBT failed (HTTP $HTTP_CODE)${NC}"
            echo "$BODY"
        fi
    fi
else
    echo -e "${RED}✗ Auction creation failed (HTTP $HTTP_CODE) - Expected if UTXO doesn't exist${NC}"
    echo "$BODY" | jq .
fi

echo ""
echo "======================================"
echo "Tests completed!"
echo "======================================"

