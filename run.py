#!/usr/bin/env python3
"""
Main entry point for the Rare Pepe Dutch Auction Machine
"""
import os
import logging
from app import create_app, db
from app.monitors import auction_monitor
from app.zmq_listener import zmq_listener

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create Flask app
app = create_app()

# Initialize monitoring and ZMQ listener with app context
auction_monitor.init_app(app)
zmq_listener.init_app(app)

# Start background monitoring
with app.app_context():
    # Ensure database directory exists
    db_path = app.config['DATABASE_PATH']
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")
    
    # Create tables if they don't exist
    db.create_all()
    logger.info("Database tables created/verified")
    
    # Start polling-based monitoring (fallback)
    auction_monitor.start()
    logger.info("Background polling monitors started (5 min intervals)")
    
    # Start ZMQ listener for real-time notifications (primary)
    if app.config.get('ZMQ_ENABLED', True):
        zmq_listener.start(
            on_new_block=auction_monitor.trigger_block_check,
            on_new_tx=auction_monitor.check_transaction_for_utxos
        )
        logger.info("ZMQ real-time notifications started")
    else:
        logger.info("ZMQ notifications disabled, using polling only")

if __name__ == '__main__':
    try:
        # Run Flask app
        port = int(os.getenv('FLASK_PORT', 5000))
        host = os.getenv('FLASK_HOST', '0.0.0.0')
        
        logger.info(f"Starting Rare Pepe Auction Machine on {host}:{port}")
        
        app.run(
            host=host,
            port=port,
            debug=app.config['DEBUG']
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        zmq_listener.stop()
        auction_monitor.stop()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        zmq_listener.stop()
        auction_monitor.stop()
        raise

