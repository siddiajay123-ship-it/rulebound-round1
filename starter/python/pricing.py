from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP


def rh(n,d=1):
    return int((Decimal(n)/Decimal(d)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def price_quote(room_id, placements, catalog, finishes):
    bysku={x['sku']:x for x in catalog}; byfin={x['finish_id']:x for x in finishes}
    grouped=defaultdict(list)
    for p in placements:
        grouped[(p['sku'],p['finish_id'])].append(p)
    lines=[]; goods=0; labour_minutes=0
    for idx,key in enumerate(sorted(grouped),1):
        sku,finish_id=key; item=bysku.get(sku); finish=byfin.get(finish_id)
        qty=len(grouped[key])
        if not item or not finish or finish_id not in item.get('compatible_finish_ids',[]) or item['family'] not in finish.get('compatible_families',[]):
            return blocked_quote(room_id, f'Unpriced or incompatible line {sku}/{finish_id}.')
        base=item['list_price_inr']*qty
        uplift=rh(base*finish['uplift_bps'],10000)
        if qty>=20: discount_bps=1000
        elif qty>=10: discount_bps=700
        elif qty>=5: discount_bps=300
        else: discount_bps=0
        discount=rh(base*discount_bps,10000)
        net=base+uplift-discount
        goods+=net; labour_minutes += item['labour_minutes']*qty
        lines.append({'line_id':f'L{idx:03d}','sku':sku,'finish_id':finish_id,'quantity':qty,
                      'unit_list_price_inr':item['list_price_inr'],'base_amount_inr':base,
                      'finish_uplift_inr':uplift,'quantity_discount_inr':discount,
                      'net_goods_inr':net,'trace':[
                          {'rule_id':'CATALOG','inputs':{'unit_price':item['list_price_inr'],'quantity':qty},'amount_inr':base},
                          {'rule_id':'RB-PRC-010','inputs':{'uplift_bps':finish['uplift_bps'],'base_amount_inr':base},'amount_inr':uplift},
                          {'rule_id':'RB-PRC-009','inputs':{'discount_bps':discount_bps,'base_amount_inr':base},'amount_inr':-discount}
                      ]})
    if labour_minutes<=240: rate=900
    elif labour_minutes<=480: rate=800
    else: rate=750
    labour=rh(labour_minutes*rate,60)
    if goods<=100000: freight=5000; ftrace={'band':'up_to_100000','flat_inr':5000,'goods_inr':goods}
    elif goods<=250000: freight=9000; ftrace={'band':'100001_to_250000','flat_inr':9000,'goods_inr':goods}
    else: freight=rh(goods*400,10000); ftrace={'band':'above_250000','percent_bps':400,'goods_inr':goods}
    total=goods+labour+freight
    return {'quote_id':f'QUOTE-{room_id}','room_id':room_id,'currency':'INR','lines':lines,
            'summary':{'goods_after_adjustments_inr':goods,'labour_minutes':labour_minutes,'labour_rate_inr_per_hour':rate,'labour_inr':labour,'freight_inr':freight,'grand_total_inr':total},
            'summary_trace':[{'rule_id':'RB-PRC-011','inputs':{'total_labour_minutes':labour_minutes,'rate_inr_per_hour':rate},'amount_inr':labour},
                             {'rule_id':'RB-PRC-012','inputs':ftrace,'amount_inr':freight}], 'status':'priced'}


def blocked_quote(room_id, reason):
    return {'quote_id':f'QUOTE-{room_id}','room_id':room_id,'currency':'INR','lines':[],
            'summary':{'grand_total_inr':0},'summary_trace':[],'status':'blocked','blocking_reasons':[reason]}
