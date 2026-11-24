"""Apply deformation before native BSB connectivity; never patch upstream rules."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import yaml
import h5py
from .runtime_info import find_model_repo
from .core import (CORTICAL,LAYER_OF,LAYERS,SCALES,ANGLES,FEATURES,Morphology,
                   validate,distribution,draw,parameters_for,sample_cells,statistics,presence_mask,population_removed)

_local_policy_path=Path(__file__).resolve().parents[1]/'local_storage.json'
_local_policy=json.loads(_local_policy_path.read_text( encoding='utf-8')) if _local_policy_path.exists() else {}
PROJECT=Path(os.environ.get('DF_PROJECT_ROOT',_local_policy.get('project_root',str(Path.cwd())))).resolve()
DEFAULT_REPO=find_model_repo(Path(__file__).resolve().parents[1], PROJECT, os.environ.get('DF_MODEL_REPO'))


def guard_hd():
    if not PROJECT.is_dir():raise RuntimeError('Project root must already exist')
    if not _local_policy:return
    mount=Path(_local_policy['mountpoint']).resolve()
    if not PROJECT.is_relative_to(mount):raise RuntimeError('Project root is outside the configured data disk')
    data=json.loads(subprocess.check_output(['findmnt','-J','-M',str(mount),'-o','UUID,FSTYPE,OPTIONS'],text=True))['filesystems'][0]
    if data['uuid']!=_local_policy['filesystem_uuid'] or data['fstype']!=_local_policy['filesystem_type'] or 'rw' not in data['options'].split(','):
        raise RuntimeError('Expected writable data filesystem is not mounted')


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def label_neurite_eligibility(ps,values):
    """Do not label ordinary populations; use a native-safe flag only if needed.

    This flag is needed only for soma-only endpoints. Its single-token spelling
    remains compatible with native report population/label parsing. Deformation
    parameters remain in `additional`, never in cell type names.
    """
    mask=(values[:,0]<100)&(values[:,1]<100)
    if np.any(~mask):ps.label_by_mask(['dfneuritespresent'],mask)
    return mask


def native_base(repo=DEFAULT_REPO):
    repo=Path(repo).resolve()
    cfg=yaml.safe_load((repo/'configurations/mouse/mouse_cerebellar_cortex.yaml').read_text( encoding='utf-8'))
    imp=cfg.pop('$import')
    if imp!={'ref':'../../morphologies/morphologies.yaml#/','values':['morphologies']}:
        raise ValueError('Upstream import layout changed: review before building')
    cfg['morphologies']=yaml.safe_load((repo/'morphologies/morphologies.yaml').read_text( encoding='utf-8'))['morphologies']
    for spec in cfg['morphologies']:
        spec['file']=str((repo/spec['file']).resolve())
        if not Path(spec['file']).is_file():raise FileNotFoundError(spec['file'])
    if set(cfg['cell_types'])!=set(LAYER_OF) or set(cfg['partitions'])!=set(LAYERS):
        raise ValueError('Only the official cortical layout (without DCN/IO/UBC extensions) is supported')
    for strat in cfg['placement'].values():
        for pop in strat['cell_types']:
            if strat['partitions']!=[LAYER_OF[pop]]:raise ValueError('Upstream layer assignment changed')
    return cfg


def max_soma_factor(recipe,pop):
    indices=[None]+[i['cell_index'] for i in recipe.get('individuals',[]) if i['population']==pop]
    specs=[distribution(parameters_for(recipe,pop,i)[SCALES[2]]) for i in indices]
    return max(1-(d['bounds'][0] if d['sigma'] else d['mean'])/100 for d in specs)


def prepare(recipe,out,repo=DEFAULT_REPO):
    recipe=validate(recipe);cfg=native_base(repo);original=copy.deepcopy(cfg);out=Path(out).resolve()
    cfg['name']=recipe['name'];cfg['rng']['seed']=recipe['seed']
    cfg['storage']['root']=str(out/'network.hdf5')
    geometry={'layers':{},'populations':{},'scope':'Deterministic layer thickness and population density; only cellular traits have sigma.'}
    layer_density={}
    identity={'mean':0.,'sigma':0.}
    for layer,part in cfg['partitions'].items():
        rule=recipe.get('layers',{}).get(layer,{})
        thickness=rule.get('thickness_df_percent',0)
        density=rule.get('density_df_percent',0)
        part['thickness']*=1-thickness/100;layer_density[layer]=1-density/100
        geometry['layers'][layer]={'thickness_df_percent':thickness,'density_df_percent':density,'thickness_um':part['thickness']}
    cfg['network']['z']=sum(p['thickness'] for p in cfg['partitions'].values())
    factors={}
    for pop in cfg['cell_types']:
        rule=recipe.get('populations',{}).get(pop,{})
        factors[pop]=(1-rule['density_df_percent']/100
                      if 'density_df_percent' in rule else layer_density[LAYER_OF[pop]])
    removed={pop for pop in cfg['cell_types'] if factors[pop]==0 or cfg['partitions'][LAYER_OF[pop]]['thickness']==0 or (pop in CORTICAL and population_removed(recipe,pop))}
    # MF count is defined relative to glomeruli by the official model.
    if 'glomerulus' in removed:removed.add('mossy_fibers')
    for pop,desc in cfg['cell_types'].items():
        spatial=desc['spatial']
        if pop in removed:
            for field in ('density','planar_density','count_ratio','relative_to'):spatial.pop(field,None)
            spatial['count']=0
        for field in ('density','planar_density'):
            if field in spatial:spatial[field]*=factors[pop]
        if 'count_ratio' in spatial:
            # Preserve the intended MF count scaling, without applying a shared layer reduction twice.
            spatial['count_ratio']*=factors[pop]/factors[spatial['relative_to']]
        if pop in CORTICAL:spatial['radius']*=max_soma_factor(recipe,pop)
        thickness=cfg['partitions'][LAYER_OF[pop]]['thickness']
        if pop not in removed and 2*spatial['radius']>thickness+1e-10:
            raise ValueError(f"{pop}: maximum reserved soma diameter {2*spatial['radius']:.6g} µm exceeds layer thickness {thickness:.6g} µm. Adjust soma effect bounds or thickness; no silent clipping is applied.")
        geometry['populations'][pop]={'density_factor':factors[pop],'removed':pop in removed,'reserved_placement_radius_um':spatial['radius'],
                                       'baseline_radius_um':original['cell_types'][pop]['spatial']['radius']}
    for name,strategy in list(cfg['placement'].items()):
        strategy['cell_types']=[pop for pop in strategy['cell_types'] if pop not in removed]
        if not strategy['cell_types']:del cfg['placement'][name]
    if cfg['connectivity']!=original['connectivity']:raise AssertionError('Native connection rules changed')
    geometry['native_connectivity_sha256']=canonical(original['connectivity'])
    return cfg,geometry


def apply_cells(recipe,path,prepared_cfg):
    from bsb import from_storage,parse_morphology_content,MorphologySet
    from bsb.storage._chunks import Chunk
    recipe=validate(recipe);path=Path(path).resolve()
    if path!=Path(prepared_cfg['storage']['root']).resolve():raise ValueError('Unexpected output network')
    with h5py.File(path,'r') as h:
        if list(h['connectivity']):raise ValueError('Refusing to deform a connected network in place')
    checkpoint=path.parent/'placement_before_remorphing.hdf5'
    if checkpoint.exists():raise FileExistsError('Transformation already attempted; preserve partial outputs and use a new folder')
    shutil.copy2(path,checkpoint);before_hash=digest(checkpoint)
    net=from_storage(str(path));reports={};arrays={};counts={}
    parsed_native_rules=copy.deepcopy(net.configuration.__tree__()['connectivity'])
    specs={Path(s['file']).stem:s for s in prepared_cfg['morphologies']}
    for pop in CORTICAL:
        ps=net.get_placement_set(pop)
        with h5py.File(path,'r') as h:
            chunks=[]
            for cid in sorted(h['placement'].get(pop,{}),key=int):
                group=h['placement'][pop][cid];positions=group['position'][:]
                if not len(positions):continue
                if 'rotation' in group and np.any(group['rotation'][:]!=0):
                    raise ValueError('Nonzero upstream placement rotations require explicit composition; refusing to discard them')
                chunks.append((cid,positions))
        count=sum(len(x) for _,x in chunks);counts[pop]=count
        if any(x['cell_index']>=count for x in recipe.get('individuals',[]) if x['population']==pop):
            raise ValueError(f'Individual index is outside realized {pop} population ({count})')
        if count==0:reports[pop]={'cells':0,'features':{}};continue
        positions=np.concatenate([a for _,a in chunks]);ids=np.arange(count,dtype=np.int64)
        if not np.array_equal(positions,ps.load_positions()):raise AssertionError('BSB chunk order differs from the declared local cell indexing')
        old_additional=ps.load_additional()
        values=sample_cells(recipe,pop,ids)
        keep=presence_mask(recipe,pop,ids,values)
        kept_values=values[keep]
        selected=prepared_cfg['cell_types'][pop]['spatial']['morphologies']
        if len(selected)!=1 or not isinstance(selected[0],str):raise ValueError('This version requires one official SWC template per population')
        spec=specs[selected[0]];template=Morphology(np.loadtxt(spec['file']),spec.get('pipeline',[]),spec.get('parser',{}).get('tags'))
        loaders=[];indices=[];keys={};metadata={};tilt_audits={}
        for row in kept_values:
            key=tuple(map(float,row))
            if key not in keys:
                array,tilt_audit=template.transform(row,with_audit=True);stream=io.StringIO();np.savetxt(stream,array,fmt='%.17g')
                # Source axes were already applied before deformation; do not apply the pipeline again.
                morph=parse_morphology_content(stream.getvalue(),**spec.get('parser',{}))
                name=f'remorph_{pop}_{len(loaders):06d}';keys[key]=len(loaders)
                if tilt_audit['requested_change_deg']:
                    measured=template.tilt_metrics(array)
                    tilt_audits[name]={**tilt_audit,'local':measured['local'],'remote':measured['remote']}
                loader=net.morphologies.save(name,morph,update_meta=False)
                loaders.append(loader);metadata[name]=loader.get_meta()
            indices.append(keys[key])
        net.morphologies.update_all_meta(metadata);net.cell_types[pop].spatial.morphologies=list(metadata) or selected
        ps.clear();offset=0;kept_offset=0
        for cid,xyz in chunks:
            end=offset+len(xyz);mask=keep[offset:end];n=int(mask.sum());kept_end=kept_offset+n
            if n:
                used,local=np.unique(indices[kept_offset:kept_end],return_inverse=True)
                additional={k:v[offset:end][mask] for k,v in old_additional.items()}
                additional.update(remorph_cell_index=ids[offset:end][mask],remorph_parameters=values[offset:end][mask],
                                  remorph_factors=1-values[offset:end][mask,:3]/100)
                ps.append_data(Chunk.from_id(int(cid),net.network.chunk_size),positions=xyz[mask],
                               morphologies=MorphologySet([loaders[int(i)] for i in used],local),
                               rotations=np.zeros((n,3)),additional=additional)
            offset=end;kept_offset=kept_end
        if len(kept_values):
            if not np.array_equal(ps.load_positions(),positions[keep]):raise AssertionError('Surviving cell positions changed')
            if not np.array_equal(ps.load_additional('remorph_parameters'),kept_values):raise AssertionError('Stored cell assignments differ')
            # Cells with a 100% neurite feature retain a soma but no neurite targets.
            label_neurite_eligibility(ps,kept_values)
        arrays[pop+'__parameters']=kept_values;arrays[pop+'__cell_index']=ids[keep];arrays[pop+'__positions']=positions[keep]
        arrays[pop+'__removed_cell_index']=ids[~keep]
        reports[pop]={'cells':int(keep.sum()),'placement_cells':count,'removed_cells':int((~keep).sum()),
                      'soma_only_cells':int(np.sum((kept_values[:,0]==100)|(kept_values[:,1]==100))),
                      'unique_morphologies':len(loaders),'layer_of_soma':LAYER_OF[pop],
                      'features':{k:statistics(kept_values[:,i]) for i,k in enumerate(FEATURES)},
                      'positions_unchanged':True,'source_swc_nodes':len(template.raw),'bifurcation_tilt_audits':tilt_audits}
        print(pop,count,'cells assigned',flush=True)
    net.storage.store_active_config(net.configuration)
    tree=net.configuration.__tree__()
    if tree['connectivity']!=parsed_native_rules:raise AssertionError('Native connectivity definitions were altered')
    (path.parent/'circuit.yaml').write_text(yaml.safe_dump(tree,sort_keys=False), encoding='utf-8', newline='\n')
    np.savez_compressed(path.parent/'cell_assignments.npz',**arrays)
    save(path.parent/'cell_assignments.json',{'populations':reports,'parameter_columns':FEATURES,
         'sampling':'bounded beta with requested arithmetic effect mean/sigma; normal unwrapped angle in degrees; keyed by seed/population/local cell index/parameter',
         'df_to_scale':'1 - df_percent / 100',
         'common_effect':'df_percent shares a single draw across length/radius/soma unless a feature is explicitly overridden',
         'population_moments':'Finite-population mean and sigma can differ from requested distribution moments; sigma=0 is exact.',
         'rotation':'extrinsic x then y then z, degrees, network axes, around original root soma; baked once, stored placement rotations are zero',
         'bifurcation_tilt':__import__('cereb_remorph.bifurcation',fromlist=['METHOD']).METHOD,
         'cell_index':'Zero-based BSB population-local order: sorted storage chunk IDs, then row within each chunk. Not a biological correspondence across reconstructions.',
         'positions_unchanged':True,'pruning':False,'electrical_changes':False,
         'checkpoint_sha256':before_hash,'native_rules_sha256':canonical(prepared_cfg['connectivity'])})
    if digest(checkpoint)!=before_hash:raise AssertionError('Placement checkpoint changed')
    return reports
