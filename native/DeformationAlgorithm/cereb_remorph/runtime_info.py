"""Resolve a companion model checkout and report source/runtime versions separately."""
import ast
from pathlib import Path
import sys


def find_model_repo(designer_root, project, override=None):
    if override:
        return Path(override).expanduser().resolve()
    root = Path(designer_root).resolve()
    for candidate in (root, *root.parents, Path(project) / 'src/cerebellar-models'):
        if (candidate / 'configurations/mouse/mouse_cerebellar_cortex.yaml').is_file() and (candidate / 'cerebellar_models/__init__.py').is_file():
            return candidate.resolve()
    # Keep the expected location visible; native_base will report the missing source.
    return (Path(project) / 'src/cerebellar-models').resolve()


def source_version(repo):
    try:
        tree = ast.parse((Path(repo) / 'cerebellar_models/__init__.py').read_text( encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    except (OSError, SyntaxError):
        pass
    return None


def software_versions(repo):
    from .desktop_paths import reconstruction_target
    target = reconstruction_target()
    return {'bsb':target['versions']['bsb-core'], 'python_executable':sys.executable,
            'native_editor':True, 'runtime_scope':'Pinned reconstruction target; editor runs without BSB or MPI',
            'cerebellar_models':source_version(repo), 'cerebellar_models_installed':'bundled source',
            'model_repository':str(Path(repo).resolve()),
            'cerebellar_models_commit':target['model_commit'], 'cerebellar_models_modified':False}
