"""Units and concise meanings from the installed EGLIF multireceptor NESTML."""

CELL = {
    'C_m': ('pF', 'Membrane capacitance: charge required to change voltage.'),
    't_ref': ('ms', 'Refractory interval after a spike.'),
    'tau_m': ('ms', 'Passive membrane relaxation time.'),
    'V_th': ('mV', 'Spike threshold voltage.'),
    'V_reset': ('mV', 'Voltage immediately after a spike.'),
    'V_min': ('mV', 'Lower bound on membrane voltage.'),
    'V_m.min': ('mV', 'Lower bound of the initial voltage distribution.'),
    'V_m.max': ('mV', 'Upper bound of the initial voltage distribution.'),
    'E_L': ('mV', 'Leak reversal potential.'),
    'I_e': ('pA', 'Constant external current bias.'),
    'A1': ('pA', 'Depolarizing current set after each spike.'),
    'A2': ('pA', 'Adaptation current increment per spike.'),
    'k_1': ('ms⁻¹', 'Decay rate of the depolarizing current.'),
    'k_2': ('ms⁻¹', 'Decay rate of the adaptation current.'),
    'k_adap': ('nS/ms', 'Voltage coupling into the adaptation-current derivative.'),
}
RECEPTOR = {
    'E_rev': ('mV', 'Receptor reversal potential.'),
    'g_init': ('nS', 'Initial conductance scale of the receptor rise kernel.'),
    'Tau_r': ('ms', 'Rise time scale of the receptor kernel.'),
    'Tau_d1': ('ms', 'Fast decay time scale of the receptor kernel.'),
    'Tau_d2': ('ms', 'Slow decay time scale of the receptor kernel.'),
    'A_r': ('dimensionless', 'Rise-kernel scaling coefficient.'),
    'A1': ('dimensionless', 'Fast decay-kernel scaling coefficient.'),
    'A2': ('dimensionless', 'Slow decay-kernel scaling coefficient.'),
}
SYNAPSE = {
    'delay': ('ms', 'Time from a presynaptic spike to synaptic delivery.'),
    'U': ('fraction', 'Baseline fraction of synaptic resources used on release.'),
    'u': ('fraction', 'Initial release utilization state.'),
    'x': ('fraction', 'Initial fraction of recovered synaptic resources.'),
    'y': ('fraction', 'Initial fraction of active synaptic resources.'),
    'tau_rec': ('ms', 'Recovery time for depleted synaptic resources.'),
    'tau_fac': ('ms', 'Facilitation decay time; zero disables facilitation.'),
    'tau_psc': ('ms', 'Decay time of the active synaptic resource state.'),
}


def info(key, model=None, receptor=None):
    if key == 'weight':
        if model == 'gap_junction':
            return ('nS', 'Electrical coupling conductance.')
        if receptor is None:
            return ('relay weight', 'Spike-relay weight; not a postsynaptic conductance.')
        return ('dimensionless', 'Multiplier of the postsynaptic receptor conductance kernel.')
    if key in CELL:
        return CELL[key]
    if key in SYNAPSE:
        return SYNAPSE[key]
    for prefix in ('AMPA_', 'AMPA2_', 'AMPA3_', 'NMDA_', 'GABA_'):
        if key.startswith(prefix) and key[len(prefix):] in RECEPTOR:
            return RECEPTOR[key[len(prefix):]]
    return ('model units', 'Native model parameter; see the installed model definition.')
