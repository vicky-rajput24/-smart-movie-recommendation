"""
=============================================================
  CineAI — Auth Routes (Login / Register / Verify)
=============================================================
  app.py mein add karo:
    from auth_routes import auth_bp
    app.register_blueprint(auth_bp)

  Install:
    pip install flask-bcrypt pyjwt
=============================================================
"""

from flask import Blueprint, request, jsonify
import json
import os
import re
import time
import hashlib
import secrets
import datetime
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# ─── CONFIG ───────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'data', 'users.json')
SECRET_KEY = 'cineai_super_secret_2024_change_this'  # ← Production mein change karo!
TOKEN_EXPIRY_HOURS = 24

# ─── SIMPLE USER DB (JSON file) ───────────────────────────
# Production mein SQLite/PostgreSQL use karo
def load_users():
    if not os.path.exists(DB_PATH):
        return {}
    with open(DB_PATH, 'r') as f:
        return json.load(f)

def save_users(users):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, 'w') as f:
        json.dump(users, f, indent=2)

# ─── PASSWORD HASHING (Bcrypt-style using hashlib) ────────
def hash_password(password: str) -> str:
    """Password ko SHA-256 + salt se hash karta hai"""
    salt   = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored: str) -> bool:
    """Stored hash se password verify karta hai"""
    try:
        salt, hashed = stored.split(':')
        check = hashlib.sha256((password + salt).encode()).hexdigest()
        return secrets.compare_digest(check, hashed)  # timing attack safe
    except Exception:
        return False

# ─── TOKEN ────────────────────────────────────────────────
def create_token(user_id: str, username: str) -> str:
    """Simple JWT-like token banata hai"""
    payload = {
        'user_id'  : user_id,
        'username' : username,
        'exp'      : int(time.time()) + TOKEN_EXPIRY_HOURS * 3600,
        'iat'      : int(time.time())
    }
    payload_str = json.dumps(payload, separators=(',',':'))
    payload_b64 = payload_str.encode().hex()
    signature   = hashlib.sha256((payload_b64 + SECRET_KEY).encode()).hexdigest()
    return f"{payload_b64}.{signature}"

def verify_token(token: str) -> dict | None:
    """Token verify karta hai, payload return karta hai ya None"""
    try:
        payload_b64, signature = token.split('.')
        expected = hashlib.sha256((payload_b64 + SECRET_KEY).encode()).hexdigest()
        if not secrets.compare_digest(expected, signature):
            return None
        payload = json.loads(bytes.fromhex(payload_b64).decode())
        if payload['exp'] < int(time.time()):
            return None  # Token expire ho gaya
        return payload
    except Exception:
        return None

# ─── VALIDATION ───────────────────────────────────────────
def validate_email(email: str) -> bool:
    return bool(re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email))

def validate_username(username: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_]{3,30}$', username))

def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password min 8 characters ka hona chahiye"
    if not re.search(r'[0-9]', password):
        return False, "Password mein kam se kam ek number hona chahiye"
    return True, "OK"

# ─── RATE LIMITING (simple in-memory) ────────────────────
_login_attempts = {}   # ip → [timestamp, ...]
MAX_ATTEMPTS    = 10
WINDOW_SEC      = 300  # 5 minutes

def is_rate_limited(ip: str) -> bool:
    now   = time.time()
    times = _login_attempts.get(ip, [])
    times = [t for t in times if now - t < WINDOW_SEC]  # cleanup old
    _login_attempts[ip] = times
    if len(times) >= MAX_ATTEMPTS:
        return True
    times.append(now)
    _login_attempts[ip] = times
    return False

# ─── REGISTER ─────────────────────────────────────────────
@auth_bp.route('/register', methods=['POST'])
def register():
    ip   = request.remote_addr
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status":"error","message":"Invalid request body"}), 400

    # Extract fields
    first_name = str(data.get('first_name', '')).strip()[:50]
    last_name  = str(data.get('last_name',  '')).strip()[:50]
    username   = str(data.get('username',   '')).strip().lower()[:30]
    email      = str(data.get('email',      '')).strip().lower()[:100]
    password   = str(data.get('password',   ''))

    # Validate
    if not all([first_name, last_name, username, email, password]):
        return jsonify({"status":"error","message":"Saare fields required hain"}), 400

    if not validate_email(email):
        return jsonify({"status":"error","message":"Invalid email format","field":"email"}), 400

    if not validate_username(username):
        return jsonify({"status":"error","message":"Username 3-30 chars, only letters/numbers/_","field":"username"}), 400

    pwd_ok, pwd_msg = validate_password(password)
    if not pwd_ok:
        return jsonify({"status":"error","message":pwd_msg,"field":"password"}), 400

    # Check duplicate
    users = load_users()
    for uid, u in users.items():
        if u['email'] == email:
            return jsonify({"status":"error","message":"Email already registered","field":"email"}), 409
        if u['username'] == username:
            return jsonify({"status":"error","message":"Username already taken","field":"username"}), 409

    # Create user
    user_id = secrets.token_hex(8)
    users[user_id] = {
        "id"         : user_id,
        "first_name" : first_name,
        "last_name"  : last_name,
        "username"   : username,
        "email"      : email,
        "password"   : hash_password(password),
        "created_at" : datetime.datetime.utcnow().isoformat(),
        "role"       : "user"
    }
    save_users(users)

    return jsonify({
        "status"  : "success",
        "message" : f"Account ban gaya! Welcome, {first_name}!",
        "user_id" : user_id
    }), 201

# ─── LOGIN ────────────────────────────────────────────────
@auth_bp.route('/login', methods=['POST'])
def login():
    ip   = request.remote_addr
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status":"error","message":"Invalid request"}), 400

    # Rate limit
    if is_rate_limited(ip):
        return jsonify({"status":"error","message":"Too many login attempts. Please wait."}), 429

    identifier = str(data.get('identifier', '')).strip().lower()
    password   = str(data.get('password',   ''))

    if not identifier or not password:
        return jsonify({"status":"error","message":"Identifier aur password zaroori hain"}), 400

    # Find user (by email OR username)
    users     = load_users()
    found_uid = None
    found_user= None
    for uid, u in users.items():
        if u['email'] == identifier or u['username'] == identifier:
            found_uid  = uid
            found_user = u
            break

    if not found_user or not verify_password(password, found_user['password']):
        return jsonify({"status":"error","message":"Invalid email/username or password"}), 401

    # Create token
    token = create_token(found_uid, found_user['username'])

    # Safe user data (no password)
    safe_user = {
        "id"        : found_uid,
        "first_name": found_user['first_name'],
        "last_name" : found_user['last_name'],
        "username"  : found_user['username'],
        "email"     : found_user['email'],
        "role"      : found_user.get('role','user')
    }

    return jsonify({
        "status" : "success",
        "message": "Login successful!",
        "token"  : token,
        "user"   : safe_user
    }), 200

# ─── VERIFY TOKEN ─────────────────────────────────────────
@auth_bp.route('/verify', methods=['GET'])
def verify():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"status":"error","message":"Token missing"}), 401

    token   = auth_header[7:]
    payload = verify_token(token)
    if not payload:
        return jsonify({"status":"error","message":"Token invalid ya expire ho gaya"}), 401

    users = load_users()
    user  = users.get(payload['user_id'])
    if not user:
        return jsonify({"status":"error","message":"User nahi mila"}), 404

    return jsonify({
        "status": "success",
        "user"  : {
            "id"        : payload['user_id'],
            "username"  : payload['username'],
            "first_name": user['first_name'],
            "role"      : user.get('role','user')
        }
    }), 200

# ─── LOGOUT ───────────────────────────────────────────────
@auth_bp.route('/logout', methods=['POST'])
def logout():
    # Client side token delete karta hai — server stateless hai
    return jsonify({"status":"success","message":"Logged out successfully"}), 200
