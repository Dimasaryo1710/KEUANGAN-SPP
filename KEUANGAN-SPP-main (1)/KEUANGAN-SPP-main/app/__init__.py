# app/__init__.py
import os
from flask import Flask
from flask_cors import CORS
from app.config import config
from app.models import db

def create_app(config_name='development'):
    """Application factory"""
    # Get the directory of the app module
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
    
    app = Flask(__name__, template_folder=template_dir)
    
    from dotenv import load_dotenv
    load_dotenv()
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    CORS(app)
    
    # Register blueprints
    from app.routes import register_routes
    register_routes(app)
    
    from app.models.notification import Notification, KRSRegistration
    from app.routes.extension_routes import extension_bp
    app.register_blueprint(extension_bp)
    with app.app_context():
        db.create_all()
    from app.schedulers import setup_billing_scheduler
    setup_billing_scheduler(app)

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404
    
    @app.errorhandler(500)
    def server_error(error):
        return {'error': 'Server error'}, 500
    
    return app
