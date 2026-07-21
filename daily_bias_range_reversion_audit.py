"""Fixed-card audit for daily BIAS range reversion."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from ema_crossover_4h_audit import ema_values
from market import load_quantify_15m_csv,resample_minutes
from regime_component_walk_forward_audit import DAY_MS,parse_day,trade_event,wilder_atr
from regime_validation import FOUR_HOURS_MS,label_completed_4h_bars,regime_at_entry
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
def sp(t):return 'formation' if parse_day('2024-01-01')<=t<=parse_day('2024-12-31',end=True) else ('oos' if parse_day('2025-01-01')<=t<=parse_day('2025-07-10',end=True) else None)
def ev(s,b):
 d=resample_minutes(b,1440);lab=label_completed_4h_bars(b);ema=ema_values(d,20);atr=wilder_atr(d,14);o=[];n=0
 for i in range(20,len(d)-9):
  ts=d[i].ts+DAY_MS
  if ts<n or sp(ts) is None or not ema[i] or not atr[i-1] or d[i].close/ema[i]-1>-0.10 or regime_at_entry(lab,ts)!='震荡':continue
  ex=next((d[j].ts+DAY_MS for j in range(i+1,min(i+8,len(d))) if ema[j] and d[j].close>=ema[j]),None);e=trade_event(s,'daily_bias_range_reversion_v1','long',ts+FOUR_HOURS_MS,b,float(atr[i-1]),ex,7*DAY_MS,parse_day('2025-07-10',end=True),'震荡')
  if e:e['split']=sp(ts);e['bias_pct']=round((d[i].close/ema[i]-1)*100,6);o.append(e);n=e['exit_ts']+900000
 return o
def _mc(x):
 from collections import defaultdict; bd=defaultdict(float);tp=0.0
 for e in x:
  v=e['net_return_pct']
  if v>0:bd[datetime.fromtimestamp(e['signal_ts']/1000,timezone.utc).strftime('%Y-%m')]+=v;tp+=v
 return max(bd.values())/tp if tp>0 else 0.0

def su(x):
 v=[z['net_return_pct'] for z in x];return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(y>0 for y in v)/len(v),6) if v else 0,'positive_return_month_concentration':round(_mc(x),6)}
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/daily_bias_range_reversion_audit.json'));p.add_argument('--symbols',nargs='+',default=DEFAULT_SYMBOLS);a=p.parse_args();x=[z for s in a.symbols for z in ev(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"))];f,o=[z for z in x if z['split']=='formation'],[z for z in x if z['split']=='oos'];sf,so=su(f),su(o)
 rs=[];st='historical_research_candidate'
 for k,z,bk in [('formation',sf,f),('oos',so,o)]:
  if z['events']<15:rs.append(f'{k} events {z["events"]} < 15');st='insufficient_evidence';continue
  if z['mean_pct']<=0:rs.append(f'{k} mean <= 0');st='historical_rejected'
  elif z['positive_return_month_concentration']>0.25:rs.append(f'{k} month concentration {z["positive_return_month_concentration"]:.1%} > 25%');st='historical_rejected'
 r={'report_type':'daily_bias_range_reversion_audit','formation':sf,'oos':so,'events':x,'status':st,'reasons':rs,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={r['status']}")
if __name__=='__main__':main()
