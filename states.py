import json
from database import db

def set_state(user_id, state, context=None):
    ctx = json.dumps(context, ensure_ascii=False) if context is not None else None
    with db() as conn:
        conn.execute("""
            INSERT INTO sessions (user_id, state, context, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                state=excluded.state,
                context=excluded.context,
                updated_at=CURRENT_TIMESTAMP
        """, (user_id, state, ctx))

def get_state(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE user_id=?", (user_id,)).fetchone()
        if not row: return None, None
        return row["state"], (json.loads(row["context"]) if row["context"] else None)

def clear_state(user_id):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))