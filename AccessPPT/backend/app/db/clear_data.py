"""
Script to delete all default/sample presentation and accessibility data.
"""
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal, sync_engine
from app.db.base import Base

def clear_all_data():
    with sync_engine.connect() as conn:
        print("Clearing all presentations and associated accessibility data...")
        conn.execute(text("DELETE FROM verification_results"))
        conn.execute(text("DELETE FROM reports"))
        conn.execute(text("DELETE FROM analysis_runs"))
        conn.execute(text("DELETE FROM remediation_actions"))
        conn.execute(text("DELETE FROM ai_suggestions"))
        conn.execute(text("DELETE FROM accessibility_issues"))
        conn.execute(text("DELETE FROM slide_objects"))
        conn.execute(text("DELETE FROM slides"))
        conn.execute(text("DELETE FROM presentations"))
        conn.commit()
        print("Successfully deleted all default presentation data!")

if __name__ == "__main__":
    clear_all_data()
