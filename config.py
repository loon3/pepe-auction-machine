import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Configuration
    API_KEY = os.getenv('API_KEY', 'change-me-in-production')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24))
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Database Configuration
    DATABASE_PATH = os.getenv('DATABASE_PATH', './data/auctions.db')
    # Convert to absolute path for SQLAlchemy
    _db_path_absolute = os.path.abspath(DATABASE_PATH)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{_db_path_absolute}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Bitcoin Core RPC Configuration
    BITCOIN_RPC_HOST = os.getenv('BITCOIN_RPC_HOST', 'bitcoind')
    BITCOIN_RPC_PORT = int(os.getenv('BITCOIN_RPC_PORT', '8332'))
    BITCOIN_RPC_USER = os.getenv('BITCOIN_RPC_USER', 'rpc')
    BITCOIN_RPC_PASSWORD = os.getenv('BITCOIN_RPC_PASSWORD', 'rpc')
    
    # Counterparty Core API Configuration
    COUNTERPARTY_API_URL = os.getenv('COUNTERPARTY_API_URL', 'https://api.counterparty.io:4000')
    
    # Monitoring Configuration (fallback polling intervals - ZMQ provides real-time updates)
    BLOCK_MONITOR_INTERVAL = int(os.getenv('BLOCK_MONITOR_INTERVAL', '300'))  # 5 min fallback
    UTXO_MONITOR_INTERVAL = int(os.getenv('UTXO_MONITOR_INTERVAL', '300'))    # 5 min fallback
    
    # ZMQ Configuration (Bitcoin Core push notifications)
    ZMQ_ENABLED = os.getenv('ZMQ_ENABLED', 'true').lower() == 'true'
    ZMQ_BLOCK_URL = os.getenv('ZMQ_BLOCK_URL', 'tcp://bitcoind:9333')  # rawblock notifications
    ZMQ_TX_URL = os.getenv('ZMQ_TX_URL', 'tcp://bitcoind:9332')        # rawtx notifications

