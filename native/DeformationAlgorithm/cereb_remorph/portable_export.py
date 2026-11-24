"""Bake uniform morphology changes and package a path-independent MPI-8 runner."""
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path
import shutil
import numpy as np

from .core import CORTICAL, FEATURES, Morphology, parameters_for, sample_cells, validate
from .bsb_adapter import DEFAULT_REPO, digest, save


LAUNCHER = '''#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Activate your BSB 8 environment first, or set CD_PYTHON=/path/to/venv/bin/python.
cd_python="${CD_PYTHON:-python3}"
if ! command -v "$cd_python" >/dev/null 2>&1; then
    echo "Python not found. Activate the BSB 8 environment or set CD_PYTHON." >&2
    exit 1
fi
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
exec "$cd_python" -u "$package_dir/reconstruct.py" "$@"
'''


README = '''Cerebellum Designer — portable reconstruction package

1. Extract the entire ZIP, including the morphologies/ directory.
2. Activate a matching BSB 8 / cerebellar-models Python environment.
3. In the extracted package directory, run:

    bash reconstruct.sh --check
    bash reconstruct.sh

Alternatively select the interpreter explicitly:

    CD_PYTHON=/path/to/bsb8-env/bin/python bash reconstruct.sh

To use a different NEW output directory:

    bash reconstruct.sh --output /path/to/new_network

The output parent directory must exist; the output directory must not exist.
The script launches mpirun -n 8 for placement, then mpirun -n 8 for connectivity.
Do not invoke reconstruct.sh through mpirun: it manages MPI itself.
Exactly eight MPI processes are requested; OpenBLAS/OMP threads are limited to one.
No --oversubscribe or MPI binding override is applied.

REQUIREMENTS
Linux/Bash, Python >=3.11, an MPI installation with at least eight available slots,
and the matching packages listed in requirements-reconstruction.txt. The manifest
also records/checks the scientific cerebellar-models Python source fingerprints:
a checkout with local scientific modifications must match those sources, even if
its release version is unchanged. The script checks dependencies; it does not
install software, download files, change the environment or run simulations.
Cerebellum Designer and the original morphology checkout are not required.
NEST is only needed later for electrical simulation, not for this reconstruction.

CONTENTS AND SEMANTICS
structural.yaml: resolved native BSB configuration with relative SWC paths.
morphologies/: all five cortical templates, transformed once at export time.
The files already use network axes; do not apply the source axis swap or the
profile's transformation a second time. An absent population retains a valid
reference template but has zero placement count; that template is not instantiated.
Native population names, SWC labels and connection rules are preserved.
deformation_profile.yaml: editable recipe and evidence; reopen it in Designer to
change parameters, then re-export. Editing a hashed package file invalidates it.
geometry.json / morphology_transformations.json: geometry and transformation audit.
electrical_parameters.yaml: active electrical model fragment, without a stimulus.
electrical_tm.yaml / electrical_static.yaml: compatible model variants when available.
report.html / report.pdf: human-readable changes, notes and references.
manifest.json: package hashes, software versions and scientific source provenance.
reconstruct.py: bundled orchestration only; no Designer installation is imported.

This portable format supports uniform population-level effects (sigma=0), including
rotations, bifurcation tilt, density/thickness changes and absent cells/neurites.
Heterogeneous or per-cell-index recipes need the staged Designer engine and are
explicitly rejected by this export; they are never silently converted.

OUTPUT
reconstruction/network.hdf5 is written only when this launcher is executed.
status.json, placement.log, connectivity.log, cell_assignments.json/.npz and
connectivity_availability.json record the run. A success.json is created only
after placement and connectivity finish and output checks pass. Existing outputs
are never overwritten; errors preserve partial outputs. No reconstruction or
simulation is started by downloading this package.
'''


def ensure_uniform(recipe):
    recipe = validate(recipe)
    if recipe.get('individuals'):
        raise ValueError('Portable morphology export requires uniform population settings; per-cell overrides need the staged Designer engine.')
    for pop in CORTICAL:
        if any(spec['sigma'] != 0 for spec in parameters_for(recipe, pop).values()):
            raise ValueError('Portable morphology export requires sigma=0; heterogeneous recipes need the staged Designer engine.')
    return recipe


def package_geometry(recipe, cfg, geometry, directory):
    """Return native config referencing baked SWCs, with no deployment paths."""
    recipe = ensure_uniform(recipe)
    directory = Path(directory)
    out = deepcopy(cfg)
    out['storage']['root'] = 'network.hdf5'
    specs = {Path(spec['file']).stem: spec for spec in cfg['morphologies']}
    baked = {}
    populations = {}
    (directory / 'morphologies').mkdir()
    for pop in CORTICAL:
        selected = cfg['cell_types'][pop]['spatial']['morphologies']
        if len(selected) != 1 or not isinstance(selected[0], str):
            raise ValueError('One canonical template per population is required')
        name = selected[0]
        if name in baked:
            raise ValueError('A shared template needs explicit variant assignment before export')
        source = specs[name]
        template = Morphology(np.loadtxt(source['file']), source.get('pipeline', []), source.get('parser', {}).get('tags'))
        parameters = sample_cells(recipe, pop, [0])[0]
        transformed, audit = template.transform(parameters, with_audit=True)
        absent = geometry['populations'][pop]['removed']
        # The BSB importer must still be able to read the template for a zero-count type.
        if absent:
            transformed = template.raw.copy()
        if not len(transformed):
            raise AssertionError('Present cells must have a valid SWC template')
        relative = 'morphologies/' + name + '.swc'
        np.savetxt(directory / relative, transformed, fmt='%.17g')
        baked[name] = deepcopy(source)
        baked[name]['file'] = relative
        baked[name]['pipeline'] = []  # axis swap and deformation already baked exactly once
        populations[pop] = {
            'file': relative, 'canonical_template': name,
            'source_sha256': digest(source['file']), 'exported_sha256': digest(directory / relative),
            'parameters_internal': parameters.tolist(), 'population_removed': absent,
            'soma_only': bool(not absent and (parameters[0] == 100 or parameters[1] == 100)),
            'source_nodes': len(template.raw), 'exported_nodes': len(transformed),
            'canonical_template_for_absent_population': absent, 'tilt_audit': audit,
            'axes': 'network axes; source pipeline applied once before deformation'}
    if set(baked) != set(specs):
        raise ValueError('Upstream morphology catalog changed; review the export before using it')
    out['morphologies'] = [baked[Path(spec['file']).stem] for spec in cfg['morphologies']]
    save(directory / 'geometry.json', geometry)
    save(directory / 'morphology_transformations.json', {
        'parameter_columns': FEATURES, 'convention': 'internal inverse DF: scale = 1 - DF/100',
        'populations': populations, 'uniform': True,
        'transformations_already_applied': True, 'source_pipeline_already_applied': True})
    return out


def package_runtime(directory):
    directory = Path(directory)
    shutil.copy2(Path(__file__).with_name('portable_runtime.py'), directory / 'reconstruct.py')
    (directory / 'reconstruct.sh').write_text(LAUNCHER, encoding='utf-8', newline='\n')
    (directory / 'reconstruct.sh').chmod(0o755)
    (directory / 'README.txt').write_text(README, encoding='utf-8', newline='\n')
    packages = ['bsb-core', 'bsb-hdf5', 'bsb-json', 'bsb-yaml', 'cerebellar-models',
                'numpy', 'scipy', 'h5py', 'mpi4py']
    from .desktop_paths import reconstruction_target
    versions = reconstruction_target()['versions']
    if versions['bsb-core'].split('.')[0] != '8':
        raise RuntimeError('Export target must use BSB 8')
    (directory / 'requirements-reconstruction.txt').write_text(
        '# Matching Python dependencies; install MPI separately.\n' +
        '\n'.join(name + '==' + value for name, value in versions.items()) + '\n', encoding='utf-8', newline='\n')
    model_source = DEFAULT_REPO / 'cerebellar_models'
    fingerprints = {p.relative_to(model_source).as_posix(): digest(p)
                    for p in sorted(model_source.rglob('*.py'))}
    if not fingerprints:
        raise ValueError('No scientific model code found')
    for candidate in ['LICENSE', 'LICENSE.txt', 'LICENSE.md']:
        license_file = DEFAULT_REPO / candidate
        if license_file.is_file():
            (directory / 'licenses').mkdir(exist_ok=True)
            shutil.copy2(license_file, directory / 'licenses' / 'cerebellar-models-LICENSE.txt')
            break
    return {'package_format': 'cerebellum-designer/portable-uniform-v1',
            'runtime_versions': versions, 'model_code_sha256': fingerprints,
            'designer_required_at_reconstruction': False,
            'original_morphology_checkout_required': False,
            'morphologies_pretransformed': True, 'uniform_population_effects': True}
