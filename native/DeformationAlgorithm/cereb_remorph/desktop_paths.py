"""Read-only bundled assets and pinned reconstruction target metadata."""
import json
import os
from pathlib import Path
APP_ASSETS = Path(os.environ.get('CD_APP_ASSETS', str(Path(__file__).resolve().parents[1])))
RESOURCES = Path(os.environ.get('CD_RESOURCE_ROOT', str(APP_ASSETS.parent / 'resources')))
def reconstruction_target():
    return json.loads((RESOURCES / 'reconstruction_target.json').read_text(encoding='utf-8'))
