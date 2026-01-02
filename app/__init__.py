from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import event
from config import Config

db = SQLAlchemy()


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Configure SQLite for better concurrency:
    - WAL mode: Allows concurrent reads during writes
    - busy_timeout: Retries for 5 seconds if database is locked
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Enable CORS for all routes
    CORS(app)
    
    db.init_app(app)
    
    with app.app_context():
        # Enable WAL mode for SQLite to improve concurrency
        # This allows readers to not block writers and vice versa
        event.listen(db.engine, "connect", _set_sqlite_pragma)
        
        # Import models
        from app import models
        
        # Create database tables
        db.create_all()
        
        # Register routes
        from app.routes import bp as routes_bp
        app.register_blueprint(routes_bp)
    
    return app

