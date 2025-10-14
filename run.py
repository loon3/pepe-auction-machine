#!/usr/bin/env python3
"""
Main entry point for the Rare Pepe Dutch Auction Machine
"""
import os
import logging
from app import create_app, db
from app.monitors import auction_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create Flask app
app = create_app()

# Initialize monitoring with app context
auction_monitor.init_app(app)

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
    
    # Start monitoring
    auction_monitor.start()
    logger.info("Background monitoring started")

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
        auction_monitor.stop()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        auction_monitor.stop()
        raise

