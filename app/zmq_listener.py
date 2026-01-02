"""
Bitcoin Core ZMQ Listener

Provides real-time notifications for new blocks and transactions from Bitcoin Core.
Works alongside the polling-based monitors as the primary notification mechanism,
with polling serving as a fallback for missed ZMQ messages.

ZMQ Topics:
- rawblock (port 9333): Full serialized block data - triggers block monitor
- rawtx (port 9332): Full serialized transaction - checks for UTXO spends
"""

import zmq
import threading
import logging
from typing import Callable, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class BitcoinZMQListener:
    """
    Listens to Bitcoin Core ZMQ notifications for real-time updates.
    Triggers callbacks on new blocks and transactions.
    """
    
    def __init__(self, app=None):
        self.app = app
        self.context: Optional[zmq.Context] = None
        self.running = False
        self.threads: list = []
        
        # Callbacks
        self.on_new_block: Optional[Callable] = None
        self.on_new_tx: Optional[Callable[[bytes], None]] = None
        
        # Track monitored UTXOs for efficient tx filtering
        self._monitored_utxos: Set[Tuple[str, int]] = set()
        self._utxo_lock = threading.Lock()
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
    
    def update_monitored_utxos(self, utxos: Set[Tuple[str, int]]):
        """
        Update the set of UTXOs we're watching for spends.
        Called by monitors when auction list changes.
        
        Args:
            utxos: Set of (txid, vout) tuples to monitor
        """
        with self._utxo_lock:
            self._monitored_utxos = utxos
            logger.debug(f"ZMQ: Updated monitored UTXOs, now watching {len(utxos)}")
    
    def start(self, on_new_block: Callable, on_new_tx: Callable[[bytes], None]):
        """
        Start listening for ZMQ notifications.
        
        Args:
            on_new_block: Callback when new block is received
            on_new_tx: Callback with raw tx bytes when new transaction is received
        """
        if not self.app.config.get('ZMQ_ENABLED', True):
            logger.info("ZMQ notifications disabled via config")
            return
        
        self.on_new_block = on_new_block
        self.on_new_tx = on_new_tx
        self.running = True
        self.context = zmq.Context()
        
        # Start block listener thread
        block_thread = threading.Thread(
            target=self._listen_blocks,
            name="zmq-block-listener",
            daemon=True
        )
        block_thread.start()
        self.threads.append(block_thread)
        
        # Start transaction listener thread
        tx_thread = threading.Thread(
            target=self._listen_transactions,
            name="zmq-tx-listener",
            daemon=True
        )
        tx_thread.start()
        self.threads.append(tx_thread)
        
        logger.info("ZMQ listeners started")
    
    def _listen_blocks(self):
        """Listen for new blocks on rawblock topic"""
        block_url = self.app.config.get('ZMQ_BLOCK_URL', 'tcp://bitcoind:9333')
        
        try:
            socket = self.context.socket(zmq.SUB)
            socket.connect(block_url)
            socket.setsockopt_string(zmq.SUBSCRIBE, "rawblock")
            socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout for graceful shutdown
            
            logger.info(f"ZMQ: Subscribed to rawblock at {block_url}")
            
            while self.running:
                try:
                    msg = socket.recv_multipart()
                    if len(msg) >= 2:
                        topic = msg[0].decode('utf-8') if isinstance(msg[0], bytes) else msg[0]
                        # msg[1] contains raw block data
                        # msg[2] contains sequence number (if present)
                        seq = msg[2].hex() if len(msg) > 2 else "unknown"
                        
                        logger.info(f"ZMQ: New block received (seq: {seq})")
                        
                        if self.on_new_block:
                            try:
                                self.on_new_block()
                            except Exception as e:
                                logger.error(f"ZMQ: Error in block callback: {e}")
                        
                except zmq.Again:
                    continue  # Timeout, check if still running
                except zmq.ZMQError as e:
                    if self.running:
                        logger.error(f"ZMQ: Error receiving block: {e}")
                    break
                except Exception as e:
                    logger.error(f"ZMQ: Unexpected error in block listener: {e}")
                    
        except zmq.ZMQError as e:
            logger.error(f"ZMQ: Failed to connect to block socket at {block_url}: {e}")
        except Exception as e:
            logger.error(f"ZMQ: Failed to start block listener: {e}")
        finally:
            logger.info("ZMQ: Block listener stopped")
    
    def _listen_transactions(self):
        """Listen for new transactions on rawtx topic"""
        tx_url = self.app.config.get('ZMQ_TX_URL', 'tcp://bitcoind:9332')
        
        try:
            socket = self.context.socket(zmq.SUB)
            socket.connect(tx_url)
            socket.setsockopt_string(zmq.SUBSCRIBE, "rawtx")
            socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout
            
            logger.info(f"ZMQ: Subscribed to rawtx at {tx_url}")
            
            while self.running:
                try:
                    msg = socket.recv_multipart()
                    if len(msg) >= 2:
                        # msg[1] contains raw transaction data
                        raw_tx = msg[1]
                        
                        if self.on_new_tx:
                            try:
                                self.on_new_tx(raw_tx)
                            except Exception as e:
                                logger.error(f"ZMQ: Error in tx callback: {e}")
                        
                except zmq.Again:
                    continue  # Timeout, check if still running
                except zmq.ZMQError as e:
                    if self.running:
                        logger.error(f"ZMQ: Error receiving tx: {e}")
                    break
                except Exception as e:
                    logger.error(f"ZMQ: Unexpected error in tx listener: {e}")
                    
        except zmq.ZMQError as e:
            logger.error(f"ZMQ: Failed to connect to tx socket at {tx_url}: {e}")
        except Exception as e:
            logger.error(f"ZMQ: Failed to start tx listener: {e}")
        finally:
            logger.info("ZMQ: Transaction listener stopped")
    
    def stop(self):
        """Stop all listeners gracefully"""
        logger.info("ZMQ: Stopping listeners...")
        self.running = False
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2)
        
        # Cleanup ZMQ context
        if self.context:
            try:
                self.context.term()
            except Exception as e:
                logger.warning(f"ZMQ: Error terminating context: {e}")
        
        self.threads = []
        logger.info("ZMQ: Listeners stopped")


# Global instance
zmq_listener = BitcoinZMQListener()
