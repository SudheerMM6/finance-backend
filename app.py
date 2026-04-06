import os
from flask import Flask, jsonify
from models import db
from routes import api
from dotenv import load_dotenv

load_dotenv()

def create_app(db_uri=None):
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        db_uri or os.environ.get('DATABASE_URL', 'sqlite:///finance.db')
    )
    # set SECRET_KEY in .env before deploying, the fallback is for local dev only
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-change-this')

    db.init_app(app)
    app.register_blueprint(api)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Route not found"), 404

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error="Bad request"), 400

    @app.errorhandler(500)
    def server_error(e):
        return jsonify(error="Internal server error"), 500

    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
