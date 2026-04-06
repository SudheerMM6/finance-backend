from models import db, User, Record
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from decimal import Decimal

class AuthService:
    ALLOWED_ROLES = ['Admin', 'Analyst', 'Viewer']
    ALLOWED_STATUS = ['active', 'inactive']

    @staticmethod
    def register_user(username, password, role):
        username = username.strip() if isinstance(username, str) else ''
        if not username or not password:
            return None, "Username and password are required", 400
        if len(username) < 2 or len(username) > 50:
            return None, "Username must be between 2 and 50 characters", 400
        if len(password) < 6:
            return None, "Password must be at least 6 characters", 400
        if role not in AuthService.ALLOWED_ROLES:
            return None, f"Invalid role. Choose from {AuthService.ALLOWED_ROLES}", 400
        if User.query.filter_by(username=username).first():
            return None, "Username already taken", 400

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(username=username, password=hashed, role=role)
        db.session.add(user)
        db.session.commit()
        return user, None, 201

    @staticmethod
    def login_user(username, password, secret):
        username = username.strip() if isinstance(username, str) else ''
        if not username or not password:
            return None, "Username and password are required", 401

        user = User.query.filter_by(username=username).first()
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return None, "Invalid credentials", 401

        # credentials valid, now check account status separately so we return 403
        if user.status != 'active':
            return None, "Account is disabled", 403

        token = jwt.encode({
            'user_id': user.id,
            'role': user.role,
            'exp': datetime.now(timezone.utc) + timedelta(hours=24)
        }, secret, algorithm="HS256")

        return token, None, 200


class FinanceService:
    @staticmethod
    def validate_record(data, partial=False):
        if not partial:
            required = ['amount', 'type', 'category', 'date']
            if not all(k in data for k in required):
                return False, "Missing required fields: amount, type, category, date"

        if 'amount' in data:
            # bool is a subclass of int in Python so reject it explicitly
            if isinstance(data['amount'], bool):
                return False, "Amount must be a positive number"
            if not isinstance(data['amount'], (int, float)) or data['amount'] <= 0:
                return False, "Amount must be a positive number"

        if 'type' in data and data['type'] not in ['income', 'expense']:
            return False, "Type must be 'income' or 'expense'"

        if 'category' in data:
            if not isinstance(data['category'], str) or not data['category'].strip():
                return False, "Category cannot be empty"

        if 'description' in data:
            if not isinstance(data['description'], str):
                return False, "Description must be a string"
            if len(data['description']) > 200:
                return False, "Description cannot exceed 200 characters"

        return True, None

    @staticmethod
    def create_record(data, user_id):
        ok, err = FinanceService.validate_record(data)
        if not ok:
            return None, err

        try:
            parsed_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        except ValueError:
            return None, "Invalid date format. Use YYYY-MM-DD"

        record = Record(
            amount=data['amount'],
            txn_type=data['type'],
            category=data['category'].strip(),
            date=parsed_date,
            description=data.get('description', '').strip(),
            user_id=user_id
        )
        db.session.add(record)
        db.session.commit()
        return record, None

    @staticmethod
    def get_dashboard(start_date=None, end_date=None):
        query = Record.query
        if start_date:
            query = query.filter(Record.date >= start_date)
        if end_date:
            query = query.filter(Record.date <= end_date)

        all_records = query.all()

        # accumulate as Decimal to keep precision consistent with Numeric column
        total_income = Decimal('0')
        total_expense = Decimal('0')
        categories = defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0')})
        monthly = defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0')})
        weekly = defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0')})

        for r in all_records:
            month_key = r.date.strftime('%Y-%m')
            week_key = r.date.strftime('%Y-%W')
            amt = r.amount
            if r.txn_type == 'income':
                total_income += amt
                categories[r.category]['income'] += amt
                monthly[month_key]['income'] += amt
                weekly[week_key]['income'] += amt
            else:
                total_expense += amt
                categories[r.category]['expense'] += amt
                monthly[month_key]['expense'] += amt
                weekly[week_key]['expense'] += amt

        recent = query.order_by(Record.date.desc(), Record.id.desc()).limit(5).all()

        def dec_to_float(d):
            return round(float(d), 2)

        return {
            'totals': {
                'income': dec_to_float(total_income),
                'expense': dec_to_float(total_expense),
                'net': dec_to_float(total_income - total_expense)
            },
            'categories': {
                cat: {'income': dec_to_float(v['income']), 'expense': dec_to_float(v['expense'])}
                for cat, v in sorted(categories.items())
            },
            'monthly_trends': {
                k: {'income': dec_to_float(v['income']), 'expense': dec_to_float(v['expense'])}
                for k, v in sorted(monthly.items())
            },
            'weekly_trends': {
                k: {'income': dec_to_float(v['income']), 'expense': dec_to_float(v['expense'])}
                for k, v in sorted(weekly.items())
            },
            'recent': [
                {
                    'id': r.id,
                    'amount': dec_to_float(r.amount),
                    'type': r.txn_type,
                    'category': r.category,
                    'date': r.date.isoformat()
                }
                for r in recent
            ]
        }
