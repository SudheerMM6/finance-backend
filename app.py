import os
import sys
from flask import Flask, jsonify, current_app
from flask_cors import CORS
from models import db
from routes import api
from dotenv import load_dotenv
from flask_migrate import Migrate
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

load_dotenv()
migrate = Migrate()

# Known dev fallback that must not be used in production
_DEV_FALLBACK_SECRET = 'dev-fallback-change-this'


def is_production():
    """Detect production environment from env vars."""
    return os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'


def normalize_database_url(url):
    """Fix common DATABASE_URL issues from Render and other platforms."""
    if not url:
        return None
    # Strip quotes and whitespace
    url = url.strip().strip('"').strip("'")
    # Convert postgres:// to postgresql:// (Render sometimes uses postgres://)
    if url.startswith('postgres://'):
        url = 'postgresql' + url[8:]
    return url


def create_app(db_uri=None, test_config=None):
    app = Flask(__name__)
    
    # CORS: allow all in dev, configurable in production
    cors_origins = os.environ.get('CORS_ORIGINS', '*')
    if cors_origins == '*':
        CORS(app)
    else:
        origins = [o.strip() for o in cors_origins.split(',')]
        CORS(app, origins=origins)

    # Database URL resolution with normalization
    raw_db_url = db_uri or os.environ.get('DATABASE_URL') or 'sqlite:///finance.db'
    db_url = normalize_database_url(raw_db_url)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    # SECRET_KEY handling: require in production, allow fallback in dev
    secret_key = os.environ.get('SECRET_KEY', _DEV_FALLBACK_SECRET)
    if is_production():
        if not secret_key or secret_key == _DEV_FALLBACK_SECRET:
            raise RuntimeError(
                "SECRET_KEY must be set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
    app.config['SECRET_KEY'] = secret_key
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Prevent SQLAlchemy from eagerly connecting
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'connect_timeout': 10} if 'postgresql' in db_url else {}
    }

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    app.register_blueprint(api)

    # Health check - always returns 200, includes DB status
    @app.route('/health')
    def health_check():
        db_ready, db_message = db_is_ready()
        return jsonify(
            status='healthy',
            service='finance-backend',
            db={'ready': db_ready, 'message': db_message}
        ), 200

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Route not found"), 404

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error="Bad request"), 400

    @app.errorhandler(500)
    def server_error(e):
        return jsonify(error="Internal server error"), 500

    @app.errorhandler(503)
    def service_unavailable(e):
        return jsonify(error="Database unavailable", retry_after=30), 503

    return app


def db_is_ready():
    """Check if database is ready without crashing. Returns (bool, message)."""
    try:
        # Use a short timeout check
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True, 'connected'
    except OperationalError as e:
        return False, f'database unavailable: {str(e)[:50]}'
    except Exception as e:
        return False, f'error: {str(e)[:50]}'


# Create the app instance (gunicorn imports this)
# DB connection is deferred to first request
app = create_app()

# Auto-create tables for SQLite in development (lazy, on first request)
@app.before_request
def init_sqlite_tables():
    """Lazy initialization - only runs on first request."""
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        try:
            db.create_all()
        except Exception:
            pass  # Tables may already exist
    # Unregister to prevent running again
    app.before_request_funcs[None].remove(init_sqlite_tables)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
