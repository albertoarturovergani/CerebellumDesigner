"""Dendritic bifurcation tilt: an explicit, exploratory geometric operator.

Angles face the parent: at a fork C, local tilt is min angle(P-C, D-C),
using the nearest noncoincident parent P and each daughter D along the
unbranched arm (duplicate junction samples are retained). Remote tilt
uses the previous and next branch endpoints (fork, tip or soma). These
operational definitions are reported, not asserted to reproduce Mavroudis'
measurement pipeline. Degrees, binary dendritic forks only.
"""
from __future__ import annotations
import numpy as np
from scipy.spatial.transform import Rotation

FEATURE = 'bifurcation_tilt_deg'
REFERENCE = 'https://rjme.ro/RJME/resources/files/580217419424.pdf'
METHOD = {
    'id': 'dendritic_parent_facing_tilt_v1',
    'reference': REFERENCE,
    'reference_label': 'Mavroudis et al. (2017), Figure 1D',
    'definition': 'Minimum parent-facing angle at binary dendritic forks. Local: nearest noncoincident SWC parent/daughters along the unbranched arms, skipping duplicate junction samples without deleting them; remote: previous/next branch endpoints. Angles in degrees.',
    'operator': 'Add the requested degrees to each local parent-daughter angle, clipped to [1, 179] degrees; rotate each complete daughter subtree rigidly about its fork, proximal to distal, before whole-cell rotation.',
    'scope': 'Exploratory geometry, not a fitted SZ effect or a reproduction of the human study. Lengths, radii and topology are preserved. Branch opening angles and spatial extent can change. Remote tilt is measured, not independently controlled. No collision avoidance or layer clipping.',
}


def angle(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return None
    a, b = a / na, b / nb
    return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b)), np.clip(a @ b, -1, 1))))


def summary(values):
    a = np.asarray(values, dtype=float)
    return {'n': len(a), 'mean_deg': float(a.mean()) if len(a) else None,
            'median_deg': float(np.median(a)) if len(a) else None,
            'min_deg': float(a.min()) if len(a) else None,
            'max_deg': float(a.max()) if len(a) else None}


class DendriticBifurcations:
    def __init__(self, array, dendritic_tags=(3, 4)):
        self.ids = array[:, 0].astype(int)
        lookup = {node: i for i, node in enumerate(self.ids)}
        self.parents = np.array([lookup.get(int(p), -1) for p in array[:, 6]])
        self.dendrite = np.isin(array[:, 1], list(dendritic_tags))
        self.children = [[] for _ in array]
        for i, p in enumerate(self.parents):
            if p >= 0:
                self.children[p].append(i)
        for children in self.children:
            children.sort(key=lambda i: self.ids[i])
        order, stack = [], list(reversed(np.flatnonzero(self.parents < 0).tolist()))
        while stack:
            i = stack.pop(); order.append(i); stack.extend(reversed(self.children[i]))
        self.order = np.array(order, dtype=int)
        self.start = np.empty(len(array), dtype=int)
        self.start[self.order] = np.arange(len(array))
        self.size = np.ones(len(array), dtype=int)
        pure = self.dendrite.copy()
        for i in reversed(order):
            for c in self.children[i]:
                self.size[i] += self.size[c]
                pure[i] &= pure[c]
        self.forks, self.nonbinary, self.mixed = [], 0, 0
        for i in order:
            cs = self.children[i]
            if not self.dendrite[i] or len(cs) < 2:
                continue
            if len(cs) != 2:
                self.nonbinary += 1
            elif not all(pure[c] for c in cs):
                self.mixed += 1
            elif self.parents[i] >= 0:
                self.forks.append(i)

    def subtree(self, child):
        s = self.start[child]
        return self.order[s:s + self.size[child]]

    def endpoints(self, i):
        p = self.parents[i]
        while self.parents[p] >= 0 and self.dendrite[p] and len(self.children[p]) == 1:
            p = self.parents[p]
        ends = []
        for c in self.children[i]:
            while len(self.children[c]) == 1:
                c = self.children[c][0]
            ends.append(c)
        return p, ends

    def local_nodes(self, i, xyz):
        p = self.parents[i]
        while p >= 0 and np.linalg.norm(xyz[p] - xyz[i]) < 1e-12:
            p = self.parents[p]
        ends = []
        skipped = p != self.parents[i]
        for first in self.children[i]:
            c = first
            while np.linalg.norm(xyz[c] - xyz[i]) < 1e-12 and len(self.children[c]) == 1:
                c = self.children[c][0]
            ends.append(c)
            skipped |= c != first
        return p, ends, bool(skipped)

    def measure(self, array):
        xyz = array[:, 2:5]
        rows, local, remote = [], [], []
        duplicate_forks = 0
        for i in self.forks:
            p, ends, skipped = self.local_nodes(i, xyz)
            duplicate_forks += skipped
            ls = [angle(xyz[p] - xyz[i], xyz[c] - xyz[i]) if p >= 0 else None for c in ends]
            p, ends = self.endpoints(i)
            rs = [angle(xyz[p] - xyz[i], xyz[c] - xyz[i]) for c in ends]
            l = min(ls) if all(v is not None for v in ls) else None
            r = min(rs) if all(v is not None for v in rs) else None
            if l is not None: local.append(l)
            if r is not None: remote.append(r)
            rows.append({'swc_id': int(self.ids[i]), 'local_deg': l, 'remote_deg': r})
        return {'method': METHOD, 'local': summary(local), 'remote': summary(remote),
                'forks': rows, 'eligible_binary_forks': len(self.forks),
                'skipped_nonbinary': self.nonbinary, 'skipped_mixed_subtrees': self.mixed,
                'duplicate_junctions_resolved': duplicate_forks,
                'undefined_local': len(self.forks) - len(local), 'undefined_remote': len(self.forks) - len(remote)}

    def transform(self, array, delta_deg):
        out = array.copy()
        audit = {'requested_change_deg': float(delta_deg), 'modified_forks': 0,
                 'clipped_daughter_angles': 0, 'skipped_zero_length_forks': 0, 'duplicate_junctions_resolved': 0,
                 'skipped_nonbinary': self.nonbinary, 'skipped_mixed_subtrees': self.mixed}
        if delta_deg == 0:
            return out, audit
        xyz = out[:, 2:5]
        for i in self.forks:
            origin = xyz[i].copy()
            p, ends, skipped = self.local_nodes(i, xyz)
            audit['duplicate_junctions_resolved'] += skipped
            if p < 0:
                audit['skipped_zero_length_forks'] += 1
                continue
            u = xyz[p] - origin
            cs = self.children[i]
            angles = [angle(u, xyz[c] - origin) for c in ends]
            if any(a is None for a in angles):
                audit['skipped_zero_length_forks'] += 1
                continue
            u /= np.linalg.norm(u)
            for c, direction_node, theta in zip(cs, ends, angles):
                target = float(np.clip(theta + delta_deg, 1, 179))
                audit['clipped_daughter_angles'] += int(abs(target - theta - delta_deg) > 1e-9)
                v = xyz[direction_node] - origin; v /= np.linalg.norm(v)
                axis = np.cross(u, v)
                if np.linalg.norm(axis) < 1e-12:
                    # Collinear fork: deterministic plane, never random noise.
                    axis = np.cross(u, np.eye(3)[np.argmin(np.abs(u))])
                axis /= np.linalg.norm(axis)
                rotation = Rotation.from_rotvec(axis * np.radians(target - theta))
                indices = self.subtree(c)
                xyz[indices] = rotation.apply(xyz[indices] - origin) + origin
            audit['modified_forks'] += 1
        return out, audit
