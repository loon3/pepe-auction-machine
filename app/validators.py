import base64
import logging
from app.bitcoin_rpc import bitcoin_rpc
from app.counterparty_api import counterparty_api

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


def validate_psbt_format(psbt_data):
    """
    Validate PSBT format
    
    Args:
        psbt_data: Base64 encoded PSBT string
        
    Returns:
        True if valid
        
    Raises:
        ValidationError if invalid
    """
    try:
        # Check if it's a valid base64 string
        decoded = base64.b64decode(psbt_data)
        
        # Check if it starts with PSBT magic bytes (psbt\xff)
        if not decoded.startswith(b'psbt\xff'):
            raise ValidationError("Invalid PSBT format: missing magic bytes")
        
        return True
        
    except Exception as e:
        raise ValidationError(f"Invalid PSBT format: {str(e)}")


def validate_utxo_exists(txid, vout):
    """
    Validate that UTXO exists and is unspent
    
    Args:
        txid: Transaction ID
        vout: Output index
        
    Returns:
        UTXO data dict if valid
        
    Raises:
        ValidationError if UTXO doesn't exist or is spent
    """
    try:
        utxo = bitcoin_rpc.get_utxo(txid, vout)
        
        if utxo is None:
            raise ValidationError(f"UTXO {txid}:{vout} does not exist or is already spent")
        
        return utxo
        
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Error validating UTXO: {str(e)}")


def validate_utxo_asset(txid, vout, expected_asset_name, expected_quantity):
    """
    Validate that UTXO has the expected asset and quantity
    
    Args:
        txid: Transaction ID
        vout: Output index
        expected_asset_name: Expected asset name (must be string)
        expected_quantity: Expected asset quantity
        
    Returns:
        Asset data dict if valid
        
    Raises:
        ValidationError if asset doesn't match or multiple assets found
    """
    try:
        result = counterparty_api.validate_utxo_asset(
            txid, vout, expected_asset_name, expected_quantity
        )
        
        if not result['valid']:
            raise ValidationError(result['error'])
        
        return result['asset_data']
        
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Error validating UTXO asset: {str(e)}")


def validate_price_progression(psbts):
    """
    Validate that PSBT prices are in descending order (Dutch auction)
    
    Args:
        psbts: List of PSBT dicts with 'block_number' and 'price_sats' keys
        
    Returns:
        True if valid
        
    Raises:
        ValidationError if prices don't decrease properly
    """
    if not psbts or len(psbts) == 0:
        raise ValidationError("No PSBTs provided")
    
    # Sort by block number to ensure we check in order
    sorted_psbts = sorted(psbts, key=lambda x: x['block_number'])
    
    # Check that prices decrease (or stay the same) as blocks increase
    for i in range(len(sorted_psbts) - 1):
        current_price = sorted_psbts[i]['price_sats']
        next_price = sorted_psbts[i + 1]['price_sats']
        
        if next_price > current_price:
            raise ValidationError(
                f"Invalid price progression: price increases from {current_price} to {next_price} "
                f"at block {sorted_psbts[i + 1]['block_number']}"
            )
    
    return True


def validate_block_range(psbts, start_block, end_block):
    """
    Validate that PSBTs cover the entire block range
    
    Args:
        psbts: List of PSBT dicts with 'block_number' key
        start_block: Expected start block
        end_block: Expected end block
        
    Returns:
        True if valid
        
    Raises:
        ValidationError if block range doesn't match
    """
    if not psbts or len(psbts) == 0:
        raise ValidationError("No PSBTs provided")
    
    # Get all block numbers
    block_numbers = sorted([psbt['block_number'] for psbt in psbts])
    
    # Check that first PSBT is at start_block
    if block_numbers[0] != start_block:
        raise ValidationError(
            f"First PSBT block ({block_numbers[0]}) doesn't match start_block ({start_block})"
        )
    
    # Check that last PSBT is at end_block
    if block_numbers[-1] != end_block:
        raise ValidationError(
            f"Last PSBT block ({block_numbers[-1]}) doesn't match end_block ({end_block})"
        )
    
    # Check that we have one PSBT per block (no gaps)
    expected_blocks = list(range(start_block, end_block + 1))
    if block_numbers != expected_blocks:
        missing_blocks = set(expected_blocks) - set(block_numbers)
        if missing_blocks:
            raise ValidationError(f"Missing PSBTs for blocks: {sorted(missing_blocks)}")
        
        extra_blocks = set(block_numbers) - set(expected_blocks)
        if extra_blocks:
            raise ValidationError(f"Extra PSBTs for blocks outside range: {sorted(extra_blocks)}")
    
    return True


def validate_auction_submission(data):
    """
    Validate complete auction submission
    
    Args:
        data: Auction submission dict with all required fields
        
    Returns:
        dict with validated data
        
    Raises:
        ValidationError if any validation fails
    """
    # Validate required fields
    required_fields = [
        'asset_name', 'asset_qty', 'utxo_txid', 'utxo_vout',
        'start_block', 'end_block', 'blocks_after_end', 'psbts'
    ]
    
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")
    
    # Validate data types
    if not isinstance(data['asset_name'], str):
        raise ValidationError("asset_name must be a string (multiple assets not supported)")
    
    if not isinstance(data['asset_qty'], int) or data['asset_qty'] <= 0:
        raise ValidationError("asset_qty must be a positive integer")
    
    if not isinstance(data['utxo_vout'], int) or data['utxo_vout'] < 0:
        raise ValidationError("utxo_vout must be a non-negative integer")
    
    if not isinstance(data['start_block'], int) or data['start_block'] <= 0:
        raise ValidationError("start_block must be a positive integer")
    
    if not isinstance(data['end_block'], int) or data['end_block'] <= 0:
        raise ValidationError("end_block must be a positive integer")
    
    if data['end_block'] <= data['start_block']:
        raise ValidationError("end_block must be greater than start_block")
    
    if not isinstance(data['blocks_after_end'], int) or data['blocks_after_end'] < 0:
        raise ValidationError("blocks_after_end must be a non-negative integer")
    
    if not isinstance(data['psbts'], list) or len(data['psbts']) == 0:
        raise ValidationError("psbts must be a non-empty list")
    
    # Validate each PSBT has required fields
    for i, psbt in enumerate(data['psbts']):
        if 'block_number' not in psbt:
            raise ValidationError(f"PSBT {i} missing block_number")
        if 'price_sats' not in psbt:
            raise ValidationError(f"PSBT {i} missing price_sats")
        if 'psbt_data' not in psbt:
            raise ValidationError(f"PSBT {i} missing psbt_data")
        
        if not isinstance(psbt['price_sats'], int) or psbt['price_sats'] <= 0:
            raise ValidationError(f"PSBT {i} price_sats must be a positive integer")
        
        # Validate PSBT format
        validate_psbt_format(psbt['psbt_data'])
    
    # Validate UTXO exists and is unspent
    validate_utxo_exists(data['utxo_txid'], data['utxo_vout'])
    
    # Validate UTXO has the correct asset and quantity
    validate_utxo_asset(
        data['utxo_txid'],
        data['utxo_vout'],
        data['asset_name'],
        data['asset_qty']
    )
    
    # Validate price progression (descending)
    validate_price_progression(data['psbts'])
    
    # Validate block range coverage
    validate_block_range(data['psbts'], data['start_block'], data['end_block'])
    
    logger.info(f"Successfully validated auction for {data['asset_name']} at {data['utxo_txid']}:{data['utxo_vout']}")
    
    return data

