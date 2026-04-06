import unittest
from app import create_app
from models import db, User
from services import FinanceService

class FinanceTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('sqlite:///:memory:')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _make_user(self, username, password, role):
        self.client.post('/auth/register', json={
            'username': username, 'password': password, 'role': role
        })
        res = self.client.post('/auth/login', json={
            'username': username, 'password': password
        })
        return res.json.get('token')

    # --- register ---

    def test_register_success(self):
        res = self.client.post('/auth/register', json={
            'username': 'sudheer', 'password': 'pass123', 'role': 'Admin'
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['username'], 'sudheer')
        self.assertEqual(res.json['role'], 'Admin')

    def test_register_bad_role(self):
        res = self.client.post('/auth/register', json={
            'username': 'badguy', 'password': 'pass123', 'role': 'Hacker'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn(b'Invalid role', res.data)

    def test_register_short_password(self):
        res = self.client.post('/auth/register', json={
            'username': 'sudheer', 'password': '123', 'role': 'Viewer'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn(b'6 characters', res.data)

    def test_register_duplicate(self):
        self.client.post('/auth/register', json={
            'username': 'sudheer', 'password': 'pass123', 'role': 'Viewer'
        })
        res = self.client.post('/auth/register', json={
            'username': 'sudheer', 'password': 'pass123', 'role': 'Viewer'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn(b'already taken', res.data)

    # --- login ---

    def test_login_success(self):
        self.client.post('/auth/register', json={
            'username': 'sudheer', 'password': 'pass123', 'role': 'Admin'
        })
        res = self.client.post('/auth/login', json={
            'username': 'sudheer', 'password': 'pass123'
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn('token', res.json)

    def test_login_wrong_password(self):
        self.client.post('/auth/register', json={
            'username': 'sudheer', 'password': 'pass123', 'role': 'Admin'
        })
        res = self.client.post('/auth/login', json={
            'username': 'sudheer', 'password': 'wrong'
        })
        self.assertEqual(res.status_code, 401)

    def test_disabled_account_returns_403(self):
        self.client.post('/auth/register', json={
            'username': 'disabled', 'password': 'pass123', 'role': 'Viewer'
        })
        user = User.query.filter_by(username='disabled').first()
        user.status = 'inactive'
        db.session.commit()

        res = self.client.post('/auth/login', json={
            'username': 'disabled', 'password': 'pass123'
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn(b'disabled', res.data)

    def test_empty_login(self):
        res = self.client.post('/auth/login', json={})
        self.assertEqual(res.status_code, 401)

    # --- auth header ---

    def test_missing_auth_header(self):
        res = self.client.get('/records')
        self.assertEqual(res.status_code, 401)

    def test_malformed_header_no_bearer(self):
        token = self._make_user('s1', 'pass123', 'Analyst')
        res = self.client.get('/records', headers={'Authorization': token})
        self.assertEqual(res.status_code, 401)

    def test_malformed_header_wrong_scheme(self):
        token = self._make_user('s2', 'pass123', 'Analyst')
        res = self.client.get('/records', headers={'Authorization': f'Token {token}'})
        self.assertEqual(res.status_code, 401)

    # --- roles ---

    def test_viewer_blocked_from_records(self):
        token = self._make_user('v1', 'pass123', 'Viewer')
        res = self.client.get('/records', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 403)

    def test_viewer_can_see_dashboard(self):
        token = self._make_user('v2', 'pass123', 'Viewer')
        res = self.client.get('/dashboard/summary', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)

    def test_analyst_can_read_records(self):
        token = self._make_user('a1', 'pass123', 'Analyst')
        res = self.client.get('/records', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 200)

    def test_analyst_cannot_create_record(self):
        token = self._make_user('a2', 'pass123', 'Analyst')
        res = self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 100, 'type': 'income', 'category': 'Test', 'date': '2025-01-01'}
        )
        self.assertEqual(res.status_code, 403)

    # --- records crud ---

    def test_admin_create_and_fetch(self):
        token = self._make_user('admin1', 'pass123', 'Admin')
        res = self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 1000, 'type': 'income', 'category': 'Salary', 'date': '2025-03-01'}
        )
        self.assertEqual(res.status_code, 201)
        self.assertIn('id', res.json)

        res2 = self.client.get('/records', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res2.json['total_count'], 1)
        self.assertEqual(res2.json['records'][0]['category'], 'Salary')

    def test_admin_update_record(self):
        token = self._make_user('admin2', 'pass123', 'Admin')
        self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 500, 'type': 'income', 'category': 'Salary', 'date': '2025-03-01'}
        )
        record_id = self.client.get('/records',
            headers={'Authorization': f'Bearer {token}'}
        ).json['records'][0]['id']

        res = self.client.put(f'/records/{record_id}',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 750, 'category': 'Bonus'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['id'], record_id)

    def test_admin_delete(self):
        token = self._make_user('admin3', 'pass123', 'Admin')
        self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 200, 'type': 'expense', 'category': 'Food', 'date': '2025-03-01'}
        )
        record_id = self.client.get('/records',
            headers={'Authorization': f'Bearer {token}'}
        ).json['records'][0]['id']

        res = self.client.delete(f'/records/{record_id}',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            self.client.get('/records',
                headers={'Authorization': f'Bearer {token}'}
            ).json['total_count'], 0
        )

    # --- filter validation ---

    def test_invalid_type_filter_returns_400(self):
        token = self._make_user('admin4', 'pass123', 'Admin')
        res = self.client.get('/records?type=garbage',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn(b'type filter', res.data)

    def test_blank_category_filter_returns_400(self):
        token = self._make_user('admin5', 'pass123', 'Admin')
        res = self.client.get('/records?category=   ',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn(b'category', res.data)

    # --- pagination ---

    def test_negative_offset_rejected(self):
        token = self._make_user('admin6', 'pass123', 'Admin')
        res = self.client.get('/records?offset=-1',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 400)

    def test_zero_limit_rejected(self):
        token = self._make_user('admin7', 'pass123', 'Admin')
        res = self.client.get('/records?limit=0',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 400)

    def test_limit_capped_at_100(self):
        token = self._make_user('admin8', 'pass123', 'Admin')
        res = self.client.get('/records?limit=500',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['limit'], 100)

    # --- dashboard ---

    def test_dashboard_returns_correct_structure(self):
        token = self._make_user('admin9', 'pass123', 'Admin')
        res = self.client.get('/dashboard/summary',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn('totals', res.json)
        self.assertIn('categories', res.json)
        self.assertIn('monthly_trends', res.json)
        self.assertIn('recent', res.json)

    def test_dashboard_totals_are_correct(self):
        token = self._make_user('admin10', 'pass123', 'Admin')
        self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 1000, 'type': 'income', 'category': 'Salary', 'date': '2025-01-01'}
        )
        self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 300, 'type': 'expense', 'category': 'Food', 'date': '2025-01-15'}
        )
        res = self.client.get('/dashboard/summary',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.json['totals']['income'], 1000.0)
        self.assertEqual(res.json['totals']['expense'], 300.0)
        self.assertEqual(res.json['totals']['net'], 700.0)

    def test_dashboard_date_filter_affects_recent(self):
        token = self._make_user('admin11', 'pass123', 'Admin')
        self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 500, 'type': 'income', 'category': 'Old', 'date': '2024-01-01'}
        )
        self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 999, 'type': 'income', 'category': 'New', 'date': '2025-06-01'}
        )
        res = self.client.get('/dashboard/summary?start_date=2025-01-01',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 200)
        dates = [r['date'] for r in res.json['recent']]
        self.assertNotIn('2024-01-01', dates)

    def test_dashboard_invalid_date(self):
        token = self._make_user('admin12', 'pass123', 'Admin')
        res = self.client.get('/dashboard/summary?start_date=not-a-date',
            headers={'Authorization': f'Bearer {token}'}
        )
        self.assertEqual(res.status_code, 400)

    # --- input validation ---

    def test_negative_amount_rejected(self):
        ok, err = FinanceService.validate_record({
            'amount': -50, 'type': 'income', 'category': 'test', 'date': '2025-01-01'
        })
        self.assertFalse(ok)
        self.assertIn('positive', err)

    def test_boolean_amount_rejected(self):
        ok, err = FinanceService.validate_record({
            'amount': True, 'type': 'income', 'category': 'test', 'date': '2025-01-01'
        })
        self.assertFalse(ok)

    def test_empty_category_rejected(self):
        token = self._make_user('admin13', 'pass123', 'Admin')
        res = self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 100, 'type': 'income', 'category': '  ', 'date': '2025-01-01'}
        )
        self.assertEqual(res.status_code, 400)

    def test_missing_required_fields(self):
        token = self._make_user('admin14', 'pass123', 'Admin')
        res = self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 100}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn(b'Missing', res.data)

    def test_invalid_date_format(self):
        token = self._make_user('admin15', 'pass123', 'Admin')
        res = self.client.post('/records',
            headers={'Authorization': f'Bearer {token}'},
            json={'amount': 100, 'type': 'income', 'category': 'Test', 'date': '01-01-2025'}
        )
        self.assertEqual(res.status_code, 400)

if __name__ == '__main__':
    unittest.main()
