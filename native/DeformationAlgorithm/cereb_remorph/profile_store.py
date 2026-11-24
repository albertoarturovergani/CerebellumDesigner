"""Saved, immutable profile revisions on the HD. No arbitrary file reads."""
import re
import yaml
from pathlib import Path
from .core import load
from .recipe_format import to_public

PATTERN = r'df_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}\.yaml'


def read_profile(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(PATTERN, identifier):
        raise ValueError('Invalid saved profile identifier')
    directory = (Path(root) / 'presets').resolve()
    path = directory / identifier
    if path.is_symlink() or not path.resolve().is_relative_to(directory):
        raise ValueError('Profile must be a regular file in presets')
    return {'id': identifier, 'recipe': to_public(load(path))}


def list_profiles(root):
    result, unreadable = [], []
    for p in sorted((Path(root) / 'presets').glob('df_*.yaml'), reverse=True):
        try:
            item = read_profile(root, p.name)
            result.append({'id': p.name, 'name': item['recipe']['name'],
                           'saved_utc': p.name[3:19]})
        except (ValueError, OSError, TypeError, KeyError, yaml.YAMLError):
            unreadable.append(p.name)
    return {'profiles': result, 'unreadable': unreadable}
