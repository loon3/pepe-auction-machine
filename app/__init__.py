from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from config import Config

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Enable CORS for all routes
    CORS(app)
    
    db.init_app(app)
    
    with app.app_context():
        # Import models
        from app import models
        
        # Create database tables
        db.create_all()
        
        # Register routes
        from app.routes import bp as routes_bp
        app.register_blueprint(routes_bp)
    
    return app

