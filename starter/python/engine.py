from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def round_half_up(value: int, denominator: int = 1) -> int:
    q = (Decimal(value) / Decimal(denominator)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(q)


def rotate_dims(w: int, d: int, rotation: int) -> tuple[int, int]:
    return (d, w) if rotation % 180 else (w, d)


def rect(cx: int, cy: int, w: int, d: int) -> tuple[int, int, int, int]:
    return (cx - w // 2, cy - d // 2, cx + (w + 1) // 2, cy + (d + 1) // 2)


def bbox_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int], gap: int = 0) -> bool:
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def orientation(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def on_segment(a, b, p):
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]) and orientation(a, b, p) == 0


def segments_intersect(a, b, c, d):
    o1, o2, o3, o4 = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and on_segment(a, b, c)) or (o2 == 0 and on_segment(a, b, d)) or (o3 == 0 and on_segment(c, d, a)) or (o4 == 0 and on_segment(c, d, b))


def point_seg_dist2(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    q = (a[0] + t * dx, a[1] + t * dy)
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2


def segment_rect_dist2(a, b, r):
    x1, y1, x2, y2 = r
    corners = [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    if any(point_in_polygon(p[0], p[1], [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]) for p in [a,b]):
        return 0.0
    if any(segments_intersect(a,b,c,d) for c,d in edges):
        return 0.0
    vals = [point_seg_dist2(p,a,b) for p in corners] + [point_seg_dist2(a,c,d) for c,d in edges] + [point_seg_dist2(b,c,d) for c,d in edges]
    return min(vals)


def rect_inside_polygon(r: tuple[int,int,int,int], poly: list[list[float]]) -> bool:
    x1,y1,x2,y2 = r
    corners = [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
    if not all(point_in_polygon(x,y,poly) or any(abs(x-p[0])<1e-9 and abs(y-p[1])<1e-9 for p in poly) for x,y in corners):
        return False
    # Prevent a rectangle edge from crossing a concave boundary while all corners happen to be inside.
    edges = list(zip(corners, corners[1:] + corners[:1]))
    pedges = list(zip(poly, poly[1:] + poly[:1]))
    return not any(segments_intersect(a,b,c,d) for a,b in edges for c,d in pedges if orientation(a,b,c) != 0 or orientation(a,b,d) != 0)


def wall_distance_ok(r, poly, minimum=100):
    # Conservative: every footprint corner must be at least minimum from every boundary segment.
    x1,y1,x2,y2=r
    corners=[(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
    pedges=list(zip(poly, poly[1:]+poly[:1]))
    for p in corners:
        if min(math.sqrt(point_seg_dist2(p,a,b)) for a,b in pedges) < minimum - 1e-9:
            return False
    return True


def door_zone(room: dict[str,Any], door: dict[str,Any], depth: int = 850):
    wall=door['wall']; off=door['offset_mm']; width=door['width_mm']
    if wall == 'south': return (off, 0, off+width, depth)
    if wall == 'north':
        h=max(p[1] for p in room['boundary_mm']); return (off, h-depth, off+width, h)
    if wall == 'west': return (0, off, depth, off+width)
    if wall == 'east':
        w=max(p[0] for p in room['boundary_mm']); return (w-depth, off, w, off+width)
    return None


def door_center(room, door):
    wall=door['wall']; off=door['offset_mm']; width=door['width_mm']
    xs=[p[0] for p in room['boundary_mm']]; ys=[p[1] for p in room['boundary_mm']]
    if wall=='south': return ((off+off+width)//2, min(ys))
    if wall=='north': return ((off+off+width)//2, max(ys))
    if wall=='west': return (min(xs), (off+off+width)//2)
    return (max(xs), (off+off+width)//2)


def egress_clear(r, room, min_width=1100):
    start=door_center(room, next(d for d in room['doors'] if d['door_id']==room['egress']['from_door_id']))
    end=tuple(room['egress']['to_point_mm'])
    return segment_rect_dist2(start,end,r) >= (min_width/2)**2


def clearance_zone(r, family, rotation):
    x1,y1,x2,y2=r
    if family == 'desk': gap=900
    elif family == 'chair': gap=750
    else: return None
    # rear/pull-out direction is +Y for 0 degrees; rotate the clearance vector with the item.
    if rotation % 360 == 0: return (x1, y2, x2, y2+gap)
    if rotation % 360 == 90: return (x2, y1, x2+gap, y2)
    if rotation % 360 == 180: return (x1, y1-gap, x2, y1)
    return (x1-gap, y1, x1, y2)


def validate_layout(room: dict[str,Any], placements: list[dict[str,Any]], catalog_by_sku: dict[str,dict[str,Any]], rules: dict[str,Any]) -> list[dict[str,Any]]:
    violations=[]
    footprints={}
    for p in placements:
        item=catalog_by_sku[p['sku']]
        w,d=rotate_dims(item['dimensions_mm']['width'],item['dimensions_mm']['depth'],p['rotation_deg'])
        footprints[p['placement_id']]=rect(p['x_mm'],p['y_mm'],w,d)
    # Room boundary and wall offset.
    for p in placements:
        r=footprints[p['placement_id']]
        if not rect_inside_polygon(r,room['boundary_mm']):
            violations.append(vio('RB-GEO-007',p,'Footprint is outside the room boundary.',{'kind':'inside_room_boundary'}))
        elif not wall_distance_ok(r,room['boundary_mm'],100):
            violations.append(vio('RB-GEO-005',p,'Furniture is closer than 100 mm to a wall.',{'min_wall_offset_mm':100}))
    # Overlaps.
    ids=list(footprints)
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            if bbox_intersects(footprints[a],footprints[b]):
                violations.append(vio('RB-GEO-006',None,'Furniture footprints overlap.',{'a':a,'b':b},[a,b]))
    # Door swings.
    for door in room.get('doors',[]):
        if not str(door.get('swing','')).startswith('inward'):
            continue
        zone=door_zone(room,door,850)
        for p in placements:
            if zone and bbox_intersects(footprints[p['placement_id']],zone):
                violations.append(vio('RB-GEO-003',p,'Furniture enters the door-swing clearance zone.',{'zone_mm':list(zone)}))
    # Egress corridor.
    for p in placements:
        if not egress_clear(footprints[p['placement_id']],room,1100):
            violations.append(vio('RB-GEO-002',p,'Furniture narrows the marked 1100 mm egress path.',{'required_width_mm':1100}))
    # Family rear/pull-out clearance. Treat clearance zone as a no-furniture zone.
    for p in placements:
        if p.get('family') not in ('desk','chair'):
            continue
        zone=clearance_zone(footprints[p['placement_id']],p['family'],p['rotation_deg'])
        if not zone: continue
        for q in placements:
            if q['placement_id']==p['placement_id']: continue
            if q.get('placement_id') in p.get('paired_with',[]):
                continue
            if bbox_intersects(footprints[q['placement_id']],zone):
                rule='RB-GEO-004' if p['family']=='desk' else 'RB-GEO-008'
                msg='Occupied desks require 900 mm rear clearance.' if rule=='RB-GEO-004' else 'Task chairs require a 750 mm pull-out zone.'
                violations.append(vio(rule,p,msg,{'required_clearance_mm':900 if rule=='RB-GEO-004' else 750},[p['placement_id'],q['placement_id']]))
    return dedupe_violations(violations)


def vio(rule_id,p,message,measured=None,affected=None):
    if affected is None: affected=[] if p is None else [p['placement_id']]
    key='-'.join(sorted(affected))
    return {'violation_id':f'V-{rule_id}-{key}', 'rule_id':rule_id, 'message':message,
            'affected_placement_ids':affected, 'measured':measured or {},
            'repair_options':[{'action':'move','strategy':'deterministic_candidate_search'}]}


def dedupe_violations(vs):
    seen=set(); out=[]
    for v in vs:
        k=(v['rule_id'],tuple(v['affected_placement_ids']))
        if k not in seen: seen.add(k); out.append(v)
    return sorted(out,key=lambda v:(v['rule_id'],v['violation_id']))


def brief_requirements(brief: str, capacity: int) -> dict[str,int]:
    b=brief.lower()
    req={}
    word_nums={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20}
    for word,n in word_nums.items():
        b=re.sub(r'\b'+word+r'\b',str(n),b)
    # Explicit family counts are authoritative when stated.
    m=re.search(r'(?:create|plan|provide|design).*?(\d+)[- ]person',b)
    if not m: m=re.search(r'team of (\d+)',b)
    people=int(m.group(1)) if m else capacity
    req['chairs']=people
    if 'desk' in b or 'work positions' in b:
        m=re.search(r'(\d+)\s+(?:fixed\s+)?work positions',b)
        if m: req['desks']=int(m.group(1))
        else:
            m=re.search(r'(\d+)\s+desk',b)
            if m: req['desks']=int(m.group(1))
            elif 'individual desks' in b: req['desks']=people
    if 'paired desks' in b:
        req['desks']=people//2
    if 'collaboration table' in b or 'collaboration tables' in b or 'collaboration zone' in b or 'touchdown table' in b:
        m=re.search(r'(\d+)\s+(?:compact\s+)?collaboration\s+table',b)
        req['collaboration']=int(m.group(1)) if m else (2 if 'two collaboration' in b else 1)
        if 'two collaboration zones' in b: req['collaboration']=2
    if 'storage' in b:
        m=re.search(r'(\d+)\s+(?:lockable\s+)?storage',b)
        req['storage']=int(m.group(1)) if m else (4 if 'distributed storage' in b or 'accessible storage' in b else 2)
    if 'accessor' in b or 'writable' in b or 'acoustic' in b:
        req['accessory']=2
    return req
