from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class BitcoinRPCClient:
    """Bitcoin Core RPC client for UTXO validation and transaction monitoring"""
    
    def __init__(self):
        self.connection = None
    
    def _get_connection(self):
        """Get or create RPC connection"""
        if self.connection is None:
            rpc_user = current_app.config['BITCOIN_RPC_USER']
            rpc_password = current_app.config['BITCOIN_RPC_PASSWORD']
            rpc_host = current_app.config['BITCOIN_RPC_HOST']
            rpc_port = current_app.config['BITCOIN_RPC_PORT']
            
            rpc_url = f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            self.connection = AuthServiceProxy(rpc_url)
        
        return self.connection
    
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
            rpc = self._get_connection()
            
            # Get transaction output
            result = rpc.gettxout(txid, vout)
            
            if result is None:
                # UTXO doesn't exist or is spent
                return None
            
            return {
                'txid': txid,
                'vout': vout,
                'value': result['value'],
                'scriptPubKey': result['scriptPubKey'],
                'confirmations': result.get('confirmations', 0)
            }
        except JSONRPCException as e:
            logger.error(f"Error getting UTXO {txid}:{vout}: {e}")
            raise Exception(f"Failed to get UTXO: {str(e)}")
    
    def is_utxo_spent(self, txid, vout):
        """
        Check if a UTXO is spent
        Returns True if spent, False if unspent
        """
        utxo = self.get_utxo(txid, vout)
        return utxo is None
    
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

