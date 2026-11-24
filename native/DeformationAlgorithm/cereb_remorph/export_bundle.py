"""Self-contained configuration package and human-readable change reports on the HD."""
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid
import zipfile
import yaml
from .recipe_format import to_public
from .portable_export import ensure_uniform, package_geometry, package_runtime
from .presets import evidence_rows, parameter_note_rows
from .core import validate, CORTICAL, FEATURES, ANGLES, BIF_TILT, parameters_for, common_spec, distribution
from .bifurcation import METHOD as TILT_METHOD
from .bsb_adapter import PROJECT, DEFAULT_REPO, prepare, native_base, guard_hd, digest, save, canonical
from .electrical import compiled, changes, catalog as electrical_catalog, available_modes

from .desktop_paths import reconstruction_target
ROOT=PROJECT/'DeformationAlgorithm'


def fmt(n):return f'{n:.5g}' if isinstance(n,(int,float)) else str(n)

def moments(spec):return f"{fmt(-spec['mean'])}%"+(f" ± {fmt(spec['sigma'])} pp" if spec['sigma'] else '')


def report_data(recipe,cfg,geometry,directory,command):
    cells=[];rotations=[];individuals=[];tilts=[]
    for p in CORTICAL:
        pars=parameters_for(recipe,p)
        cells.append([p.replace('_',' '),moments(common_spec(recipe,p))]+[moments(pars[k]) for k in FEATURES[:3]])
        rotations.append([p.replace('_',' ')]+[f"{fmt(pars[k]['mean'])}°"+(f" ± {fmt(pars[k]['sigma'])}°" if pars[k]['sigma'] else '') for k in ANGLES])
        tilts.append([p.replace('_',' '),f"{fmt(pars[BIF_TILT]['mean'])}°"])
    base=native_base();layers=[];density=[]
    for name,g in geometry['layers'].items():
        spec=recipe.get('layers',{}).get(name,{}).get('thickness_df_percent',{'mean':0,'sigma':0})
        layers.append([name.replace('_',' '),fmt(base['partitions'][name]['thickness']),fmt(-spec if isinstance(spec,(int,float)) else -spec['mean'])+'%',fmt(g['thickness_um'])])
    for name,g in geometry['populations'].items():density.append([name.replace('_',' '),fmt(g['density_factor']*100)+'%', 'Absent' if g['removed'] else 'Eligible for placement'])
    for x in recipe.get('individuals',[]):
        for k,spec in x['cells'].items():individuals.append([x['population'],str(x['cell_index']),k,str(spec)])
    electrical_changes=changes(recipe.get('electrical'))
    erows=[[(x['section'].replace('Connection ','')+' / ' if x['section'].startswith('Connection ') else '')+x['target'],x['parameter'],fmt(x['baseline']),fmt(-x['df_percent'])+'%',fmt(x['value'])+' '+x['unit']] for x in electrical_changes]
    sections=[
      {'title':'01 / Cell morphology','note':'Signed change relative to the healthy reference. The dashboard applies uniform effects within each population. Global change -100% removes the cell even when a feature override retains a nonzero soma. Neurite-only endpoints remove neurites and retain the soma.','headers':['Population','Common DF','Length DF','Radius DF','Soma DF'],'rows':cells,'widths':[115,99,99,99,99]},
      {'title':'02 / Cell rotation','note':'Extrinsic X, then Y, then Z, in degrees, around the root soma. Rotation does not move the soma center.','headers':['Population','X','Y','Z'],'rows':rotations,'widths':[145,122,122,122]},
      {'title':'02b / Dendritic bifurcation tilt','note':TILT_METHOD['operator']+' '+TILT_METHOD['definition']+' '+TILT_METHOD['scope']+' Reference: Mavroudis et al. (2017), Figure 1D. '+TILT_METHOD['reference'],'headers':['Population','Local-angle change'],'rows':tilts,'widths':[280,231]},
      {'title':'03 / Layer geometry','note':'Reference and realized thickness in µm. Thickness and density are deterministic; no network sigma. A zero-thickness layer is absent; cells are not squeezed into an infinitesimal layer.','headers':['Layer','Reference µm','Thickness DF','Current µm'],'rows':layers,'widths':[160,85,166,100]},
      {'title':'04 / Population density','note':'Percentage retained relative to the native density. This is a density factor, not a measured cell count; native placement includes chunk allocation and rounding. PCs use planar density; MF count is relative to glomeruli.','headers':['Population','Density retained','Placement status'],'rows':density,'widths':[185,140,186]},
      {'title':'05 / Individual overrides','note':'Explicit population-local indices take precedence over population rules. Finite-sample means may differ from requested distribution means.','headers':['Population','Index','Feature','Override'],'rows':individuals,'widths':[125,42,165,179]},
      {'title':'06 / Electrical modifications','note':'Only changed values are listed, including inactive preset edits if present. Active synapse preset: '+recipe.get('electrical',{}).get('synapse_mode','tm')+'. Cell receptor kinetics are shared by every input on the same receptor. Negative voltages move towards zero when reduced.','headers':['Target','Parameter','Reference','DF','Current'],'rows':[],'widths':[157,135,70,47,102]}
    ]
    sections[-1]['rows']=[[(x['section'].replace('Connection ','')+' / ' if x['section'].startswith('Connection ') else '')+x['target'],x['parameter'],fmt(x['baseline']),fmt(-x['df_percent'])+'%',fmt(x['value'])+' '+x['unit']] for x in electrical_changes]
    return {'version':'0.0.1','maintainer':'Alberto Arturo Vergani','parameter_notes':parameter_note_rows(recipe),'annotations':recipe.get('annotations',{}),'evidence':evidence_rows(recipe),'name':recipe['name'],'seed':recipe['seed'],'created_utc':datetime.now(timezone.utc).isoformat(),
        'summary':f"Cortical depth: {fmt(base['network']['z'])} → {fmt(cfg['network']['z'])} µm. Five cortical cell populations; 16 native connection rules. {len(electrical_changes)} electrical parameter modifications.",
        'sections':sections,'command':command,'output_folder':'reconstruction/ (inside the extracted package on the BSB machine)',
        'recipe_sha256':digest(directory/'deformation_profile.yaml'),
        'model_commit':reconstruction_target()['model_commit'],
        'files':[['deformation_profile.yaml','Editable transformation recipe and references; reopen in Designer to change it. Transformations are already baked into exported SWCs.'],['structural.yaml','Resolved native BSB configuration referencing the included, pretransformed SWCs through relative paths. Use the launcher for validated MPI-8 reconstruction and absent-feature handling.'],['electrical_parameters.yaml','Modified in-vitro multireceptor cell and connection model fragment. No stimulation protocol is selected.'],[' / '.join('electrical_'+mode+'.yaml' for mode in available_modes(recipe.get('electrical',{}).get('model','eglif_multirec'),recipe.get('electrical',{}).get('state','in-vitro'))),'Resolved parameters for synapse presets supported by the selected model and condition.'],['morphologies/','All cortical templates, transformed once at export time; native labels are preserved.'],['reconstruct.sh / reconstruct.py','Portable reconstruction workflow with mpirun -n 8; checks package, environment and model code without importing Designer.'],['requirements-reconstruction.txt','Matching Python package versions; an MPI installation is also required.'],['README.txt','Bash instructions, outputs and endpoint semantics.'],['report.html / report.pdf','Human-readable settings and changes.'],['manifest.json','SHA-256 hashes and upstream version provenance.']]}


def html_report(d):
    sections=[]
    for s in d['sections']:
        table='<p class="quiet">No modifications.</p>'
        if s['rows']:
            table='<div class="table"><table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in s['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in r)+'</tr>' for r in s['rows'])+'</tbody></table></div>'
        sections.append('<section><h2>'+escape(s['title'])+'</h2><p>'+escape(s['note'])+'</p>'+table+'</section>')
    if d.get('parameter_notes'):
        notes=['<section><h2>Parameter notes / justification log</h2>']
        for item in d['parameter_notes']:
            notes.append('<h3>'+escape(item['path'])+'</h3><p>Current signed setting: '+escape(str(item['value']) if item['value'] is not None else 'inherited / reset')+'</p><p>'+escape(item['note']).replace('\n','<br>')+'</p>')
        notes.append('</section>');sections.append(''.join(notes))
    annotations=d.get('annotations',{})
    if annotations:
        parts=['<section><h2>Notes &amp; references</h2><p>'+escape(annotations.get('summary',''))+'</p>']
        for e in d.get('evidence',[]):
            parts.append('<h3>'+escape(e['title'])+'</h3><p>'+escape(e['evidence'] if e['matches'] else 'Modified after preload')+'</p><p>'+escape(e['rationale'])+'</p>')
            for t in e['current']:parts.append('<p><code>'+escape(t['path'])+'</code>: preset '+escape(str(t['expected']))+'; current '+escape(str(t['current']))+'</p>')
            parts.append('<p>Sources: '+escape(', '.join(e['sources']))+'</p>')
        for ref in annotations.get('sources',[]):parts.append('<p id="'+escape(ref['id'],quote=True)+'"><a href="'+escape(ref['url'],quote=True)+'">'+escape(ref['title'])+'</a> — '+escape(ref['kind']+'. '+ref['note'])+'</p>')
        if annotations.get('notes'):parts.append('<h3>Your notes</h3><p>'+escape(annotations['notes']).replace('\n','<br>')+'</p>')
        parts.append('</section>');sections.append(''.join(parts))
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>DF report</title><style>body{margin:0;background:#f4f8fa;color:#1c3b4b;font:15px/1.65 system-ui}main{max-width:1120px;margin:auto;padding:44px 30px}header{border-bottom:3px solid #078491;padding:10px 0 28px}h1{font-size:38px;letter-spacing:-1px;margin:9px 0}small{color:#547b8a}h2{font-size:22px;color:#087d8b}p{color:#557080}section{background:white;border:1px solid #dce5e9;border-radius:10px;margin:24px 0;padding:22px 28px}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:12px;border-bottom:1px solid #e2ecef;text-align:left}th{background:#e6f2f3}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#183544;color:#eefbfa;padding:22px;border-radius:8px}footer{font-size:12px;overflow-wrap:anywhere}a{color:#087d8b}@media print{body{background:white}section{break-inside:avoid}main{padding:10px}}</style><main><header><small>DEFORMATIONALGORITHM v0.0.1 / MAINTAINED BY ALBERTO ARTURO VERGANI</small><h1>'+escape(d['name'])+'</h1><p>'+escape(d['summary'])+'</p><small>Seed '+str(d['seed'])+' · '+escape(d['created_utc'])+'</small></header>'+''.join(sections)+'<section><h2>Reconstruction from a terminal</h2><p>On a separate BSB 8 / MPI machine, activate the matching environment and enter the extracted package folder. Copy into Bash to start the reconstruction. The package has been prepared; no full reconstruction or simulation has been launched. Existing output folders will not be overwritten.</p><pre>'+escape(d['command'])+'</pre><p>Output: '+escape(d['output_folder'])+'</p><p>Use reconstruct.sh for MPI-8 reconstruction and correct absent-feature handling. Included SWCs are already transformed: do not apply the profile again. Activate a matching BSB 8 environment; use README.txt after moving this package. Electrical YAML is a model fragment without a stimulus.</p><p><a href="report.pdf">PDF report</a> · <a href="deformation_profile.yaml">DF recipe</a> · <a href="electrical_parameters.yaml">Electrical parameters</a></p></section><footer>Model commit: '+escape(d['model_commit'])+'<br>Recipe SHA-256: '+escape(d['recipe_sha256'])+'<br>Exploratory configuration. Parameter validation is not physiological validation.</footer></main></html>'


def export_bundle(recipe):
    guard_hd();recipe=ensure_uniform(recipe)
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    directory=ROOT/'exports'/name
    cfg,geometry=prepare(recipe,directory/'reconstruction')
    electrical=compiled(recipe.get('electrical'))
    both={}
    for mode in available_modes(recipe.get('electrical',{}).get('model','eglif_multirec'),recipe.get('electrical',{}).get('state','in-vitro')):
        e=deepcopy(recipe.get('electrical',{}));e['synapse_mode']=mode;both[mode]=compiled(e)
    directory.mkdir(parents=True,exist_ok=False)
    cfg=package_geometry(recipe,cfg,geometry,directory)
    runtime=package_runtime(directory)
    def ysave(name,obj):(directory/name).write_text(yaml.safe_dump(obj,sort_keys=False,allow_unicode=True), encoding='utf-8', newline='\n')
    ysave('deformation_profile.yaml',to_public(recipe));ysave('structural.yaml',cfg);ysave('electrical_parameters.yaml',electrical)
    for mode,e in both.items():ysave('electrical_'+mode+'.yaml',e)
    command='# On your BSB 8 / MPI machine: activate its matching environment, then\n# enter the extracted package folder and run:\nbash reconstruct.sh --check\nbash reconstruct.sh'
    data=report_data(recipe,cfg,geometry,directory,command);save(directory/'report_data.json',data)
    (directory/'report.html').write_text(html_report(data), encoding='utf-8', newline='\n')
    from .render_report import render
    render(data,directory/'report.pdf')
    manifest={**runtime,'editor_platform':'native Windows configuration editor','runtime_versions_scope':'reconstruction target; not editor-installed packages','version':'0.0.1','maintainer':'Alberto Arturo Vergani','created_utc':data['created_utc'],'mpi_ranks':8,'model_commit':data['model_commit'],
              'electrical_source':electrical_catalog()['source'],'electrical_source_sha256':electrical_catalog()['source_sha256'],
              'reconstruction_launched':False,'simulation_launched':False,'electrical_model':recipe.get('electrical',{}).get('model','eglif_multirec'),'electrical_condition':recipe.get('electrical',{}).get('state','in-vitro'),'compatible_synapse_presets':list(both),
              'source_files':{str(p):digest(p) for p in [DEFAULT_REPO/'configurations/mouse/mouse_cerebellar_cortex.yaml',Path(electrical_catalog()['source']),*[Path(s['file']) for s in native_base()['morphologies']],*[Path(__file__).with_name(n) for n in ('core.py','bifurcation.py','recipe_format.py','presets.py','cli.py','bsb_adapter.py','stage.py','electrical.py','parameter_info.py','runtime_info.py','portable_export.py','portable_runtime.py')]]},
              'files':{p.relative_to(directory).as_posix():digest(p) for p in sorted(directory.rglob('*')) if p.is_file()}}
    save(directory/'manifest.json',manifest)
    with zipfile.ZipFile(directory/'deformation_package.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix!='.zip':z.write(p,arcname=p.relative_to(directory).as_posix())
    base='/exports/'+name+'/'
    return {'folder':str(directory),'download':base+'deformation_package.zip','html':base+'report.html','pdf':base+'report.pdf','command':command}
