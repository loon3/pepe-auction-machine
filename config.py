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
    BITCOIN_RPC_USER = os.getenv('BITCOIN_RPC_USER', 'rpc_user')
    BITCOIN_RPC_PASSWORD = os.getenv('BITCOIN_RPC_PASSWORD', 'rpc_password')
    
    # Counterparty Core API Configuration
    COUNTERPARTY_HOST = os.getenv('COUNTERPARTY_HOST', 'counterparty')
    COUNTERPARTY_PORT = int(os.getenv('COUNTERPARTY_PORT', '4000'))
    
    # Monitoring Configuration
    BLOCK_MONITOR_INTERVAL = int(os.getenv('BLOCK_MONITOR_INTERVAL', '30'))  # seconds
    UTXO_MONITOR_INTERVAL = int(os.getenv('UTXO_MONITOR_INTERVAL', '60'))  # seconds

