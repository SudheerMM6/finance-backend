import os
from flask import Flask, jsonify
from flask_cors import CORS
from models import db
from routes import api
from dotenv import load_dotenv
from flask_migrate import Migrate

load_dotenv()
migrate = Migrate()

def create_app(db_uri=None):
    app = Flask(__name__)
    # Enable CORS for all domains (safe for public API)
    CORS(app)

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        db_uri or os.environ.get('DATABASE_URL', 'sqlite:///finance.db')
    )
    # Required in production (set via Render env vars)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-change-this')
    # Disable SQLAlchemy event system to save memory
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    app.register_blueprint(api)

    @app.route('/health')
    def health_check():
        return jsonify(status='healthy', service='finance-backend'), 200

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Route not found"), 404

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error="Bad request"), 400

    @app.errorhandler(500)
    def server_error(e):
        return jsonify(error="Internal server error"), 500

    # Auto-create tables for SQLite (dev only). Production uses `flask db upgrade`.
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        with app.app_context():
            db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
