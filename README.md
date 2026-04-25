# Finance backend — Sudheer Manduri
April 6, 2026

Backend for a role-based internal finance dashboard. Covers user
management, financial record CRUD, filtering, and summary analytics.

---

## Roles

| Role    | What they can do                              |
|---------|-----------------------------------------------|
| Viewer  | Dashboard summary only                        |
| Analyst | Read and filter records, dashboard            |
| Admin   | Full CRUD on records, manage users, dashboard |

This is a shared internal dashboard. All records are visible to
Analyst and Admin regardless of who created them.

---

## Structure

```
models.py      User and Record schema
services.py    auth logic, record logic, dashboard aggregation
middleware.py  JWT validation, role checks
routes.py      HTTP endpoints
app.py         app factory, env config, error handlers
tests.py       32 tests
```

The app factory in app.py lets tests run against an in-memory
database without touching the dev database. Business logic stays
in services, not in route handlers.

---

## Auth

Passwords hashed with bcrypt. JWTs expire in 24 hours and require
Authorization: Bearer <token> format. Anything else returns 401.

Disabled accounts are blocked at login before a token is issued,
not just at middleware. A deactivated user cannot get a new token
immediately. Previously issued tokens expire after 24 hours. A
production system would add a token blacklist for immediate
revocation but that felt out of scope here.

Secret key loads from .env. The fallback in app.py is for local
development only.

---

## Assumptions

Records are shared across the org. Treated this as a shared finance
dashboard. If per-user scoping were needed, filtering records by
user_id would handle it.

Role is selectable at registration for evaluation purposes. In a
real system, new users would default to Viewer and only an Admin
could promote them via PUT /admin/users/<id>.

Amounts are stored as Numeric(12, 2) to avoid binary floating point
drift on money values. Decimal accumulation is used in dashboard
math and only cast to float at the JSON boundary. Integer cents
would be stricter but this covers the assignment scope.

Trend aggregation runs in Python rather than SQL. SQLite's strftime
is not supported in Postgres or MySQL so doing it in Python keeps
the code portable. For large datasets, EXTRACT() at the database
level would be the right move.

No soft delete. Would need a deleted_at column and a filter on
every query. Not asked for here.

No refresh tokens. The login-time status check covers the main
case and keeps the implementation simple.

---

## Validation

- Username: 2 to 50 characters, whitespace stripped
- Password: minimum 6 characters
- Amount: positive number only, booleans rejected
- Type: income or expense only, enforced on create and on filter
- Category: non-empty string, enforced on create and on filter
- Description: string, max 200 characters
- Pagination: limit must be above 0 and is capped at 100,
  offset must be 0 or above
- Dates: YYYY-MM-DD on all endpoints that accept them

---

## API

Auth
```
POST /auth/register    {username, password, role}
POST /auth/login       {username, password}  ->  {token}
```

Records (Analyst and Admin)
```
GET    /records         ?category ?type ?start_date ?end_date
                        ?limit ?offset
POST   /records         Admin only
PUT    /records/<id>    Admin only
DELETE /records/<id>    Admin only
```

Admin
```
GET  /admin/users
PUT  /admin/users/<id>  {role?, status?}
```

Dashboard (all roles)
```
GET /dashboard/summary  ?start_date ?end_date
```

Returns income and expense totals, net balance, category breakdown
split by type, monthly and weekly trends, and the five most recent
records. All results respect the date range if provided.

---

## Quick test with curl

Start the server first: `python app.py`

```bash
# register
curl -X POST http://localhost:5000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "sudheer", "password": "pass123", "role": "Admin"}'

# login — copy the token from the response
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "sudheer", "password": "pass123"}'

# create a record (replace TOKEN)
curl -X POST http://localhost:5000/records \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "type": "income", "category": "Salary", "date": "2025-04-01"}'

# fetch records with filter
curl "http://localhost:5000/records?type=income&limit=5" \
  -H "Authorization: Bearer TOKEN"

# dashboard (works for all roles)
curl http://localhost:5000/dashboard/summary \
  -H "Authorization: Bearer TOKEN"
```

---

## Troubleshooting

SECRET_KEY not set: copy .env.example to .env and add a value.
Schema errors after model changes: delete finance.db and restart,
db.create_all() does not migrate existing tables.
Tests failing: make sure you are running from the project root
and all dependencies are installed.

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# set SECRET_KEY in .env
python app.py
python tests.py
```

32 tests covering registration, login, disabled account 403,
malformed auth headers, all three role tiers, record CRUD and
updates, type and category filter validation, pagination bounds,
dashboard structure, dashboard date filtering, dashboard totals
correctness, boolean amount rejection, and input validation.

---

## Deploy to Render (Production)

### 1. Database Setup (Neon - Recommended)

1. Go to [neon.tech](https://neon.tech) → Sign up → Create new project
2. Choose **Postgres 15** or higher
3. Select region: **US East (N. Virginia)** (closest to Render's Oregon region)
4. Copy the connection string: `postgresql://user:password@host:5432/dbname`
5. Save this for the next step

### 2. Render Web Service Setup

1. Go to [render.com](https://render.com) → Dashboard → **New +** → **Web Service**
2. Connect your GitHub repo → Select this project
3. Configure:
   - **Name**: `finance-backend` (or your preference)
   - **Region**: `Oregon (US West)`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
4. Add Environment Variables:
   - `DATABASE_URL`: paste your Neon connection string
   - `SECRET_KEY`: generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
5. Click **Create Web Service**
6. Once deployed, note the URL (e.g., `https://finance-backend-xxx.onrender.com`)

### 3. Run Database Migrations

After the web service is live, open **Shell** in Render dashboard and run:

```bash
python migrate.py
```

This applies the initial migration and creates tables in Postgres.

### 4. Smoke Test (Production)

Replace `https://your-app.onrender.com` with your actual Render URL:

```bash
# Test health endpoint
curl https://your-app.onrender.com/health

# Register an admin user
curl -X POST https://your-app.onrender.com/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "pass123", "role": "Admin"}'

# Login (save the token)
curl -X POST https://your-app.onrender.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "pass123"}'

# Create a record
curl -X POST https://your-app.onrender.com/records \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "type": "income", "category": "Salary", "date": "2025-04-01"}'

# Check dashboard
curl https://your-app.onrender.com/dashboard/summary \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Files Changed for Deployment

| File | Purpose |
|------|---------|
| `app.py` | Added Flask-Migrate, /health endpoint, PORT binding |
| `requirements.txt` | Added psycopg2-binary, gunicorn, flask-migrate |
| `.env.example` | Documented all required env vars |
| `migrate.py` | Production migration runner |
| `migrations/` | Alembic migration files |
| `render.yaml` | Infrastructure-as-code for Render |

---

## Alternative: Deploy via render.yaml (Blueprint)

If you prefer infrastructure-as-code:

1. Push the `render.yaml` to your repo
2. In Render dashboard: **Blueprints** → **New Blueprint Instance**
3. Select this repo → Render creates both the web service and Postgres database
4. Note: Uses Render's managed Postgres (not Neon), but still works fine
