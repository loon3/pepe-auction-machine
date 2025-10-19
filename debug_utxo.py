#!/usr/bin/env python3
"""
Debug script to test UTXO validation
Usage: python debug_utxo.py <txid> <vout>
"""
import sys
import logging
from app import create_app
from app.bitcoin_rpc import bitcoin_rpc
from app.counterparty_api import counterparty_api

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def debug_utxo(txid, vout):
    """Debug UTXO validation"""
    app = create_app()
    
    with app.app_context():
        logger.info(f"=" * 80)
        logger.info(f"Debugging UTXO: {txid}:{vout}")
        logger.info(f"=" * 80)
        
        # Test Bitcoin RPC
        logger.info("\n1. Testing Bitcoin Core RPC connection...")
        try:
            block_height = bitcoin_rpc.get_current_block_height()
            logger.info(f"✓ Bitcoin Core connected, current block: {block_height}")
        except Exception as e:
            logger.error(f"✗ Bitcoin Core connection failed: {e}")
            return
        
        # Test UTXO lookup
        logger.info(f"\n2. Testing UTXO lookup for {txid}:{vout}...")
        try:
            utxo = bitcoin_rpc.get_utxo(txid, vout)
            if utxo:
                logger.info(f"✓ UTXO found!")
                logger.info(f"  - Confirmations: {utxo.get('confirmations', 0)}")
                logger.info(f"  - Value: {utxo.get('value', 0)} BTC")
            else:
                logger.warning(f"✗ UTXO not found or already spent")
                return
        except Exception as e:
            logger.error(f"✗ UTXO lookup failed: {e}")
            logger.error(f"  Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return
        
        # Test Counterparty API
        logger.info(f"\n3. Testing Counterparty API for {txid}:{vout}...")
        try:
            balances = counterparty_api.get_utxo_balances(txid, vout)
            if balances['error']:
                logger.error(f"✗ Counterparty API error: {balances['error']}")
            else:
                logger.info(f"✓ Counterparty API responded")
                logger.info(f"  - Assets found: {len(balances['assets'])}")
                for asset in balances['assets']:
                    logger.info(f"    - {asset['asset']}: {asset['quantity']}")
        except Exception as e:
            logger.error(f"✗ Counterparty API failed: {e}")
            import traceback
            traceback.print_exc()
        
        logger.info(f"\n" + "=" * 80)
        logger.info("Debug complete")
        logger.info("=" * 80)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python debug_utxo.py <txid> <vout>")
        print("Example: python debug_utxo.py abc123...xyz 0")
        sys.exit(1)
    
    txid = sys.argv[1]
    try:
        vout = int(sys.argv[2])
    except ValueError:
        print(f"Error: vout must be an integer, got '{sys.argv[2]}'")
        sys.exit(1)
    
    debug_utxo(txid, vout)

