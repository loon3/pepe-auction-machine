from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from app import db
from app.models import Auction, PSBT
from app.bitcoin_rpc import bitcoin_rpc
import logging

logger = logging.getLogger(__name__)


class AuctionMonitor:
    """Background monitoring services for auctions"""
    
    def __init__(self, app=None):
        self.scheduler = None
        self.app = app
        
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
    
    def stop(self):
        """Stop the background monitoring tasks"""
        if self.scheduler is not None:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("Auction monitoring stopped")
    
    def _block_monitor_job(self):
        """
        Monitor blockchain height and update auction statuses
        Updates: upcoming → active, active → finished
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
                
                # Update active auctions to finished if past end_block
                active_auctions = Auction.query.filter_by(status='active').all()
                for auction in active_auctions:
                    if current_block > auction.end_block:
                        try:
                            # Check if UTXO is still unspent
                            if not bitcoin_rpc.is_utxo_spent(auction.utxo_txid, auction.utxo_vout):
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
        - If spent via PSBT → status = 'sold', set purchase_txid
        - Otherwise → status = 'closed', set closed_txid
        
        Note: Expired auctions are not checked (cleanup window passed, auction completely over)
        """
        with self.app.app_context():
            try:
                # Get all auctions that could have their UTXO spent
                # Exclude 'expired' - no need to monitor once cleanup window has passed
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
                                # Note: This is a simplified check. In production, you might want to
                                # decode the spending transaction and verify it matches the PSBT structure
                                is_psbt_purchase = self._check_if_psbt_purchase(auction, spending_txid)
                                
                                if is_psbt_purchase:
                                    auction.status = 'sold'
                                    auction.purchase_txid = spending_txid
                                    logger.info(f"Auction {auction.id} sold via PSBT, txid: {spending_txid}")
                                else:
                                    auction.status = 'closed'
                                    auction.closed_txid = spending_txid
                                    logger.info(f"Auction {auction.id} closed (not via PSBT), txid: {spending_txid}")
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
        
        This is a simplified implementation. In a production system, you would:
        1. Get the spending transaction details
        2. Extract the output values
        3. Compare with PSBT prices to determine if it matches
        
        For now, we'll do basic validation that the transaction exists
        """
        try:
            spending_tx = bitcoin_rpc.get_transaction(spending_txid)
            
            if not spending_tx:
                return False
            
            # Get all PSBT prices for this auction
            psbt_prices = [psbt.price_sats for psbt in auction.psbts]
            
            # Check outputs to see if any match our expected prices
            # Note: This is simplified - you'd want to check specific output indices
            for vout in spending_tx.get('vout', []):
                # Convert BTC to satoshis
                value_sats = int(vout.get('value', 0) * 100000000)
                
                if value_sats in psbt_prices:
                    logger.info(f"Found matching PSBT price: {value_sats} sats")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if PSBT purchase: {str(e)}")
            return False


# Global instance
auction_monitor = AuctionMonitor()

