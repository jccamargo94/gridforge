from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_head_creates_all_tables(tmp_path):
    db_path = tmp_path / "migration_smoke.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert {"scenarios", "cases", "runs", "metric_sets"}.issubset(tables)


def test_alembic_upgrade_head_adds_runs_log_path_column(tmp_path):
    db_path = tmp_path / "migration_smoke_log.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    assert "log_path" in columns


def test_alembic_upgrade_head_creates_input_datasets_table(tmp_path):
    db_path = tmp_path / "migration_smoke_input_datasets.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "input_datasets" in tables

    columns = {c["name"] for c in inspect(engine).get_columns("input_datasets")}
    assert {
        "id",
        "dataset",
        "partition_key",
        "source",
        "checksum",
        "row_count",
        "fetched_at",
    }.issubset(columns)

    unique_constraints = inspect(engine).get_unique_constraints("input_datasets")
    constraint_names = {c["name"] for c in unique_constraints}
    assert "uq_input_datasets_dataset_partition_key" in constraint_names


def test_alembic_upgrade_head_adds_dispatch_metric_columns(tmp_path):
    db_path = tmp_path / "migration_smoke_dispatch.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)

    metric_columns = {c["name"] for c in inspect(engine).get_columns("metric_sets")}
    assert {"dispatch_mae_mw", "dispatch_rmse_mw"}.issubset(metric_columns)

    run_columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    assert "marginal_plants_path" in run_columns


def test_alembic_upgrade_head_adds_nodal_results_table_and_case_column(tmp_path):
    db_path = tmp_path / "migration_smoke_nodal.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "nodal_results" in tables

    columns = {c["name"] for c in inspect(engine).get_columns("nodal_results")}
    assert {
        "id",
        "run_id",
        "metrics",
        "redistribution",
        "gen_revenue_by_zone",
        "network",
        "lmp_path",
        "dispatch_path",
        "branch_flows_path",
        "settlement_status_quo_path",
        "settlement_lmp_path",
        "comparison_path",
        "summary_path",
    }.issubset(columns)

    unique_constraints = inspect(engine).get_unique_constraints("nodal_results")
    assert {c["name"] for c in unique_constraints} == {"uq_nodal_results_run_id"}

    case_columns = {c["name"] for c in inspect(engine).get_columns("cases")}
    assert "nodal_network" in case_columns

    command.downgrade(cfg, "0004")

    tables = set(inspect(engine).get_table_names())
    assert "nodal_results" not in tables

    case_columns = {c["name"] for c in inspect(engine).get_columns("cases")}
    assert "nodal_network" not in case_columns


def test_alembic_upgrade_head_adds_run_plans_and_daily_columns(tmp_path):
    db_path = tmp_path / "migration_smoke_daily.db"
    database_url = f"sqlite:///{db_path}"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert "run_plans" in tables

    plan_columns = {c["name"] for c in inspect(engine).get_columns("run_plans")}
    assert {
        "id",
        "kind",
        "target_date",
        "status",
        "attempts",
        "due_at",
        "run_id",
        "error",
        "created_at",
        "started_at",
        "finished_at",
    }.issubset(plan_columns)
    unique_constraints = inspect(engine).get_unique_constraints("run_plans")
    assert {c["name"] for c in unique_constraints} == {"uq_run_plans_kind_target_date"}

    run_columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    assert {"visibility", "input_grade"}.issubset(run_columns)
    user_id_nullable = next(
        c for c in inspect(engine).get_columns("runs") if c["name"] == "user_id"
    )
    assert user_id_nullable["nullable"] is True

    metric_columns = {c["name"] for c in inspect(engine).get_columns("metric_sets")}
    assert {"reference", "evaluated_at"}.issubset(metric_columns)

    command.downgrade(cfg, "0005")
    tables = set(inspect(engine).get_table_names())
    assert "run_plans" not in tables
    run_columns = {c["name"] for c in inspect(engine).get_columns("runs")}
    assert "visibility" not in run_columns
    assert "input_grade" not in run_columns
    metric_columns = {c["name"] for c in inspect(engine).get_columns("metric_sets")}
    assert "reference" not in metric_columns
