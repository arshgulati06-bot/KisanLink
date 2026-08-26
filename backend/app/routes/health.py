from flask import Blueprint, jsonify
from app.config.db import check_db_connection

health_bp = Blueprint('health', __name__)

@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check API route confirming backend service status and MySQL DB connection state.
    """
    db_connected, db_message = check_db_connection()
    
    return jsonify({
        "status": "healthy" if db_connected else "degraded",
        "message": "KisanLink Flask Backend Service is up and running.",
        "database": {
            "connected": db_connected,
            "details": db_message
        }
    }), 200
