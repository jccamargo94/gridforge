import contextlib
import io
import json
import logging
import time
import traceback

from sqlalchemy.orm import Session

from app.db import queries
from app.db.claim import claim_next_pending_run
from app.db.session import get_engine, get_sessionmaker
from app.pipeline.runner import run_case
from app.schemas import BessScenario, DispatchCase, DispatchLevel
from app.storage import get_storage

POLL_INTERVAL_SECONDS = 5


def _build_case(session: Session, case_row) -> DispatchCase:
    scenario = None
    if case_row.scenario_id is not None:
        scenario_row = queries.get_scenario(session, case_row.scenario_id)
        scenario = BessScenario(
            mode=scenario_row.mode,
            penetration_level=scenario_row.penetration_level,
            units=scenario_row.units,
        )
    return DispatchCase(
        dispatch_date=case_row.dispatch_date,
        level=DispatchLevel(case_row.level),
        solver=case_row.solver,
        compute_prices=case_row.compute_prices,
        bess_scenario=scenario,
    )


def process_once(
    session: Session, *, data_dir: str = "data", results_root: str = "data/results"
) -> bool:
    run = claim_next_pending_run(session)
    if run is None:
        return False

    out_dir = f"{results_root}/{run.id}"
    log_path = f"{out_dir}/run.log"

    try:
        case_row = queries.get_case(session, run.case_id)
        case = _build_case(session, case_row)

        if case_row.nodal_network:
            network_path = f"{out_dir}/network.json"
            with get_storage(".").open(network_path, "w") as f:
                json.dump(case_row.nodal_network, f)
            case.nodal_network = network_path

        # Close the read-only transaction _build_case's queries opened so the
        # session sits idle (not idle-in-transaction) for the duration of the
        # solve, instead of pinning a pooler connection with an open transaction.
        session.commit()

        # Egret/Pyomo emit their own warnings (e.g. the cbc dual-suffix
        # warning) via `logging`, not `print()` -- a logging.StreamHandler
        # bound to stderr at import time doesn't care that sys.stderr gets
        # swapped below, so redirect_stdout/redirect_stderr alone would miss
        # them and leave run.log empty even though the solver warned.
        log_buffer = io.StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)
        try:
            with contextlib.redirect_stdout(log_buffer), contextlib.redirect_stderr(log_buffer):
                result = run_case(
                    case, evaluate=True, out=out_dir, data_dir=data_dir, session=session
                )
        finally:
            root_logger.removeHandler(log_handler)

        with contextlib.suppress(OSError):
            with get_storage(".").open(log_path, "w") as f:
                f.write(log_buffer.getvalue())
            run.log_path = log_path

        if result.ok:
            if result.nodal is not None:
                queries.finish_nodal_run_ok(session, run, result, out_dir=out_dir)
            else:
                queries.finish_run_ok(session, run, result, out_dir=out_dir)
        else:
            queries.finish_run_failed(
                session, run, result.error or "unknown error", log_path=log_path
            )
        return True
    except Exception as exc:
        # Never let a per-run failure escape and crash the worker loop. Roll back
        # any aborted/broken transaction, then record the failure. Guard the
        # recording itself so a double-failure can't propagate either.
        session.rollback()
        try:
            queries.finish_run_failed(session, run, f"{type(exc).__name__}: {exc}")
        except Exception:
            traceback.print_exc()
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
