"""Populate the local opportunity store from the configured public Luma source."""
from api.main import DB, db, run_event_pipeline
from opportunity_engine.db import all_opportunities

def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = db()
    connection.close()
    run_event_pipeline()
    count = len([item for item in all_opportunities() if item.source == "luma"])
    print(f"Loaded {count} Luma opportunities into {DB}")

if __name__ == "__main__":
    main()
