"""Loopback-only visual editor backed by the very same DF core as reconstruction.

Morphology previews, native placement-only previews, and configuration export; no simulations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import uuid
import re
import mimetypes
import subprocess
from .runtime_info import software_versions as read_software_versions
from urllib.parse import urlsplit, parse_qs

import numpy as np
import yaml

from .recipe_format import to_public
from .morphometry import dendritic_complexity
from .core import (CORTICAL, LAYER_OF, FEATURES, Morphology, RecipeLoader,
                   load, validate, sample_cells, statistics, parameters_for, common_spec, presence_mask)
from .bsb_adapter import DEFAULT_REPO, PROJECT, native_base, prepare, guard_hd, digest

from .desktop_paths import APP_ASSETS
ROOT = PROJECT / 'DeformationAlgorithm'
STATIC = APP_ASSETS / 'dashboard' / 'static'
NAMES = dict(zip(CORTICAL, ['Granule', 'Golgi', 'Purkinje', 'Basket', 'Stellate']))
NAMES.update(glomerulus='Glomerulus', mossy_fibers='Mossy fibers')
LAYER_NAMES = {'granular_layer':'Granular layer', 'purkinje_layer':'Purkinje layer',
               'b_molecular_layer':'Molecular layer · basket', 't_molecular_layer':'Molecular layer · stellate'}


@lru_cache(maxsize=5)
def template(pop):
    if pop not in CORTICAL:
        raise ValueError('Unknown cortical population')
    cfg = native_base()
    name = cfg['cell_types'][pop]['spatial']['morphologies'][0]
    spec = next(s for s in cfg['morphologies'] if Path(s['file']).stem == name)
    morph = Morphology(np.loadtxt(spec['file']), spec.get('pipeline', []),spec.get('parser',{}).get('tags'))
    # Use upstream semantic labels, including the non-standard SWC tags.
    extra = spec.get('parser', {}).get('tags', {})
    labels = {1:['soma'], 2:['axon'], 3:['dendrites'], 4:['dendrites']}
    labels.update({int(k):v for k,v in extra.items()})
    types = ['soma' if row[1] == 1 else ('axon' if 'axon' in labels.get(int(row[1]), []) else
             'dendrite' if 'dendrites' in labels.get(int(row[1]), []) else 'other') for row in morph.raw]
    parent = [morph.lookup.get(int(row[6]), -1) for row in morph.raw]
    return morph, parent, types, Path(spec['file'])


def metrics(array, parent, types, dendrites_only=False):
    children = [[] for _ in parent]
    selected = {i for i,t in enumerate(types) if t == 'dendrite' or (not dendrites_only and t != 'soma')}
    length = 0.0
    for i in selected:
        p = parent[i]
        if p >= 0:
            length += float(np.linalg.norm(array[i,2:5]-array[p,2:5]))
            children[p].append(i)
    tips = sum(not children[i] for i in selected)
    forks = sum(len(children[i]) > 1 for i in selected)
    return {'length_um':length, 'tips':int(tips), 'branch_points':int(forks)}


def dendrogram(array, parent, types):
    """Topological dendritic tree, x=path distance from root soma, y=leaf ordering."""
    if not len(array):return {'lines':[],'max_distance_um':0,'leaves':0}
    keep = {i for i,t in enumerate(types) if t in ('soma','dendrite')}
    roots = [i for i,p in enumerate(parent) if p < 0]
    root = roots[0]
    children = {i:[] for i in keep}
    for i in keep:
        p = parent[i]
        if p in keep: children[p].append(i)
    order, stack = [], [root]
    distance = {root:0.0}
    while stack:
        i = stack.pop(); order.append(i)
        for c in reversed(children[i]):
            distance[c] = distance[i]+float(np.linalg.norm(array[c,2:5]-array[i,2:5]))
            stack.append(c)
    ys = {}; leaf_count = 0
    for i in order:
        if not children[i]: ys[i]=leaf_count; leaf_count += 1
    for i in reversed(order):
        if children[i]: ys[i] = float(np.mean([ys[c] for c in children[i]]))
    lines=[]
    for i in order:
        cs=children[i]
        if not cs: continue
        if len(cs)>1: lines.append([distance[i], min(ys[c] for c in cs), distance[i], max(ys[c] for c in cs)])
        for c in cs: lines.append([distance[i],ys[c],distance[c],ys[c]])
    return {'lines':lines,'max_distance_um':max(distance.values()),'leaves':leaf_count}


def morphology_payload(pop):
    morph,parent,types,path=template(pop)
    return {'population':pop,'name':NAMES[pop], 'nodes':morph.raw[:,2:6].tolist(),
            'parents':parent,'types':types,'pivot':morph.pivot.tolist(),
            'source':path.name,'source_sha256':digest(path),
            'dendrogram':dendrogram(morph.raw,parent,types),
            'metrics':metrics(morph.raw,parent,types),
            'dci':dendritic_complexity(morph.raw,parent,types),
            'bifurcation_tilt':morph.tilt_metrics(),
            'raw_sizes':{'neurite_radius_um':float(np.median(morph.raw[np.array(types)!='soma',5])), 'soma_radius_um':float(np.median(morph.raw[np.array(types)=='soma',5]))},
            'dendrite_metrics':metrics(morph.raw,parent,types,True)}


def preview(recipe,pop,index,mode='mean'):
    recipe=validate(recipe)
    if pop not in CORTICAL or type(index) is not int or not 0<=index<1000000:
        raise ValueError('Invalid preview population or cell index')
    if mode not in ('mean','individual'):
        raise ValueError('Preview mode must be mean or individual')
    cfg,geometry=prepare(recipe, PROJECT/'DeformationAlgorithm/runs/preview_only', DEFAULT_REPO)
    morph,parent,types,_=template(pop)
    values=(np.array([parameters_for(recipe,pop)[k]['mean'] for k in FEATURES],dtype=float)
            if mode=='mean' else sample_cells(recipe,pop,np.array([index],dtype=np.int64))[0])
    present=(common_spec(recipe,pop)['mean']<100 and values[2]<100) if mode=='mean' else bool(presence_mask(recipe,pop,[index],values.reshape(1,-1))[0])
    changed,tilt_audit=morph.transform(values,with_audit=True) if present else (np.empty((0,7)),{'requested_change_deg':float(values[-1]),'modified_forks':0,'clipped_daughter_angles':0})
    lookup={int(row[0]):i for i,row in enumerate(changed)}
    current_parent=[lookup.get(int(row[6]),-1) for row in changed]
    current_types=[types[morph.lookup[int(row[0])]] for row in changed]
    # A synthetic sample of identifiers; these are not an already reconstructed population.
    samples=sample_cells(recipe,pop,np.arange(512,dtype=np.int64))
    hist,edges=np.histogram(-samples[:,0],bins=np.linspace(-100,100,27))
    return {'valid':True,'yaml':yaml.safe_dump(to_public(recipe),sort_keys=False,allow_unicode=True),
            'recipe':to_public(recipe),'population':pop,'cell_index':index,'preview_mode':mode,
            'nodes':changed[:,2:6].tolist(),'parents':current_parent,'types':current_types,'present':bool(present),'parameters':{k:float(v if k.endswith('_deg') else -v) for k,v in zip(FEATURES,values)},
            'metrics':metrics(changed,current_parent,current_types),
            'dendrite_metrics':metrics(changed,current_parent,current_types,True),
            'dendrogram':dendrogram(changed,current_parent,current_types),
            'dci':dendritic_complexity(changed,current_parent,current_types),
            'bifurcation_tilt':morph.tilt_metrics(changed),'tilt_audit':tilt_audit,
            'sample':{'n':512,'length_df':statistics(-samples[:,0]),'hist':hist.tolist(),'edges':edges.tolist()},
            'geometry':geometry,
            'network':{'x':cfg['network']['x'],'y':cfg['network']['y'],'z':cfg['network']['z']}}


def software_versions():
    return read_software_versions(DEFAULT_REPO)


def catalog():
    from .electrical import catalog as electrical_catalog
    cfg=native_base()
    return {'name':'Cerebellum Designer', 'version':'0.0.1', 'maintainer':'Alberto Arturo Vergani',
            'software':software_versions(),
            'native_editor':True, 'data_directory':str(PROJECT),
            'capabilities':{'exact_placement':False,'simulation':False,'portable_export':True},
            'recipe':to_public(load(APP_ASSETS/'examples/identity.yaml')),
            'populations':[{'id':p,'name':NAMES.get(p,p),'layer':LAYER_OF[p],
                            'spatial':d['spatial']} for p,d in cfg['cell_types'].items()],
            'layers':[{'id':k,'name':LAYER_NAMES[k],'thickness_um':d['thickness']}
                      for k,d in cfg['partitions'].items()],
            'presets':__import__('cereb_remorph.presets',fromlist=['catalog']).catalog(),
            'spatial_sampling':{'voxel_pathways':[{'name':name, 'pre':c.get('voxels_pre'), 'post':c.get('voxels_post')} for name,c in cfg['connectivity'].items() if 'VoxelIntersection' in c.get('strategy','')], 'chunk_size_um':cfg['network'].get('chunk_size')},
            'network':cfg['network'], 'features':list(FEATURES),'electrical':electrical_catalog()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(STATIC),**kwargs)

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

    def json_reply(self,value,status=200):
        body=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass

    def allowed(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin')
        return host in allowed and (not origin or origin in {f'http://{h}' for h in allowed})

    def do_GET(self):
        if not self.allowed():return self.json_reply({'error':'Loopback origin required'},403)
        url=urlsplit(self.path)
        try:
            if url.path.startswith('/exports/'):
                match=re.fullmatch(r'/exports/([0-9]{8}T[0-9]{6}Z_[0-9a-f]{8})/([a-zA-Z_]+\.(?:zip|html|pdf|yaml|json|txt|sh))',url.path)
                if not match:return self.json_reply({'error':'Invalid export path'},404)
                target=(ROOT/'exports'/match[1]/match[2]).resolve()
                if not target.is_relative_to((ROOT/'exports').resolve()) or not target.is_file():return self.json_reply({'error':'Export not found'},404)
                data=target.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)))
                if target.suffix=='.zip':self.send_header('Content-Disposition','attachment; filename=deformation_package.zip')
                self.end_headers();self.wfile.write(data);return
            if url.path=='/api/network-reference':
                from .network_preview import reference
                return self.json_reply(reference())
            if url.path=='/api/network-status':
                from .network_preview import state
                return self.json_reply(state(parse_qs(url.query).get('key',[''])[0]))
            if url.path=='/api/profiles':
                from .profile_store import list_profiles
                return self.json_reply(list_profiles(ROOT))
            if url.path=='/api/profile':
                from .profile_store import read_profile
                return self.json_reply(read_profile(ROOT,parse_qs(url.query).get('id',[''])[0]))
            if url.path=='/api/catalog':return self.json_reply(catalog())
            if url.path=='/api/morphology':
                return self.json_reply(morphology_payload(parse_qs(url.query).get('population',[''])[0]))
            if url.path.startswith('/api/'):return self.json_reply({'error':'Unknown endpoint'},404)
            return super().do_GET()
        except (ValueError,KeyError,OSError) as e:return self.json_reply({'error':str(e)},400)

    def do_POST(self):
        if not self.allowed():return self.json_reply({'error':'Loopback origin required'},403)
        try:
            if self.headers.get_content_type()!='application/json':raise ValueError('JSON body required')
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=1048576:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(n))
            path=urlsplit(self.path).path
            if path=='/api/quit':
                import threading
                self.json_reply({'closed':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if path not in ('/api/preview','/api/import','/api/save','/api/network','/api/export','/api/save-profile'):return self.json_reply({'error':'Unknown endpoint'},404)
            raw=yaml.load(body['yaml'],Loader=RecipeLoader) if path=='/api/import' else body['recipe']
            uniform_adjustment=False
            if path=='/api/import':
                def uniform(value):
                    nonlocal uniform_adjustment
                    if isinstance(value,dict):
                        if 'mean' in value and value.get('sigma',0)!=0:value['sigma']=0;uniform_adjustment=True
                        for child in value.values():uniform(child)
                    elif isinstance(value,list):
                        for child in value:uniform(child)
                uniform(raw)
            recipe=validate(raw)
            if path=='/api/network':
                from .network_preview import request
                return self.json_reply(request(recipe))
            if path=='/api/export':
                from .export_bundle import export_bundle
                return self.json_reply(export_bundle(recipe))
            if path in ('/api/preview','/api/import'):
                return self.json_reply(preview(recipe,body.get('population','golgi_cell'),body.get('cell_index',0),body.get('preview_mode','mean')) | {'uniform_adjustment':uniform_adjustment})
            # Saving an approved recipe is reversible; no build or shell execution is exposed.
            prepare(recipe,PROJECT/'DeformationAlgorithm/runs/preview_only',DEFAULT_REPO)
            guard_hd()
            directory=ROOT/'presets';directory.mkdir(parents=True,exist_ok=True)
            name='df_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]+'.yaml'
            path=directory/name
            path.write_text(yaml.safe_dump(to_public(recipe),sort_keys=False,allow_unicode=True), encoding='utf-8', newline='\n')
            return self.json_reply({'saved':True,'path':str(path),'sha256':digest(path),'id':name})
        except (ValueError,KeyError,TypeError,OSError,RuntimeError,yaml.YAMLError) as e:
            return self.json_reply({'valid':False,'error':str(e)},400)


def main():
    parser=argparse.ArgumentParser(description='Local DF morphology and layer editor')
    parser.add_argument('--port',type=int,default=8891)
    args=parser.parse_args()
    guard_hd()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'DeformationAlgorithm dashboard: http://127.0.0.1:{args.port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
