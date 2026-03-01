from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src_dir = Path(__file__).resolve().parents[1] / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    monkeypatch.setenv("UMEM_DB_PATH", str(tmp_path / "memories.db"))

    if "umem.server" in sys.modules:
        del sys.modules["umem.server"]
    if "umem.database" in sys.modules:
        del sys.modules["umem.database"]
    if "umem.config" in sys.modules:
        del sys.modules["umem.config"]

    server = importlib.import_module("umem.server")
    server._db = None

    yield server

    if server._db is not None:
        server._db.close()
    server._db = None
