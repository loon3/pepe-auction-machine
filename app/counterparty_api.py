import requests
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class CounterpartyAPIClient:
    """Counterparty Core REST API client for asset validation"""
    
    def __init__(self):
        self.base_url = None
    
    def _get_base_url(self):
        """Get Counterparty API base URL"""
        if self.base_url is None:
            api_url = current_app.config['COUNTERPARTY_API_URL']
            self.base_url = f"{api_url}"
        return self.base_url
    
    def get_utxo_balances(self, txid, vout):
        """
        Get asset balances attached to a UTXO with verbose info
        
        Args:
            txid: Transaction ID
            vout: Output index
            
        Returns:
            dict with keys:
                - assets: list of asset dicts with asset_info (divisible, description, etc.)
                - single_asset: boolean indicating if only one asset is attached
                - error: error message if request failed
        """
        try:
            url = f"{self._get_base_url()}/v2/utxos/{txid}:{vout}/balances?verbose=true"
            
            logger.info(f"Requesting Counterparty balances from: {url}")
            
            response = requests.get(url, timeout=10)
            
            logger.info(f"Counterparty API response status: {response.status_code}")
            
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"Counterparty API response data: {data}")
            
            result_list = data.get('result', [])
            
            # Check if it's a single asset
            single_asset = len(result_list) == 1
            
            logger.info(f"Found {len(result_list)} asset(s) on UTXO {txid}:{vout}")
            
            return {
                'assets': result_list,
                'single_asset': single_asset,
                'error': None
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException getting UTXO balances for {txid}:{vout}: {e}", exc_info=True)
            return {
                'assets': [],
                'single_asset': False,
                'error': f"Failed to get UTXO balances: {str(e)}"
            }
    
    def validate_utxo_asset(self, txid, vout, expected_asset_name, expected_quantity):
        """
        Validate that a UTXO has the expected asset and quantity
        Handles both divisible and indivisible assets
        
        Args:
            txid: Transaction ID
            vout: Output index
            expected_asset_name: Expected asset name (must be a string)
            expected_quantity: Expected asset quantity (int for indivisible, float for divisible)
            
        Returns:
            dict with keys:
                - valid: boolean
                - error: error message if not valid
                - asset_data: asset information if valid
        """
        # Validate that asset_name is a string (not multiple assets)
        if not isinstance(expected_asset_name, str):
            return {
                'valid': False,
                'error': 'asset_name must be a string (multiple assets not supported)',
                'asset_data': None
            }
        
        balances = self.get_utxo_balances(txid, vout)
        
        if balances['error']:
            return {
                'valid': False,
                'error': balances['error'],
                'asset_data': None
            }
        
        # Check if multiple assets
        if not balances['single_asset']:
            return {
                'valid': False,
                'error': f"UTXO has {len(balances['assets'])} assets attached. Only single asset UTXOs are supported.",
                'asset_data': None
            }
        
        # Check if no assets
        if len(balances['assets']) == 0:
            return {
                'valid': False,
                'error': 'No assets found on UTXO',
                'asset_data': None
            }
        
        # Get the single asset
        asset_data = balances['assets'][0]
        
        # Validate asset name
        if asset_data['asset'] != expected_asset_name:
            return {
                'valid': False,
                'error': f"Asset mismatch. Expected '{expected_asset_name}', found '{asset_data['asset']}'",
                'asset_data': asset_data
            }
        
        # Determine if asset is divisible
        asset_info = asset_data.get('asset_info', {})
        is_divisible = asset_info.get('divisible', False)
        
        # Get the appropriate quantity based on divisibility
        if is_divisible:
            # For divisible assets, use normalized quantity (float with up to 8 decimals)
            actual_quantity = float(asset_data.get('quantity_normalized', 0))
            expected_quantity = float(expected_quantity)
        else:
            # For indivisible assets, use raw quantity (integer)
            actual_quantity = asset_data.get('quantity', 0)
            expected_quantity = int(expected_quantity)
        
        # Validate quantity
        if actual_quantity != expected_quantity:
            return {
                'valid': False,
                'error': f"Quantity mismatch. Expected {expected_quantity}, found {actual_quantity} ({'divisible' if is_divisible else 'indivisible'} asset)",
                'asset_data': asset_data
            }
        
        logger.info(f"Asset validation successful: {expected_asset_name} ({expected_quantity} {'divisible' if is_divisible else 'indivisible'} units)")
        
        return {
            'valid': True,
            'error': None,
            'asset_data': asset_data
        }


# Global instance
counterparty_api = CounterpartyAPIClient()

