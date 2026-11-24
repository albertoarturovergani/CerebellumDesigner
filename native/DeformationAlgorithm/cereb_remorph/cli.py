"""Validate a recipe or construct a new structural network on the external HD."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml
from .core import load, validate
from .recipe_format import to_public
from .bsb_adapter import DEFAULT_REPO,PROJECT,guard_hd,prepare,apply_cells,save,digest


def build(recipe,out,repo=DEFAULT_REPO,ranks=8,fixture_counts=None):
    guard_hd();recipe=validate(recipe);out=Path(out).resolve()
    if not out.is_relative_to(PROJECT):raise ValueError('Build outputs must be inside SZ_PAPER2 on the HD')
    if ranks!=8:raise ValueError('This workflow uses the approved mpirun -n 8')
    cfg,geometry=prepare(recipe,out,repo)
    if fixture_counts is not None:
        for pop,n in fixture_counts.items():
            sp=cfg['cell_types'][pop]['spatial']
            for k in ('density','planar_density','count_ratio','relative_to'):sp.pop(k,None)
            sp['count']=0 if geometry['populations'][pop]['removed'] else n
        cfg['after_connectivity']={}
    out.mkdir(parents=True,exist_ok=False)
    save(out/'recipe.json',to_public(recipe));save(out/'geometry.json',geometry)
    from .electrical import compiled, changes
    (out/'electrical_parameters.yaml').write_text(yaml.safe_dump(compiled(recipe.get('electrical')),sort_keys=False), encoding='utf-8', newline='\n')
    (out/'recipe.yaml').write_text(yaml.safe_dump(to_public(recipe),sort_keys=False), encoding='utf-8', newline='\n')
    placement=out/'placement.yaml';placement.write_text(yaml.safe_dump(cfg,sort_keys=False), encoding='utf-8', newline='\n')
    status={'status':'PREPARED','started_utc':datetime.now(timezone.utc).isoformat(),'mpi_ranks':ranks,
            'technical_fixture':fixture_counts is not None,'electrical_changes':bool(changes(recipe.get('electrical'))),'electrical_scope':'Parameters exported, no stimulation protocol or simulation selected','stimuli':'not configured'}
    env=os.environ.copy();env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MPLBACKEND='Agg')
    def stage(name,path):
        guard_hd();status['status']=name.upper();save(out/'status.json',status)
        with (out/(name+'.log')).open('w') as log:
            subprocess.run(['mpirun','-n',str(ranks),sys.executable,'-m','cereb_remorph.stage',name,str(path)],
                           cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    try:
        stage('placement',placement)
        status['status']='DEFORMING';save(out/'status.json',status)
        apply_cells(recipe,out/'network.hdf5',cfg)
        stage('connectivity',out/'network.hdf5')
        status.update(status='COMPLETED',finished_utc=datetime.now(timezone.utc).isoformat(),
                      network_sha256=digest(out/'network.hdf5'),recipe_sha256=digest(out/'recipe.json'),
                      cerebellar_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip())
        save(out/'status.json',status);save(out/'success.json',status)
        print('Network ready:',out/'network.hdf5',flush=True)
        return out
    except BaseException as e:
        status.update(status='STOPPED_ON_ERROR',error=str(e),partial_outputs_preserved=True);save(out/'status.json',status);raise


def main():
    parser=argparse.ArgumentParser(description='Heterogeneous structural deformation: v2 factor = 1 + change/100; no stimulation protocols.')
    parser.add_argument('command',choices=['validate','build'])
    parser.add_argument('recipe',type=Path)
    parser.add_argument('--output',type=Path,default=PROJECT/'DeformationAlgorithm/runs/network')
    parser.add_argument('--model-repo',type=Path,default=DEFAULT_REPO)
    args=parser.parse_args()
    try:
        recipe=load(args.recipe)
        if args.command=='validate':
            _,geometry=prepare(recipe,args.output,args.model_repo)
            print(json.dumps({'valid':True,'signed_change_to_scale':'1+change/100','geometry':geometry},indent=2))
        else:build(recipe,args.output,args.model_repo)
    finally:
        if 'mpilock' in sys.modules:sys.modules['mpilock']._stop_all_pumps()


if __name__=='__main__':main()
