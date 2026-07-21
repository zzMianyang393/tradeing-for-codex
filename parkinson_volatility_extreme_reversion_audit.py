"""Fixed-card historical audit for Parkinson volatility extreme reversion."""
from __future__ import annotations
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from ema_crossover_4h_audit import ema_values
from market import load_quantify_15m_csv,resample_minutes
from regime_component_walk_forward_audit import DAY_MS,parse_day,trade_event,wilder_atr
from regime_validation import FOUR_HOURS_MS,label_completed_4h_bars,regime_at_entry
def nearest_rank_percentile(values, percentile):
 if not values: raise ValueError('percentile requires values')
 if not 0 < percentile <= 1: raise ValueError('percentile must be in (0, 1]')
 ordered=sorted(values); return ordered[math.ceil(percentile*len(ordered))-1]
def split(t):
 return 'formation' if parse_day('2024-01-01')<=t<=parse_day('2024-12-31',end=True) else ('oos' if parse_day('2025-01-01')<=t<=parse_day('2025-07-10',end=True) else None)
def events(s,b):
 d=resample_minutes(b,1440);lab=label_completed_4h_bars(b); ema=ema_values(d,20);atr=wilder_atr(d,20); pv=[None]*len(d);out=[];nxt=0
 for i in range(20,len(d)):
  if d[i].high>d[i].low>0: pv[i]=math.sqrt(sum(math.log(x.high/x.low)**2 for x in d[i-19:i+1] if x.high>x.low>0)/(4*math.log(2)*20))
 for i in range(140,len(d)-9):
  ts=d[i].ts+DAY_MS
  if ts<nxt or split(ts) is None or not atr[i-1] or pv[i] is None or not ema[i] or regime_at_entry(lab,ts)!='高波动转换':continue
  q=nearest_rank_percentile([x for x in pv[i-120:i] if x is not None],.90)
  if pv[i]<q or d[i].close>=ema[i]:continue
  exit=None
  for j in range(i+1,min(i+8,len(d))):
   if ema[j] is not None and d[j].close>=ema[j]:exit=d[j].ts+DAY_MS;break
  e=trade_event(s,'parkinson_volatility_extreme_reversion_v1','long',ts+FOUR_HOURS_MS,b,float(atr[i-1]),exit,7*DAY_MS,parse_day('2025-07-10',end=True),'高波动转换')
  if e:e['split']=split(ts);e['parkinson_volatility']=round(pv[i],8);out.append(e);nxt=e['exit_ts']+900000
 return out
def _mc(x):
 from collections import defaultdict; bd=defaultdict(float);tp=0.0
 for e in x:
  v=e['net_return_pct']
  if v>0:bd[datetime.fromtimestamp(e['signal_ts']/1000,timezone.utc).strftime('%Y-%m')]+=v;tp+=v
 return max(bd.values())/tp if tp>0 else 0.0

def sm(x):
 v=[z['net_return_pct'] for z in x];return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(y>0 for y in v)/len(v),6) if v else 0}
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/parkinson_volatility_extreme_reversion_audit.json'));p.add_argument('--symbols',nargs='+',default=['BTC-USDT-SWAP','ETH-USDT-SWAP']);a=p.parse_args();x=[e for s in a.symbols for e in events(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"))];f,o=[e for e in x if e['split']=='formation'],[e for e in x if e['split']=='oos'];sf,so=sm(f),sm(o)
 rs=[];st='historical_research_candidate'
 for k,z,bk in [('formation',sf,f),('oos',so,o)]:
  if z['events']<15:rs.append(f'{k} events {z["events"]} < 15');st='insufficient_evidence'
  elif z['mean_pct']<=0:rs.append(f'{k} mean <= 0');st='historical_rejected'
  else:
   c=_mc(bk)
   if c>0.25:rs.append(f'{k} month concentration {c:.1%} > 25%');st='historical_rejected'
 r={'report_type':'parkinson_volatility_extreme_reversion_audit','formation':sf,'oos':so,'events':x,'status':st,'reasons':rs,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={r['status']}")
if __name__=='__main__':main()
