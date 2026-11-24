"""Meaningful editor/export checks, also executed inside the frozen Windows EXE."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def self_test(data):
    import numpy as np
    import yaml
    from cereb_remorph.designer import catalog, preview, morphology_payload
    from cereb_remorph.core import CORTICAL, validate
    from cereb_remorph.recipe_format import to_public
    from cereb_remorph.presets import sz_preset
    from cereb_remorph.export_bundle import export_bundle
    from cereb_remorph.network_preview import reference, request
    from cereb_remorph.desktop_paths import RESOURCES
    from cereb_remorph.bsb_adapter import DEFAULT_REPO
    checks = []
    def check(name, condition):
        if not condition:raise AssertionError(name)
        checks.append(name)
    original = {p.relative_to(DEFAULT_REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in DEFAULT_REPO.rglob('*') if p.is_file()}
    c = catalog()
    check('native catalog without exact-placement capability', c['native_editor'] and not c['capabilities']['exact_placement'])
    check('SZ preset present with references', any(x['id']=='sz' and x['recipe']['annotations']['sources'] for x in c['presets']))
    healthy, sz = c['recipe'], sz_preset()
    results = {}
    for label,recipe in [('healthy',healthy),('sz',sz)]:
        for pop in CORTICAL:
            base = morphology_payload(pop)
            current = preview(recipe,pop,0)
            nodes = np.array(current['nodes'])
            check(f'{label}/{pop}: finite morphology and DCI', np.isfinite(nodes).all() and current['dci'] is not None)
            check(f'{label}/{pop}: topology retained', current['parents']==base['parents'] and current['types']==base['types'])
            if label=='healthy':
                check(f'{pop}: unchanged canonical geometry', np.allclose(nodes,base['nodes'],rtol=0,atol=1e-10))
            results[label+'/'+pop] = {'metrics':current['metrics'],'dci':current['dci'], 'nodes_shape':list(nodes.shape),
                                     'coordinate_sum':nodes.sum(axis=0).tolist()}
    # Comparison with results from the original Ubuntu engine; no new scientific transformation.
    golden_path = RESOURCES/'compatibility_reference.json'
    if golden_path.exists():
        golden = json.loads(golden_path.read_text(encoding='utf-8'))
        for key,value in results.items():
            check(key+': original-engine parity', value['nodes_shape']==golden[key]['nodes_shape'] and
                  np.allclose(value['coordinate_sum'],golden[key]['coordinate_sum'],rtol=1e-10,atol=1e-7) and
                  np.isclose(value['metrics']['length_um'],golden[key]['metrics']['length_um'],rtol=1e-10))
    variant = deepcopy(healthy)
    variant.setdefault('populations',{})['purkinje_cell']={'cells':{'rotation_x_deg':{'mean':180,'sigma':0}}}
    rotation = preview(variant,'purkinje_cell',0)
    baseline = preview(healthy,'purkinje_cell',0)
    check('180-degree rotation preserves length', np.isclose(rotation['metrics']['length_um'],baseline['metrics']['length_um']))
    check('180-degree rotation changes coordinates', not np.allclose(rotation['nodes'],baseline['nodes']))
    bad = deepcopy(healthy);bad['seed']=-1
    try:validate(bad)
    except ValueError:checks.append('invalid seed rejected')
    else:raise AssertionError('Invalid seed accepted')
    try:request(healthy)
    except ValueError:checks.append('native editor never starts placement')
    else:raise AssertionError('Native placement should be unavailable')
    check('real canonical soma coordinates included', all(v['count']==len(v['positions']) for v in reference()['populations'].values()))
    exports = []
    for label,recipe in [('healthy',healthy),('sz',sz)]:
        bundle = export_bundle(recipe);folder=Path(bundle['folder'])
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        check(label+': all export hashes valid', all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==sha for name,sha in manifest['files'].items()))
        structural=yaml.safe_load((folder/'structural.yaml').read_text(encoding='utf-8'))
        check(label+': native populations and 16 rules retained', len(structural['connectivity'])==16 and set(CORTICAL)<=set(structural['cell_types']))
        check(label+': PDF generated', (folder/'report.pdf').read_bytes().startswith(b'%PDF'))
        check(label+': Bash uses LF and MPI8', b'\r' not in (folder/'reconstruct.sh').read_bytes() and manifest['mpi_ranks']==8 and b'mpirun' in (folder/'reconstruct.py').read_bytes())
        check(label+': reconstruction not launched', not manifest['reconstruction_launched'] and not (folder/'reconstruction').exists())
        check(label+': no executable-as-Python command', sys.executable not in bundle['command'])
        with zipfile.ZipFile(folder/'deformation_package.zip') as archive:
            check(label+': complete portable ZIP', archive.testzip() is None and 'structural.yaml' in archive.namelist() and 'report.pdf' in archive.namelist())
        exports.append({'profile':label, 'folder':str(folder)})
    check('model sources remain unchanged', original == {p.relative_to(DEFAULT_REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in DEFAULT_REPO.rglob('*') if p.is_file()})
    check('BSB MPI NEST not imported', not any(x.split('.')[0] in ('bsb','mpi4py','nest','cerebellar_models') for x in sys.modules))
    return {'passed':True,'checks':checks,'count':len(checks),'exports':exports,'metrics':results,
            'frozen':bool(getattr(sys,'frozen',False)),'platform':sys.platform}
