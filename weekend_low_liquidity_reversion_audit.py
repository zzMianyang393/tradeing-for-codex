"""Fixed-card historical audit for weekend low-liquidity mean reversion."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from daily_rsi_mean_revert_audit import rsi_values
from ema_crossover_4h_audit import ema_values
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DAY_MS, parse_day, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry

def split(ts:int)->str|None:
    if parse_day('2024-01-01')<=ts<=parse_day('2024-12-31',end=True): return 'formation'
    if parse_day('2025-01-01')<=ts<=parse_day('2025-07-10',end=True): return 'oos'
    return None
def events(symbol:str,bars:list[Bar])->list[dict]:
    d=resample_minutes(bars,1440); labels=label_completed_4h_bars(bars); ema=ema_values(d,5); atr=wilder_atr(d,14); rsi=rsi_values([x.close for x in d]); out=[]; next_ts=0
    for i in range(20,len(d)-4):
        ts=d[i].ts+DAY_MS
        if ts<next_ts or split(ts) is None or datetime.fromtimestamp(d[i].ts/1000,timezone.utc).weekday()!=5: continue
        prior=sorted(x.volume_quote for x in d[i-20:i]); threshold=prior[int(.30*(len(prior)-1))]
        if not atr[i-1] or not ema[i] or rsi[i] is None or d[i].volume_quote>=threshold or d[i].close>=ema[i] or rsi[i]>=40 or regime_at_entry(labels,ts)!='震荡': continue
        entry_i=next((j for j,x in enumerate(bars) if x.ts>=ts+FOUR_HOURS_MS),None)
        if entry_i is None: continue
        exit_ts = None
        for day_index in range(i + 1, min(i + 3, len(d))):
            if ema[day_index] is not None and d[day_index].close >= ema[day_index]:
                exit_ts = d[day_index].ts + DAY_MS
                break
        end_i=next((j for j, bar in enumerate(bars) if bar.ts >= (exit_ts if exit_ts is not None else bars[entry_i].ts + 2 * DAY_MS)), len(bars)-1)
        entry=bars[entry_i]; stop=entry.open-1.5*atr[i-1]; exit_i=end_i; price=bars[end_i].open; reason='ema5' if exit_ts is not None else 'time'
        for j in range(entry_i,end_i+1):
            if bars[j].low<=stop: exit_i=j; price=stop; reason='stop'; break
        gross=price/entry.open-1; out.append({'symbol':symbol,'split':split(ts),'signal_ts':ts,'net_return_pct':round(gross*100-.16,6),'exit_reason':reason,'rsi14':round(rsi[i],6),'volume_ratio':round(d[i].volume_quote/(sum(prior)/len(prior)),6)}); next_ts=bars[exit_i].ts+900000
    return out
def _month_conc(items):
    from collections import defaultdict
    by_m=defaultdict(float); tp=0.0
    for e in items:
        v=e['net_return_pct']
        if v>0: by_m[datetime.fromtimestamp(e['signal_ts']/1000,timezone.utc).strftime('%Y-%m')]+=v; tp+=v
    return max(by_m.values())/tp if tp>0 else 0.0

def summary(xs:list[dict])->dict:
    v=[x['net_return_pct'] for x in xs]; return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(x>0 for x in v)/len(v),6) if v else 0}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/weekend_low_liquidity_reversion_audit.json'));p.add_argument('--symbols',nargs='+',default=['BTC-USDT-SWAP','ETH-USDT-SWAP']);a=p.parse_args(); xs=[e for s in a.symbols for e in events(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"))]; f,o=[e for e in xs if e['split']=='formation'],[e for e in xs if e['split']=='oos']; sf,so=summary(f),summary(o)
 reasons=[]; status='historical_research_candidate'
 for n,z,bk in [('formation',sf,f),('oos',so,o)]:
  if z['events']<15: reasons.append(f'{n} events {z["events"]} < 15'); status='insufficient_evidence'
  elif z['mean_pct']<=0: reasons.append(f'{n} mean <= 0'); status='historical_rejected'
  else:
   c=_month_conc(bk)
   if c>0.25: reasons.append(f'{n} month concentration {c:.1%} > 25%'); status='historical_rejected'
 r={'report_type':'weekend_low_liquidity_reversion_audit','formation':sf,'oos':so,'events':xs,'status':status,'reasons':reasons,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={r['status']}");return 0
if __name__=='__main__':raise SystemExit(main())
