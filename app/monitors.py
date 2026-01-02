from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from app import db
from app.models import Auction, PSBT
from app.bitcoin_rpc import bitcoin_rpc
import logging
import threading
from typing import Set, Tuple

logger = logging.getLogger(__name__)


class AuctionMonitor:
    """
    Background monitoring services for auctions.
    
    Supports two notification mechanisms:
    1. ZMQ (primary): Real-time push notifications from Bitcoin Core
    2. Polling (fallback): Periodic checks every 5 minutes
    
    ZMQ triggers immediate checks, polling catches any missed events.
    """
    
    def __init__(self, app=None):
        self.scheduler = None
        self.app = app
        self._check_lock = threading.Lock()  # Prevent concurrent monitor runs
        
    def init_app(self, app):
        """Initialize monitoring with Flask app"""
        self.app = app
        
    def start(self):
        """Start the background monitoring tasks"""
        if self.scheduler is not None:
            logger.warning("Scheduler already running")
            return
        
        self.scheduler = BackgroundScheduler()
        
        # Add block monitoring job
        self.scheduler.add_job(
            func=self._block_monitor_job,
            trigger='interval',
            seconds=self.app.config['BLOCK_MONITOR_INTERVAL'],
            id='block_monitor',
            name='Monitor blockchain height and update auction statuses',
            replace_existing=True
        )
        
        # Add UTXO monitoring job
        self.scheduler.add_job(
            func=self._utxo_monitor_job,
            trigger='interval',
            seconds=self.app.config['UTXO_MONITOR_INTERVAL'],
            id='utxo_monitor',
            name='Monitor UTXO spends and update auction statuses',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Auction monitoring started")
        
        # Run initial checks immediately on startup
        # This catches any changes that happened while server was down
        logger.info("Running initial monitor checks on startup...")
        try:
            self._block_monitor_job()
            logger.info("✓ Initial block monitor check completed")
        except Exception as e:
            logger.error(f"Initial block monitor check failed: {str(e)}")
        
        try:
            self._utxo_monitor_job()
            logger.info("✓ Initial UTXO monitor check completed")
        except Exception as e:
            logger.error(f"Initial UTXO monitor check failed: {str(e)}")
        
        logger.info("Initial monitor checks completed")
    
    # =========================================================================
    # ZMQ Trigger Methods - Called by zmq_listener for real-time notifications
    # =========================================================================
    
    def trigger_block_check(self):
        """
        Trigger immediate block check (called by ZMQ on new block).
        Uses lock to prevent concurrent runs with scheduled polling.
        """
        if not self._check_lock.acquire(blocking=False):
            logger.debug("ZMQ: Block check already in progress, skipping")
            return
        
        try:
            logger.info("ZMQ: Triggering immediate block check")
            self._block_monitor_job()
        finally:
            self._check_lock.release()
    
    def trigger_utxo_check(self):
        """
        Trigger immediate UTXO check (called by ZMQ when relevant tx detected).
        Uses lock to prevent concurrent runs with scheduled polling.
        """
        if not self._check_lock.acquire(blocking=False):
            logger.debug("ZMQ: UTXO check already in progress, skipping")
            return
        
        try:
            logger.info("ZMQ: Triggering immediate UTXO check")
            self._utxo_monitor_job()
        finally:
            self._check_lock.release()
    
    def check_transaction_for_utxos(self, raw_tx: bytes):
        """
        Check if a raw transaction spends any of our monitored UTXOs.
        Called by ZMQ listener for every new transaction.
        
        If a monitored UTXO is spent, triggers immediate UTXO check.
        
        Args:
            raw_tx: Raw transaction bytes from ZMQ
        """
        try:
            # Parse transaction inputs from raw bytes
            inputs = self._parse_tx_inputs(raw_tx)
            
            if not inputs:
                return
            
            # Get currently monitored UTXOs
            monitored = self.get_monitored_utxos()
            
            if not monitored:
                return
            
            # Check if any input matches our monitored UTXOs
            for txid, vout in inputs:
                if (txid, vout) in monitored:
                    logger.info(f"ZMQ: Detected spend of monitored UTXO {txid}:{vout}")
                    self.trigger_utxo_check()
                    return  # Only need to trigger once
                    
        except Exception as e:
            logger.debug(f"ZMQ: Error parsing transaction: {e}")
    
    def get_monitored_utxos(self) -> Set[Tuple[str, int]]:
        """
        Get the set of UTXOs currently being monitored.
        
        Returns:
            Set of (txid, vout) tuples for active auctions
        """
        with self.app.app_context():
            try:
                auctions = Auction.query.filter(
                    Auction.status.in_(['upcoming', 'active', 'finished'])
                ).with_entities(Auction.utxo_txid, Auction.utxo_vout).all()
                
                return {(a.utxo_txid, a.utxo_vout) for a in auctions}
            except Exception as e:
                logger.error(f"Error getting monitored UTXOs: {e}")
                return set()
    
    def _parse_tx_inputs(self, raw_tx: bytes) -> list:
        """
        Parse transaction inputs from raw transaction bytes.
        
        Bitcoin transaction format:
        - 4 bytes: version
        - varint: input count
        - inputs: each with 32-byte txid (reversed) + 4-byte vout + script + sequence
        
        Returns:
            List of (txid, vout) tuples
        """
        try:
            inputs = []
            pos = 0
            
            # Skip version (4 bytes)
            pos += 4
            
            # Check for segwit marker
            if len(raw_tx) > pos + 2 and raw_tx[pos] == 0x00 and raw_tx[pos + 1] == 0x01:
                # Segwit transaction - skip marker and flag
                pos += 2
            
            # Read input count (varint)
            input_count, varint_size = self._read_varint(raw_tx, pos)
            pos += varint_size
            
            # Parse each input
            for _ in range(input_count):
                if pos + 36 > len(raw_tx):
                    break
                
                # Read txid (32 bytes, reversed for display)
                txid_bytes = raw_tx[pos:pos + 32]
                txid = txid_bytes[::-1].hex()  # Reverse byte order
                pos += 32
                
                # Read vout (4 bytes, little-endian)
                vout = int.from_bytes(raw_tx[pos:pos + 4], 'little')
                pos += 4
                
                # Skip script (varint length + script bytes)
                script_len, varint_size = self._read_varint(raw_tx, pos)
                pos += varint_size + script_len
                
                # Skip sequence (4 bytes)
                pos += 4
                
                # Skip coinbase inputs (txid all zeros)
                if txid != '0' * 64:
                    inputs.append((txid, vout))
            
            return inputs
            
        except Exception as e:
            logger.debug(f"Error parsing tx inputs: {e}")
            return []
    
    def _read_varint(self, data: bytes, pos: int) -> tuple:
        """
        Read a Bitcoin varint from data at position.
        
        Returns:
            Tuple of (value, bytes_read)
        """
        if pos >= len(data):
            return 0, 0
        
        first_byte = data[pos]
        
        if first_byte < 0xFD:
            return first_byte, 1
        elif first_byte == 0xFD:
            return int.from_bytes(data[pos + 1:pos + 3], 'little'), 3
        elif first_byte == 0xFE:
            return int.from_bytes(data[pos + 1:pos + 5], 'little'), 5
        else:
            return int.from_bytes(data[pos + 1:pos + 9], 'little'), 9
    
    # =========================================================================
    # End ZMQ Trigger Methods
    # =========================================================================
    
    def stop(self):
        """Stop the background monitoring tasks"""
        if self.scheduler is not None:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("Auction monitoring stopped")
    
    def _block_monitor_job(self):
        """
        Monitor blockchain height and update auction statuses
        Updates: upcoming → active, active → finished/expired
        
        After processing block changes, runs backfill job to populate spent_block/spent_at
        for any transactions that have now been confirmed.
        """
        with self.app.app_context():
            try:
                current_block = bitcoin_rpc.get_current_block_height()
                logger.info(f"Block monitor: current block {current_block}")
                
                # Update upcoming auctions to active
                upcoming_auctions = Auction.query.filter_by(status='upcoming').all()
                for auction in upcoming_auctions:
                    if current_block >= auction.start_block:
                        try:
                            # Check if UTXO is still unspent
                            if not bitcoin_rpc.is_utxo_spent(auction.utxo_txid, auction.utxo_vout):
                                auction.status = 'active'
                                logger.info(f"Auction {auction.id} status updated: upcoming → active")
                            else:
                                # UTXO was spent before auction started
                                auction.status = 'closed'
                                logger.warning(f"Auction {auction.id} UTXO spent before start, marking as closed")
                        except Exception as e:
                            # Skip this auction if we can't check the UTXO (e.g., unconfirmed transaction)
                            if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                                logger.debug(f"Auction {auction.id} UTXO not yet confirmed, skipping status update")
                            else:
                                logger.error(f"Error checking auction {auction.id} UTXO: {str(e)}")
                            continue
                
                # Update active auctions to finished/expired if past end_block
                active_auctions = Auction.query.filter_by(status='active').all()
                for auction in active_auctions:
                    if current_block > auction.end_block:
                        try:
                            # Check if UTXO is still unspent
                            if not bitcoin_rpc.is_utxo_spent(auction.utxo_txid, auction.utxo_vout):
                                # If blocks_after_end is 0, go straight to expired
                                if auction.blocks_after_end == 0:
                                    auction.status = 'expired'
                                    logger.info(f"Auction {auction.id} status updated: active → expired (no cleanup window)")
                                else:
                                    auction.status = 'finished'
                                    logger.info(f"Auction {auction.id} status updated: active → finished")
                            # If spent, UTXO monitor will handle it
                        except Exception as e:
                            if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                                logger.debug(f"Auction {auction.id} UTXO not yet confirmed, skipping status update")
                            else:
                                logger.error(f"Error checking auction {auction.id} UTXO: {str(e)}")
                            continue
                
                # Update finished auctions to expired if past cleanup window
                finished_auctions = Auction.query.filter_by(status='finished').all()
                for auction in finished_auctions:
                    if current_block >= auction.end_block + auction.blocks_after_end:
                        try:
                            # Check if UTXO is still unspent (should be, but verify)
                            if not bitcoin_rpc.is_utxo_spent(auction.utxo_txid, auction.utxo_vout):
                                auction.status = 'expired'
                                logger.info(f"Auction {auction.id} status updated: finished → expired (cleanup window passed)")
                            # If spent, UTXO monitor will handle it
                        except Exception as e:
                            if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                                logger.debug(f"Auction {auction.id} UTXO not yet confirmed, skipping status update")
                            else:
                                logger.error(f"Error checking auction {auction.id} UTXO: {str(e)}")
                            continue
                
                db.session.commit()
                
                # Run backfill job after block changes
                # New blocks = new confirmations, perfect time to check
                self._backfill_unconfirmed_job()
                
            except Exception as e:
                db.session.rollback()
                # Only log as error if it's not a confirmation issue
                if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                    logger.debug(f"Bitcoin RPC not ready (unconfirmed transactions), skipping block monitor cycle")
                else:
                    logger.error(f"Error in block monitor: {str(e)}")
    
    def _utxo_monitor_job(self):
        """
        Monitor UTXO spends and update auction statuses (optimized with batch checking)
        For active/upcoming/finished auctions, check if UTXO is spent:
        - If spent via PSBT → status = 'sold', set spent_txid and recipient
        - Otherwise → status = 'closed', set spent_txid and recipient
        
        Optimization: Only monitors auctions that could potentially change:
        - 'upcoming', 'active', 'finished' = monitored (UTXO not yet spent or still relevant)
        - 'sold', 'closed', 'expired' = NOT monitored (terminal states, no updates needed)
        
        This automatically reduces monitoring load as auctions complete.
        """
        with self.app.app_context():
            try:
                # Get all auctions that could have their UTXO spent
                # Excludes terminal states: 'sold', 'closed', 'expired'
                # Once an auction reaches a terminal state, it's automatically removed from monitoring
                auctions_to_check = Auction.query.filter(
                    Auction.status.in_(['upcoming', 'active', 'finished'])
                ).all()
                
                if not auctions_to_check:
                    logger.info("UTXO monitor: no auctions to check")
                    return
                
                logger.info(f"UTXO monitor: checking {len(auctions_to_check)} auctions (excluding expired)")
                
                # Collect all UTXOs to check in batch
                utxo_list = []
                auction_map = {}  # Map (txid, vout) -> auction object
                
                for auction in auctions_to_check:
                    utxo_key = (auction.utxo_txid, auction.utxo_vout)
                    utxo_list.append(utxo_key)
                    auction_map[utxo_key] = auction
                
                # Batch check all UTXOs
                try:
                    spent_status = bitcoin_rpc.check_utxos_batch(utxo_list)
                    logger.info(f"Batch checked {len(spent_status)} UTXOs")
                except Exception as e:
                    logger.error(f"Batch UTXO check failed: {str(e)}")
                    # If batch check fails, skip this monitor cycle
                    if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                        logger.debug("Skipping monitor cycle due to unconfirmed transactions")
                    return
                
                # Process results
                for utxo_key, is_spent in spent_status.items():
                    auction = auction_map.get(utxo_key)
                    if not auction:
                        continue
                    
                    if is_spent:
                        logger.info(f"Auction {auction.id} UTXO is spent, investigating...")
                        
                        try:
                            # Try to find the spending transaction
                            spending_txid = bitcoin_rpc.find_spending_transaction(
                                auction.utxo_txid,
                                auction.utxo_vout
                            )
                            
                            if spending_txid:
                                # Check if this matches any of our PSBTs
                                is_psbt_purchase = self._check_if_psbt_purchase(auction, spending_txid)
                                
                                # Get transaction details (block height, timestamp, recipient)
                                tx_details = bitcoin_rpc.get_transaction_details(spending_txid)
                                recipient = bitcoin_rpc.get_recipient_address(spending_txid)
                                
                                # Extract details
                                spent_block = tx_details.get('block_height') if tx_details else None
                                spent_at = tx_details.get('timestamp') if tx_details else None
                                
                                if is_psbt_purchase:
                                    auction.status = 'sold'
                                    auction.spent_txid = spending_txid
                                    auction.spent_block = spent_block
                                    auction.spent_at = spent_at
                                    auction.recipient = recipient
                                    logger.info(f"Auction {auction.id} sold via PSBT, txid: {spending_txid}, block: {spent_block}, recipient: {recipient}")
                                else:
                                    auction.status = 'closed'
                                    auction.spent_txid = spending_txid
                                    auction.spent_block = spent_block
                                    auction.spent_at = spent_at
                                    auction.recipient = recipient
                                    logger.info(f"Auction {auction.id} closed (not via PSBT), txid: {spending_txid}, block: {spent_block}, recipient: {recipient}")
                            else:
                                # Can't determine spending transaction, mark as closed
                                auction.status = 'closed'
                                logger.warning(f"Auction {auction.id} UTXO spent but can't find spending tx, marking as closed")
                        
                        except Exception as e:
                            logger.error(f"Error investigating spent UTXO for auction {auction.id}: {str(e)}")
                            continue
                
                db.session.commit()
                logger.info("UTXO monitor cycle completed")
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error in UTXO monitor: {str(e)}")
    
    def _check_if_psbt_purchase(self, auction, spending_txid):
        """
        Check if a spending transaction matches one of the auction's PSBTs
        
        Validates that:
        1. The transaction exists and is confirmed
        2. The transaction spends the auction UTXO as an input
        3. One of the outputs matches a PSBT price (payment to seller)
        
        Returns True if this is a valid PSBT purchase, False otherwise
        """
        try:
            spending_tx = bitcoin_rpc.get_transaction(spending_txid)
            
            if not spending_tx:
                logger.warning(f"Auction {auction.id}: Could not get spending transaction {spending_txid}")
                return False
            
            # Verify that this transaction actually spends our auction UTXO
            spends_auction_utxo = False
            for vin in spending_tx.get('vin', []):
                if vin.get('txid') == auction.utxo_txid and vin.get('vout') == auction.utxo_vout:
                    spends_auction_utxo = True
                    break
            
            if not spends_auction_utxo:
                logger.warning(f"Auction {auction.id}: Transaction {spending_txid} does not spend auction UTXO {auction.utxo_txid}:{auction.utxo_vout}")
                return False
            
            logger.info(f"Auction {auction.id}: Transaction {spending_txid} spends auction UTXO, checking outputs...")
            
            # Get all PSBT prices for this auction
            psbt_prices = set([psbt.price_sats for psbt in auction.psbts])
            logger.info(f"Auction {auction.id}: Expected PSBT prices: {sorted(psbt_prices)}")
            
            # Check outputs to see if any match our expected prices
            # Use proper decimal conversion to avoid floating-point rounding errors
            from decimal import Decimal, ROUND_HALF_UP
            
            matched_outputs = []
            for idx, vout in enumerate(spending_tx.get('vout', [])):
                # Convert BTC to satoshis using Decimal for precision
                btc_value = Decimal(str(vout.get('value', 0)))
                value_sats = int((btc_value * Decimal('100000000')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                
                logger.debug(f"Auction {auction.id}: Output {idx} value: {value_sats} sats (BTC: {btc_value})")
                
                if value_sats in psbt_prices:
                    matched_outputs.append((idx, value_sats))
                    logger.info(f"Auction {auction.id}: Found matching PSBT price in output {idx}: {value_sats} sats")
            
            if matched_outputs:
                logger.info(f"Auction {auction.id}: Transaction is a valid PSBT purchase (matched outputs: {matched_outputs})")
                return True
            
            logger.info(f"Auction {auction.id}: No matching PSBT prices found in transaction outputs")
            return False
            
        except Exception as e:
            logger.error(f"Auction {auction.id}: Error checking if PSBT purchase: {str(e)}", exc_info=True)
            return False
    
    def _backfill_unconfirmed_job(self):
        """
        Backfill spent_block and spent_at for auctions with initially unconfirmed transactions
        
        When a transaction is detected but not yet confirmed, the auction is marked as sold/closed
        but spent_block and spent_at are NULL. This job checks for such auctions and populates
        the fields once the transaction is confirmed.
        
        Called by block monitor on each new block (when confirmations happen).
        """
        with self.app.app_context():
            try:
                # Find sold/closed auctions with spent_txid but missing block/timestamp data
                auctions_to_check = Auction.query.filter(
                    Auction.status.in_(['sold', 'closed']),
                    Auction.spent_txid.isnot(None),
                    db.or_(
                        Auction.spent_block.is_(None),
                        Auction.spent_at.is_(None)
                    )
                ).all()
                
                if not auctions_to_check:
                    logger.debug("Backfill: No auctions with missing block/timestamp data")
                    return
                
                logger.info(f"Backfill: Checking {len(auctions_to_check)} auction(s) with unconfirmed transactions")
                
                updated_count = 0
                still_unconfirmed_count = 0
                
                for auction in auctions_to_check:
                    try:
                        # Get transaction details
                        tx_details = bitcoin_rpc.get_transaction_details(auction.spent_txid)
                        
                        if tx_details:
                            block_height = tx_details.get('block_height')
                            timestamp = tx_details.get('timestamp')
                            
                            if block_height or timestamp:
                                # Transaction is now confirmed!
                                logger.info(f"Backfill: Auction {auction.id} transaction confirmed (block {block_height})")
                                
                                if block_height and not auction.spent_block:
                                    auction.spent_block = block_height
                                if timestamp and not auction.spent_at:
                                    auction.spent_at = timestamp
                                
                                updated_count += 1
                            else:
                                logger.debug(f"Backfill: Auction {auction.id} transaction still unconfirmed")
                                still_unconfirmed_count += 1
                        else:
                            # Transaction not confirmed yet
                            logger.debug(f"Backfill: Auction {auction.id} transaction still unconfirmed")
                            still_unconfirmed_count += 1
                            
                    except Exception as e:
                        if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                            logger.debug(f"Backfill: Auction {auction.id} transaction not yet confirmed")
                            still_unconfirmed_count += 1
                        else:
                            logger.error(f"Backfill: Error processing auction {auction.id}: {str(e)}")
                
                if updated_count > 0:
                    db.session.commit()
                    logger.info(f"Backfill: Updated {updated_count} auction(s) with confirmed transaction data")
                
                if still_unconfirmed_count > 0:
                    logger.debug(f"Backfill: {still_unconfirmed_count} auction(s) still waiting for confirmation")
                
            except Exception as e:
                db.session.rollback()
                if "not yet confirmed" in str(e) or "Request-sent" in str(e):
                    logger.debug("Backfill: Skipping cycle due to unconfirmed transactions")
                else:
                    logger.error(f"Backfill: Error in backfill job: {str(e)}")


# Global instance
auction_monitor = AuctionMonitor()

