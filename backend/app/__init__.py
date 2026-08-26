import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

def create_app():
    """
    Flask application factory.
    """
    app = Flask(__name__)
    
    # Configure application
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_kisanlink_secret_key')
    
    # Enable CORS
    CORS(app)
    
    # Register API Blueprints
    from app.routes.health import health_bp
    app.register_blueprint(health_bp)
    
    return app
