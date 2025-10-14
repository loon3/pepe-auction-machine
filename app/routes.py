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


@bp.route('/auctions', methods=['POST'])
@require_api_key
def create_auction():
    """
    Create a new auction
    
    Required JSON fields:
    - asset_name: string
    - asset_qty: integer
    - utxo_txid: string
    - utxo_vout: integer
    - start_block: integer
    - end_block: integer
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
        
        # Check if auction already exists for this UTXO
        existing_auction = Auction.query.filter_by(
            utxo_txid=validated_data['utxo_txid'],
            utxo_vout=validated_data['utxo_vout']
        ).first()
        
        if existing_auction:
            return jsonify({
                'error': f"Auction already exists for UTXO {validated_data['utxo_txid']}:{validated_data['utxo_vout']}"
            }), 409
        
        # Create auction
        auction = Auction(
            asset_name=validated_data['asset_name'],
            asset_qty=validated_data['asset_qty'],
            utxo_txid=validated_data['utxo_txid'],
            utxo_vout=validated_data['utxo_vout'],
            start_block=validated_data['start_block'],
            end_block=validated_data['end_block'],
            blocks_after_end=validated_data['blocks_after_end'],
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
        
        logger.info(f"Created auction {auction.id} for {auction.asset_name}")
        
        return jsonify({
            'success': True,
            'auction_id': auction.id,
            'message': f'Auction created successfully',
            'auction': auction.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating auction: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/auctions', methods=['GET'])
def list_auctions():
    """
    List all auctions with optional status filter
    
    Query params:
    - status: upcoming, active, sold, closed, finished
    """
    try:
        status_filter = request.args.get('status')
        
        query = Auction.query
        
        if status_filter:
            if status_filter not in ['upcoming', 'active', 'sold', 'closed', 'finished', 'expired']:
                return jsonify({'error': 'Invalid status filter'}), 400
            query = query.filter_by(status=status_filter)
        
        auctions = query.order_by(Auction.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'count': len(auctions),
            'auctions': [auction.to_dict() for auction in auctions]
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing auctions: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/auctions/<int:auction_id>', methods=['GET'])
def get_auction(auction_id):
    """
    Get auction details (metadata only, NO PSBTs)
    
    Security: Never returns PSBT data to prevent revealing future prices
    """
    try:
        auction = Auction.query.get(auction_id)
        
        if not auction:
            return jsonify({'error': 'Auction not found'}), 404
        
        return jsonify({
            'success': True,
            'auction': auction.to_dict(include_psbts=False)
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting auction {auction_id}: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/auctions/<int:auction_id>/current-psbt', methods=['GET'])
def get_current_psbt(auction_id):
    """
    Get the currently active PSBT for an auction
    
    Returns ONLY the PSBT for the current block height.
    If auction has ended, returns the final (lowest price) PSBT.
    
    Security: Never returns future PSBTs to prevent revealing lowest price early
    """
    try:
        auction = Auction.query.get(auction_id)
        
        if not auction:
            return jsonify({'error': 'Auction not found'}), 404
        
        # Get current block height
        try:
            current_block = bitcoin_rpc.get_current_block_height()
        except Exception as e:
            logger.error(f"Error getting current block height: {str(e)}")
            return jsonify({'error': 'Unable to get current block height'}), 503
        
        # Check if auction is in cleanup period (ended + blocks_after_end)
        if current_block >= auction.end_block + auction.blocks_after_end:
            return jsonify({
                'success': True,
                'current_block': current_block,
                'auction_id': auction_id,
                'psbt': None,
                'message': 'Auction has ended and is in cleanup period'
            }), 200
        
        # If auction hasn't started yet
        if current_block < auction.start_block:
            return jsonify({
                'success': True,
                'current_block': current_block,
                'auction_id': auction_id,
                'psbt': None,
                'message': 'Auction has not started yet',
                'starts_at_block': auction.start_block
            }), 200
        
        # If auction is sold or closed, no PSBT available
        if auction.status in ['sold', 'closed']:
            return jsonify({
                'success': True,
                'current_block': current_block,
                'auction_id': auction_id,
                'psbt': None,
                'status': auction.status,
                'message': f'Auction is {auction.status}'
            }), 200
        
        # Determine which PSBT to return
        if current_block <= auction.end_block:
            # Auction is active - return PSBT for current block
            target_block = current_block
        else:
            # Auction has ended but not yet in cleanup - return final (lowest price) PSBT
            target_block = auction.end_block
        
        # Get the PSBT for the target block
        psbt = PSBT.query.filter_by(
            auction_id=auction_id,
            block_number=target_block
        ).first()
        
        if not psbt:
            logger.warning(f"No PSBT found for auction {auction_id} at block {target_block}")
            return jsonify({
                'error': f'No PSBT available for block {target_block}'
            }), 404
        
        return jsonify({
            'success': True,
            'current_block': current_block,
            'auction_id': auction_id,
            'auction_status': auction.status,
            'psbt': psbt.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting current PSBT for auction {auction_id}: {str(e)}")
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

