"""Dendritic complexity following Masoli et al. 2024, equation 2.

Orders count dendritic branch points between the soma and a terminal tip;
SWC sampling points do not increment order. Primary unbranched stems have order 0.
Lengths include the attachment edge from soma to the first dendritic point.
"""
import numpy as np

DCI_SOURCE = 'https://doi.org/10.1038/s42003-023-05689-y'


def dendritic_complexity(array, parents, types):
    selected = {i for i, t in enumerate(types) if t == 'dendrite'}
    children = {i: [] for i in selected}
    roots = []
    length = 0.0
    for i in selected:
        p = parents[i]
        if p in selected:
            children[p].append(i)
        else:
            roots.append(i)
        if p >= 0:
            length += float(np.linalg.norm(array[i, 2:5] - array[p, 2:5]))
    tip_orders = []
    stack = [(i, 0) for i in roots]
    while stack:
        i, order = stack.pop()
        if not children[i]:
            tip_orders.append(order)
        else:
            next_order = order + (len(children[i]) > 1)
            stack.extend((c, next_order) for c in children[i])
    dci = (sum(tip_orders) + len(tip_orders)) * length / len(roots) if roots else 0.0
    return dict(dci=dci, length_um=length, primary_dendrites=len(roots),
                tips=len(tip_orders), tip_order_sum=sum(tip_orders),
                source=DCI_SOURCE, unit='µm',
                order_convention='Number of dendritic branch points from soma to tip; primary stem order 0.')
