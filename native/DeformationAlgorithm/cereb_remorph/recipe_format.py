"""Public v2 uses signed changes; the validated legacy engine uses inverse DF.

The conversion is exact: it reflects means/bounds, never sigma or angles.
This preserves the keyed samples and physical effects of existing v1 recipes.
"""
from copy import deepcopy

def reflect(recipe, schema):
    r=deepcopy(recipe)
    def cell(params):
        for key,spec in params.items():
            if key.endswith('_df_percent') or key=='df_percent':
                spec['mean']=-spec['mean']
                bounds=spec.get('bounds',[0,65] if schema=='cereb-df/v2' else [-100,100])
                spec['bounds']=[-bounds[1],-bounds[0]]
    def network(values):
        for key in ('thickness_df_percent','density_df_percent'):
            if key in values:
                spec=values[key]
                if isinstance(spec,dict):
                    spec['mean']=-spec['mean']
                    bounds=spec.get('bounds',[0,65] if schema=='cereb-df/v2' else [-100,100])
                    spec['bounds']=[-bounds[1],-bounds[0]]
                else:values[key]=-spec
    cell(r.get('defaults',{}))
    for group in ('layers','populations'):
        for values in r.get(group,{}).values():
            network(values);cell(values.get('cells',{}))
    for item in r.get('individuals',[]):cell(item.get('cells',{}))
    e=r.get('electrical',{})
    for values in e.get('cells',{}).values():
        for key in values:values[key]=-values[key]
    for conns in e.get('connections',{}).values():
        for components in conns.values():
            for values in components.values():
                for key in values:values[key]=-values[key]
    r['schema']=schema
    return r

def to_engine(recipe):
    return reflect(recipe,'cereb-df/v1') if recipe.get('schema')=='cereb-df/v2' else deepcopy(recipe)

def to_public(recipe):
    return reflect(recipe,'cereb-df/v2') if recipe.get('schema')=='cereb-df/v1' else deepcopy(recipe)
