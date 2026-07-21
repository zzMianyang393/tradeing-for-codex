"""Fixed-card audit for BTC trend-confirmed alt momentum."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from ema_crossover_4h_audit import ema_values
from market import load_quantify_15m_csv,resample_minutes
from regime_component_walk_forward_audit import DAY_MS,parse_day,trade_event,wilder_atr
from regime_validation import FOUR_HOURS_MS,label_completed_4h_bars,regime_at_entry
def sp(t):return 'formation' if parse_day('2024-01-01')<=t<=parse_day('2024-12-31',end=True) else ('oos' if parse_day('2025-01-01')<=t<=parse_day('2025-07-10',end=True) else None)
def ev(s,b,btc):
 d=resample_minutes(b,1440);bd=resample_minutes(btc,1440); lab=label_completed_4h_bars(b); ema=ema_values(d,20);be20=ema_values(bd,20);be50=ema_values(bd,50);atr=wilder_atr(d,14);out=[];n=0
 for i in range(50,min(len(d),len(bd))-9):
  ts=d[i].ts+DAY_MS
  if s.startswith('BTC') or ts<n or sp(ts) is None or not atr[i-1] or not ema[i] or not be20[i] or not be50[i] or d[i-5].close<=0 or bd[i-5].close<=0:continue
  if be20[i]<=be50[i] or bd[i].close/bd[i-5].close<=1 or d[i].close/d[i-5].close<=1 or d[i].close<=ema[i] or regime_at_entry(lab,ts)!='趋势上行':continue
  ex=None
  for j in range(i+1,min(i+8,len(d),len(bd))):
   if be20[j] is not None and be50[j] is not None and (be20[j]<=be50[j] or d[j].close<ema[j]):ex=d[j].ts+DAY_MS;break
  e=trade_event(s,'btc_trend_confirmed_alt_momentum_v1','long',ts+FOUR_HOURS_MS,b,float(atr[i-1]),ex,7*DAY_MS,parse_day('2025-07-10',end=True),'趋势上行')
  if e:e['split']=sp(ts);out.append(e);n=e['exit_ts']+900000
 return out
def su(x):
 v=[z['net_return_pct'] for z in x];return {'events':len(v),'net_sum_pct':round(sum(v),6),'mean_pct':round(mean(v),6) if v else 0,'win_rate':round(sum(y>0 for y in v)/len(v),6) if v else 0}
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--out',type=Path,default=Path('reports/btc_trend_confirmed_alt_momentum_audit.json'));p.add_argument('--symbols',nargs='+',default=['BTC-USDT-SWAP','ETH-USDT-SWAP']);a=p.parse_args();btc=load_quantify_15m_csv(a.data/'BTC_15m.csv');x=[z for s in a.symbols for z in ev(s,load_quantify_15m_csv(a.data/f"{s.split('-',1)[0]}_15m.csv"),btc)];f,o=[z for z in x if z['split']=='formation'],[z for z in x if z['split']=='oos'];sf,so=su(f),su(o);rs=[];st='historical_research_candidate'
 for k,z in [('formation',sf),('oos',so)]:
  if z['events']<15:rs.append(f'{k} events {z["events"]} < 15');st='insufficient_evidence'
  elif z['mean_pct']<=0:rs.append(f'{k} mean <= 0');st='historical_rejected'
 r={'report_type':'btc_trend_confirmed_alt_momentum_audit','formation':sf,'oos':so,'events':x,'status':st,'reasons':rs,'safety_gates':{'approved_for_paper':[],'eligible_for_paper':False,'safe_to_enable_trading':False}};a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(f"formation={sf['events']}; oos={so['events']}; status={st}")
if __name__=='__main__':main()
