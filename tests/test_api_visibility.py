from datetime import date

from app.db import queries


def _public_run(api_client, level="ideal", grade="provisional", user=None):
    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level=level,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=user,
        visibility="public",
        input_grade=grade,
    )
    session.close()
    return run.id


def test_manual_run_stays_private_with_null_grade(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]
    body = api_client.get(f"/runs/{run_id}").json()
    assert body["visibility"] == "private"
    assert body["input_grade"] is None


def test_list_shows_own_private_and_others_public_runs(api_client):
    own = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    other_public = _public_run(api_client)

    resp = api_client.get("/runs")
    assert resp.status_code == 200
    rows = {r["run_id"]: r for r in resp.json()}
    assert own.json()["run_id"] in rows
    assert rows[other_public]["visibility"] == "public"
    assert rows[other_public]["input_grade"] == "provisional"


def test_other_users_private_run_is_invisible_and_404(api_client):
    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
        visibility="private",
    )
    run_id = run.id
    session.close()

    listed = {r["run_id"] for r in api_client.get("/runs").json()}
    assert run_id not in listed
    assert api_client.get(f"/runs/{run_id}").status_code == 404


def test_public_run_detail_log_and_artifact_available_to_any_user(api_client, tmp_path):
    run_id = _public_run(api_client)
    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)

    out_dir = tmp_path / "results" / run_id
    out_dir.mkdir(parents=True)
    price = out_dir / "price.csv"
    price.write_text("datetime,ideal_marginal_price\n2024-04-18 00:00:00,180000.0\n")
    log = out_dir / "run.log"
    log.write_text("solver log line\n")
    run.log_path = str(log)
    run.price_path = str(price)
    run.status = "done"
    session.commit()
    session.close()

    assert api_client.get(f"/runs/{run_id}").status_code == 200
    assert api_client.get(f"/runs/{run_id}/log").status_code == 200
    assert api_client.get(f"/runs/{run_id}/prices").status_code == 200
