"""Explicit percentage reductions of the official in-vitro multireceptor preset."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import re
import yaml
from .bsb_adapter import DEFAULT_REPO, digest
from .core import CORTICAL, check_keys, number

SOURCE=DEFAULT_REPO/'configurations/mouse/in-vitro/nest/cell_models/eglif_multirec.yaml'
MODES={'tm':'tsodyks_synapse_connection_models','static':'static_synapse_connection_models'}
RECEPTORS={1:'AMPA',2:'NMDA',3:'GABA',4:'AMPA2',5:'AMPA3'}
MODE_LABELS={'tm':'Tsodyks–Markram (TM)', 'static':'Static'}

@lru_cache(maxsize=1)
def baseline():return yaml.safe_load(SOURCE.read_text( encoding='utf-8'))

def available_modes(model='eglif_multirec', state='in-vitro'):
    """Presets belong to a supported model/condition and must exist in its source."""
    if model!='eglif_multirec' or state!='in-vitro':
        raise ValueError('Only the installed in-vitro eglif_multirec preset is supported')
    data=baseline()
    modes={mode:source for mode,source in MODES.items() if data.get(source)}
    if not modes:raise ValueError('The selected electrical model has no supported synapse preset')
    return modes

def model_options():
    modes=available_modes()
    return [{'id':'eglif_multirec','label':'NEST · EGLIF multireceptor','simulator':'nest','available':True,
             'conditions':[{'id':'in-vitro','label':'In vitro','available':True,
                            'synapse_presets':[{'id':mode,'label':MODE_LABELS[mode]} for mode in modes]},
                           {'id':'in-vivo','label':'In vivo — unavailable for this model','available':False,'synapse_presets':[]}]},
            {'id':'neuron_multicompartment','label':'NEURON · multicompartment — planned','simulator':'neuron',
             'available':False,'conditions':[]}]

def flat(constants):
    out={k:v for k,v in constants.items() if number(v)}
    if isinstance(constants.get('V_m'),dict):
        out.update({'V_m.'+k:v for k,v in constants['V_m'].items() if number(v)})
    return out

def put(constants,key,value):
    if key.startswith('V_m.'):constants['V_m'][key[4:]]=value
    else:constants[key]=value

from .parameter_info import info

def units(k):return info(k)[0]

def group(k):
    for r in ('AMPA2','AMPA3','AMPA','NMDA','GABA'):
        if k.startswith(r+'_'):return r+' receptor'
    return 'Membrane and adaptation'

def positive(k):return k in ('C_m','tau_m','k_1','k_2','tau_rec','tau_psc') or '_Tau_' in k

def catalog():
    b=baseline()
    return {'model':'eglif_multirec','state':'in-vitro','models':model_options(),'source':str(SOURCE),'source_sha256':digest(SOURCE),
            'cells':{p:[{'key':k,'baseline':v,'unit':units(k),'description':info(k)[1],'group':group(k),'strictly_positive':positive(k)} for k,v in flat(b['cell_models'][p]['constants']).items()] for p in CORTICAL},
            'connections':{mode:{conn:[{'index':i,'model':s['model'],'receptor':RECEPTORS.get(s.get('receptor_type'),'Electrical coupling' if s['model']=='gap_junction' else 'Relay'),
                          'receptor_type':s.get('receptor_type'),'parameters':[{'key':k,'baseline':v,'unit':info(k,s['model'],s.get('receptor_type'))[0],'description':info(k,s['model'],s.get('receptor_type'))[1],'strictly_positive':positive(k) or k=='delay'} for k,v in s.items() if number(v) and k!='receptor_type']}
                         for i,s in enumerate(c['synapses'])] for conn,c in b[src].items()} for mode,src in available_modes().items()},
            'convention':'Public v2: value = official value * (1 + change / 100). Positive changes increase magnitude; this is not a percentage of firing-rate change.',
            'scope':'Population-level constants. Receptor kinetics are shared by all inputs using that receptor on that population. Connection weights and TM parameters are pathway-specific.'}

def check_reductions(r,allowed,where):
    check_keys(r,allowed,where)
    for k,v in r.items():
        if not number(v) or not -100<=v<=100:raise ValueError(f'{where}.{k}: electrical DF must be between -100 and 100% (inverse engine convention)')

def validate_electrical(e):
    check_keys(e,('model','state','synapse_mode','cells','connections'),'electrical')
    modes=available_modes(e.get('model','eglif_multirec'),e.get('state','in-vitro'))
    if e.get('synapse_mode',next(iter(modes))) not in modes:raise ValueError('Synapse preset is unavailable for the selected model and condition')
    b=baseline()
    check_keys(e.get('cells',{}),CORTICAL,'electrical cells')
    for p,r in e.get('cells',{}).items():check_reductions(r,flat(b['cell_models'][p]['constants']),p)
    check_keys(e.get('connections',{}),modes,'electrical connections')
    for mode,conns in e.get('connections',{}).items():
        source=b[modes[mode]];check_keys(conns,source,mode)
        for conn,rows in conns.items():
            check_keys(rows,[str(i) for i in range(len(source[conn]['synapses']))],conn)
            for i,r in rows.items():
                syn=source[conn]['synapses'][int(i)]
                check_reductions(r,[k for k,v in syn.items() if number(v) and k!='receptor_type'],conn+'.'+i)
    compiled(e,check=False)
    for mode in e.get('connections',{}):
        if mode!=e.get('synapse_mode',next(iter(modes))):
            try:compiled(e|{'synapse_mode':mode},check=False)
            except ValueError as exc:raise ValueError(f'Inactive {mode} preset: {exc}') from exc
    return deepcopy(e)

def compiled(e=None,check=True):
    e=e or {}
    if check:validate_electrical(e)
    modes=available_modes(e.get('model','eglif_multirec'),e.get('state','in-vitro'))
    b=baseline();mode=e.get('synapse_mode',next(iter(modes)))
    result={'simulator':'nest','modules':deepcopy(b['modules']),'cell_models':deepcopy(b['cell_models']),
            'connection_models':deepcopy(b[modes[mode]])}
    for p,r in e.get('cells',{}).items():
        c=result['cell_models'][p]['constants'];old=flat(c)
        for k,df in r.items():put(c,k,old[k]*(1-df/100))
    for p,model in result['cell_models'].items():
        c=model['constants']
        for k,v in flat(c).items():
            if positive(k) and v<=0:raise ValueError(f'{p}.{k} must remain > 0; -100% change is not valid for this parameter')
        if c['V_reset']>=c['V_th']:raise ValueError(f'{p}: V_reset must remain below V_th')
        if c.get('V_min',-float('inf'))>min(c['V_reset'],c['V_m']['min']):raise ValueError(f'{p}: V_min exceeds reset or initial potential')
        if c['V_m']['min']>c['V_m']['max']:raise ValueError(f'{p}: initial V_m min exceeds max')
    for conn,rows in e.get('connections',{}).get(mode,{}).items():
        for i,r in rows.items():
            s=result['connection_models'][conn]['synapses'][int(i)]
            for k,df in r.items():s[k]*=1-df/100
    for conn,c in result['connection_models'].items():
        for s in c['synapses']:
            for k,v in s.items():
                if number(v) and positive(k) and v<=0:raise ValueError(f'{conn}.{k} must remain > 0')
            if 'delay' in s and s['delay']<0.1-1e-12:raise ValueError(f'{conn}: delay must be at least 0.1 ms, the official resolution')
            for k in ('U','u','x','y'):
                if k in s and not 0<=s[k]<=1:raise ValueError(f'{conn}.{k}: TM probability/resources must be between 0 and 1')
            if s.get('x',0)+s.get('y',0)>1+1e-12:raise ValueError(f'{conn}: TM initial resources x + y must be <= 1')
    return result

def changes(e=None):
    e=e or {};b=baseline();out=[]
    for p,r in e.get('cells',{}).items():
        base=flat(b['cell_models'][p]['constants'])
        for k,v in r.items():
            if v:out.append({'section':'Cell electrical','target':p,'parameter':k,'df_percent':v,'baseline':base[k],'value':base[k]*(1-v/100),'unit':units(k)})
    for mode,conns in e.get('connections',{}).items():
        for conn,rows in conns.items():
            for i,r in rows.items():
                base=b[MODES[mode]][conn]['synapses'][int(i)]
                for k,v in r.items():
                    if v:out.append({'section':'Connection '+mode,'target':conn+' / '+RECEPTORS.get(base.get('receptor_type'),'relay/gap'),'parameter':k,'df_percent':v,'baseline':base[k],'value':base[k]*(1-v/100),'unit':info(k,base['model'],base.get('receptor_type'))[0]})
    return out
