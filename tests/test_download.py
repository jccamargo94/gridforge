from datetime import date

from app.data.download import (
    ensure_data_for_date,
    force_refresh_blob,
    save_file,
)
from app.storage import LocalStorage


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content


def test_save_file_writes_via_storage(monkeypatch, tmp_path):
    captured = {}

    def _fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse("file-contents-áéí".encode("utf-8"))

    monkeypatch.setattr("app.data.download.requests.get", _fake_get)
    storage = LocalStorage(str(tmp_path))
    save_file(file_type="OFEI", file_date=date(2024, 4, 18), storage=storage)

    assert captured["url"] == (
        "https://api-portalxm.xm.com.co/administracion-archivos/ficheros/descarga-archivo"
    )
    assert captured["params"] == {
        "ruta": "M:/InformacionAgentes/Usuarios/Publico/OFERTAS/INICIAL/2024-04/OFEI0418.txt",
        "nombreBlobContainer": "storageportalxm",
    }
    assert (tmp_path / "2024-04-18" / "OFEI0418.txt").read_text() == "file-contents-áéí"


def test_ensure_data_for_date_skips_when_all_files_exist(monkeypatch, tmp_path):
    """When all 6 files exist, ensure_data_for_date should skip all downloads."""
    (tmp_path / "2024-04-18").mkdir()
    # Pre-populate all 6 files with dummy content
    (tmp_path / "2024-04-18" / "OFEI0418.txt").write_text("existing")
    (tmp_path / "2024-04-18" / "dCondIniU0418.txt").write_text("existing")
    (tmp_path / "2024-04-18" / "dCondIniP0418.txt").write_text("existing")
    (tmp_path / "2024-04-18" / "PrId0418_NAL.txt").write_text("existing")
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text("existing")
    (tmp_path / "2024-04-18" / "dAGCUNIDAD0418.txt").write_text("existing")

    def _boom(*a, **k):
        raise AssertionError("save_file should not be called when all files exist")

    monkeypatch.setattr("app.data.download.save_file", _boom)
    folder = ensure_data_for_date(date(2024, 4, 18), data_dir=str(tmp_path))
    assert folder == tmp_path / "2024-04-18"


def test_ensure_data_for_date_fetches_missing_files(monkeypatch, tmp_path):
    """When some files are missing, they should be fetched (regression test for dAGCUNIDAD)."""
    (tmp_path / "2024-04-18").mkdir()
    # Pre-populate ONLY OFEI, simulating a folder that existed before dAGCUNIDAD was added
    (tmp_path / "2024-04-18" / "OFEI0418.txt").write_text("existing")

    fetched = []

    def _fake_save_file(file_type: str, file_date: date, storage) -> None:
        fetched.append(file_type)

    monkeypatch.setattr("app.data.download.save_file", _fake_save_file)
    ensure_data_for_date(date(2024, 4, 18), data_dir=str(tmp_path))

    # All file types except OFEI should be fetched
    assert "dAGCUNIDAD" in fetched, "dAGCUNIDAD should be fetched"
    assert "OFEI" not in fetched, "OFEI should not be re-fetched"
    # Exactly the 5 missing types should be fetched
    assert set(fetched) == {"dCondIniU", "dCondIniP", "PrId", "iMAR", "dAGCUNIDAD"}


def test_force_refresh_blob_overwrites_flat_and_organized_copies(monkeypatch, tmp_path):
    """Post-final-review: reeval needs the FINAL iMAR, and ensure_data_for_date
    never refreshes existing files — force_refresh_blob re-downloads and
    truncate-writes every local copy (flat + organized, which resolve_input
    prefers)."""
    captured = {}

    def _fake_get(url, params=None, **kwargs):
        captured["params"] = params
        return _FakeResponse("final-áé".encode("utf-8"))

    monkeypatch.setattr("app.data.download.requests.get", _fake_get)

    flat = tmp_path / "2024-04-18"
    flat.mkdir(parents=True)
    (flat / "iMAR0418.txt").write_text("stale")
    organized = tmp_path / "predespacho_ideal"
    organized.mkdir()
    (organized / "iMAR0418.txt").write_text("stale-organized")

    force_refresh_blob(file_type="iMAR", file_date=date(2024, 4, 18), data_dir=str(tmp_path))

    assert captured["params"] == {
        "ruta": "M:/InformacionAgentes/Usuarios/Publico/PredespachoIdeal/2024-04/iMAR0418.txt",
        "nombreBlobContainer": "storageportalxm",
    }
    assert (flat / "iMAR0418.txt").read_text() == "final-áé"
    assert (organized / "iMAR0418.txt").read_text() == "final-áé"


def test_force_refresh_blob_does_not_create_organized_copy_when_absent(monkeypatch, tmp_path):
    """Only the flat layout present -> only the flat copy is (re)written; the
    organized copy must not materialize out of nowhere."""
    flat = tmp_path / "2024-04-18"
    flat.mkdir(parents=True)
    (flat / "iMAR0418.txt").write_text("stale")

    monkeypatch.setattr(
        "app.data.download.requests.get",
        lambda *a, **kw: _FakeResponse("final".encode("utf-8")),
    )
    force_refresh_blob(file_type="iMAR", file_date=date(2024, 4, 18), data_dir=str(tmp_path))

    assert (flat / "iMAR0418.txt").read_text() == "final"
    assert not (tmp_path / "predespacho_ideal" / "iMAR0418.txt").exists()
