"""
LifeLine PostgreSQL database layer.

All persistent application data is stored in PostgreSQL:
- users
- ambulances
- hospitals
- requests
- emergencies

The Flask application keeps using the same helper functions
(load_data, save_data, find_user, create_user, etc.), so the
existing API/workflow does not need to be rewritten just because
the database engine changed.

Set DATABASE_URL in .env, for example:
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/lifeline_db
"""

import os
from datetime import datetime
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to .env, for example: "
        "DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/lifeline_db"
    )


@contextmanager
def get_db_connection():
    """Open one PostgreSQL connection and always close it safely."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Create the PostgreSQL tables and indexes required by LifeLine."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    role VARCHAR(20) NOT NULL,
                    mobile VARCHAR(80) NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (role, mobile)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ambulances (
                    id VARCHAR(120) PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS hospitals (
                    id VARCHAR(120) PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id VARCHAR(120) PRIMARY KEY,
                    status VARCHAR(40),
                    request_timestamp TIMESTAMPTZ,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS emergencies (
                    id VARCHAR(120) PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_role_mobile
                ON users (role, mobile)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_requests_status
                ON requests (status)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_requests_timestamp
                ON requests (request_timestamp)
            """)

        conn.commit()


# Create tables as soon as the backend starts.
init_database()


def _parse_timestamp(value):
    """Convert the app's ISO timestamp into a PostgreSQL timestamp."""
    if not value:
        return None

    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _clean_user(record):
    """Return a normal Python dictionary for a user record."""
    return dict(record) if record else None


def _get_users(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, role, mobile, data
            FROM users
            ORDER BY id
        """)
        rows = cur.fetchall()

    users = []
    for row in rows:
        user = dict(row["data"] or {})
        # Keep the database id/role/mobile authoritative.
        user["id"] = row["id"]
        user["role"] = row["role"]
        user["mobile"] = row["mobile"]
        users.append(user)

    return users


def _get_records(conn, table_name):
    """Read JSON records from a known application table."""
    allowed = {
        "ambulances",
        "hospitals",
        "requests",
        "emergencies",
    }

    if table_name not in allowed:
        raise ValueError("Invalid table name")

    order = "ORDER BY id"
    if table_name == "requests":
        order = "ORDER BY COALESCE(request_timestamp, created_at) DESC"

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT data FROM {table_name} {order}"
        )
        return [
            dict(row["data"] or {})
            for row in cur.fetchall()
        ]


def load_data():
    """
    Return the same dictionary shape used by the existing Flask code.

    Unlike the old implementation, this reads everything from PostgreSQL.
    No SQLite file and no sample.json are used at runtime.
    """
    with get_db_connection() as conn:
        return {
            "users": _get_users(conn),
            "otps": [],
            "ambulances": _get_records(conn, "ambulances"),
            "hospitals": _get_records(conn, "hospitals"),
            "requests": _get_records(conn, "requests"),
            "emergencies": _get_records(conn, "emergencies"),
        }


def _upsert_user(cur, user):
    role = str(user.get("role", "")).strip()
    mobile = str(user.get("mobile", "")).strip()

    if role not in {"patient", "driver", "hospital"}:
        raise ValueError("Invalid user role.")

    if not mobile:
        raise ValueError("Mobile number is required.")

    data = dict(user)
    user_id = data.get("id")

    if user_id is not None:
        cur.execute("""
            INSERT INTO users (id, role, mobile, data, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                role = EXCLUDED.role,
                mobile = EXCLUDED.mobile,
                data = EXCLUDED.data,
                updated_at = NOW()
        """, (user_id, role, mobile, Jsonb(data)))
    else:
        cur.execute("""
            INSERT INTO users (role, mobile, data, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (role, mobile) DO UPDATE SET
                data = EXCLUDED.data,
                updated_at = NOW()
        """, (role, mobile, Jsonb(data)))


def _upsert_json_records(cur, table_name, records):
    allowed = {
        "ambulances",
        "hospitals",
        "requests",
        "emergencies",
    }

    if table_name not in allowed:
        raise ValueError("Invalid table name")

    for record in records or []:
        record = dict(record or {})
        record_id = record.get("id")

        if not record_id:
            # Current LifeLine records all have IDs. Skip malformed records
            # instead of creating an unusable database row.
            continue

        if table_name == "requests":
            status = record.get("status")
            request_timestamp = _parse_timestamp(
                record.get("timestamp")
            )

            cur.execute("""
                INSERT INTO requests
                    (id, status, request_timestamp, data, updated_at)
                VALUES
                    (%s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    request_timestamp = EXCLUDED.request_timestamp,
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """, (
                str(record_id),
                status,
                request_timestamp,
                Jsonb(record),
            ))
        else:
            cur.execute(f"""
                INSERT INTO {table_name}
                    (id, data, updated_at)
                VALUES
                    (%s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """, (
                str(record_id),
                Jsonb(record),
            ))


def save_data(data):
    """
    Persist the current application state to PostgreSQL.

    This keeps compatibility with the existing Flask workflow, which
    modifies a loaded dictionary and then calls save_data().
    """
    data = data or {}

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cur:
                for user in data.get("users", []):
                    _upsert_user(cur, user)

                _upsert_json_records(
                    cur,
                    "ambulances",
                    data.get("ambulances", []),
                )

                _upsert_json_records(
                    cur,
                    "hospitals",
                    data.get("hospitals", []),
                )

                _upsert_json_records(
                    cur,
                    "requests",
                    data.get("requests", []),
                )

                _upsert_json_records(
                    cur,
                    "emergencies",
                    data.get("emergencies", []),
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise


def get_ambulances():
    with get_db_connection() as conn:
        return _get_records(conn, "ambulances")


def update_ambulance(ambulance_id, updates):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT data
                FROM ambulances
                WHERE id = %s
                FOR UPDATE
            """, (str(ambulance_id),))

            row = cur.fetchone()
            if not row:
                return None

            ambulance = dict(row["data"] or {})
            ambulance.update(updates or {})

            cur.execute("""
                UPDATE ambulances
                SET data = %s, updated_at = NOW()
                WHERE id = %s
            """, (
                Jsonb(ambulance),
                str(ambulance_id),
            ))

        conn.commit()
        return ambulance


def get_hospitals():
    with get_db_connection() as conn:
        return _get_records(conn, "hospitals")


def get_requests():
    with get_db_connection() as conn:
        return _get_records(conn, "requests")


def create_request(request_dict):
    request_dict = dict(request_dict or {})
    request_id = request_dict.get("id")

    if not request_id:
        raise ValueError("Request id is required.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO requests
                    (id, status, request_timestamp, data, updated_at)
                VALUES
                    (%s, %s, %s, %s, NOW())
            """, (
                str(request_id),
                request_dict.get("status"),
                _parse_timestamp(request_dict.get("timestamp")),
                Jsonb(request_dict),
            ))
        conn.commit()

    return request_dict


def update_request(request_id, updates):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT data
                FROM requests
                WHERE id = %s
                FOR UPDATE
            """, (str(request_id),))

            row = cur.fetchone()
            if not row:
                return None

            request_data = dict(row["data"] or {})
            request_data.update(updates or {})

            cur.execute("""
                UPDATE requests
                SET status = %s,
                    request_timestamp = %s,
                    data = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                request_data.get("status"),
                _parse_timestamp(request_data.get("timestamp")),
                Jsonb(request_data),
                str(request_id),
            ))

        conn.commit()
        return request_data


def get_users():
    with get_db_connection() as conn:
        return _get_users(conn)


def find_user(mobile, role):
    mobile = str(mobile or "").strip()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, role, mobile, data
                FROM users
                WHERE mobile = %s
                  AND role = %s
                LIMIT 1
            """, (mobile, role))

            row = cur.fetchone()

    if not row:
        return None

    user = dict(row["data"] or {})
    user["id"] = row["id"]
    user["role"] = row["role"]
    user["mobile"] = row["mobile"]
    return user


def create_user(user_dict):
    user_dict = dict(user_dict or {})

    role = str(user_dict.get("role", "")).strip()
    mobile = str(user_dict.get("mobile", "")).strip()

    if role not in {"patient", "driver", "hospital"}:
        raise ValueError("Invalid user role.")

    if not mobile:
        raise ValueError("Mobile number is required.")

    password_hash = user_dict.get("password_hash", "")
    password = user_dict.get("password", "")

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cur:
                # Duplicate check gives the same friendly error as before.
                cur.execute("""
                    SELECT id
                    FROM users
                    WHERE mobile = %s AND role = %s
                    LIMIT 1
                """, (mobile, role))

                if cur.fetchone():
                    raise ValueError(
                        "A user with this mobile number already exists."
                    )

                data = dict(user_dict)
                data["mobile"] = mobile
                data["role"] = role
                data["password"] = password
                data["password_hash"] = password_hash

                cur.execute("""
                    INSERT INTO users (
                        role,
                        mobile,
                        data,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, NOW(), NOW())
                    RETURNING id
                """, (
                    role,
                    mobile,
                    Jsonb(data),
                ))

                user_id = cur.fetchone()["id"]

            conn.commit()

        except ValueError:
            conn.rollback()
            raise

        except Exception as error:
            conn.rollback()

            if "unique" in str(error).lower() and "mobile" in str(error).lower():
                raise ValueError(
                    "A user with this mobile number already exists."
                )

            raise ValueError(
                "Database error: " + str(error)
            )

    created_user = dict(user_dict)
    created_user["id"] = user_id
    return created_user
