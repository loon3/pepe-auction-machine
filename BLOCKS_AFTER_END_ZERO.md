# blocks_after_end = 0 Feature

## Overview

Auctions can now be configured with `blocks_after_end = 0` to expire immediately after the `end_block`, skipping the `finished` state entirely.

## Use Cases

**When to use `blocks_after_end = 0`:**
- Auctions that should expire immediately after end_block
- No grace period needed for late purchases  
- Seller wants UTXO available for new auction ASAP
- Time-sensitive auctions with strict end times

**When to use `blocks_after_end > 0` (typical: 144):**
- Allow buyers grace period for late purchases
- More flexible auction endings
- Prevent network congestion from affecting sales
- Standard practice for most auctions

## Behavior Comparison

### Normal Flow (blocks_after_end = 144)
```
Block 1000: Auction created (upcoming)
Block 1100: Auction starts (active)
Block 1200: Still active - LAST BLOCK for purchases
Block 1201: Auction transitions to finished ← Grace period begins
Block 1345: Grace period ends (expired) ← 144 blocks after end_block
```

**Lifecycle:**
```
upcoming → active → finished → expired
           ↓          ↓
          sold      sold
```

### Fast Expiration (blocks_after_end = 0)
```
Block 1000: Auction created (upcoming)
Block 1100: Auction starts (active)
Block 1200: Still active - LAST BLOCK for purchases
Block 1201: Auction transitions to expired ← Immediate expiration!
```

**Lifecycle:**
```
upcoming → active → expired
           ↓
          sold
```

## Implementation Details

### Database Schema
No changes needed - `blocks_after_end` already supports integer values including 0.

### Monitor Logic (`app/monitors.py`)
```python
# Transition happens the block AFTER end_block
# At end_block: auction is still active (can purchase)
# At end_block + 1: transition occurs

if current_block > auction.end_block:  # After end_block
    if auction.blocks_after_end == 0:
        # Skip finished state, go straight to expired
        auction.status = 'expired'
    else:
        # Normal flow with grace period
        auction.status = 'finished'
```

### API Behavior

**Status Filter:**
- Monitors only check: `['upcoming', 'active', 'finished']`
- With `blocks_after_end = 0`, auctions skip `finished` entirely
- Goes directly from `active` → `expired`

**PSBT Availability:**
- During `active`: PSBTs available
- After `end_block` with `blocks_after_end = 0`: No PSBTs (expired immediately)
- After `end_block` with `blocks_after_end > 0`: Final PSBT available during `finished` state

## Example Auction Creation

```json
POST /api/auctions
{
  "asset_name": "RAREPEPE",
  "asset_qty": 1,
  "utxo_txid": "abc123...",
  "utxo_vout": 0,
  "start_block": 850000,
  "end_block": 850010,
  "start_price_sats": 100000,
  "end_price_sats": 50000,
  "price_decrement": 5000,
  "blocks_after_end": 0,  ← Immediate expiration
  "psbts": [...]
}
```

## Status Transitions

### With blocks_after_end = 0
| Block Range | Status | PSBT Available | Can Purchase? |
|-------------|--------|----------------|---------------|
| < start_block | upcoming | No | No |
| start_block to end_block (inclusive) | active | Yes | Yes |
| end_block + 1 onwards | expired | No | No |

### With blocks_after_end = 144
| Block Range | Status | PSBT Available | Can Purchase? |
|-------------|--------|----------------|---------------|
| < start_block | upcoming | No | No |
| start_block to end_block (inclusive) | active | Yes | Yes |
| end_block + 1 to end_block + 144 | finished | Yes (final) | Yes |
| end_block + 145 onwards | expired | No | No |

## Monitoring Efficiency

Both configurations are equally efficient:

**Active monitoring stops when:**
- Auction is sold → `sold` status (terminal)
- Auction is closed → `closed` status (terminal)
- Auction expires → `expired` status (terminal)

**blocks_after_end = 0 benefit:**
- Reaches terminal state faster (immediately after end_block)
- Reduces time in monitoring queue
- UTXO becomes available for new auction sooner

## Validation

The validator already handles `blocks_after_end = 0`:

```python
# From validators.py
if not isinstance(data['blocks_after_end'], int) or data['blocks_after_end'] < 0:
    raise ValidationError("blocks_after_end must be a non-negative integer")
```

✅ Value of 0 is valid
✅ Negative values are rejected

## Testing Recommendations

1. **Create auction with blocks_after_end = 0**
2. **Verify lifecycle:**
   - Status: upcoming → active → expired (no finished state)
3. **Verify monitoring:**
   - Auction removed from monitoring after expiration
4. **Verify PSBT availability:**
   - Available during active
   - Not available after end_block

## Migration Notes

No migration needed - this is a configuration option that works with existing code. The monitor logic now handles both cases:
- `blocks_after_end = 0` → Direct expiration
- `blocks_after_end > 0` → Normal cleanup window

## Summary

✅ **Implemented:** Monitor logic updated to skip `finished` state when `blocks_after_end = 0`
✅ **Documented:** API.md updated with lifecycle diagrams and examples
✅ **Efficient:** No performance impact, actually reduces monitoring time
✅ **Backward Compatible:** Existing auctions with `blocks_after_end > 0` work unchanged

