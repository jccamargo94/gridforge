import time
import traceback

from app.db.claim import claim_next_pending_run
from app.db.session import get_engine, get_sessionmaker
from app.scheduler.executor import execute_run

POLL_INTERVAL_SECONDS = 5


def process_once(session, *, data_dir: str = "data", results_root: str = "data/results") -> bool:
    run = claim_next_pending_run(session)
    if run is None:
        return False
    execute_run(session, run, data_dir=data_dir, results_root=results_root)
    return True


def main() -> None:
    engine = get_engine()
    session_factory = get_sessionmaker(engine)
    while True:
        with session_factory() as session:
            try:
                processed = process_once(session)
            except Exception:
                traceback.print_exc()
                processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
