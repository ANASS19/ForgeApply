import os
import tempfile
from pathlib import Path

# Set before importing app modules.
os.environ['FORGEAPPLY_HOME']=tempfile.mkdtemp(prefix='forgeapply-test-')
