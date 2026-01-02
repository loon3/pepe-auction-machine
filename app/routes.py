from flask import Blueprint, request, jsonify, current_app
from functools import wraps
from app import db
from app.models import Auction, PSBT
from app.validators import validate_auction_submission, ValidationError
from app.bitcoin_rpc import bitcoin_rpc
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')


def require_api_key(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        if api_key != current_app.config['API_KEY']:
            return jsonify({'error': 'Invalid API key'}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


@bp.route('/listings', methods=['POST'])
@require_api_key
def create_listing():
    """
    Create a new listing
    
    This is an alias for /api/auctions POST endpoint that accepts the same parameters.
    
    Required JSON fields:
    - asset_name: string
    - asset_qty: integer
    - utxo_txid: string
    - utxo_vout: integer
    - start_block: integer
    - end_block: integer
    - start_price_sats: integer (highest price)
    - end_price_sats: integer (lowest price)
    - price_decrement: integer (price decrease per block)
    - blocks_after_end: integer
    - psbts: list of {block_number, price_sats, psbt_data}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate the submission
        try:
            validated_data = validate_auction_submission(data)
        except ValidationError as e:
            logger.warning(f"Validation failed: {str(e)}")
            return jsonify({'error': str(e)}), 400
        
        # Check if an active/relevant auction already exists for this UTXO
        # Only block if there's an auction that isn't finished (expired, sold, closed are OK to replace)
        existing_active_auction = Auction.query.filter_by(
            utxo_txid=validated_data['utxo_txid'],
            utxo_vout=validated_data['utxo_vout']
        ).filter(
            Auction.status.in_(['upcoming', 'active', 'finished'])
        ).first()
        
        if existing_active_auction:
            return jsonify({
                'error': f"Active listing already exists for UTXO {validated_data['utxo_txid']}:{validated_data['utxo_vout']} with status '{existing_active_auction.status}'. Wait for it to expire before creating a new listing."
            }), 409
        
        # Create auction
        auction = Auction(
            asset_name=validated_data['asset_name'],
            asset_qty=validated_data['asset_qty'],
            utxo_txid=validated_data['utxo_txid'],
            utxo_vout=validated_data['utxo_vout'],
            start_block=validated_data['start_block'],
            end_block=validated_data['end_block'],
            start_price_sats=validated_data['start_price_sats'],
            end_price_sats=validated_data['end_price_sats'],
            price_decrement=validated_data['price_decrement'],
            blocks_after_end=validated_data['blocks_after_end'],
            seller=validated_data.get('seller'),  # Seller address extracted from PSBT
            status='upcoming'
        )
        
        db.session.add(auction)
        db.session.flush()  # Get auction ID
        
        # Create PSBTs
        for psbt_data in validated_data['psbts']:
            psbt = PSBT(
                auction_id=auction.id,
                block_number=psbt_data['block_number'],
                price_sats=psbt_data['price_sats'],
                psbt_data=psbt_data['psbt_data']
            )
            db.session.add(psbt)
        
        db.session.commit()
        
        logger.info(f"Created listing {auction.id} for {auction.asset_name}")
        
        return jsonify({
            'success': True,
            'listing_id': auction.id,
            'message': f'Listing created successfully',
            'listing': auction.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating listing: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/listings', methods=['GET'])
def list_listings():
    """
    List all listings with optional status filter
    
    Query params:
    - status: upcoming, active, sold, closed, finished, expired (can be comma-separated for multiple)
    
    This is an alias for /api/auctions that returns the same data
    """
    try:
        status_filter = request.args.get('status')
        
        query = Auction.query
        
        if status_filter:
            # Parse comma-separated statuses
            statuses = [s.strip() for s in status_filter.split(',')]
            valid_statuses = ['upcoming', 'active', 'sold', 'closed', 'finished', 'expired']
            
            # Validate all statuses
            invalid_statuses = [s for s in statuses if s not in valid_statuses]
            if invalid_statuses:
                return jsonify({'error': f'Invalid status filter(s): {", ".join(invalid_statuses)}'}), 400
            
            # Filter by multiple statuses using IN clause
            query = query.filter(Auction.status.in_(statuses))
        
        auctions = query.order_by(Auction.created_at.desc()).all()
        
        # Get current block height
        try:
            current_block = bitcoin_rpc.get_current_block_height()
        except Exception as e:
            logger.warning(f"Could not get current block height: {str(e)}")
            current_block = None
        
        # Build auction list with current PSBT data for active auctions
        auction_list = []
        for auction in auctions:
            auction_data = auction.to_dict()
            
            # Add current PSBT data and price based on auction status
            if current_block and auction.status == 'active':
                # Active: return PSBT for current block
                if current_block <= auction.end_block:
                    target_block = current_block
                else:
                    # Auction ended but still active (shouldn't happen, but be safe)
                    target_block = auction.end_block
                
                # Get the PSBT for the current block
                current_psbt = PSBT.query.filter_by(
                    auction_id=auction.id,
                    block_number=target_block
                ).first()
                
                if current_psbt:
                    auction_data['current_psbt_data'] = current_psbt.psbt_data
                    auction_data['current_price_sats'] = current_psbt.price_sats
                else:
                    auction_data['current_psbt_data'] = None
                    auction_data['current_price_sats'] = None
            elif auction.status == 'finished':
                # Finished: show the final (lowest) price PSBT
                # Buyers can still purchase during cleanup window
                final_psbt = PSBT.query.filter_by(
                    auction_id=auction.id,
                    block_number=auction.end_block
                ).first()
                
                if final_psbt:
                    auction_data['current_psbt_data'] = final_psbt.psbt_data
                    auction_data['current_price_sats'] = final_psbt.price_sats
                else:
                    auction_data['current_psbt_data'] = None
                    auction_data['current_price_sats'] = auction.end_price_sats
            elif auction.status == 'expired':
                # Expired: cleanup window passed, no PSBT
                auction_data['current_psbt_data'] = None
                auction_data['current_price_sats'] = auction.end_price_sats
            elif auction.status == 'upcoming':
                # For upcoming auctions, show the start price (no PSBT yet)
                auction_data['current_psbt_data'] = None
                auction_data['current_price_sats'] = auction.start_price_sats
            elif auction.status == 'sold':
                # For sold auctions, extract the actual sale price from the purchase transaction
                auction_data['current_psbt_data'] = None
                
                if auction.spent_txid:
                    try:
                        # Get the purchase transaction
                        purchase_tx = bitcoin_rpc.get_transaction(auction.spent_txid)
                        
                        if purchase_tx:
                            # Get all PSBT prices for comparison
                            from decimal import Decimal, ROUND_HALF_UP
                            psbt_prices = set([psbt.price_sats for psbt in auction.psbts])
                            
                            # Find which output matches a PSBT price
                            for vout in purchase_tx.get('vout', []):
                                btc_value = Decimal(str(vout.get('value', 0)))
                                value_sats = int((btc_value * Decimal('100000000')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                                
                                if value_sats in psbt_prices:
                                    auction_data['current_price_sats'] = value_sats
                                    break
                            
                            if not auction_data.get('current_price_sats'):
                                # Fallback: couldn't find matching PSBT price
                                auction_data['current_price_sats'] = None
                                logger.warning(f"Could not determine sale price for sold auction {auction.id}")
                        else:
                            auction_data['current_price_sats'] = None
                    except Exception as e:
                        logger.error(f"Error getting sale price for auction {auction.id}: {str(e)}")
                        auction_data['current_price_sats'] = None
                else:
                    auction_data['current_price_sats'] = None
            else:
                # For closed or other statuses
                auction_data['current_psbt_data'] = None
                auction_data['current_price_sats'] = None
            
            auction_list.append(auction_data)
        
        return jsonify({
            'success': True,
            'current_block': current_block,
            'count': len(auction_list),
            'listings': auction_list
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing listings: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/listings/<int:listing_id>', methods=['GET'])
def get_listing(listing_id):
    """
    Get listing details (metadata only, NO PSBTs)
    
    Security: Never returns PSBT data to prevent revealing future prices
    
    This is an alias for /api/auctions/<id> that returns the same data
    """
    try:
        auction = Auction.query.get(listing_id)
        
        if not auction:
            return jsonify({'error': 'Listing not found'}), 404
        
        return jsonify({
            'success': True,
            'listing': auction.to_dict(include_psbts=False)
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting listing {listing_id}: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/address/<address>', methods=['GET'])
def get_listings_by_address(address):
    """
    Get all listings where the address matches recipient or seller
    
    Query params:
    - status: upcoming, active, sold, closed, finished, expired (can be comma-separated for multiple)
    - role: buyer, seller (optional) - filter by address role
    
    Returns all listings where the provided address is either the seller or recipient
    """
    try:
        # Validate address format (basic check)
        if not address or len(address) < 10:
            return jsonify({'error': 'Invalid address format'}), 400
        
        status_filter = request.args.get('status')
        role_filter = request.args.get('role')
        
        # Validate role filter if provided
        if role_filter and role_filter not in ['buyer', 'seller']:
            return jsonify({'error': 'Invalid role filter. Must be "buyer" or "seller"'}), 400
        
        # Query for auctions where address matches seller or recipient based on role
        if role_filter == 'seller':
            # Only show listings where address is the seller
            query = Auction.query.filter(Auction.seller == address)
        elif role_filter == 'buyer':
            # Only show listings where address is the recipient (buyer)
            query = Auction.query.filter(Auction.recipient == address)
        else:
            # Show both - address matches seller or recipient
            query = Auction.query.filter(
                db.or_(
                    Auction.seller == address,
                    Auction.recipient == address
                )
            )
        
        if status_filter:
            # Parse comma-separated statuses
            statuses = [s.strip() for s in status_filter.split(',')]
            valid_statuses = ['upcoming', 'active', 'sold', 'closed', 'finished', 'expired']
            
            # Validate all statuses
            invalid_statuses = [s for s in statuses if s not in valid_statuses]
            if invalid_statuses:
                return jsonify({'error': f'Invalid status filter(s): {", ".join(invalid_statuses)}'}), 400
            
            # Filter by multiple statuses using IN clause
            query = query.filter(Auction.status.in_(statuses))
        
        auctions = query.order_by(Auction.created_at.desc()).all()
        
        # Get current block height
        try:
            current_block = bitcoin_rpc.get_current_block_height()
        except Exception as e:
            logger.warning(f"Could not get current block height: {str(e)}")
            current_block = None
        
        # Build auction list with current PSBT data for active auctions
        auction_list = []
        for auction in auctions:
            auction_data = auction.to_dict()
            
            # Add current PSBT data and price based on auction status
            if current_block and auction.status == 'active':
                # Active: return PSBT for current block
                if current_block <= auction.end_block:
                    target_block = current_block
                else:
                    # Auction ended but still active (shouldn't happen, but be safe)
                    target_block = auction.end_block
                
                # Get the PSBT for the current block
                current_psbt = PSBT.query.filter_by(
                    auction_id=auction.id,
                    block_number=target_block
                ).first()
                
                if current_psbt:
                    auction_data['current_psbt_data'] = current_psbt.psbt_data
                    auction_data['current_price_sats'] = current_psbt.price_sats
                else:
                    auction_data['current_psbt_data'] = None
                    auction_data['current_price_sats'] = None
            elif auction.status == 'finished':
                # Finished: show the final (lowest) price PSBT
                # Buyers can still purchase during cleanup window
                final_psbt = PSBT.query.filter_by(
                    auction_id=auction.id,
                    block_number=auction.end_block
                ).first()
                
                if final_psbt:
                    auction_data['current_psbt_data'] = final_psbt.psbt_data
                    auction_data['current_price_sats'] = final_psbt.price_sats
                else:
                    auction_data['current_psbt_data'] = None
                    auction_data['current_price_sats'] = auction.end_price_sats
            elif auction.status == 'expired':
                # Expired: cleanup window passed, no PSBT
                auction_data['current_psbt_data'] = None
                auction_data['current_price_sats'] = auction.end_price_sats
            elif auction.status == 'upcoming':
                # For upcoming auctions, show the start price (no PSBT yet)
                auction_data['current_psbt_data'] = None
                auction_data['current_price_sats'] = auction.start_price_sats
            elif auction.status == 'sold':
                # For sold auctions, extract the actual sale price from the purchase transaction
                auction_data['current_psbt_data'] = None
                
                if auction.spent_txid:
                    try:
                        # Get the purchase transaction
                        purchase_tx = bitcoin_rpc.get_transaction(auction.spent_txid)
                        
                        if purchase_tx:
                            # Get all PSBT prices for comparison
                            from decimal import Decimal, ROUND_HALF_UP
                            psbt_prices = set([psbt.price_sats for psbt in auction.psbts])
                            
                            # Find which output matches a PSBT price
                            for vout in purchase_tx.get('vout', []):
                                btc_value = Decimal(str(vout.get('value', 0)))
                                value_sats = int((btc_value * Decimal('100000000')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                                
                                if value_sats in psbt_prices:
                                    auction_data['current_price_sats'] = value_sats
                                    break
                            
                            if not auction_data.get('current_price_sats'):
                                # Fallback: couldn't find matching PSBT price
                                auction_data['current_price_sats'] = None
                                logger.warning(f"Could not determine sale price for sold auction {auction.id}")
                        else:
                            auction_data['current_price_sats'] = None
                    except Exception as e:
                        logger.error(f"Error getting sale price for auction {auction.id}: {str(e)}")
                        auction_data['current_price_sats'] = None
                else:
                    auction_data['current_price_sats'] = None
            else:
                # For closed or other statuses
                auction_data['current_psbt_data'] = None
                auction_data['current_price_sats'] = None
            
            auction_list.append(auction_data)
        
        response_data = {
            'success': True,
            'address': address,
            'current_block': current_block,
            'count': len(auction_list),
            'listings': auction_list
        }
        
        # Add role filter to response if provided
        if role_filter:
            response_data['role'] = role_filter
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error getting listings for address {address}: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check Bitcoin RPC connection
        try:
            block_height = bitcoin_rpc.get_current_block_height()
            bitcoin_status = 'connected'
        except Exception as e:
            block_height = None
            bitcoin_status = f'error: {str(e)}'
        
        return jsonify({
            'status': 'healthy',
            'bitcoin_rpc': bitcoin_status,
            'current_block': block_height
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

