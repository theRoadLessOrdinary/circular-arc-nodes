#!/usr/bin/env python3
"""
Circular Arc Between Nodes

In the Node tool (N), select two or more nodes on one path, then run this.
Only the first and last selected node (in path order) are used. Everything
between them, including any nodes, is replaced by one true circular arc
(an SVG "A" segment, not a Bezier approximation).

Two end nodes alone fit any number of circles, so the arc's bulge is set by
the neighbor: the arc leaves the first end node in the same direction the
segment before it arrives, which leaves no corner at that join. If there is
no segment before the first end node, the segment after the last end node
sets the direction instead. If the selection spans the whole path, the
existing curve's own direction at the first end node is used.

At the other end node, if it is a smooth node, the neighboring Bezier handle
is rotated to line up with the arc (its length is kept). Inkscape does not do
this by itself after a path is rewritten.

The arc is a true circle on the canvas even when the path sits inside groups
that scale it unevenly: the "A" segment is written as the ellipse that those
transforms turn back into a circle.

No dialog, so it can be bound to a keyboard shortcut in Preferences >
Interface > Keyboard Shortcuts.
"""
import math

import inkex
from inkex import EffectExtension, PathElement
from inkex.paths import Arc, Curve, Line, Move, Path, Quadratic, ZoneClose

EPS = 1e-9
SMOOTH_TYPES = "sza"
SMOOTH_ANGLE_TOL = math.radians(2.0)
NODETYPES = "sodipodi:nodetypes"

HOW_TO = (
    "Switch to the Node tool (N), select two or more nodes on one path, "
    "then run this again. The first and last selected node become the ends "
    "of the arc."
)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def length(v):
    return math.hypot(v[0], v[1])


def unit(v):
    n = length(v)
    return (v[0] / n, v[1] / n)


def same_point(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def end_point(cmd):
    return (cmd.args[-2], cmd.args[-1])


def segment_cubic(p0, cmd):
    """The four cubic control points of one absolute, non-shorthand segment
    starting at p0. Arcs give the handles of their first and last piece,
    which is all that is needed for a direction."""
    p3 = end_point(cmd)
    if isinstance(cmd, Curve):
        a = cmd.args
        return [p0, (a[0], a[1]), (a[2], a[3]), p3]
    if isinstance(cmd, Quadratic):
        q = (cmd.args[0], cmd.args[1])
        return [
            p0,
            (p0[0] + 2.0 / 3.0 * (q[0] - p0[0]), p0[1] + 2.0 / 3.0 * (q[1] - p0[1])),
            (p3[0] + 2.0 / 3.0 * (q[0] - p3[0]), p3[1] + 2.0 / 3.0 * (q[1] - p3[1])),
            p3,
        ]
    if isinstance(cmd, Arc):
        csp = Path([Move(*p0), cmd]).to_superpath()[0]
        return [p0, tuple(csp[0][2]), tuple(csp[-1][0]), p3]
    return [p0, p0, p3, p3]


def arrive_dir(cubic):
    """Direction of travel where the segment ends, or None if it has no length."""
    p0, c1, c2, p3 = cubic
    for q in (c2, c1, p0):
        v = sub(p3, q)
        if length(v) > EPS:
            return unit(v)
    return None


def leave_dir(cubic):
    """Direction of travel where the segment starts, or None if it has no length."""
    p0, c1, c2, p3 = cubic
    for q in (c1, c2, p3):
        v = sub(q, p0)
        if length(v) > EPS:
            return unit(v)
    return None


def tangent_arc(a, b, t):
    """Circle through a and b that leaves a in direction t (a unit vector).

    Returns (radius, large_arc, sweep, direction_at_b). radius is None when
    b lies straight ahead of a, where the arc is a straight line.
    Raises ValueError when b lies straight behind a (no circle fits)."""
    d = sub(b, a)
    dist = length(d)
    n = (-t[1], t[0])
    dn = d[0] * n[0] + d[1] * n[1]
    dt = d[0] * t[0] + d[1] * t[1]
    if abs(dn) < 1e-9 * dist:
        if dt > 0:
            return None, 0, 0, t
        raise ValueError
    k = dist * dist / (2.0 * dn)
    dh = (d[0] / dist, d[1] / dist)
    proj = t[0] * dh[0] + t[1] * dh[1]
    at_b = (2.0 * proj * dh[0] - t[0], 2.0 * proj * dh[1] - t[1])
    return abs(k), 1 if dt < 0 else 0, 1 if k > 0 else 0, at_b


def ellipse_of(linear, radius):
    """rx, ry and rotation (degrees) of the ellipse a circle of the given
    radius becomes under the 2x2 matrix ((m00, m01), (m10, m11))."""
    (m00, m01), (m10, m11) = linear
    e, f = (m00 + m11) / 2.0, (m00 - m11) / 2.0
    g, h = (m10 + m01) / 2.0, (m10 - m01) / 2.0
    q, r = math.hypot(e, h), math.hypot(f, g)
    a1, a2 = math.atan2(g, f), math.atan2(h, e)
    return radius * (q + r), radius * abs(q - r), math.degrees((a2 + a1) / 2.0)


def format_cmd(cmd):
    return " ".join([cmd.letter] + [f"{v:.10g}" for v in cmd.args])


class Subpath:
    """One subpath as a list of absolute commands. cmds[0] is the Move, and
    node i is the end point of cmds[i]."""

    def __init__(self):
        self.cmds = []
        self.closed = False

    def point(self, i):
        return end_point(self.cmds[i])

    @property
    def returns_to_start(self):
        return len(self.cmds) > 1 and same_point(self.point(-1), self.point(0))

    @property
    def nodetype_count(self):
        if self.closed and not self.returns_to_start:
            return len(self.cmds) + 1
        return len(self.cmds)


def split_subpaths(path):
    subs = []
    for cmd in path:
        if isinstance(cmd, Move):
            subs.append(Subpath())
            subs[-1].cmds.append(cmd)
        elif isinstance(cmd, ZoneClose):
            if subs:
                subs[-1].closed = True
        elif subs:
            subs[-1].cmds.append(cmd)
    return subs


class CircularArcNodes(EffectExtension):
    def effect(self):
        groups = {}
        for sel in self.options.selected_nodes:
            try:
                elem_id, sp, node = sel.rsplit(":", 2)
                groups.setdefault(elem_id, {}).setdefault(int(sp), set()).add(int(node))
            except ValueError:
                continue

        done = 0
        problems = []
        for elem_id, by_subpath in groups.items():
            elem = self.svg.getElementById(elem_id)
            if not isinstance(elem, PathElement):
                continue
            if elem.get("inkscape:original-d") is not None:
                problems.append(
                    f"{elem_id}: has a path effect, which this does not handle."
                )
                continue
            done += self.process(elem, by_subpath, problems)

        if problems:
            inkex.errormsg("\n".join(problems))
        elif not done:
            raise inkex.AbortExtension(HOW_TO)

    def process(self, elem, by_subpath, problems):
        to_canvas = elem.composed_transform()
        to_local = -to_canvas
        linear = ((to_local.a, to_local.c), (to_local.b, to_local.d))
        flipped = to_local.a * to_local.d - to_local.b * to_local.c < 0

        def canvas(p):
            q = to_canvas.apply_to_point(p)
            return (q.x, q.y)

        def local(p):
            q = to_local.apply_to_point(p)
            return (q.x, q.y)

        subs = split_subpaths(elem.path.to_absolute().to_non_shorthand())
        types = elem.get(NODETYPES)
        if types is not None and len(types) != sum(s.nodetype_count for s in subs):
            types = None
        offsets = []
        total = 0
        for s in subs:
            offsets.append(total)
            total += s.nodetype_count

        done = 0
        removed = []
        for sp_index in sorted(by_subpath):
            nodes = by_subpath[sp_index]
            if sp_index >= len(subs) or len(nodes) < 2:
                continue
            s = subs[sp_index]
            a, b = min(nodes), max(nodes)
            if b >= len(s.cmds):
                continue
            if any(isinstance(c, Arc) for c in s.cmds[: b + 1]):
                problems.append(
                    f"{elem.get_id()}: this path already has an arc segment at or "
                    "before the selected nodes, and Inkscape numbers the nodes of "
                    "arc segments differently from how they are stored, so the "
                    "selection cannot be trusted. Move any node of the path a "
                    "little and back (Inkscape then rewrites the arc as Beziers), "
                    "then run this again."
                )
                continue
            pa, pb = canvas(s.point(a)), canvas(s.point(b))
            if same_point(pa, pb):
                continue

            def cubic(i):
                """Segment ending at node i, in canvas coordinates."""
                return [canvas(p) for p in segment_cubic(s.point(i - 1), s.cmds[i])]

            before = after = None
            if a > 0:
                before = cubic(a)
            elif s.closed:
                last = len(s.cmds) - 1
                if s.returns_to_start and last > b:
                    before = cubic(last)
                elif not s.returns_to_start:
                    end = canvas(s.point(last))
                    before = [end, end, pa, pa]
            if b + 1 < len(s.cmds):
                after = cubic(b + 1)
            elif s.closed and not s.returns_to_start and a > 0:
                start = canvas(s.point(0))
                after = [pb, pb, start, start]

            old_arrive_b = arrive_dir(cubic(b))
            t_a = arrive_dir(before) if before else None
            t_b = leave_dir(after) if after else None
            try:
                if t_a is not None:
                    radius, large, sweep, at_b = tangent_arc(pa, pb, t_a)
                elif t_b is not None:
                    back = (-t_b[0], -t_b[1])
                    radius, large, sweep, _ = tangent_arc(pb, pa, back)
                    sweep = 1 - sweep
                    at_b = t_b
                else:
                    own = leave_dir(cubic(a + 1))
                    if own is None:
                        continue
                    radius, large, sweep, at_b = tangent_arc(pa, pb, own)
            except ValueError:
                problems.append(
                    f"{elem.get_id()}: the last selected node lies exactly behind "
                    "the direction the path arrives from, so no circle fits."
                )
                continue

            end = s.point(b)
            if radius is None:
                new_cmd = Line(*end)
            else:
                rx, ry, rot = ellipse_of(linear, radius)
                new_cmd = Arc(rx, ry, rot, large, 1 - sweep if flipped else sweep, *end)

            # Line the neighbor's handle up with the arc at a smooth end node.
            nxt = b + 1
            if t_a is not None and nxt < len(s.cmds) and isinstance(s.cmds[nxt], Curve):
                if types is not None:
                    smooth = types[offsets[sp_index] + b] in SMOOTH_TYPES
                else:
                    smooth = (
                        old_arrive_b is not None
                        and t_b is not None
                        and abs(
                            math.atan2(
                                old_arrive_b[0] * t_b[1] - old_arrive_b[1] * t_b[0],
                                old_arrive_b[0] * t_b[0] + old_arrive_b[1] * t_b[1],
                            )
                        )
                        < SMOOTH_ANGLE_TOL
                    )
                handle = length(sub(after[1], pb))
                if smooth and handle > EPS:
                    c1 = local((pb[0] + at_b[0] * handle, pb[1] + at_b[1] * handle))
                    args = s.cmds[nxt].args
                    s.cmds[nxt] = Curve(c1[0], c1[1], *args[2:])

            s.cmds[a + 1 : b + 1] = [new_cmd]
            removed.extend(range(offsets[sp_index] + a + 1, offsets[sp_index] + b))
            done += 1

        if not done:
            return 0

        out = []
        for s in subs:
            out.extend(s.cmds)
            if s.closed:
                out.append(ZoneClose())
        # Written by hand: inkex rounds to 6 significant digits, which is
        # enough to put a visible fraction of a degree of corner into the join.
        elem.set("d", " ".join(format_cmd(c) for c in out))
        if types is not None:
            gone = set(removed)
            elem.set(NODETYPES, "".join(c for i, c in enumerate(types) if i not in gone))
        elif elem.get(NODETYPES) is not None:
            elem.set(NODETYPES, None)
        return done


if __name__ == "__main__":
    CircularArcNodes().run()
