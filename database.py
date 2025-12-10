import os
from datetime import datetime
import psycopg2
import psycopg2.extras

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "coffee_bot")
DB_USER = os.getenv("DB_USER", "coffee")
DB_PASSWORD = os.getenv("DB_PASSWORD", "coffee")

DEFAULT_THRESHOLD = 7
DEFAULT_PROMPT_INTERVAL = 3600  # seconds
DEFAULT_DRINK = 'coffee'


def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    conn.autocommit = True
    return conn


def init_db():
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                desire INTEGER DEFAULT 0,
                desire_type TEXT DEFAULT 'coffee',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id BIGINT,
                username TEXT,
                info TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS events_created_at_idx ON events(created_at)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS invites (
                code TEXT PRIMARY KEY,
                created_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                used_by BIGINT,
                used_at TIMESTAMPTZ,
                active BOOLEAN DEFAULT TRUE
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
    ensure_default_settings()

def add_user(user_id, username):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (user_id, username, desire, desire_type)
            VALUES (%s, %s, 0, %s)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
            """,
            (user_id, username, DEFAULT_DRINK),
        )

def set_desire(user_id, level):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE users SET desire = %s WHERE user_id = %s', (level, user_id))

def get_all_users():
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT user_id, username, desire, desire_type FROM users')
        rows = cursor.fetchall()
    return [
        {
            "user_id": row["user_id"],
            "username": row["username"],
            "desire": row["desire"],
            "desire_type": row.get("desire_type") or DEFAULT_DRINK,
        }
        for row in rows
    ]

def reset_desires():
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE users SET desire = 0')

def get_user(user_id):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT user_id, username, desire, desire_type FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
    if row:
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "desire": row["desire"],
            "desire_type": row.get("desire_type") or DEFAULT_DRINK,
        }
    return None

def user_exists(user_id):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT 1 FROM users WHERE user_id = %s', (user_id,))
        exists = cursor.fetchone() is not None
    return exists

def log_event(event_type, user_id=None, username=None, info=None):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO events (event_type, user_id, username, info) VALUES (%s, %s, %s, %s)',
            (event_type, user_id, username, info),
        )

def create_invite(code, created_by):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO invites (code, created_by, active, used_by, used_at)
            VALUES (%s, %s, TRUE, NULL, NULL)
            ON CONFLICT (code) DO UPDATE SET
                created_by = EXCLUDED.created_by,
                active = TRUE,
                used_by = NULL,
                used_at = NULL
            """,
            (code, created_by),
        )

def consume_invite(code, user_id, username):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE invites
            SET active = FALSE, used_by = %s, used_at = NOW()
            WHERE code = %s AND active = TRUE AND used_by IS NULL
            RETURNING 1
            """,
            (user_id, code),
        )
        row = cursor.fetchone()
    return row is not None

def get_coffee_events_since(days: int = 7):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            '''
            SELECT created_at FROM events
            WHERE event_type = 'coffee_consumed'
              AND created_at >= NOW() - INTERVAL %s
            ORDER BY created_at ASC
            ''',
            (f'{days} days',),
        )
        rows = cursor.fetchall()
    return [row["created_at"] for row in rows]

def weekly_coffee_stats():
    """Returns count and gap metrics for last 7 days."""
    events = get_coffee_events_since(7)
    return compute_gap_stats(events)

def get_all_coffee_events():
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            '''
            SELECT created_at FROM events
            WHERE event_type = 'coffee_consumed'
            ORDER BY created_at ASC
            '''
        )
        rows = cursor.fetchall()
    return [row["created_at"] for row in rows]

def compute_gap_stats(event_timestamps):
    """Given list of timestamp objects/strings, compute count and gap metrics."""
    count = len(event_timestamps)
    if count == 0:
        return {
            "count": 0,
            "shortest_gap": None,
            "longest_gap": None,
            "average_gap": None,
            "first_at": None,
            "last_at": None,
        }

    times = []
    for ts in event_timestamps:
        if isinstance(ts, datetime):
            times.append(ts)
        else:
            times.append(datetime.fromisoformat(str(ts)))

    times = sorted(times)
    if count == 1:
        return {
            "count": 1,
            "shortest_gap": None,
            "longest_gap": None,
            "average_gap": None,
            "first_at": times[0],
            "last_at": times[0],
        }

    gaps = []
    for prev, cur in zip(times, times[1:]):
        diff = (cur - prev).total_seconds()
        gaps.append(diff)

    avg_gap = sum(gaps) / len(gaps) if gaps else None
    return {
        "count": count,
        "shortest_gap": int(min(gaps)) if gaps else None,
        "longest_gap": int(max(gaps)) if gaps else None,
        "average_gap": int(avg_gap) if avg_gap is not None else None,
        "first_at": times[0],
        "last_at": times[-1],
    }

def all_time_coffee_stats():
    """Returns stats for all recorded coffee events."""
    return compute_gap_stats(get_all_coffee_events())

# -------- Settings helpers --------

def get_setting(key, default=None):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT value FROM settings WHERE key = %s', (key,))
        row = cursor.fetchone()
    if row is None:
        return default
    return row["value"]

def set_setting(key, value):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            ''',
            (key, str(value)),
        )

def ensure_default_settings():
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
            ''',
            ('threshold', DEFAULT_THRESHOLD),
        )
        cursor.execute(
            '''
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
            ''',
            ('prompt_interval', DEFAULT_PROMPT_INTERVAL),
        )

# -------- Drink helpers --------

def set_desire_type(user_id, drink_code):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE users SET desire_type = %s WHERE user_id = %s', (drink_code, user_id))

def get_desire_type(user_id):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT desire_type FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
    if row is None or row.get("desire_type") is None:
        return DEFAULT_DRINK
    return row["desire_type"]

# -------- Stats per user --------

def user_weekly_stats(days: int = 7):
    """
    Aggregate per-user stats for the last N days:
    - want_count: how many times user set desire
    - drink_selects: how many times each drink was selected
    - consumed_total: coffee_consumed events
    - consumed_by_drink: coffee_consumed grouped by drink
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            '''
            SELECT user_id, username, event_type, info
            FROM events
            WHERE created_at >= NOW() - INTERVAL %s
            ''',
            (f'{days} days',),
        )
        rows = cursor.fetchall()

    def parse_drink(info_value):
        if not info_value:
            return DEFAULT_DRINK
        if info_value.startswith('drink:'):
            return info_value.split(':', 1)[1]
        return info_value

    stats = {}
    for user_id, username, event_type, info in rows:
        if user_id is None:
            continue
        if user_id not in stats:
            stats[user_id] = {
                'user_id': user_id,
                'username': username,
                'want_count': 0,
                'drink_selects': {},
                'consumed_total': 0,
                'consumed_by_drink': {},
            }
        entry = stats[user_id]

        if event_type == 'set_desire':
            entry['want_count'] += 1
        elif event_type == 'set_drink':
            drink = parse_drink(info)
            entry['drink_selects'][drink] = entry['drink_selects'].get(drink, 0) + 1
        elif event_type == 'coffee_consumed':
            drink = parse_drink(info)
            entry['consumed_total'] += 1
            entry['consumed_by_drink'][drink] = entry['consumed_by_drink'].get(drink, 0) + 1

    return list(stats.values())

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
