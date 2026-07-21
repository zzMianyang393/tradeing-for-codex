"""Fixed-card audit for RSI percentile range reversion."""
from __future__ import annotations
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from daily_rsi_mean_revert_audit import rsi_values
from market import load_quantify_15m_csv,resample_minutes
from regime_component_walk_forward_audit import DAY_MS,parse_day,trade_event,wilder_atr
from regime_validation import FOUR_HOURS_MS,label_completed_4h_bars,regime_at_entry
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
def sp(t):return 'formation' if parse_day('2024-01-01')<=t<=parse_day('2024-12-31',end=True) else ('oos' if parse_day('2025-01-01')<=t<=parse_day('2025-07-10',end=True) else None)
def ev(s,b):
 d=resample_minutes(b,1440);lab=label_completed_4h_bars(b);atr=wilder_atr(d,14);r=rsi_values([x.close for x in d]);out=[];n=0
 for i in range(134,len(d)-9):
  ts=d[i].ts+DAY_MS;hist=[x for x in r[i-120:i] if x is not None]
  if len(hist)<120 or ts<n or sp(ts) is None or not atr[i-1] or r[i] is None or r[i]>sorted(hist)[math.ceil(.05*len(hist))-1] or regime_at_entry(lab,ts)!='震荡':continue
  ex=next((d[j].ts+DAY_MS for j in range(i+1,min(i+8,len(d))) if r[j] is not None and r[j]>=50),None);e=trade_event(s,'daily_rsi_percentile_range_reversion_v1','long',ts+FOUR_HOURS_MS,b,float(atr[i-1]),ex,7*DAY_MS,parse_day('2025-07-10',end=True),'震荡')
  if e:e['split']=sp(ts);e['rsi14']=round(r[i],6);out.append(e);n=e['exit_ts']+900000
 return out
def su(x):
 v=[z['net_return_pct'] for z in x];return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(y>0 for y in v)/len(v),6) if v else 0,'positive_return_month_concentration':round(conc(x),6)}
def conc(x):
 by={}
 for z in x:
  if z['net_return_pct']>0:by[datetime.fromtimestamp(z['signal_ts']/1000,timezone.utc).strftime('%Y-%m')]=by.get(datetime.fromtimestamp(z['signal_ts']/1000,timezone.utc).strftime('%Y-%m'),0)+z['net_return_pct']
 return max(by.values())/sum(by.values()) if by else 0
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/daily_rsi_percentile_range_reversion_audit.json'));p.add_argument('--symbols',nargs='+',default=DEFAULT_SYMBOLS);a=p.parse_args();x=[z for s in a.symbols for z in ev(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"))];f,o=[z for z in x if z['split']=='formation'],[z for z in x if z['split']=='oos'];sf,so=su(f),su(o);rs=[];st='historical_research_candidate'
 for k,z in [('formation',sf),('oos',so)]:
  if z['events']<15:rs.append(f'{k} events {z["events"]} < 15');st='insufficient_evidence'
  elif z['mean_pct']<=0 or z['positive_return_month_concentration']>.25:rs.append(f'{k} mean <= 0 or month concentration >25%');st='historical_rejected'
 r={'report_type':'daily_rsi_percentile_range_reversion_audit','formation':sf,'oos':so,'events':x,'status':st,'reasons':rs,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={st}")
if __name__=='__main__':main()
