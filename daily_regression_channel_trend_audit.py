"""Fixed-card audit for daily regression-channel trend following."""
from __future__ import annotations
import argparse,json,math
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from market import load_quantify_15m_csv,resample_minutes
from regime_component_walk_forward_audit import DAY_MS,parse_day,trade_event,wilder_atr
from regime_validation import FOUR_HOURS_MS,label_completed_4h_bars,regime_at_entry
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
def channel(xs):
 n=len(xs); mx=(n-1)/2; my=mean(xs); den=sum((i-mx)**2 for i in range(n)); slope=sum((i-mx)*(x-my) for i,x in enumerate(xs))/den; intercept=my-slope*mx; fit=[intercept+slope*i for i in range(n)]; sd=math.sqrt(sum((x-y)**2 for x,y in zip(xs,fit))/n);return slope,fit[-1],sd
def sp(t):return 'formation' if parse_day('2024-01-01')<=t<=parse_day('2024-12-31',end=True) else ('oos' if parse_day('2025-01-01')<=t<=parse_day('2025-07-10',end=True) else None)
def ev(s,b):
 d=resample_minutes(b,1440);lab=label_completed_4h_bars(b);atr=wilder_atr(d,14);o=[];nxt=0
 for i in range(31,len(d)-12):
  ts=d[i].ts+DAY_MS; sl,mid,sd=channel([x.close for x in d[i-30:i]]); psl,pmid,psd=channel([x.close for x in d[i-31:i-1]]); direction='long' if sl>0 and d[i-1].close<=pmid+1.5*psd and d[i].close>mid+1.5*sd else ('short' if sl<0 and d[i-1].close>=pmid-1.5*psd and d[i].close<mid-1.5*sd else None);reg=regime_at_entry(lab,ts)
  if not direction or ts<nxt or sp(ts) is None or not atr[i-1] or (direction=='long' and reg!='趋势上行') or (direction=='short' and reg!='趋势下行'):continue
  ex=None
  for j in range(i+1,min(i+11,len(d))):
   _,m,_=channel([x.close for x in d[j-30:j]])
   if (direction=='long' and d[j].close<m) or (direction=='short' and d[j].close>m):ex=d[j].ts+DAY_MS;break
  e=trade_event(s,'daily_regression_channel_trend_v1',direction,ts+FOUR_HOURS_MS,b,float(atr[i-1]),ex,10*DAY_MS,parse_day('2025-07-10',end=True),reg)
  if e:e['split']=sp(ts);o.append(e);nxt=e['exit_ts']+900000
 return o
def _mc(x):
 from collections import defaultdict; by_month=defaultdict(float); total=0.0
 for event in x:
  value=event['net_return_pct']
  if value>0:
   by_month[datetime.fromtimestamp(event['signal_ts']/1000,timezone.utc).strftime('%Y-%m')]+=value;total+=value
 return max(by_month.values())/total if total else 0.0
def su(x):
 v=[z['net_return_pct'] for z in x];return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(y>0 for y in v)/len(v),6) if v else 0,'positive_return_month_concentration':round(_mc(x),6)}
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/daily_regression_channel_trend_audit.json'));p.add_argument('--symbols',nargs='+',default=DEFAULT_SYMBOLS);a=p.parse_args();x=[z for s in a.symbols for z in ev(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"))];f,o=[z for z in x if z['split']=='formation'],[z for z in x if z['split']=='oos'];sf,so=su(f),su(o);rs=[];st='historical_research_candidate'
 for k,z in [('formation',sf),('oos',so)]:
  if z['events']<15:rs.append(f'{k} events {z["events"]} < 15');st='insufficient_evidence'
  elif z['mean_pct']<=0:rs.append(f'{k} mean <= 0');st='historical_rejected'
  elif z['positive_return_month_concentration']>0.25:rs.append(f'{k} month concentration {z["positive_return_month_concentration"]:.1%} > 25%');st='historical_rejected'
 r={'report_type':'daily_regression_channel_trend_audit','formation':sf,'oos':so,'events':x,'status':st,'reasons':rs,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={st}")
if __name__=='__main__':main()
