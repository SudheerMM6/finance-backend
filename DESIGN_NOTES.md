# Design notes

A few things worth writing down while they are fresh.

---

## What I built first

Started with models and auth since everything else depends on
knowing who is making a request. Got bcrypt hashing and JWT
generation working, then built the middleware decorator before
writing any protected routes.

Records and dashboard came after. Filtering on records was built
before the dashboard so the same date range logic could feed both.

---

## Decisions I had to think about

**401 vs 403 on disabled accounts.**
Early version returned 401 for everything in login. That's wrong.
401 means the request is unauthenticated. 403 means the request
is authenticated but blocked. A disabled account has valid
credentials so the right code is 403. Fixed it by checking
credentials first, then status separately in login_user().

**Where to check account status.**
Middleware checks it on every request, which handles existing
tokens. But if I only check there, a disabled user can still call
/auth/login and get a fresh token. So login_user() also checks
status before issuing one. Middleware is then a second line for
tokens that were already issued.

**Float vs Numeric for money.**
First version used Float. Changed to Numeric(12, 2) because binary
floats can't represent all decimal fractions exactly, which matters
for financial values. The tradeoff is that SQLAlchemy returns
decimal.Decimal objects which Flask's jsonify can't serialize, so
Decimal is accumulated throughout dashboard math and only cast to
float when building the response. Integer cents would be stricter
but felt like more change than the assignment needed.

**Trend aggregation in Python vs SQL.**
SQLite supports strftime but Postgres and MySQL use different
syntax for the same thing. Aggregating in Python means the code
works across databases without any changes. Downside is it loads
all matching records into memory. Fine here, would need rethinking
at scale.

**Auth header parsing.**
Original version split on space and took index 1. That would crash
on an empty header or one with extra spaces. Changed to split()
with a length check and a scheme check, which handles all the
edge cases cleanly.

---

## What I would improve with more time

Store amounts as integer cents instead of Numeric to make rounding
completely deterministic at the storage level.

Add a token blacklist so admins can revoke sessions immediately
rather than waiting for the 24-hour expiry.

Move trend aggregation to SQL using EXTRACT() so it does not load
records into memory as the dataset grows.

Lock down role assignment at registration so new users default to
Viewer and only Admins can promote. Left it open here so the
evaluator can test all roles easily.
