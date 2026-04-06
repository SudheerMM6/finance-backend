from flask import request, jsonify, current_app, g
import jwt
from functools import wraps
from models import db, User

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        parts = header.split()

        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Missing or malformed Authorization header'}), 401

        try:
            payload = jwt.decode(parts[1], current_app.config['SECRET_KEY'], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        user = db.session.get(User, payload.get('user_id'))
        if not user:
            return jsonify({'error': 'User not found'}), 403
        if user.status != 'active':
            return jsonify({'error': 'Account disabled'}), 403

        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def role_check(allowed):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if g.current_user.role not in allowed:
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator
