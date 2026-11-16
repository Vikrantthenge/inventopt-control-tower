import numpy as np
import pandas as pd
from statistics import NormalDist

def sample():
    rng=np.random.default_rng(42); rows=[]
    for sku,base,cost in [('Rice',95,65),('Tea',45,120),('Soap',70,38),('Oil',60,145),('Biscuits',110,22)]:
        for dc in ['Mumbai DC','Pune DC']:
            for store in ['Store A','Store B','Store C']:
                for i,d in enumerate(pd.date_range('2025-01-06',periods=104,freq='W-MON')):
                    demand=max(0,round(base*(1+.15*np.sin(i*2*np.pi/52))*(1+.002*i)+rng.normal(0,base*.13)))
                    rows.append((d,sku,dc,store,demand,cost))
    return pd.DataFrame(rows,columns=['date','sku','dc','store','demand','unit_cost'])

def plan(df,service=.95,store_lt=1,dc_lt=2,review=1):
    z=NormalDist().inv_cdf(service); rows=[]; hubs=[]
    for (sku,dc),g in df.groupby(['sku','dc']):
        pivot=g.pivot_table(index='date',columns='store',values='demand',aggfunc='sum',fill_value=0).sort_index().tail(26)
        cost=g.unit_cost.mean(); total=pivot.sum(axis=1); pooled=z*total.std(ddof=0)*np.sqrt(dc_lt+review)
        independent=z*pivot.std(ddof=0).sum()*np.sqrt(dc_lt+review)
        for store,s in pivot.items():
            mu=s.tail(8).mean(); ss=z*s.std(ddof=0)*np.sqrt(store_lt+review); target=mu*(store_lt+review)+ss
            rows.append([sku,dc,store,mu,ss,target,cost,target*cost])
        mu=total.tail(8).mean(); hubs.append([sku,dc,mu,pooled,independent,mu*(dc_lt+review)+pooled,cost])
    return pd.DataFrame(rows,columns=['sku','dc','store','weekly_forecast','safety_stock','target_stock','unit_cost','target_value']),pd.DataFrame(hubs,columns=['sku','dc','weekly_forecast','pooled_buffer','independent_buffer','target_stock','unit_cost'])

if __name__=='__main__': sample().to_csv('retail_demand.csv',index=False)
