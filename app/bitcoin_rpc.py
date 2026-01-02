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
                
                # Log which UTXOs are being checked
                utxo_list_str = ", ".join([f"{txid[:8]}...:{vout}" for txid, vout in batch])
                logger.info(f"Batch checking {len(batch)} UTXOs: {utxo_list_str}")
                
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
    
    def get_transaction_details(self, txid):
        """
        Get transaction details including block height and timestamp
        
        Args:
            txid: Transaction ID
            
        Returns:
            dict: {'block_height': int, 'timestamp': datetime} or None
        """
        try:
            tx = self.get_transaction(txid)
            
            if not tx:
                return None
            
            # Check if transaction is confirmed
            confirmations = tx.get('confirmations', 0)
            if confirmations == 0:
                logger.debug(f"Transaction {txid} not yet confirmed")
                return None
            
            result = {}
            
            # Get block height (blockhash indicates it's in a block)
            if 'blockhash' in tx:
                # Calculate block height from current height - confirmations + 1
                current_height = self.get_current_block_height()
                block_height = current_height - confirmations + 1
                result['block_height'] = block_height
            else:
                result['block_height'] = None
            
            # Get timestamp (blocktime is Unix timestamp)
            if 'blocktime' in tx:
                from datetime import datetime
                result['timestamp'] = datetime.utcfromtimestamp(tx['blocktime'])
            elif 'time' in tx:
                from datetime import datetime
                result['timestamp'] = datetime.utcfromtimestamp(tx['time'])
            else:
                result['timestamp'] = None
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting transaction details for {txid}: {e}")
            return None
    
    def get_recipient_address(self, txid):
        """
        Get the recipient address from a transaction (first non-OP_RETURN output)
        
        Args:
            txid: Transaction ID
            
        Returns:
            str: Recipient address or None if not found
        """
        try:
            tx = self.get_transaction(txid)
            
            if not tx or 'vout' not in tx:
                return None
            
            # Find first non-OP_RETURN output
            for vout in tx['vout']:
                script_pub_key = vout.get('scriptPubKey', {})
                script_type = script_pub_key.get('type', '')
                
                # Skip OP_RETURN outputs
                if script_type == 'nulldata':
                    continue
                
                # Try to get address (newer format)
                if 'address' in script_pub_key:
                    return script_pub_key['address']
                
                # Try legacy format
                if 'addresses' in script_pub_key and len(script_pub_key['addresses']) > 0:
                    return script_pub_key['addresses'][0]
            
            logger.warning(f"No recipient address found in transaction {txid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting recipient address for {txid}: {e}")
            return None
    
    def get_address_from_utxo(self, txid, vout):
        """
        Get the address that controls a specific UTXO
        
        Args:
            txid: Transaction ID
            vout: Output index
            
        Returns:
            str: Address controlling the UTXO or None if not found
        """
        try:
            tx = self.get_transaction(txid)
            
            if not tx or 'vout' not in tx:
                logger.warning(f"Could not get transaction {txid}")
                return None
            
            # Check if vout index is valid
            if vout >= len(tx['vout']):
                logger.warning(f"vout {vout} out of range for transaction {txid}")
                return None
            
            # Get the output at the specified index
            output = tx['vout'][vout]
            script_pub_key = output.get('scriptPubKey', {})
            
            # Try to get address (newer format)
            if 'address' in script_pub_key:
                return script_pub_key['address']
            
            # Try legacy format
            if 'addresses' in script_pub_key and len(script_pub_key['addresses']) > 0:
                return script_pub_key['addresses'][0]
            
            logger.warning(f"No address found for UTXO {txid}:{vout}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting address for UTXO {txid}:{vout}: {e}")
            return None
    
    def find_spending_transaction(self, txid, vout):
        """
        Find the transaction that spent a specific UTXO
        Returns transaction ID if found, None otherwise
        
        Tries multiple methods in order:
        1. gettxspendingprevout (Bitcoin Core 24.0+, works without wallet)
        2. getspentinfo (requires spentindex=1)
        3. listreceivedbyaddress (requires wallet, fallback)
        
        Note: Works best with txindex=1 in Bitcoin Core
        """
        try:
            rpc = self._get_connection()
            
            # First check if UTXO is spent
            if not self.is_utxo_spent(txid, vout):
                return None
            
            # Method 1: Try gettxspendingprevout (Bitcoin Core 24.0+)
            # This works without a wallet and is the most efficient method
            try:
                prevout = {"txid": txid, "vout": vout}
                result = rpc.gettxspendingprevout([prevout])
                
                if result and len(result) > 0:
                    spent_info = result[0]
                    if 'spendingtxid' in spent_info and spent_info.get('spendingtxid'):
                        spending_txid = spent_info['spendingtxid']
                        logger.info(f"Found spending transaction using gettxspendingprevout: {spending_txid}")
                        return spending_txid
            except JSONRPCException as e:
                logger.debug(f"gettxspendingprevout not available: {e}")
            
            # Method 2: Try getspentinfo (requires spentindex=1)
            try:
                spent_info = rpc.getspentinfo({"txid": txid, "index": vout})
                if spent_info and 'txid' in spent_info:
                    spending_txid = spent_info['txid']
                    logger.info(f"Found spending transaction using getspentinfo: {spending_txid}")
                    return spending_txid
            except JSONRPCException as e:
                logger.debug(f"getspentinfo not available: {e}")
            
            # Method 3: Try listreceivedbyaddress (requires wallet)
            # Get the original transaction to find the address
            tx = self.get_transaction(txid)
            if not tx or vout >= len(tx['vout']):
                logger.warning(f"Could not get transaction {txid} or vout {vout} out of range")
                return None
            
            # Get the scriptPubKey and address
            vout_data = tx['vout'][vout]
            # Try both 'addresses' (legacy) and 'address' (newer format)
            addresses = vout_data['scriptPubKey'].get('addresses', [])
            if not addresses and 'address' in vout_data['scriptPubKey']:
                addresses = [vout_data['scriptPubKey']['address']]
            
            if not addresses:
                logger.warning(f"No address found for UTXO {txid}:{vout}, cannot use wallet-based search")
                return None
            
            address = addresses[0]
            
            try:
                # This requires a loaded wallet
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
                                            logger.info(f"Found spending transaction using listreceivedbyaddress: {spending_txid}")
                                            return spending_txid
            except JSONRPCException as e:
                logger.debug(f"listreceivedbyaddress not available (likely no wallet loaded): {e}")
            
            logger.warning(f"Could not find spending transaction for {txid}:{vout} using any available method")
            logger.warning(f"Consider enabling spentindex=1 in Bitcoin Core or use a block explorer")
            return None
            
        except JSONRPCException as e:
            logger.error(f"Error finding spending transaction for {txid}:{vout}: {e}")
            return None


# Global instance
bitcoin_rpc = BitcoinRPCClient()

