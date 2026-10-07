"""
Reset LifeLine operational state without deleting registered users.

Run from the project root:
    python reset_demo.py
"""

from backend import database as db
from psycopg.types.json import Jsonb


def reset():
    with db.get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM requests")
            cur.execute("DELETE FROM emergencies")

            cur.execute("SELECT id, data FROM ambulances")
            rows = cur.fetchall()

            for row in rows:
                ambulance = dict(row["data"] or {})
                ambulance["available"] = True
                ambulance["emergency"] = False

                for key in (
                    "offered_to",
                    "offer_expires_at",
                    "offer_distance_km",
                    "offered_at",
                ):
                    ambulance.pop(key, None)

                cur.execute("""
                    UPDATE ambulances
                    SET data = %s, updated_at = NOW()
                    WHERE id = %s
                """, (Jsonb(ambulance), row["id"]))

        conn.commit()

    print("LifeLine operational data reset successfully.")
    print("Registered users and ambulance definitions were kept.")
    print("All ambulances are available.")


if __name__ == "__main__":
    reset()
