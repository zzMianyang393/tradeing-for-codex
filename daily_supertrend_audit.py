"""Fixed-card audit for daily SuperTrend flips."""
from __future__ import annotations
import argparse,json
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from statistics import mean
from market import load_quantify_15m_csv,resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS,parse_day,trade_event,supertrend_direction,wilder_atr
from regime_validation import FOUR_HOURS_MS,label_completed_4h_bars,regime_at_entry
def sp(t):return 'formation' if parse_day('2024-01-01')<=t<=parse_day('2024-12-31',end=True) else ('oos' if parse_day('2025-01-01')<=t<=parse_day('2025-07-10',end=True) else None)
def ev(s,b):
 d=resample_minutes(b,1440);lab=label_completed_4h_bars(b);directions,_=supertrend_direction(d,10,3);atr=wilder_atr(d,14);o=[];n=0
 for i in range(11,len(d)-12):
  ts=d[i].ts+DAY_MS;direction='long' if directions[i-1]<=0<directions[i] else ('short' if directions[i-1]>=0>directions[i] else None);reg=regime_at_entry(lab,ts)
  if not direction or ts<n or sp(ts) is None or not atr[i-1] or (direction=='long' and reg!='趋势上行') or (direction=='short' and reg!='趋势下行'):continue
  ex=next((d[j].ts+DAY_MS for j in range(i+1,min(i+11,len(d))) if directions[j]!=directions[i]),None);e=trade_event(s,'daily_supertrend_v1',direction,ts+FOUR_HOURS_MS,b,float(atr[i-1]),ex,10*DAY_MS,parse_day('2025-07-10',end=True),reg)
  if e:e['split']=sp(ts);o.append(e);n=e['exit_ts']+900000
 return o
def su(x):
 v=[z['net_return_pct'] for z in x];return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(y>0 for y in v)/len(v),6) if v else 0}
def month_concentration(x):
 positive=defaultdict(float)
 for event in x:
  if event['net_return_pct']>0:
   month=datetime.fromtimestamp(event['signal_ts']/1000,tz=timezone.utc).strftime('%Y-%m')
   positive[month]+=event['net_return_pct']
 total=sum(positive.values())
 return max(positive.values())/total if total else 0.0
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/daily_supertrend_audit.json'));p.add_argument('--symbols',nargs='+',default=DEFAULT_SYMBOLS);a=p.parse_args();x=[z for s in a.symbols for z in ev(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"))];f,o=[z for z in x if z['split']=='formation'],[z for z in x if z['split']=='oos'];sf,so=su(f),su(o);rs=[];st='historical_research_candidate'
 for k,z,bucket in [('formation',sf,f),('oos',so,o)]:
  if z['events']<15:rs.append(f'{k} events {z["events"]} < 15');st='insufficient_evidence'
  elif z['mean_pct']<=0:rs.append(f'{k} mean <= 0');st='historical_rejected'
  elif month_concentration(bucket)>0.25:rs.append(f'{k} month concentration {month_concentration(bucket):.1%} > 25%');st='historical_rejected'
 sf['positive_return_month_concentration']=round(month_concentration(f),6);so['positive_return_month_concentration']=round(month_concentration(o),6)
 r={'report_type':'daily_supertrend_audit','formation':sf,'oos':so,'events':x,'status':st,'reasons':rs,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={st}")
if __name__=='__main__':main()
