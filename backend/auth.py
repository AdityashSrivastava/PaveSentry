import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

import jwt
import bcrypt
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from database.db_manager import (
    get_user_by_email,
    get_user_by_id,
    create_user,
    update_user_last_login,
    DB_PATH
)

# Cryptographically sound secret key (at least 64 bytes for HS256)
JWT_SECRET_KEY = os.environ.get(
    "PAVESENTRY_JWT_SECRET",
    "pavesentry_super_secure_delhi_pavement_management_jwt_secret_key_2026_at_least_64_bytes!!"
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
COOKIE_NAME = "pavesentry_token"

# Canonical Role Definitions
ROLE_PWD_ENGINEER = "pwd_engineer"
ROLE_MCD_PLANNER = "mcd_planner"
ROLE_CRRI_AUDITOR = "crri_auditor"

ROLE_DISPLAY_NAMES = {
    ROLE_PWD_ENGINEER: "Delhi PWD Division Engineer",
    ROLE_MCD_PLANNER: "MCD Urban Planner",
    ROLE_CRRI_AUDITOR: "CSIR-CRRI Auditor"
}

ROLE_PERMISSIONS = {
    ROLE_PWD_ENGINEER: {
        "can_retrain": True,
        "can_predict": True,
        "can_live_sync": True,
        "can_upload_surveys": True,
        "can_report_potholes": True,
        "can_update_potholes": True,
        "can_export": True,
        "can_audit_validate": True,
        "description": "Full engineering write, model retraining, field survey ingestion, and work schedule export authority."
    },
    ROLE_MCD_PLANNER: {
        "can_retrain": False,
        "can_predict": False,
        "can_live_sync": False,
        "can_upload_surveys": False,
        "can_report_potholes": True,
        "can_update_potholes": True,
        "can_export": True,
        "can_audit_validate": False,
        "description": "Read-only access to prioritization scores and budget allocations; can report ward potholes and export schedules."
    },
    ROLE_CRRI_AUDITOR: {
        "can_retrain": False,
        "can_predict": True,
        "can_live_sync": False,
        "can_upload_surveys": True,
        "can_report_potholes": True,
        "can_update_potholes": False,
        "can_export": True,
        "can_audit_validate": True,
        "description": "Pavement roughness audit verification, IRC:82 compliance certification, and profilometer survey ingestion."
    }
}

def canonicalize_role(role_input: str) -> str:
    """Normalizes role strings to canonical identifiers."""
    if not role_input:
        return ROLE_PWD_ENGINEER
    r = role_input.strip().lower()
    if "pwd" in r or "engineer" in r:
        return ROLE_PWD_ENGINEER
    if "mcd" in r or "planner" in r or "urban" in r:
        return ROLE_MCD_PLANNER
    if "crri" in r or "audit" in r:
        return ROLE_CRRI_AUDITOR
    return ROLE_PWD_ENGINEER

def hash_password(plain_password: str) -> str:
    """Hashes a password using bcrypt with standard salt rounds."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generates a signed JWT with expiration timestamp."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT signature and expiration."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

# Optional Bearer HTTP security header extractor
security = HTTPBearer(auto_error=False)

def extract_token_from_request(request: Request, creds: Optional[HTTPAuthorizationCredentials] = None) -> Optional[str]:
    """Extracts JWT token from Authorization header or HttpOnly cookie."""
    if creds and creds.credentials:
        return creds.credentials
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None

def get_current_user(request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, Any]:
    """
    FastAPI Dependency: Authenticates request and returns the authenticated user dictionary.
    Raises HTTP 401 if token is missing or invalid.
    """
    token = extract_token_from_request(request, creds)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to your Delhi government account.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing subject claim."
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists."
        )

    canonical_role = canonicalize_role(user["role"])
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": canonical_role,
        "role_display": ROLE_DISPLAY_NAMES.get(canonical_role, user["role"]),
        "division": user["division"],
        "permissions": ROLE_PERMISSIONS.get(canonical_role, {})
    }

def get_optional_user(request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[Dict[str, Any]]:
    """FastAPI Dependency: Returns authenticated user if present, or None if guest."""
    try:
        return get_current_user(request, creds)
    except HTTPException:
        return None

def require_role(allowed_roles: List[str]):
    """
    FastAPI Dependency Factory: Enforces role-based endpoint access.
    Raises HTTP 403 Forbidden if user's role is not in allowed_roles.
    """
    def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = user.get("role")
        canonical_allowed = [canonicalize_role(r) for r in allowed_roles]
        if user_role not in canonical_allowed:
            allowed_names = [ROLE_DISPLAY_NAMES.get(r, r) for r in canonical_allowed]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: Action restricted to {' / '.join(allowed_names)}. Your account role is '{user.get('role_display', user_role)}'."
            )
        return user
    return role_checker

def seed_default_users(db_path=DB_PATH):
    """Ensures official seeded test accounts exist with bcrypt-hashed credentials."""
    default_accounts = [
        {
            "user_id": "usr-pwd-001",
            "email": "engineer@pwd.delhi.gov.in",
            "password": "delhi2026pwd",
            "full_name": "Er. Rajesh Sharma",
            "role": ROLE_PWD_ENGINEER,
            "division": "PWD South Division (M-11)"
        },
        {
            "user_id": "usr-mcd-002",
            "email": "planner@mcd.delhi.gov.in",
            "password": "delhi2026mcd",
            "full_name": "Ananya Verma",
            "role": ROLE_MCD_PLANNER,
            "division": "MCD Urban Planning HQ"
        },
        {
            "user_id": "usr-crri-003",
            "email": "auditor@crri.delhi.res.in",
            "password": "delhi2026crri",
            "full_name": "Dr. Vikram Sengupta",
            "role": ROLE_CRRI_AUDITOR,
            "division": "CSIR-CRRI Pavement Research Division"
        }
    ]

    for acc in default_accounts:
        existing = get_user_by_email(acc["email"], db_path=db_path)
        if not existing:
            hashed_pw = hash_password(acc["password"])
            create_user(
                user_id=acc["user_id"],
                email=acc["email"],
                hashed_password=hashed_pw,
                full_name=acc["full_name"],
                role=acc["role"],
                division=acc["division"],
                db_path=db_path
            )
            print(f"Seeded official user account: {acc['email']} ({acc['role']})")
