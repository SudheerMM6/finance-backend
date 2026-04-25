from flask import Blueprint, request, jsonify, g
from models import db, User, Record
from middleware import token_required, role_check
from services import AuthService, FinanceService
from datetime import datetime
from functools import wraps
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

api = Blueprint('api', __name__)


def require_db(f):
    """Decorator that returns 503 if database is unavailable."""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            # Lightweight connectivity check
            db.session.execute(text('SELECT 1'))
        except OperationalError:
            return jsonify({'error': 'Database unavailable', 'retry_after': 30}), 503
        except Exception:
            return jsonify({'error': 'Database unavailable', 'retry_after': 30}), 503
        return f(*args, **kwargs)
    return decorated

@api.route('/auth/register', methods=['POST'])
@require_db
def register():
    data = request.json or {}
    user, err, status = AuthService.register_user(
        data.get('username', ''),
        data.get('password', ''),
        data.get('role', 'Viewer')
    )
    if err:
        return jsonify({'error': err}), status
    return jsonify({'msg': 'User created', 'username': user.username, 'role': user.role}), 201

@api.route('/auth/login', methods=['POST'])
@require_db
def login():
    data = request.json or {}
    from flask import current_app
    token, err, status = AuthService.login_user(
        data.get('username', ''),
        data.get('password', ''),
        current_app.config['SECRET_KEY']
    )
    if err:
        return jsonify({'error': err}), status
    return jsonify({'token': token})

@api.route('/admin/users', methods=['GET'])
@token_required
@role_check(['Admin'])
@require_db
def list_users():
    users = User.query.all()
    return jsonify([
        {'id': u.id, 'username': u.username, 'role': u.role, 'status': u.status}
        for u in users
    ])

@api.route('/admin/users/<int:user_id>', methods=['PUT'])
@token_required
@role_check(['Admin'])
@require_db
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.json or {}

    if 'role' in data:
        role = data['role'].strip() if isinstance(data['role'], str) else ''
        if role not in AuthService.ALLOWED_ROLES:
            return jsonify({'error': f"Invalid role. Choose from {AuthService.ALLOWED_ROLES}"}), 400
        user.role = role

    if 'status' in data:
        status = data['status'].strip() if isinstance(data['status'], str) else ''
        if status not in AuthService.ALLOWED_STATUS:
            return jsonify({'error': 'Status must be active or inactive'}), 400
        user.status = status

    db.session.commit()
    return jsonify({'msg': 'User updated', 'id': user.id})

@api.route('/records', methods=['GET'])
@token_required
@role_check(['Analyst', 'Admin'])
@require_db
def get_records():
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)

    if limit <= 0:
        return jsonify({'error': 'limit must be a positive integer'}), 400
    if offset < 0:
        return jsonify({'error': 'offset cannot be negative'}), 400

    limit = min(limit, 100)

    type_filter = request.args.get('type')
    category_filter = request.args.get('category')

    if type_filter is not None and type_filter not in ['income', 'expense']:
        return jsonify({'error': "type filter must be 'income' or 'expense'"}), 400
    if category_filter is not None and not category_filter.strip():
        return jsonify({'error': 'category filter cannot be blank'}), 400

    query = Record.query
    if category_filter:
        query = query.filter_by(category=category_filter.strip())
    if type_filter:
        query = query.filter_by(txn_type=type_filter)

    try:
        start = request.args.get('start_date')
        end = request.args.get('end_date')
        if start:
            query = query.filter(Record.date >= datetime.strptime(start, '%Y-%m-%d').date())
        if end:
            query = query.filter(Record.date <= datetime.strptime(end, '%Y-%m-%d').date())
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    total = query.count()
    records = query.order_by(Record.date.desc()).offset(offset).limit(limit).all()

    return jsonify({
        'total_count': total,
        'limit': limit,
        'offset': offset,
        'records': [
            {
                'id': r.id,
                'amount': round(float(r.amount), 2),
                'type': r.txn_type,
                'category': r.category,
                'date': r.date.isoformat(),
                'description': r.description
            }
            for r in records
        ]
    })

@api.route('/records', methods=['POST'])
@token_required
@role_check(['Admin'])
@require_db
def add_record():
    record, err = FinanceService.create_record(request.json or {}, g.current_user.id)
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'msg': 'Record added', 'id': record.id}), 201

@api.route('/records/<int:record_id>', methods=['PUT'])
@token_required
@role_check(['Admin'])
@require_db
def update_record(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        return jsonify({'error': 'Record not found'}), 404

    data = request.json or {}
    ok, err = FinanceService.validate_record(data, partial=True)
    if not ok:
        return jsonify({'error': err}), 400

    try:
        if 'amount' in data:
            record.amount = data['amount']
        if 'category' in data:
            record.category = data['category'].strip()
        if 'type' in data:
            record.txn_type = data['type']
        if 'description' in data:
            record.description = data['description'].strip()
        if 'date' in data:
            record.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    db.session.commit()
    return jsonify({'msg': 'Record updated', 'id': record.id})

@api.route('/records/<int:record_id>', methods=['DELETE'])
@token_required
@role_check(['Admin'])
@require_db
def delete_record(record_id):
    record = db.session.get(Record, record_id)
    if not record:
        return jsonify({'error': 'Record not found'}), 404
    db.session.delete(record)
    db.session.commit()
    return jsonify({'msg': 'Record deleted'})

@api.route('/dashboard/summary', methods=['GET'])
@token_required
@role_check(['Viewer', 'Analyst', 'Admin'])
@require_db
def dashboard_summary():
    try:
        start = request.args.get('start_date')
        end = request.args.get('end_date')
        start_date = datetime.strptime(start, '%Y-%m-%d').date() if start else None
        end_date = datetime.strptime(end, '%Y-%m-%d').date() if end else None
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    return jsonify(FinanceService.get_dashboard(start_date, end_date))
