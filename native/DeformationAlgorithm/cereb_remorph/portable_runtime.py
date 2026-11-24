"""Bundled reconstruction runner. Uses BSB 8, never imports Cerebellum Designer.

This file is copied into every portable export. Morphologies are already transformed;
no deformation is performed at reconstruction time. All paths resolve from the ZIP.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, data):
    target = Path(path)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(target)


def local_path(name):
    path = (PACKAGE / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(PACKAGE):
        raise ValueError('Package paths must be relative and remain inside the package: ' + name)
    return path


def verify_package():
    manifest = json.loads((PACKAGE / 'manifest.json').read_text( encoding='utf-8'))
    if manifest.get('package_format') != 'cerebellum-designer/portable-uniform-v1':
        raise ValueError('Unsupported reconstruction package format')
    for name, expected in manifest['files'].items():
        path = local_path(name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError('Package file missing or changed: ' + name + '; re-export from Designer.')
    return manifest


def verify_environment(manifest):
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required')
    errors = []
    for name, expected in manifest['runtime_versions'].items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = 'not installed'
        if actual != expected:
            errors.append(f'{name}: expected {expected}, found {actual}')
    if errors:
        raise RuntimeError('Activate the matching BSB 8 environment (or set CD_PYTHON).\n' + '\n'.join(errors))
    if not shutil.which('mpirun'):
        raise RuntimeError('mpirun is not on PATH; install/configure MPI before reconstruction')
    spec = importlib.util.find_spec('cerebellar_models')
    root = Path(next(iter(spec.submodule_search_locations)))
    for name, expected in manifest['model_code_sha256'].items():
        path = root / name
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError('Installed cerebellar-models code differs from the exported model: ' + name)
    # Load required native plugins before creating output files. No NEST simulation is loaded.
    import bsb  # noqa: F401
    import bsb_hdf5  # noqa: F401
    from mpi4py import MPI
    if MPI.COMM_WORLD.Get_size() != 1:
        raise RuntimeError('Run bash reconstruct.sh directly; it launches mpirun -n 8 itself')
    return {'python': sys.executable, 'versions': manifest['runtime_versions'],
            'mpi_library': MPI.Get_library_version().strip(), 'mpi_ranks': 8}


def stamp_placement(path):
    """Preserve native populations/positions; attach transformation provenance only."""
    import h5py
    import numpy as np
    from bsb import from_storage
    from bsb.storage._chunks import Chunk
    metadata = json.loads((PACKAGE / 'morphology_transformations.json').read_text( encoding='utf-8'))
    net = from_storage(str(path))
    reports = {}
    arrays = {}
    for population, info in metadata['populations'].items():
        ps = net.get_placement_set(population)
        with h5py.File(path, 'r') as h:
            chunks = [(key, len(group['position']))
                      for key, group in sorted(h['placement'].get(population, {}).items(), key=lambda x: int(x[0]))
                      if 'position' in group and len(group['position'])]
        count = len(ps)
        values = np.tile(info['parameters_internal'], (count, 1))
        indices = np.arange(count, dtype=np.int64)
        offset = 0
        for key, size in chunks:
            chunk = Chunk.from_id(int(key), net.network.chunk_size)
            ps.append_additional('remorph_cell_index', chunk, indices[offset:offset + size])
            ps.append_additional('remorph_parameters', chunk, values[offset:offset + size])
            ps.append_additional('remorph_factors', chunk, 1 - values[offset:offset + size, :3] / 100)
            offset += size
        if offset != count:
            raise AssertionError('Placement chunk count mismatch for ' + population)
        soma_only = bool(info['soma_only']) and count > 0
        if soma_only:
            ps.label_by_mask(['dfneuritespresent'], np.zeros(count, dtype=bool))
        reports[population] = {'cells': count, 'placement_cells': count, 'removed_cells': 0,
                               'soma_only_cells': count if soma_only else 0,
                               'unique_morphologies': int(count > 0),
                               'morphology': info['file'], 'positions_unchanged': True,
                               'bifurcation_tilt_audit': info['tilt_audit']}
        arrays[population + '__parameters'] = values
        arrays[population + '__cell_index'] = indices
    save(path.parent / 'cell_assignments.json', {
        'populations': reports, 'parameter_columns': metadata['parameter_columns'],
        'morphologies_pretransformed': True, 'transformation_applied_during_reconstruction': False,
        'positions_unchanged': True, 'uniform_population_effects': True,
        'df_to_scale_internal': '1 - df_percent / 100',
        'source_profile': 'deformation_profile.yaml'})
    np.savez_compressed(path.parent / 'cell_assignments.npz', **arrays)


def connectivity(path):
    """Native rules, with the existing Designer policy for absent cells/neurites."""
    from bsb import from_storage
    from mpi4py import MPI
    comm = MPI.COMM_WORLD
    net = from_storage(str(path))
    reports = json.loads((Path(path).parent / 'cell_assignments.json').read_text( encoding='utf-8'))['populations']
    strategies = list(net.connectivity.values())
    skipped = {}
    filtered = []
    for strategy in strategies:
        for side in ('presynaptic', 'postsynaptic'):
            hemi = getattr(strategy, side)
            labels = hemi.morphology_labels or []
            if labels and 'soma' not in labels and any(reports.get(ct.name, {}).get('soma_only_cells', 0) for ct in hemi.cell_types):
                if hemi.labels:
                    raise ValueError('Existing cell filters require explicit composition')
                hemi.labels = ['dfneuritespresent']
                filtered.append({'rule': strategy.name, 'side': side, 'reason': 'Absent neurites'})
            if not sum(len(net.get_placement_set(ct, labels=hemi.labels)) for ct in hemi.cell_types):
                skipped[strategy.name] = 'No eligible ' + side + ' cells'
    changed = True
    while changed:
        changed = False
        for strategy in strategies:
            if strategy.name not in skipped and any(dep.name in skipped for dep in strategy.depends_on):
                skipped[strategy.name] = 'Required upstream connectivity is empty'
                changed = True
    if comm.rank == 0:
        for strategy in strategies:
            for pre in strategy.presynaptic.cell_types:
                for post in strategy.postsynaptic.cell_types:
                    for name in strategy.get_output_names(pre, post):
                        net.require_connectivity_set(pre, post, name)
        save(Path(path).parent / 'connectivity_availability.json', {
            'skipped': skipped, 'cell_filters': filtered, 'native_rules_preserved': True})
    comm.Barrier()
    net.run_connectivity(strategies=[s for s in strategies if s.name not in skipped], pipelines=False)
    if not skipped and not filtered:
        net.run_after_connectivity(pipelines=False)
    elif comm.rank == 0:
        print('Empty features recorded; optional native structure PDF omitted.', flush=True)


def internal_stage(stage, path):
    from mpi4py import MPI
    if MPI.COMM_WORLD.Get_size() != 8:
        raise RuntimeError('Reconstruction requires exactly 8 MPI processes')
    if stage == 'placement':
        from bsb.cli import handle_command
        handle_command(['compile', str(path), '--skip-connectivity', '--skip-after-placement',
                        '--skip-after-connectivity', '-v3'])
    else:
        connectivity(path)


def reconstruct(output, manifest, environment):
    import yaml
    import h5py
    # Exclusive mkdir prevents overwrite and concurrent runs targeting the same output.
    output = output.expanduser().resolve()
    if not output.parent.is_dir():
        raise ValueError('Output parent directory must already exist: ' + str(output.parent))
    cfg = yaml.safe_load((PACKAGE / 'structural.yaml').read_text( encoding='utf-8'))
    for morphology in cfg['morphologies']:
        morphology['file'] = str(local_path(morphology['file']))
    cfg['storage']['root'] = str(output / 'network.hdf5')
    output.mkdir(exist_ok=False)
    status = {'status': 'PREPARED', 'started_utc': datetime.now(timezone.utc).isoformat(),
              'mpi_ranks': 8, 'package_manifest_sha256': digest(PACKAGE / 'manifest.json'),
              'environment': environment, 'reconstruction_only': True, 'simulation_launched': False}
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MPLBACKEND='Agg')
    def stage(name, path):
        status['status'] = name.upper()
        command = ['mpirun', '-n', '8', sys.executable, '-u', str(PACKAGE / 'reconstruct.py'),
                   '--internal-stage', name, str(path)]
        status['command'] = command
        save(output / 'status.json', status)
        print(name.capitalize() + ': ' + ' '.join(command), flush=True)
        with (output / (name + '.log')).open('x') as log:
            subprocess.run(command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        for name in ['deformation_profile.yaml', 'geometry.json', 'morphology_transformations.json',
                     'electrical_parameters.yaml', *('electrical_' + mode + '.yaml' for mode in manifest['compatible_synapse_presets'])]:
            shutil.copy2(PACKAGE / name, output / name)
        (output / 'placement.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8', newline='\n')
        stage('placement', output / 'placement.yaml')
        status['status'] = 'ANNOTATING_PLACEMENT'
        save(output / 'status.json', status)
        stamp_placement(output / 'network.hdf5')
        stage('connectivity', output / 'network.hdf5')
        from bsb import from_storage
        net = from_storage(str(output / 'network.hdf5'))
        tree = net.configuration.__tree__()
        if tree['cell_types'].keys() != cfg['cell_types'].keys():
            raise AssertionError('Native population names changed')
        (output / 'circuit.yaml').write_text(yaml.safe_dump(tree, sort_keys=False), encoding='utf-8', newline='\n')
        counts = {name: len(net.get_placement_set(name)) for name in cfg['cell_types']}
        contacts = {cs.tag: len(cs) for cs in net.get_connectivity_sets()}
        if set(contacts) != set(cfg['connectivity']):
            raise AssertionError('Expected native connection sets are missing')
        # Recheck all immutable package files after the reconstruction.
        verify_package()
        status.update(status='COMPLETED', finished_utc=datetime.now(timezone.utc).isoformat(),
                      populations=counts, connections=contacts,
                      network_sha256=digest(output / 'network.hdf5'))
        save(output / 'status.json', status)
        save(output / 'success.json', status)
        print('Network ready: ' + str(output / 'network.hdf5'), flush=True)
    except BaseException as error:
        status.update(status='STOPPED_ON_ERROR', error=str(error), partial_outputs_preserved=True)
        save(output / 'status.json', status)
        raise


def main():
    parser = argparse.ArgumentParser(description='Cerebellum Designer: reconstruct with BSB 8 / MPI x8; no simulation.')
    parser.add_argument('--check', action='store_true', help='Check files and environment without reconstructing')
    parser.add_argument('--output', type=Path, default=PACKAGE / 'reconstruction', help='New output folder; existing folders are refused')
    parser.add_argument('--internal-stage', choices=['placement', 'connectivity'], help=argparse.SUPPRESS)
    parser.add_argument('stage_path', nargs='?', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.internal_stage:
        internal_stage(args.internal_stage, args.stage_path)
        return
    manifest = verify_package()
    environment = verify_environment(manifest)
    print('Package, morphology files and matching BSB 8 environment verified. MPI processes: 8.', flush=True)
    if not args.check:
        reconstruct(args.output, manifest, environment)


if __name__ == '__main__':
    try:
        main()
    finally:
        if 'mpilock' in sys.modules:
            sys.modules['mpilock']._stop_all_pumps()
