import pytest

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
 """Every test gets its own database and notes vault, so nothing touches the repo's vault/ or opportunities.sqlite3."""
 monkeypatch.setenv('OE_DB_PATH',str(tmp_path/'oe.sqlite3'));monkeypatch.setenv('OMEN_VAULT_PATH',str(tmp_path/'notes'))
