"""Curated, versioned exploratory presets with parameter-level evidence."""
from copy import deepcopy
import math
from urllib.parse import urlsplit

SOURCES=[
 {'id':'maloku2010','title':'Maloku et al. (2010). Lower number of cerebellar Purkinje neurons in psychosis is associated with reduced reelin expression.','url':'https://pubmed.ncbi.nlm.nih.gov/20150511/','kind':'Human postmortem','note':'Approximately 20% lower linear Purkinje density in schizophrenia and bipolar disorder. Applying the same relative reduction to mouse planar density is a modelling assumption, not a measured mouse or areal effect.'},
 {'id':'andersen2003','title':'Andersen and Pakkenberg (2003). Stereological quantitation in cerebella from people with schizophrenia.','url':'https://doi.org/10.1192/bjp.182.4.354','kind':'Human postmortem stereology','note':'Table 4 reports regional molecular-layer thickness in 8 SZ and 10 control brains. Differences range from about -1.6% to -13.4%; none is statistically significant. Does not calibrate a uniform -10% reduction.'},
 {'id':'mavroudis2017','title':'Mavroudis et al. (2017). Purkinje cells pathology in schizophrenia. A morphometric approach.','url':'https://rjme.ro/RJME/resources/files/580217419424.pdf','kind':'Human postmortem','note':'Reduced distal/terminal dendrites, spine density and molecular-layer depth; PC density difference was not significant. Does not measure the preset percentages.'},
 {'id':'tran1998','title':'Tran et al. (1998). Reduced Purkinje cell size in the cerebellar vermis of elderly patients with schizophrenia.','url':'https://pubmed.ncbi.nlm.nih.gov/9734558/','kind':'Human postmortem','note':'Mean PC cross-sectional area was 8.3% smaller in 14 elderly patients versus 13 controls; linear density was unchanged. Isotropic conversion to a linear soma scale is an assumption.'},
 {'id':'bullock2009','title':'Bullock et al. (2009). Schizophrenia-like GABAergic gene expression deficits in cerebellar Golgi cells from rats chronically exposed to low-dose phencyclidine.','url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC2764837/','kind':'Rat pharmacological model','note':'Chronic PCP reduced Golgi-selective NR2B/NR2D transcripts. A separate acute PCP experiment reduced Golgi spontaneous firing. Neither experiment measures the preset synaptic-weight percentage.'},
 {'id':'schmitt2010','title':'Schmitt et al. (2010). Gene expression of NMDA receptor subunits in the cerebellum of elderly patients with schizophrenia.','url':'https://pubmed.ncbi.nlm.nih.gov/19856012/','kind':'Human molecular study','note':'Subunit/genotype-dependent findings do not establish a uniform reduction of all NMDA currents.'}
]

def validate_annotations(a):
    from .core import check_keys,number
    check_keys(a,('preset_id','version','title','summary','notes','sources','entries','parameter_notes'),'annotations')
    for key in ('preset_id','version','title','summary','notes'):
        if key in a and (not isinstance(a[key],str) or len(a[key])>12000):raise ValueError('Annotation text must be a string of at most 12000 characters')
    notes=a.get('parameter_notes',{})
    if not isinstance(notes,dict) or len(notes)>1024:raise ValueError('Invalid parameter notes')
    for path,text in notes.items():
        if not isinstance(path,str) or len(path)>300 or not path.startswith(('populations.','layers.','electrical.','defaults.')) or not isinstance(text,str) or len(text)>4000:
            raise ValueError('Invalid parameter note')
    sources=a.get('sources',[]);entries=a.get('entries',[])
    if not isinstance(sources,list) or len(sources)>40 or not isinstance(entries,list) or len(entries)>80:raise ValueError('Invalid reference/entry list')
    ids=set()
    for s in sources:
        check_keys(s,('id','title','url','kind','note'),'reference')
        if not all(isinstance(s.get(k),str) and len(s[k])<=2500 for k in ('id','title','url','kind','note')):raise ValueError('Invalid reference text')
        url=urlsplit(s['url'])
        if url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('Reference URLs must be HTTPS')
        if not s['id'] or s['id'] in ids:raise ValueError('Duplicate reference identifier')
        ids.add(s['id'])
    for e in entries:
        check_keys(e,('title','rationale','evidence','sources','targets'),'evidence entry')
        if not all(isinstance(e.get(k),str) and len(e[k])<=4000 for k in ('title','rationale','evidence')):raise ValueError('Invalid evidence entry')
        if not isinstance(e.get('sources'),list) or not all(x in ids for x in e['sources']):raise ValueError('Unknown reference in entry')
        if not isinstance(e.get('targets'),list) or len(e['targets'])>30:raise ValueError('Invalid parameter targets')
        for t in e['targets']:
            check_keys(t,('path','value'),'parameter target')
            if not isinstance(t.get('path'),str) or len(t['path'])>250 or not t['path'].startswith(('populations.','layers.','electrical.','defaults.')) or not number(t.get('value')):raise ValueError('Invalid parameter target')

def value_at(r,path):
    # Electrical keys such as V_m.min themselves contain dots.
    if not isinstance(r,dict):return None
    if path in r:return r[path]
    head,sep,tail=path.partition('.')
    return value_at(r.get(head),tail) if sep else r.get(head)


def parameter_note_rows(recipe):
    from .recipe_format import to_public
    r=to_public(recipe)
    return [{'path':path,'note':note,'value':value_at(r,path)}
            for path,note in r.get('annotations',{}).get('parameter_notes',{}).items() if note.strip()]


def evidence_rows(recipe):
    from .recipe_format import to_public
    r=to_public(recipe);rows=[]
    for e in r.get('annotations',{}).get('entries',[]):
        d=deepcopy(e);d['matches']=all(value_at(r,t['path'])==t['value'] for t in e['targets'])
        d['current']=[{'path':t['path'],'expected':t['value'],'current':value_at(r,t['path'])} for t in e['targets']]
        rows.append(d)
    return rows

def sz_preset():
    from .electrical import catalog as electrical_catalog
    # Native v2 signed values: negative = reduction. No network dispersion.
    r={'schema':'cereb-df/v2','name':'SZ - structure + NMDA','seed':1234,
       'defaults':{'df_percent':{'mean':0,'sigma':0,'bounds':[-100,100]}},'layers':{},'populations':{},'individuals':[],
       'electrical':{'model':'eglif_multirec','state':'in-vitro','synapse_mode':'tm','cells':{},'connections':{}},
       'annotations':{'preset_id':'sz_structure_nmda_v1','version':'2.0','title':'SZ - structure + NMDA',
       'summary':'One SZ preset: structural changes plus selective NMDA hypofunction, without resilience. Primary-study references accompany every changed parameter. Weight, neurite-length and thickness percentages are exploratory; soma scaling is derived under isotropy. GABA, AMPA, intrinsic parameters and TM dynamics remain canonical. Not a calibrated clinical model.',
       'notes':'','sources':deepcopy(SOURCES),'entries':[]}}
    entries=r['annotations']['entries']
    def entry(title,evidence,rationale,sources,targets):
        entries.append(dict(title=title,evidence=evidence,rationale=rationale,sources=sources,targets=[{'path':p,'value':v} for p,v in targets]))
    def morph(k,mean,sigma):
        r['populations'].setdefault('purkinje_cell',{'cells':{}})['cells'][k]={'mean':mean,'sigma':sigma,'bounds':[-65,0]}
        return [('populations.purkinje_cell.cells.'+k+'.mean',mean)]
    entry('Purkinje neurite length: -15%','Direction supported; magnitude exploratory',
      'Mavroudis et al. (2017), p.421, Results / Dendritic changes and Figure 1: reduced dendritic extent with distal/terminal branch loss. The selected -15% is a pilot perturbation, not the measured effect size. CD scales the entire neurite arbor, including axon; it does not selectively prune dendrites or represent spines.',
      ['mavroudis2017'],morph('neurite_length_df_percent',-15,0))
    entry('Purkinje neurite radius: unchanged','No calibrated uniform radius reduction',
      'The dendritic and bifurcation findings of Mavroudis et al. (2017) do not identify a uniform radius multiplier. Radius remains at the canonical value (0% change), separately from neurite length. This replaces the exploratory -15% radius setting of preset 1.1; historical run recipes are unchanged.',
      ['mavroudis2017'],morph('neurite_radius_df_percent',0,0))
    soma=(math.sqrt(.917)-1)*100
    entry('Purkinje soma: -4.24% linear size','Derived under isotropy',
      'Tran et al. (1998), Results: mean soma cross-sectional area -8.3% in 14 elderly patients versus 13 controls. Under isotropic scaling, sqrt(0.917) gives -4.24% linear size. Applying this human vermis measurement to the mouse soma is an assumption; this is not a directly measured -4.24% radius deficit.',
      ['tran1998'],morph('soma_size_df_percent',soma,0))
    r['populations']['purkinje_cell']['density_df_percent']=-20
    entry('Purkinje density: -20%','Measured human linear-density difference; cross-species and dimensional mapping assumed',
      'Maloku et al. (2010) reported approximately 20% lower linear Purkinje density (neurons/mm) in schizophrenia and bipolar disorder. The user-selected model transfers the 0.8 ratio to mouse planar density (neurons per square micrometre), with cortical area unchanged. This is not a conversion of absolute units or proof of 20% total neuron loss throughout the cerebellum. Actual counts depend on BSB placement. Findings are not uniform across cohorts: Andersen and Pakkenberg (2003) found no significant total Purkinje-number deficit. The Purkinje-layer thickness remains 15 micrometres.',
      ['maloku2010','andersen2003'],[('populations.purkinje_cell.density_df_percent',-20)])
    targets=[]
    for layer in ('b_molecular_layer','t_molecular_layer'):
        r['layers'][layer]={'thickness_df_percent':-10,'density_df_percent':0}
        targets.append(('layers.'+layer+'.thickness_df_percent',-10))
    entry('Molecular layer thickness: -10%','Exploratory magnitude',
      'Mavroudis et al. (2017), p.421, Neuronal density and cortical thickness: reduced molecular-layer depth without a tabulated percentage. Andersen and Pakkenberg (2003), Table 4, measured 8 SZ and 10 control brains: anterior lobe 600 vs 610 micrometres (P=0.91), posterior lobe 570 vs 580 (P=0.77), anterior vermis 610 vs 620 (P=0.97), posterior vermis 580 vs 670 (P=0.20), and flocculonodular lobe 420 vs 430 (P=0.83). These regional point estimates are not significant and do not establish uniform thinning. The selected -10% and applying the same ratio to both native molecular sublayers remain exploratory assumptions, not extracted effect sizes. Thicknesses are 50 to 45 and 100 to 90 micrometres. Granular (130) and Purkinje (15) layers are unchanged; total depth is 295 to 280 micrometres. Basket/stellate density is unchanged, so thinner layers can contain fewer cells; no separate MLI-loss measurement is assumed.',
      ['mavroudis2017','andersen2003'],targets)
    cat=electrical_catalog()['connections']
    for pathway,receptor,df in [('glomerulus_to_granule','NMDA',-20),('glomerulus_to_golgi','NMDA',-15),('ascending_axon_to_golgi','NMDA',-15)]:
        targets=[]
        for mode in cat:
            component=next(x for x in cat[mode][pathway] if x['receptor']==receptor)
            index=str(component['index'])
            r['electrical']['connections'].setdefault(mode,{})[pathway]={index:{'weight':df}}
            targets.append((f'electrical.connections.{mode}.{pathway}.{index}.weight',df))
        rationale=(
          'Schmitt et al. (2010), Results: NMDA-subunit expression depends on region and NRG1 genotype, with increased NR2D and genotype-associated reduced NR2C. This motivates a selective NMDA hypothesis; it does not establish a -20% current deficit at MF-granule synapses. Mapping to glomerulus_to_granule and the -20% weight are explicit exploratory choices.'
          if pathway=='glomerulus_to_granule' else
          'Bullock et al. (2009), Abstract and Results: chronic PCP reduced Golgi-selective NR2B/NR2D expression; a separate acute PCP experiment reduced spontaneous Golgi firing. This supports probing NMDA vulnerability on Golgi cells. Applying -15% weight to this specific input is exploratory, not a measured pathway-specific conductance change.')
        entry(pathway.replace('_',' ')+' / '+receptor+f': {df}% weight','Mechanistic mapping; magnitude exploratory',
          rationale+' Weight is a dimensionless multiplier of the receptor kernel. The same relative change applies to compatible TM/static presets, each from its own baseline. AMPA, GABA, receptor kinetics, intrinsic cell parameters, delays and TM parameters are unchanged; NMDA_g_init is not scaled again.',
          ['schmitt2010'] if pathway=='glomerulus_to_granule' else ['bullock2009'],targets)
    entry('Purkinje orientation: evidence and modelling limit','Not calibrated as a rigid rotation',
      'Mavroudis et al. report altered local/remote bifurcation tilt. These measurements do not specify whole-cell XYZ rotations relative to the layer. Rotation remains 0 degrees in this preset; manual rotations are exploratory sensitivity tests, not a calibrated SZ phenotype.',
      ['mavroudis2017'],[])
    entry('Scope and unchanged parameters','Model scope',
      'Densities other than Purkinje, other cell morphologies, intrinsic electrical parameters, AMPA/GABA weights, TM parameters, rotations and connectivity rules remain canonical. No GABA hypofunction module is included. The preset is uniform (sigma=0), without resilience or DCN/IO extensions. Existing saved profiles and simulation recipes remain historical snapshots; loading this revision does not migrate them.',
      [],[])
    r['annotations']['parameter_notes']={}
    for e in entries:
        refs='\nPrimary references:\n'+'\n'.join(next(s['title']+' '+s['url'] for s in SOURCES if s['id']==i) for i in e['sources'])
        for t in e['targets']:r['annotations']['parameter_notes'][t['path']]='Evidence: '+e['evidence']+'\n'+e['rationale']+refs
    validate_annotations(r['annotations']);return r

def catalog():
    return [{'id':'sz','label':'SZ - structure + NMDA','available':True,'recipe':sz_preset()},
            *[{'id':k,'label':name+' - not yet defined','available':False} for k,name in [('alzheimer','Alzheimer'),('autism','Autism'),('ataxia','Ataxia')]]]
