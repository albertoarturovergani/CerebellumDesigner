"""MPI placement and native connectivity, with explicit absent-feature handling."""
import json
from pathlib import Path
import sys


def connectivity(path):
    from bsb import from_storage
    from mpi4py import MPI
    comm=MPI.COMM_WORLD
    net=from_storage(path)
    report_path=Path(path).parent/'cell_assignments.json'
    reports=json.loads(report_path.read_text( encoding='utf-8'))['populations'] if report_path.exists() else {}
    skipped={};filtered=[]
    strategies=list(net.connectivity.values())
    for s in strategies:
        for side in ('presynaptic','postsynaptic'):
            hemi=getattr(s,side)
            labels=hemi.morphology_labels or []
            if labels and 'soma' not in labels and any(reports.get(ct.name,{}).get('soma_only_cells',0) for ct in hemi.cell_types):
                if hemi.labels:raise ValueError('Existing cell filters require explicit composition')
                hemi.labels=['dfneuritespresent']
                filtered.append({'rule':s.name,'side':side,'reason':'Absent neurites cannot supply synaptic contacts; soma-only cells remain in the population.'})
            if not sum(len(net.get_placement_set(ct,labels=hemi.labels)) for ct in hemi.cell_types):
                skipped[s.name]=f'No eligible {side} cells'
    changed=True
    while changed:
        changed=False
        for s in strategies:
            if s.name not in skipped and any(dep.name in skipped for dep in s.depends_on):
                skipped[s.name]='Required upstream connectivity is empty';changed=True
    if comm.rank==0:
        for s in strategies:
            for pre in s.presynaptic.cell_types:
                for post in s.postsynaptic.cell_types:
                    for name in s.get_output_names(pre,post):net.require_connectivity_set(pre,post,name)
        (Path(path).parent/'connectivity_availability.json').write_text(json.dumps({'skipped':skipped,'cell_filters':filtered,'native_rules_preserved':True},indent=2)+'\n', encoding='utf-8', newline='\n')
    comm.Barrier()
    net.run_connectivity(strategies=[s for s in strategies if s.name not in skipped],pipelines=False)
    if not skipped and not filtered:net.run_after_connectivity(pipelines=False)
    elif comm.rank==0:print('Empty features: native connectivity completed; availability is recorded in connectivity_availability.json. Optional upstream PDF analysis skipped for empty populations.',flush=True)

try:
    if sys.argv[1]=='placement':
        from bsb.cli import handle_command
        handle_command(['compile',sys.argv[2],'--skip-connectivity','--skip-after-placement','--skip-after-connectivity','-v3'])
    elif sys.argv[1]=='connectivity':connectivity(sys.argv[2])
    else:raise ValueError('Unknown stage')
finally:
    if 'mpilock' in sys.modules:sys.modules['mpilock']._stop_all_pumps()
