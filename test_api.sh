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

# Test 2: List all listings
echo "2. Listing all listings..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/listings")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ List listings passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ List listings failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 3: Get specific listing by ID
echo "3. Getting listing details (ID=1)..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/listings/1")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get listing details passed${NC}"
    echo "$BODY" | jq .
elif [ "$HTTP_CODE" -eq 404 ]; then
    echo -e "${GREEN}✓ Get listing details returned 404 (no listings exist)${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get listing details failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 4: Get listings by address (example address)
echo "4. Getting listings by address..."
TEST_ADDRESS="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/address/${TEST_ADDRESS}")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get listings by address passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get listings by address failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 5: Get listings by address with status filter
echo "5. Getting active listings by address..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/address/${TEST_ADDRESS}?status=active")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get active listings by address passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get active listings by address failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 6: Get listings by address with role=seller filter
echo "6. Getting seller listings by address..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/address/${TEST_ADDRESS}?role=seller")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get seller listings by address passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get seller listings by address failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 7: Get listings by address with role=buyer filter
echo "7. Getting buyer listings by address..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/address/${TEST_ADDRESS}?role=buyer")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get buyer listings by address passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get buyer listings by address failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 8: Get listings with multiple statuses
echo "8. Getting listings with multiple statuses (active,sold)..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/listings?status=active,sold")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get listings with multiple statuses passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get listings with multiple statuses failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 9: Get address listings with multiple statuses
echo "9. Getting address listings with multiple statuses..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/address/${TEST_ADDRESS}?status=active,upcoming,sold")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Get address listings with multiple statuses passed${NC}"
    echo "$BODY" | jq .
else
    echo -e "${RED}✗ Get address listings with multiple statuses failed (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
fi
echo ""

# Test 10: Create listing via POST /listings
echo "10. Testing listing creation via POST /listings (will fail without valid UTXO)..."
LISTING_PAYLOAD='{
  "asset_name": "TESTPEPE2",
  "asset_qty": 1,
  "utxo_txid": "1111111111111111111111111111111111111111111111111111111111111111",
  "utxo_vout": 0,
  "start_block": 900100,
  "end_block": 900105,
  "start_price_sats": 50000,
  "end_price_sats": 25000,
  "price_decrement": 5000,
  "blocks_after_end": 144,
  "psbts": [
    {
      "block_number": 900100,
      "price_sats": 50000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900101,
      "price_sats": 45000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900102,
      "price_sats": 40000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900103,
      "price_sats": 35000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900104,
      "price_sats": 30000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    },
    {
      "block_number": 900105,
      "price_sats": 25000,
      "psbt_data": "cHNidP8BAH8CAAAAAQhJsNX0FQ=="
    }
  ]
}'

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/listings" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d "$LISTING_PAYLOAD")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 201 ]; then
    echo -e "${GREEN}✓ Listing creation via POST /listings passed${NC}"
    echo "$BODY" | jq .
    LISTING_ID=$(echo "$BODY" | jq -r '.listing_id')
    
    # Test 11: Get the newly created listing
    if [ -n "$LISTING_ID" ] && [ "$LISTING_ID" != "null" ]; then
        echo ""
        echo "11. Getting newly created listing details..."
        RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}/listings/${LISTING_ID}")
        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
        BODY=$(echo "$RESPONSE" | head -n-1)
        
        if [ "$HTTP_CODE" -eq 200 ]; then
            echo -e "${GREEN}✓ Get newly created listing details passed${NC}"
            echo "$BODY" | jq .
        else
            echo -e "${RED}✗ Get newly created listing details failed (HTTP $HTTP_CODE)${NC}"
            echo "$BODY"
        fi
    fi
else
    echo -e "${RED}✗ Listing creation via POST /listings failed (HTTP $HTTP_CODE) - Expected if UTXO doesn't exist${NC}"
    echo "$BODY" | jq .
fi

echo ""
echo "======================================"
echo "Tests completed!"
echo "======================================"

