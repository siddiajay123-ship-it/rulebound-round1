from __future__ import annotations
import argparse, json
from pathlib import Path
from rulebound_loader import load_asset_pack
from engine import brief_requirements, validate_layout, rotate_dims, rect, bbox_intersects, door_zone, egress_clear, clearance_zone, rect_inside_polygon, wall_distance_ok
from pricing import price_quote, blocked_quote

def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def compatible(item, finish):
    return finish['finish_id'] in item.get('compatible_finish_ids',[]) and item['family'] in finish.get('compatible_families',[])

def choose_sku(family, catalog, finishes, preferred=('F03','F02','F05','F09','F01')):
    items=sorted((x for x in catalog if x['family']==family), key=lambda x:(x['dimensions_mm']['width']*x['dimensions_mm']['depth'],x['sku']))
    for fid in preferred:
        fin=next((z for z in finishes if z['finish_id']==fid),None)
        for x in items:
            if fin and compatible(x,fin): return x,fin
    x=items[0]; return x,next(f for f in finishes if compatible(x,f))

def make_candidates(room, item):
    xs=[p[0] for p in room['boundary_mm']]; ys=[p[1] for p in room['boundary_mm']]
    minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
    for rotation in (0,90,180,270):
        w,d=rotate_dims(item['dimensions_mm']['width'],item['dimensions_mm']['depth'],rotation)
        for y in range(miny+100+d//2, maxy-100-d//2+1, 200):
            for x in range(minx+100+w//2, maxx-100-w//2+1, 200):
                yield x,y,rotation

def fits_basic(room,p,placed,catalog_by_sku):
    item=catalog_by_sku[p['sku']]; w,d=rotate_dims(item['dimensions_mm']['width'],item['dimensions_mm']['depth'],p['rotation_deg']); r=rect(p['x_mm'],p['y_mm'],w,d)
    if not rect_inside_polygon(r,room['boundary_mm']) or not wall_distance_ok(r,room['boundary_mm'],100): return False
    for q in placed:
        qi=catalog_by_sku[q['sku']]; qw,qd=rotate_dims(qi['dimensions_mm']['width'],qi['dimensions_mm']['depth'],q['rotation_deg']); qr=rect(q['x_mm'],q['y_mm'],qw,qd)
        if bbox_intersects(r,qr): return False
        z=clearance_zone(qr,q.get('family'),q['rotation_deg'])
        if z and bbox_intersects(r,z): return False
    for door in room.get('doors',[]):
        if str(door.get('swing','')).startswith('inward') and bbox_intersects(r,door_zone(room,door,850)): return False
    if not egress_clear(r,room,1100): return False
    return True

def candidate_moves(room,p,placed,catalog_by):
    item=catalog_by[p['sku']]; original=(p['x_mm'],p['y_mm'],p['rotation_deg'])
    for x,y,r in make_candidates(room,item):
        if (x,y,r)==original: continue
        q=dict(p,x_mm=x,y_mm=y,rotation_deg=r)
        others=[z for z in placed if z['placement_id']!=p['placement_id']]
        if fits_basic(room,q,others,catalog_by): yield q

def arbitrate(room,placements,catalog,failed_family=None,demo=False):
    catalog_by={x['sku']:x for x in catalog}
    if demo and len(placements)>1:
        bad=dict(placements[0]); bad['x_mm']=placements[1]['x_mm']; bad['y_mm']=placements[1]['y_mm']
        placements=list(placements); placements[0]=bad
        print('DEMO: injected RB-GEO-006 overlap; arbitration will repair it.')
    history=[]; max_passes=max(1,len(placements)*8+8)
    for pass_no in range(max_passes):
        violations=validate_layout(room,placements,catalog_by,{})
        if not violations and not failed_family:
            if history: print(f'Arbitration {room["room_id"]}: repaired in {len(history)} pass(es).')
            return {'room_id':room['room_id'],'placements':sorted(placements,key=lambda p:p['placement_id']),'violations':[],'status':'valid'}
        if not violations: break
        before=len(violations); repaired=False
        for v in violations:
            for target in [p for p in placements if p['placement_id'] in v['affected_placement_ids']]:
                for moved in candidate_moves(room,target,placements,catalog_by):
                    trial=list(placements); trial[placements.index(target)]=moved
                    after=validate_layout(room,trial,catalog_by,{})
                    if len(after)<before:
                        placements=trial; history.append({'pass':pass_no+1,'rule_id':v['rule_id'],'placement_id':target['placement_id'],'measure_before':before,'measure_after':len(after)}); repaired=True; break
                if repaired: break
            if repaired: break
        if not repaired: break
    violations=validate_layout(room,placements,catalog_by,{})
    if failed_family and not violations:
        violations=[{'violation_id':f'V-ESCALATE-{failed_family.upper()}',
                     'rule_id':'RB-GEO-002',
                     'message':f'No remaining placement candidate can satisfy the complete released geometry while adding the required {failed_family} quantity.',
                     'affected_placement_ids':[],
                     'measured':{'requested_family':failed_family},
                     'repair_options':[{'action':'trade_off','strategy':f'Reduce the requested {failed_family} quantity or relax a spatial requirement.'}]}]
    return {'room_id':room['room_id'],'placements':sorted(placements,key=lambda p:p['placement_id']),'violations':violations,'status':'unsatisfiable'}

def plan_room(room, brief, catalog, finishes, demo=False):
    req=brief_requirements(brief,room['capacity']); req.setdefault('chairs',room['capacity'])
    catalog_by={x['sku']:x for x in catalog}; placements=[]; pid=1
    family_order=['desk','collaboration','storage','chair','accessory']
    for family in family_order:
        count=req.get({'desk':'desks','chair':'chairs'}.get(family,family),0)
        if not count: continue
        item,finish=choose_sku(family,catalog,finishes)
        for _ in range(count):
            found=None
            for x,y,rot in make_candidates(room,item):
                p={'placement_id':f'P{pid:03d}','sku':item['sku'],'finish_id':finish['finish_id'],'family':family,'x_mm':x,'y_mm':y,'rotation_deg':rot}
                if fits_basic(room,p,placements,catalog_by): found=p; break
            if not found:
                # Try every smaller/larger released SKU before escalation.
                alternatives=sorted((z for z in catalog if z['family']==family and compatible(z,finish)), key=lambda z:(z['dimensions_mm']['width']*z['dimensions_mm']['depth'],z['sku']))
                for alt in alternatives:
                    for x,y,rot in make_candidates(room,alt):
                        p={'placement_id':f'P{pid:03d}','sku':alt['sku'],'finish_id':finish['finish_id'],'family':family,'x_mm':x,'y_mm':y,'rotation_deg':rot}
                        if fits_basic(room,p,placements,catalog_by): found=p; break
                    if found: break
            if not found:
                return arbitrate(room,placements,catalog,failed_family=family,demo=demo)
            placements.append(found); pid+=1
    # Deterministically pair chairs to desks when both are present; pairing permits the intended seated clearance relationship.
    desks=[p for p in placements if p['family']=='desk']; chairs=[p for p in placements if p['family']=='chair']
    for c in chairs:
        if desks:
            nearest=min(desks,key=lambda d:((d['x_mm']-c['x_mm'])**2+(d['y_mm']-c['y_mm'])**2,d['placement_id']))
            c['paired_with']=[nearest['placement_id']]
            if 'paired_with' not in nearest: nearest['paired_with']=[]
            nearest['paired_with'].append(c['placement_id'])
    return arbitrate(room,placements,catalog,demo=demo)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',required=True); ap.add_argument('--demo-violation',action='store_true'); args=ap.parse_args()
    pack=load_asset_pack(args.input); root=Path(args.output)
    for room in sorted(pack.rooms,key=lambda r:r['room_id']):
        layout=plan_room(room,pack.briefs.get(room['room_id'],''),pack.catalog,pack.finishes,demo=args.demo_violation and room['room_id']=='ROOM-01')
        quote=price_quote(room['room_id'],layout['placements'],pack.catalog,pack.finishes) if layout['status']=='valid' else blocked_quote(room['room_id'],'No valid geometry was found; pricing is blocked by RB-PRC-013.')
        write_json(root/room['room_id']/ 'layout.json',layout); write_json(root/room['room_id']/ 'quote.json',quote)
if __name__=='__main__': main()
