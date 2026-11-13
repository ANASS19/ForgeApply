import os
import tempfile
from pathlib import Path

# Set before importing app modules.
os.environ['FORGEAPPLY_HOME']=tempfile.mkdtemp(prefix='forgeapply-test-')

import pytest

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path,monkeypatch):
    from forgeapply import store
    from forgeapply import app as app_module
    monkeypatch.setattr(store,'DB_FILE',tmp_path/'test.sqlite3')
    monkeypatch.setattr(app_module,'CV_DIR',tmp_path)
    store.init_db()
