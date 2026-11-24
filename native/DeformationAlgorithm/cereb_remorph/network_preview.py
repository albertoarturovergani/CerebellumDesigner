"""Canonical reference coordinates; native editor never runs BSB placement."""
import json
from .desktop_paths import RESOURCES

def reference():
    return json.loads((RESOURCES / 'network_reference.json').read_text(encoding='utf-8'))

def request(recipe):
    raise ValueError('Exact BSB placement is not available in the Windows editor. Export the package for reconstruction in BSB 8.')

def state(key):
    raise ValueError('The native editor does not launch BSB placement jobs.')
