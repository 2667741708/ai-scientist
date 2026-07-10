from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi import Header, HTTPException


PASSWORD_ITERATIONS = 160_000
TOKEN_TTL_SECONDS = 24 * 60 * 60
LOCAL_ADMIN_USERNAME = "admin"
LOCAL_ADMIN_MIN_PASSWORD_LENGTH = 6

AUTH_ROOT = Path(os.getenv("COSCIENTIST_AUTH_ROOT", str(Path(__file__).resolve().parents[1] / ".auth")))
AUTH_DB_PATH = Path(os.getenv("COSCIENTIST_AUTH_DB_PATH", str(AUTH_ROOT / "accounts.sqlite3")))
LOCAL_ACCOUNT_SECRETS_PATH = Path(
    os.getenv("COSCIENTIST_LOCAL_ACCOUNT_SECRETS_PATH", str(AUTH_ROOT / "local-account-secrets.json"))
)
AUTH_SECRET = os.getenv("COSCIENTIST_AUTH_SECRET", "open-coscientist-local-dev-secret-change-me")
DEFAULT_ADMIN_EMAIL = os.getenv("COSCIENTIST_ADMIN_EMAIL", "haomingwang@stumail.ysu.edu.cn")
DEFAULT_ADMIN_PASSWORD = os.getenv("COSCIENTIST_ADMIN_PASSWORD", "ResearchAdmin123!")

ROLE_ALIASES = {"user": "researcher", "administrator": "admin"}
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "researcher": {
        "workspace:read",
        "workspace:write",
        "papers:read",
        "papers:write",
        "hypotheses:run",
        "reports:read",
    },
    "admin": {
        "workspace:read",
        "workspace:write",
        "papers:read",
        "papers:write",
        "hypotheses:run",
        "reports:read",
        "runtime:read",
        "runtime:write",
        "users:manage",
    },
}


def _now() -> float:
    return time.time()


def _connect() -> sqlite3.Connection:
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _normalize_email(email: str) -> str:
    value = email.strip().lower()
    if value == LOCAL_ADMIN_USERNAME:
        return value
    if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
        raise ValueError("邮箱格式不正确")
    if len(value) > 180:
        raise ValueError("邮箱长度超过限制")
    return value


def normalize_role(role: str) -> str:
    return ROLE_ALIASES.get(role.strip(), role.strip())


def permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(normalize_role(role), set()))


def _public_user(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": normalize_role(row["role"]),
        "permissions": permissions_for_role(row["role"]),
        "status": row["status"],
        "login_count": int(row["login_count"] or 0),
        "recovery_configured": bool(row["recovery_question"] and row["recovery_answer_hash"]),
        "last_login_at": row["last_login_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _read_local_account_secrets(path: Optional[Path] = None) -> Dict[str, Any]:
    secrets_path = path or LOCAL_ACCOUNT_SECRETS_PATH
    if not secrets_path.exists():
        return {
            "purpose": "本文件只用于本机开发时记录管理员明确设置过的账号密码备忘；.auth/ 已被 webapp/.gitignore 忽略，不要提交或同步到公共位置。",
            "database": str(AUTH_DB_PATH),
            "notes": [
                "后端账号数据库只保存 password_hash，不能从数据库反推出原始密码。",
                "管理员只能记录自己创建或重置时设置的密码，不能查看用户自行设置的原始密码。",
                "用户通过登录页忘记密码流程自行重置的密码不会写入本文件。",
            ],
            "accounts": [],
        }
    try:
        raw = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    accounts = raw.get("accounts")
    if not isinstance(accounts, list):
        accounts = []
    raw["accounts"] = accounts
    raw.setdefault("purpose", "本机账号密码备忘。")
    raw.setdefault("database", str(AUTH_DB_PATH))
    raw.setdefault("notes", [])
    return raw


def record_local_account_secret(
    user: Dict[str, Any],
    password: str,
    *,
    source: str,
    actor_email: str = "",
    path: Optional[Path] = None,
) -> Path:
    """Record admin-created/reset passwords in a local ignored memo file.

    This intentionally does not run during normal user login or self-service
    password recovery. It only records passwords an administrator explicitly set.
    """

    secrets_path = path or LOCAL_ACCOUNT_SECRETS_PATH
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_local_account_secrets(secrets_path)
    normalized_email = _normalize_email(str(user["email"]))
    account_record = {
        "id": user["id"],
        "email": normalized_email,
        "display_name": user.get("display_name", ""),
        "role": normalize_role(str(user.get("role", "researcher"))),
        "password": password,
        "source": source,
        "actor_email": actor_email,
        "updated_at": _now(),
        "note": "仅记录管理员创建账号或重置密码时明确设置过的密码。",
    }
    accounts = [item for item in payload["accounts"] if item.get("email") != normalized_email]
    accounts.append(account_record)
    payload["accounts"] = sorted(accounts, key=lambda item: str(item.get("email", "")))
    secrets_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return secrets_path


def init_auth_store() -> None:
    with _connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
              id TEXT PRIMARY KEY,
              email TEXT NOT NULL UNIQUE,
              display_name TEXT NOT NULL,
              role TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              password_hash TEXT NOT NULL,
              recovery_question TEXT NOT NULL DEFAULT '',
              recovery_answer_hash TEXT NOT NULL DEFAULT '',
              recovery_updated_at REAL,
              login_count INTEGER NOT NULL DEFAULT 0,
              last_login_at REAL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            )
            """
        )
        _ensure_account_column(db, "recovery_question", "TEXT NOT NULL DEFAULT ''")
        _ensure_account_column(db, "recovery_answer_hash", "TEXT NOT NULL DEFAULT ''")
        _ensure_account_column(db, "recovery_updated_at", "REAL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_role ON accounts(role)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
        db.commit()
    ensure_seed_admin()


def _ensure_account_column(db: sqlite3.Connection, name: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(accounts)").fetchall()}
    if name not in columns:
        db.execute(f"ALTER TABLE accounts ADD COLUMN {name} {definition}")


def _hash_secret(value: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_secret(value: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def hash_password(password: str, salt: Optional[bytes] = None, *, minimum_length: int = 8) -> str:
    if len(password) < minimum_length:
        raise ValueError(f"密码至少需要 {minimum_length} 个字符")
    return _hash_secret(password, salt)


def verify_password(password: str, password_hash: str) -> bool:
    return _verify_secret(password, password_hash)


def _account_password_minimum(email: str, role: str) -> int:
    if email == LOCAL_ADMIN_USERNAME and role == "admin":
        return LOCAL_ADMIN_MIN_PASSWORD_LENGTH
    return 8


def _normalize_recovery_question(question: str) -> str:
    value = " ".join(question.strip().split())
    if len(value) > 200:
        raise ValueError("密保问题长度超过限制")
    return value


def _normalize_recovery_answer(answer: str) -> str:
    return " ".join(answer.strip().casefold().split())


def hash_recovery_answer(answer: str, salt: Optional[bytes] = None) -> str:
    normalized = _normalize_recovery_answer(answer)
    if len(normalized) < 2:
        raise ValueError("密保答案至少需要 2 个字符")
    if len(normalized) > 200:
        raise ValueError("密保答案长度超过限制")
    return _hash_secret(normalized, salt)


def verify_recovery_answer(answer: str, answer_hash: str) -> bool:
    normalized = _normalize_recovery_answer(answer)
    if not normalized:
        return False
    return _verify_secret(normalized, answer_hash)


def create_account(
    email: str,
    password: str,
    display_name: str = "",
    role: str = "researcher",
    recovery_question: str = "",
    recovery_answer: str = "",
) -> Dict[str, Any]:
    normalized_email = _normalize_email(email)
    normalized_role = normalize_role(role)
    if normalized_role not in ROLE_PERMISSIONS:
        raise ValueError(f"不支持的角色：{role}")
    name = display_name.strip() or normalized_email.split("@", 1)[0]
    question = _normalize_recovery_question(recovery_question)
    if bool(question) != bool(recovery_answer.strip()):
        raise ValueError("密保问题和答案需要同时填写")
    recovery_hash = hash_recovery_answer(recovery_answer) if question else ""
    recovery_updated_at = _now() if question else None
    now = _now()
    with _connect() as db:
        try:
            cursor = db.execute(
                """
                INSERT INTO accounts (
                  id, email, display_name, role, status, password_hash,
                  recovery_question, recovery_answer_hash, recovery_updated_at,
                  login_count, last_login_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    f"acct_{uuid.uuid4().hex[:12]}",
                    normalized_email,
                    name,
                    normalized_role,
                    hash_password(
                        password,
                        minimum_length=_account_password_minimum(normalized_email, normalized_role),
                    ),
                    question,
                    recovery_hash,
                    recovery_updated_at,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("账号已存在") from exc
        db.commit()
        row = db.execute("SELECT * FROM accounts WHERE rowid = ?", (cursor.lastrowid,)).fetchone()
        return _public_user(row)


def ensure_seed_admin() -> Dict[str, Any]:
    normalized_email = _normalize_email(DEFAULT_ADMIN_EMAIL)
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE email = ?", (normalized_email,)).fetchone()
        if row:
            return _public_user(row)
    return create_account(
        normalized_email,
        DEFAULT_ADMIN_PASSWORD,
        display_name=os.getenv("COSCIENTIST_ADMIN_DISPLAY_NAME", "本地管理员"),
        role="admin",
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode((data + "=" * (-len(data) % 4)).encode("ascii"))


def _sign(payload: str) -> str:
    signature = hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64(signature)


def create_token(user: Dict[str, Any]) -> str:
    payload = _b64(
        json.dumps(
            {
                "sub": user["id"],
                "email": user["email"],
                "role": normalize_role(user["role"]),
                "exp": int(_now()) + TOKEN_TTL_SECONDS,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign(payload)}"


def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    if not hmac.compare_digest(_sign(payload), signature):
        raise HTTPException(status_code=401, detail="invalid token")
    data = json.loads(_unb64(payload))
    if int(data.get("exp", 0)) < int(_now()):
        raise HTTPException(status_code=401, detail="token expired")
    return data


def authenticate(email: str, password: str) -> Dict[str, Any]:
    init_auth_store()
    normalized_email = _normalize_email(email)
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE email = ?", (normalized_email,)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="邮箱或密码不正确")
        if row["status"] != "active":
            raise HTTPException(status_code=403, detail="账号已停用")
        now = _now()
        db.execute(
            "UPDATE accounts SET login_count = login_count + 1, last_login_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["id"]),
        )
        db.commit()
        updated = db.execute("SELECT * FROM accounts WHERE id = ?", (row["id"],)).fetchone()
        user = _public_user(updated)
        return {"access_token": create_token(user), "token_type": "bearer", "user": user}


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    init_auth_store()
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE id = ?", (user_id,)).fetchone()
    return _public_user(row) if row else None


def user_from_authorization(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token_data = decode_token(authorization.split(" ", 1)[1].strip())
    user = get_user_by_id(str(token_data.get("sub", "")))
    if not user or user["status"] != "active":
        raise HTTPException(status_code=401, detail="account disabled or missing")
    return user


def require_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    return user_from_authorization(authorization)


def require_permission(permission: str):
    def dependency(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        user = user_from_authorization(authorization)
        if permission not in set(user["permissions"]):
            raise HTTPException(status_code=403, detail=f"missing permission: {permission}")
        return user

    return dependency


def list_accounts() -> list[Dict[str, Any]]:
    init_auth_store()
    with _connect() as db:
        rows = db.execute("SELECT * FROM accounts ORDER BY created_at ASC").fetchall()
    return [_public_user(row) for row in rows]


def set_account_status(account_id: str, status: str) -> Dict[str, Any]:
    if status not in {"active", "disabled"}:
        raise ValueError("账号状态只能是 active 或 disabled")
    init_auth_store()
    now = _now()
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise FileNotFoundError("账号不存在")
        if row["role"] == "admin" and status != "active":
            active_admins = db.execute(
                "SELECT COUNT(*) FROM accounts WHERE role = 'admin' AND status = 'active'"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("不能停用最后一个管理员")
        db.execute("UPDATE accounts SET status = ?, updated_at = ? WHERE id = ?", (status, now, account_id))
        db.commit()
        updated = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return _public_user(updated)


def reset_account_password(account_id: str, password: str) -> Dict[str, Any]:
    init_auth_store()
    now = _now()
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise FileNotFoundError("账号不存在")
        minimum_length = _account_password_minimum(str(row["email"]), str(row["role"]))
        db.execute(
            "UPDATE accounts SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(password, minimum_length=minimum_length), now, account_id),
        )
        db.commit()
        updated = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return _public_user(updated)


def get_recovery_challenge(email: str) -> Dict[str, Any]:
    init_auth_store()
    normalized_email = _normalize_email(email)
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE email = ?", (normalized_email,)).fetchone()
    if not row:
        return {
            "available": False,
            "email": normalized_email,
            "message": "未找到已配置密保的账号，请联系管理员重置临时密码。",
        }
    if row["status"] != "active":
        return {
            "available": False,
            "email": normalized_email,
            "message": "账号已停用，请联系管理员恢复访问。",
        }
    if not row["recovery_question"] or not row["recovery_answer_hash"]:
        return {
            "available": False,
            "email": normalized_email,
            "message": "该账号未设置密保问题，请联系管理员重置临时密码。",
        }
    return {
        "available": True,
        "email": normalized_email,
        "question": row["recovery_question"],
        "message": "请回答密保问题并设置新密码。",
    }


def reset_password_with_recovery(email: str, answer: str, new_password: str) -> Dict[str, Any]:
    init_auth_store()
    normalized_email = _normalize_email(email)
    now = _now()
    with _connect() as db:
        row = db.execute("SELECT * FROM accounts WHERE email = ?", (normalized_email,)).fetchone()
        if not row or not row["recovery_question"] or not row["recovery_answer_hash"]:
            raise ValueError("该账号未设置密保问题，请联系管理员重置临时密码")
        if row["status"] != "active":
            raise ValueError("账号已停用，请联系管理员恢复访问")
        if not verify_recovery_answer(answer, row["recovery_answer_hash"]):
            raise ValueError("密保答案不正确")
        db.execute(
            "UPDATE accounts SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(new_password), now, row["id"]),
        )
        db.commit()
        updated = db.execute("SELECT * FROM accounts WHERE id = ?", (row["id"],)).fetchone()
        return _public_user(updated)


def role_rows() -> Iterable[Dict[str, Any]]:
    for role, permissions in ROLE_PERMISSIONS.items():
        yield {"role": role, "permissions": sorted(permissions)}
