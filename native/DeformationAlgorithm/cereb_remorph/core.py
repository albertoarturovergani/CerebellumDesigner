"""Strict recipes, keyed sampling and soma-anchored morphology transformations."""
from __future__ import annotations
import copy
import hashlib
import math
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
import yaml
from .bifurcation import DendriticBifurcations, FEATURE as BIF_TILT

CORTICAL = ("granule_cell", "golgi_cell", "purkinje_cell", "basket_cell", "stellate_cell")
LAYER_OF = {"granule_cell":"granular_layer", "golgi_cell":"granular_layer",
            "glomerulus":"granular_layer", "mossy_fibers":"granular_layer",
            "purkinje_cell":"purkinje_layer", "basket_cell":"b_molecular_layer",
            "stellate_cell":"t_molecular_layer"}
LAYERS = tuple(dict.fromkeys(LAYER_OF.values()))
SCALES = ("neurite_length_df_percent", "neurite_radius_df_percent", "soma_size_df_percent")
ANGLES = ("rotation_x_deg", "rotation_y_deg", "rotation_z_deg")
FEATURES = SCALES + ANGLES + (BIF_TILT,)
COMMON = 'df_percent'
IDENTITY = {k:0.0 for k in FEATURES}


class RecipeLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for kn, vn in node.value:
        key = loader.construct_object(kn, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(vn, deep=deep)
    return result


RecipeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def number(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def check_keys(value, allowed, where):
    if not isinstance(value, dict) or set(value)-set(allowed):
        raise ValueError(f"{where}: expected mapping with keys {list(allowed)}")


def distribution(spec, angular=False):
    """Mean and sigma are arithmetic distribution moments, never relative CV."""
    check_keys(spec, ('mean','sigma','bounds'), 'distribution')
    if not all(k in spec and number(spec[k]) for k in ('mean','sigma')):
        raise ValueError('Each parameter requires finite numeric mean and sigma')
    mean, sigma = float(spec['mean']), float(spec['sigma'])
    if sigma < 0:
        raise ValueError('Sigma must be nonnegative')
    if angular:
        if 'bounds' in spec:
            raise ValueError('Angles use an unwrapped normal in degrees; bounds are not accepted')
        return {'mean':mean,'sigma':sigma}
    bounds = spec.get('bounds',[0.0,65.0])
    if not isinstance(bounds,(list,tuple)) or len(bounds)!=2 or not all(number(x) for x in bounds):
        raise ValueError('Effect bounds must be [minimum, maximum] in percentage points')
    low, high = map(float,bounds)
    if not (-100 <= low < high <= 100 and low <= mean <= high):
        raise ValueError('Effect mean must lie inside its bounds, with maximum at most 100%; factor = 1 - effect/100')
    if sigma and sigma*sigma >= (mean-low)*(high-mean):
        raise ValueError('Requested mean/sigma are impossible for a continuous bounded distribution; change the explicit bounds or moments')
    return {'mean':mean,'sigma':sigma,'bounds':[low,high]}


def validate_parameters(parameters):
    check_keys(parameters,FEATURES+(COMMON,),'cell parameters')
    result = {k:distribution(v,k in ANGLES or k == BIF_TILT) for k,v in parameters.items()}
    if BIF_TILT in result:
        d = result[BIF_TILT]
        if not -180 <= d['mean'] <= 180 or d['sigma'] != 0:
            raise ValueError('Bifurcation tilt requires degrees in [-180, 180] and sigma = 0')
    return result


def network_df(value):
    """Network quantities are deterministic; accept old zero-sigma recipes losslessly."""
    if isinstance(value,dict):
        d=distribution(value)
        if d['sigma']!=0:raise ValueError('Network thickness and density have no sigma. Use a single DF percentage; cell sigma remains available.')
        value=d['mean']
    if not number(value) or not -100<=value<=100:
        raise ValueError('Network DF must be one finite percentage from -100 to 100')
    return float(value)


def validate(recipe):
    from .recipe_format import to_engine
    recipe=to_engine(recipe)
    check_keys(recipe,('schema','name','seed','defaults','layers','populations','individuals','electrical','annotations'),'recipe')
    recipe=copy.deepcopy(recipe)
    if recipe.get('schema') != 'cereb-df/v1':
        raise ValueError('Expected schema: cereb-df/v1')
    if type(recipe.get('seed')) is not int or not 0 <= recipe['seed'] < 2**63:
        raise ValueError('seed must be a nonnegative integer below 2**63')
    if not isinstance(recipe.get('name'),str) or not 1 <= len(recipe['name']) <= 120:
        raise ValueError('name must be a string of 1–120 characters')
    validate_parameters(recipe.get('defaults',{}))
    check_keys(recipe.get('layers',{}),LAYERS,'layers')
    for layer, values in recipe.get('layers',{}).items():
        check_keys(values,('thickness_df_percent','density_df_percent','cells'),layer)
        for field in ('thickness_df_percent','density_df_percent'):
            if field in values: values[field]=network_df(values[field])
        validate_parameters(values.get('cells',{}))
    check_keys(recipe.get('populations',{}),LAYER_OF,'populations')
    for pop,values in recipe.get('populations',{}).items():
        check_keys(values,('density_df_percent','cells'),pop)
        if 'density_df_percent' in values:values['density_df_percent']=network_df(values['density_df_percent'])
        if pop not in CORTICAL and values.get('cells'):
            raise ValueError(f'{pop} is an input/relay population without an SWC morphology')
        validate_parameters(values.get('cells',{}))
    individuals = recipe.get('individuals',[])
    if not isinstance(individuals,list):raise ValueError('individuals must be a list')
    seen=set()
    for item in individuals:
        check_keys(item,('population','cell_index','cells'),'individual')
        key=(item.get('population'),item.get('cell_index'))
        if key[0] not in CORTICAL or type(key[1]) is not int or key[1]<0 or key in seen:
            raise ValueError('Invalid or duplicate individual population/cell_index')
        seen.add(key);validate_parameters(item.get('cells',{}))
    if 'electrical' in recipe:
        from .electrical import validate_electrical
        validate_electrical(recipe['electrical'])
    if 'annotations' in recipe:
        from .presets import validate_annotations
        validate_annotations(recipe['annotations'])
    return copy.deepcopy(recipe)


def load(path):
    return validate(yaml.load(Path(path).read_text( encoding='utf-8'),Loader=RecipeLoader))


def rng(seed, population, cell_index, feature):
    token=f'cereb-df-v1|{seed}|{population}|{cell_index}|{feature}'
    digest=hashlib.sha256(token.encode()).digest()
    return np.random.default_rng(np.frombuffer(digest[:16],dtype='<u4'))


def draw(spec, seed, population, cell_index, feature, angular=False):
    d=distribution(spec,angular);mean=d['mean'];sigma=d['sigma']
    if sigma==0:return mean
    gen=rng(seed,population,cell_index,feature)
    if angular:return float(gen.normal(mean,sigma))
    low,high=d['bounds'];width=high-low;mu=(mean-low)/width
    concentration=(mean-low)*(high-mean)/(sigma*sigma)-1
    return float(low+width*gen.beta(mu*concentration,(1-mu)*concentration))


def resolved_parameters(recipe,population,cell_index=None):
    if population not in CORTICAL:raise ValueError('Only the five cortical morphologies are supported')
    result={k:{'mean':v,'sigma':0.0} for k,v in IDENTITY.items()}
    streams={k:k for k in FEATURES}
    overlays=[recipe.get('defaults',{}),
              recipe.get('layers',{}).get(LAYER_OF[population],{}).get('cells',{}),
              recipe.get('populations',{}).get(population,{}).get('cells',{})]
    if cell_index is not None:
        for item in recipe.get('individuals',[]):
            if (item['population'],item['cell_index'])==(population,int(cell_index)):
                overlays.append(item.get('cells',{}))
    for overlay in overlays:
        if COMMON in overlay:
            for k in SCALES:result[k]=overlay[COMMON];streams[k]=COMMON
        for k,spec in overlay.items():
            if k!=COMMON:result[k]=spec;streams[k]=k
    return copy.deepcopy(result),streams


def parameters_for(recipe,population,cell_index=None):
    return resolved_parameters(recipe,population,cell_index)[0]


def sample_cells(recipe,population,ids):
    ids=np.asarray(ids)
    if ids.ndim!=1 or not np.issubdtype(ids.dtype,np.integer) or np.any(ids<0) or len(np.unique(ids))!=len(ids):
        raise ValueError('Cell IDs must be unique nonnegative integers')
    rows=[]
    for index in ids:
        params,streams=resolved_parameters(recipe,population,int(index))
        rows.append([draw(params[k],recipe['seed'],population,int(index),streams[k],k in ANGLES or k == BIF_TILT) for k in FEATURES])
    return np.asarray(rows,dtype=float).reshape((-1,len(FEATURES)))


def common_spec(recipe,population,cell_index=None):
    spec={'mean':0,'sigma':0}
    overlays=[recipe.get('defaults',{}),recipe.get('layers',{}).get(LAYER_OF[population],{}).get('cells',{}),
              recipe.get('populations',{}).get(population,{}).get('cells',{})]
    if cell_index is not None:
        overlays.extend(i.get('cells',{}) for i in recipe.get('individuals',[]) if (i['population'],i['cell_index'])==(population,int(cell_index)))
    for overlay in overlays:
        if COMMON in overlay:spec=overlay[COMMON]
    return spec


def presence_mask(recipe,population,ids,values=None):
    ids=np.asarray(ids,dtype=np.int64)
    if values is None:values=sample_cells(recipe,population,ids)
    common=np.array([draw(common_spec(recipe,population,int(i)),recipe['seed'],population,int(i),COMMON) for i in ids])
    # A whole-cell endpoint takes precedence even if a feature override retains the soma.
    return (common < 100) & (values[:,2] < 100)


def population_removed(recipe,population):
    specs=[common_spec(recipe,population),parameters_for(recipe,population)[SCALES[2]]]
    if not any(d['mean']==100 and d['sigma']==0 for d in specs):return False
    for item in recipe.get('individuals',[]):
        if item['population']==population and presence_mask(recipe,population,[item['cell_index']])[0]:return False
    return True


def statistics(values):
    a=np.asarray(values,dtype=float)
    if not a.size:return {'n':0,'mean':None,'sigma':None,'min':None,'max':None}
    return {'n':int(a.size),'mean':float(a.mean()),'sigma':0.0 if np.ptp(a)==0 else float(a.std(ddof=0)),
            'min':float(a.min()),'max':float(a.max())}


class Morphology:
    """SWC tree in network axes; preserve tags, topology and actual soma attachments."""
    def __init__(self,array,pipeline=(),tags=None):
        a=np.asarray(array,dtype=float).copy()
        if a.ndim!=2 or a.shape[1]!=7 or not np.isfinite(a).all():raise ValueError('Invalid SWC array')
        if any(np.any(a[:,col]!=a[:,col].astype(int)) for col in (0,1,6)):raise ValueError('Noninteger SWC identifiers/tags')
        if np.any(a[:,5]<=0):raise ValueError('SWC radii must be positive')
        for step in pipeline:
            if set(step)!={'func','axis1','axis2'} or step['func']!='swap_axes':raise ValueError('Unsupported source morphology pipeline')
            i,j=step['axis1'],step['axis2']
            if i not in (0,1,2) or j not in (0,1,2):raise ValueError('Invalid axis')
            a[:,[2+i,2+j]]=a[:,[2+j,2+i]]
        self.lookup={int(row[0]):i for i,row in enumerate(a)}
        if len(self.lookup)!=len(a):raise ValueError('Duplicate SWC node')
        soma=a[:,1]==1;roots=np.flatnonzero(a[:,6]==-1)
        if len(roots)!=1 or not soma[roots[0]]:raise ValueError('Expected one rooted soma tree')
        for row in a:
            seen=set();node=int(row[0])
            while node!=-1:
                if node in seen or node not in self.lookup:raise ValueError('Cycle or missing SWC parent')
                seen.add(node);node=int(a[self.lookup[node],6])
        self.pivot=a[roots[0],2:5].copy();self.soma=soma;self.raw=a
        anchors=[]
        for row in a:
            node=int(row[0])
            while not soma[self.lookup[node]]:
                node=int(a[self.lookup[node],6])
                if node==-1:raise ValueError('Neurite has no soma ancestor')
            anchors.append(self.lookup[node])
        self.anchors=np.asarray(anchors)
        labels={1:['soma'],2:['axon'],3:['dendrites'],4:['dendrites']}
        labels.update({int(k):v for k,v in (tags or {}).items()})
        self.dendritic_tags={k for k,v in labels.items() if 'dendrites' in v and 'axon' not in v}
        self.bifurcations=DendriticBifurcations(a,self.dendritic_tags)

    def transform(self,values,with_audit=False):
        if not isinstance(values,dict) and len(values) not in (6,len(FEATURES)):
            raise ValueError('Unexpected cell transformation column count')
        p=dict(zip(FEATURES,values)) if not isinstance(values,dict) else dict(values)
        # Old six-column transformations keep their exact identity and meaning.
        p.setdefault(BIF_TILT,0.0)
        if set(p)!=set(FEATURES) or not all(number(x) for x in p.values()):raise ValueError('Incomplete cell transformation')
        if any(p[k]>100 for k in SCALES):raise ValueError('Effect cannot exceed 100%')
        if not -180<=p[BIF_TILT]<=180:raise ValueError('Bifurcation tilt must be within [-180, 180] degrees')
        audit={'requested_change_deg':p[BIF_TILT],'modified_forks':0,'clipped_daughter_angles':0,'skipped_zero_length_forks':0}
        if p[SCALES[2]]==100:
            out=np.empty((0,7))
            return (out,audit) if with_audit else out
        soma_only=p[SCALES[0]]==100 or p[SCALES[1]]==100
        out=self.raw.copy();length=1-p[SCALES[0]]/100;radius=1-p[SCALES[1]]/100;soma=1-p[SCALES[2]]/100
        # Explicit identity path preserves every point and radius, including terminal tips.
        if length!=1 or soma!=1:
            anchors=self.raw[self.anchors,2:5]
            out[:,2:5]=self.pivot+soma*(anchors-self.pivot)+length*(self.raw[:,2:5]-anchors)
        if radius!=1:out[~self.soma,5]*=radius
        if soma!=1:out[self.soma,5]*=soma
        if not soma_only:
            out,audit=self.bifurcations.transform(out,p[BIF_TILT])
        angles=[p[k] for k in ANGLES]
        if any(a!=0 for a in angles):
            out[:,2:5]=Rotation.from_euler('xyz',angles,degrees=True).apply(out[:,2:5]-self.pivot)+self.pivot
        out=out[self.soma] if soma_only else out
        return (out,audit) if with_audit else out

    def tilt_metrics(self,array=None):
        if array is None:return self.bifurcations.measure(self.raw)
        return DendriticBifurcations(array,self.dendritic_tags).measure(array)
