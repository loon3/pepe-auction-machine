from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class BitcoinRPCClient:
    """Bitcoin Core RPC client for UTXO validation and transaction monitoring"""
    
    def __init__(self):
        self.connection = None
        self._connection_url = None
    
    def _get_connection(self):
        """Get or create RPC connection"""
        # Always create a fresh connection URL from config
        rpc_user = current_app.config['BITCOIN_RPC_USER']
        rpc_password = current_app.config['BITCOIN_RPC_PASSWORD']
        rpc_host = current_app.config['BITCOIN_RPC_HOST']
        rpc_port = current_app.config['BITCOIN_RPC_PORT']
        
        rpc_url = f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
        
        # Create a new connection for each call to avoid thread safety issues
        # AuthServiceProxy connections should not be shared across threads
        return AuthServiceProxy(rpc_url)
    
    def get_current_block_height(self):
        """Get current blockchain height"""
        try:
            rpc = self._get_connection()
            return rpc.getblockcount()
        except JSONRPCException as e:
            logger.error(f"Error getting block height: {e}")
            raise Exception(f"Failed to get block height: {str(e)}")
    
    def get_utxo(self, txid, vout):
        """
        Get UTXO information
        Returns dict with keys: txid, vout, value, scriptPubKey
        Returns None if UTXO doesn't exist or is spent
        """
        try:
            logger.info(f"Calling Bitcoin RPC gettxout for {txid}:{vout} (vout type: {type(vout)})")
            rpc = self._get_connection()
            
            # Ensure vout is an integer
            if not isinstance(vout, int):
                logger.warning(f"vout is not an integer: {vout} (type: {type(vout)}), converting...")
                vout = int(vout)
            
            # Get transaction output
            logger.debug(f"Executing: gettxout('{txid}', {vout})")
            result = rpc.gettxout(txid, vout)
            
            if result is None:
                # UTXO doesn't exist or is spent
                logger.warning(f"gettxout returned None for {txid}:{vout} (UTXO doesn't exist or is spent)")
                return None
            
            logger.info(f"Successfully retrieved UTXO {txid}:{vout}, confirmations: {result.get('confirmations', 0)}")
            return {
                'txid': txid,
                'vout': vout,
                'value': result['value'],
                'scriptPubKey': result['scriptPubKey'],
                'confirmations': result.get('confirmations', 0)
            }
        except JSONRPCException as e:
            error_msg = str(e)
            logger.error(f"JSONRPCException getting UTXO {txid}:{vout}: {error_msg}", exc_info=True)
            
            # Check for common error cases
            if "Request-sent" in error_msg or "not yet confirmed" in error_msg:
                raise Exception("UTXO transaction is not yet confirmed. Please wait for at least 1 confirmation before creating an auction.")
            elif "No such mempool or blockchain transaction" in error_msg:
                raise Exception("Transaction not found. Please verify the transaction ID is correct and has been broadcast.")
            else:
                raise Exception(f"Failed to get UTXO: {error_msg}")
    
    def is_utxo_spent(self, txid, vout):
        """
        Check if a UTXO is spent
        Returns True if spent, False if unspent
        """
        utxo = self.get_utxo(txid, vout)
        return utxo is None
    
    def check_utxos_batch(self, utxo_list, batch_size=50):
        """
        Check multiple UTXOs in batches using RPC batch requests
        
        Args:
            utxo_list: List of (txid, vout) tuples to check
            batch_size: Maximum number of UTXOs per batch (default 50)
            
        Returns:
            dict: {(txid, vout): is_spent, ...}
            - is_spent is True if UTXO is spent/doesn't exist, False if unspent
        """
        if not utxo_list:
            return {}
        
        results = {}
        
        # Split into batches
        for i in range(0, len(utxo_list), batch_size):
            batch = utxo_list[i:i + batch_size]
            
            try:
                rpc = self._get_connection()
                
                logger.debug(f"Batch checking {len(batch)} UTXOs")
                
                # Execute batch request using batch_ with list of call lists
                # Format: [['method_name', param1, param2], ...]
                # Must be lists, not tuples, because library calls .pop()
                batch_calls = [['gettxout', txid, vout] for txid, vout in batch]
                batch_results = rpc.batch_(batch_calls)
                
                # Process results
                for (txid, vout), result in zip(batch, batch_results):
                    # result is None if UTXO is spent or doesn't exist
                    is_spent = (result is None)
                    results[(txid, vout)] = is_spent
                    
            except Exception as e:
                logger.error(f"Error in batch UTXO check: {str(e)}", exc_info=True)
                # Fall back to individual checks for this batch
                logger.info(f"Falling back to individual checks for batch of {len(batch)} UTXOs")
                for txid, vout in batch:
                    try:
                        is_spent = self.is_utxo_spent(txid, vout)
                        results[(txid, vout)] = is_spent
                    except Exception as e2:
                        logger.error(f"Error checking UTXO {txid}:{vout}: {str(e2)}")
                        # Skip this UTXO if we can't check it
                        continue
        
        return results
    
    def get_transaction(self, txid):
        """
        Get raw transaction information
        Returns decoded transaction data
        """
        try:
            rpc = self._get_connection()
            
            # Get raw transaction
            raw_tx = rpc.getrawtransaction(txid, True)
            
            return raw_tx
        except JSONRPCException as e:
            logger.error(f"Error getting transaction {txid}: {e}")
            return None
    
    def find_spending_transaction(self, txid, vout):
        """
        Find the transaction that spent a specific UTXO
        Returns transaction ID if found, None otherwise
        Note: This requires txindex=1 in Bitcoin Core
        """
        try:
            rpc = self._get_connection()
            
            # First check if UTXO is spent
            if not self.is_utxo_spent(txid, vout):
                return None
            
            # Get the original transaction to find the address
            tx = self.get_transaction(txid)
            if not tx or vout >= len(tx['vout']):
                return None
            
            # Get the scriptPubKey and address
            vout_data = tx['vout'][vout]
            addresses = vout_data['scriptPubKey'].get('addresses', [])
            
            if not addresses:
                # Can't search without an address
                logger.warning(f"No address found for UTXO {txid}:{vout}")
                return None
            
            address = addresses[0]
            
            # Search for transactions involving this address
            # This is a simplified approach - in production you might want to use
            # a more efficient method like maintaining a database of spent UTXOs
            try:
                # Get list of transactions for the address
                # Note: This requires addressindex=1 in Bitcoin Core or using getaddressinfo
                received_by_address = rpc.listreceivedbyaddress(0, True, True, address)
                
                if received_by_address:
                    # Check transactions to find which one spent our UTXO
                    for item in received_by_address:
                        if 'txids' in item:
                            for spending_txid in item['txids']:
                                spending_tx = self.get_transaction(spending_txid)
                                if spending_tx:
                                    # Check if this transaction has our UTXO as an input
                                    for vin in spending_tx['vin']:
                                        if vin.get('txid') == txid and vin.get('vout') == vout:
                                            return spending_txid
            except JSONRPCException:
                # Method might not be available, try alternative approach
                pass
            
            logger.warning(f"Could not find spending transaction for {txid}:{vout}")
            return None
            
        except JSONRPCException as e:
            logger.error(f"Error finding spending transaction for {txid}:{vout}: {e}")
            return None


# Global instance
bitcoin_rpc = BitcoinRPCClient()

