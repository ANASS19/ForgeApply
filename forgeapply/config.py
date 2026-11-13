from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(os.getenv('FORGEAPPLY_HOME', str(Path.home() / '.forgeapply'))).expanduser().resolve()
ROOT.mkdir(parents=True, exist_ok=True)
CV_DIR = ROOT / 'resumes'
CV_DIR.mkdir(exist_ok=True)
DB_FILE = ROOT / 'forgeapply.sqlite3'
PORT = int(os.getenv('FORGEAPPLY_PORT', '8765'))
