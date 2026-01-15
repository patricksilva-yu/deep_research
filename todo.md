# Session-Based Authentication with PostgreSQL

## Overview
Add session-based authentication to the FastAPI app, protecting all routes (frontend + API) with PostgreSQL for user storage.

## Files to Create

### 1. `auth/__init__.py` - Empty init file

### 2. `auth/database.py` - SQLAlchemy async setup
- Async engine with `asyncpg` driver
- Session maker factory
- `Base` declarative class
- `get_db()` dependency for sessions
- `init_db()` to create tables on startup

### 3. `auth/models.py` - User model
```python
class User(Base):
    id, email, hashed_password, full_name, is_active, created_at, updated_at
```

### 4. `auth/security.py` - Password & session utilities
- `hash_password()` / `verify_password()` using bcrypt
- `create_session_token()` / `verify_session_token()` using itsdangerous

### 5. `auth/dependencies.py` - FastAPI dependencies
- `get_current_user()` - Returns 401 if not authenticated (for API routes)
- `get_current_user_optional()` - Returns None if not authenticated (for HTML routes that redirect)

### 6. `auth/router.py` - Auth endpoints
- `GET /sign-in` - Render login form
- `POST /sign-in` - Handle login, set session cookie
- `POST /sign-out` - Clear session cookie
- `GET /register` - Render registration form
- `POST /register` - Create user, auto-login

### 7. `templates/register.html` - Registration form

### 8. `scripts/create_user.py` - CLI script to create initial user

## Files to Modify

### 1. `requirements.txt`
Add:
```
sqlalchemy[asyncio]
asyncpg
passlib[bcrypt]
itsdangerous
python-multipart
```

### 2. `main.py`
- Add `lifespan` context manager to call `init_db()` on startup
- Import and include `auth_router`
- Add `Depends(get_current_user)` to API routers
- Update `/` and `/chat` routes to check auth and redirect to sign-in
- Keep `/health` public

### 3. `templates/signin.html`
Replace placeholder with actual login form (email, password, error display)

### 4. `templates/base.html`
Update nav to show user email + sign-out button when logged in

### 5. `.env.example`
Add:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/hivemind
SECRET_KEY=your-secret-key
```

### 6. `Dockerfile`
Add `libpq-dev` for PostgreSQL client library

### 7. `docker-compose.yml`
Add PostgreSQL service for local development

## Implementation Order
1. Add dependencies to `requirements.txt`
2. Create `auth/` module (database, models, security, dependencies, router)
3. Update `main.py` with auth integration
4. Update templates (signin.html, base.html, create register.html)
5. Update Docker configs
6. Create initial user script

## Verification
1. Run locally with `docker-compose up` (includes PostgreSQL)
2. Test sign-in with invalid credentials shows error
3. Test sign-in with valid credentials redirects to `/`
4. Test accessing `/chat` without auth redirects to `/sign-in?next=/chat`
5. Test API endpoints return 401 without session cookie
6. Test sign-out clears cookie and redirects to sign-in
