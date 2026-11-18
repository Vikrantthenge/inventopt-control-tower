import html
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from model import sample, plan

st.set_page_config(page_title='InventOpt 2.0 | Inventory Control Tower', page_icon='📦', layout='wide')
NAVY='#102b46'; BLUE='#2563a6'; TEAL='#078a75'; RED='#dc4545'; AMBER='#d99a27'
COLORS={'Below target':RED,'On target':TEAL,'Above target':AMBER}
st.markdown('''<style>
.block-container{padding-top:2rem;max-width:1500px} .hero{background:linear-gradient(110deg,#102b46,#205b85);color:white;padding:28px;border-radius:16px;margin-bottom:20px}.hero h1{color:white;margin:0;font-size:2.1rem}.hero p{color:#dceaf5;margin:8px 0 0}.kpi{background:#f4f8fc;border:1px solid #dce6ef;border-radius:12px;padding:17px;min-height:125px;color:#102b46;border-top:4px solid #2563a6}.kpi small{color:#52687b}.kpi strong{display:block;font-size:1.8rem;margin:8px 0}.stTabs [data-baseweb=tab]{font-weight:600} [data-testid=stSidebar]{border-right:1px solid #dce6ef}
</style>''',unsafe_allow_html=True)
st.markdown('<div class="hero"><small>DECISION ANALYTICS • SUPPLY CHAIN PORTFOLIO</small><h1>📦 InventOpt 2.0</h1><p>Enterprise Inventory Intelligence &amp; MEIO Control Tower</p><p>Monitor • Forecast • Optimize • Plan</p></div>',unsafe_allow_html=True)
st.caption('Independent demonstration | Synthetic retail data by default | Stock snapshots are simulated, not actual client results.')
with st.sidebar:
    st.header('🎛 Planning assumptions')
    upload=st.file_uploader('Optional demand CSV',type='csv')
    service=st.slider('Target cycle service level (%)',80,99,95)/100
    sl=st.slider('Store lead time (weeks)',1,4,1)
    dl=st.slider('DC lead time (weeks)',1,8,2)
    growth=st.slider('Annual demand growth (%)',-20,30,8)/100
    stock_factor=st.slider('Simulated stock vs target (%)',30,170,100)/100
    st.caption('These sliders control the proposed scenario. The baseline is fixed below for comparison.')
    with st.expander('📌 Baseline assumptions', expanded=False):
        base_service = st.slider('Baseline service level (%)', 80, 99, 95, key='base_service') / 100
        base_sl = st.slider('Baseline store lead time (weeks)', 1, 4, 1, key='base_sl')
        base_dl = st.slider('Baseline DC lead time (weeks)', 1, 8, 2, key='base_dl')
        base_growth = st.slider('Baseline annual demand growth (%)', -20, 30, 8, key='base_growth') / 100
        base_stock_factor = st.slider('Baseline simulated stock vs target (%)', 30, 170, 100, key='base_stock_factor') / 100
try:
    path=Path(__file__).with_name('retail_demand.csv')
    df=pd.read_csv(upload) if upload is not None else (pd.read_csv(path) if path.exists() else sample())
    df=df[['date','sku','dc','store','demand','unit_cost']].copy()
    df['date']=pd.to_datetime(df.date,errors='raise')
    for c in ['demand','unit_cost']: df[c]=pd.to_numeric(df[c],errors='raise')
    if df.empty or df.isna().any().any() or not np.isfinite(df[['demand','unit_cost']]).all().all() or (df[['demand','unit_cost']]<0).any().any(): raise ValueError('Use complete, finite, nonnegative data.')
    df['date']=df.date.dt.to_period('W-SUN').dt.start_time
    for c in ['sku','dc','store']: df[c]=df[c].astype(str)
except Exception as e:
    st.error(f'Invalid CSV: {e}'); st.stop()
with st.sidebar:
    st.header('🔎 Network filters')
    for col,label in [('sku','Product'),('dc','Distribution centre'),('store','Store')]:
        opts=sorted(df[col].unique()); chosen=st.multiselect(label,opts,default=opts,key=col); df=df[df[col].isin(chosen)]
    st.caption('Region is represented by distribution centre; no separate region field is required.')
if df.empty: st.info('Select at least one product, distribution centre and store.'); st.stop()
# Calculate BOTH cases using the same original planning model and filtered data.
# Reuse one set of simulated stock multipliers to isolate the effect of changed assumptions.
baseline_a, baseline_b = plan(df, base_service, base_sl, base_dl)
a, b = plan(df, service, sl, dl)
rng = np.random.default_rng(8)
stock_multipliers = rng.uniform(.55, 1.45, len(a))

def enrich(store_plan, dc_plan, stock_scale):
    store_plan = store_plan.copy()
    dc_plan = dc_plan.copy()
    store_plan['simulated_stock'] = np.round(store_plan.target_stock * stock_scale * stock_multipliers)
    store_plan['gap'] = store_plan.simulated_stock - store_plan.target_stock
    store_plan['status'] = np.select(
        [store_plan.gap < -.15 * store_plan.target_stock,
         store_plan.gap > .15 * store_plan.target_stock],
        ['Below target', 'Above target'], default='On target')
    store_plan['reorder_qty'] = np.ceil((-store_plan.gap).clip(lower=0))
    store_plan['excess_units'] = store_plan.gap.clip(lower=0)
    store_plan['excess_value'] = store_plan.excess_units * store_plan.unit_cost
    dc_plan['buffer_saving'] = (dc_plan.independent_buffer - dc_plan.pooled_buffer).clip(lower=0)
    return store_plan, dc_plan

baseline_a, baseline_b = enrich(baseline_a, baseline_b, base_stock_factor)
a, b = enrich(a, b, stock_factor)
low = a[a.status == 'Below target']
high = a[a.status == 'Above target']
on = a[a.status == 'On target']

def metrics(store_plan, dc_plan, annual_growth):
    network_value = (store_plan.target_value.sum()
                     + (dc_plan.target_stock * dc_plan.unit_cost).sum())
    return {
        'Weekly demand (units)': float(store_plan.weekly_forecast.sum()),
        'Store target value (INR)': float(store_plan.target_value.sum()),
        'Network target value (INR)': float(network_value),
        'Below-target combinations': int((store_plan.status == 'Below target').sum()),
        'Replenishment review (units)': float(
            store_plan.loc[store_plan.status == 'Below target', 'reorder_qty'].sum()),
        'Excess inventory value (INR)': float(store_plan.excess_value.sum()),
        'DC pooling potential (units)': float(dc_plan.buffer_saving.sum()),
        'Year 3 indicative stock value (INR)': float(network_value * (1 + annual_growth)**3),
    }

baseline_metrics = metrics(baseline_a, baseline_b, base_growth)
scenario_metrics = metrics(a, b, growth)
def kpi(col,label,value,detail,color=BLUE):
    col.markdown(f'<div class="kpi" style="border-top-color:{color}"><small>{html.escape(label)}</small><strong>{html.escape(str(value))}</strong><small>{html.escape(detail)}</small></div>',unsafe_allow_html=True)
def chart(fig):
    fig.update_layout(template='plotly_white',font=dict(family='Arial',color=NAVY),margin=dict(l=15,r=15,t=55,b=20),legend_title_text='')
    st.plotly_chart(fig,width='stretch',config={'displaylogo':False})
def table(data): st.dataframe(data.round(2),width='stretch',hide_index=True)
def download(label,data,name): st.download_button(label,data.to_csv(index=False),name,mime='text/csv')
cols=st.columns(4)
kpi(cols[0],'📈 Weekly demand',f'{a.weekly_forecast.sum():,.0f} units','Eight-week average')
kpi(cols[1],'💰 Store target value',f'₹{a.target_value.sum():,.0f}','Indicative inventory investment')
kpi(cols[2],'⚠ Below target',len(low),'Product–store combinations',RED)
kpi(cols[3],'🏭 DC pooling potential',f'{b.buffer_saving.sum():,.0f} units','Indicative safety buffer reduction',TEAL)
st.write('')
t0,t1,t2,t3,t4,t5=st.tabs(['⚖️ Scenario comparison','Executive overview','Demand forecast','MEIO network','3-year plan','Action centre'])
with t0:
    st.subheader('Baseline vs proposed scenario')
    st.caption('Both cases use the same uploaded/filtered demand data, the original plan() model, '
               'and the same simulated stock multipliers. Only planning assumptions change.')
    assumptions = pd.DataFrame([
        {'Assumption': 'Cycle service level', 'Baseline': f'{base_service:.0%}', 'Scenario': f'{service:.0%}'},
        {'Assumption': 'Store lead time', 'Baseline': f'{base_sl} weeks', 'Scenario': f'{sl} weeks'},
        {'Assumption': 'DC lead time', 'Baseline': f'{base_dl} weeks', 'Scenario': f'{dl} weeks'},
        {'Assumption': 'Annual demand growth', 'Baseline': f'{base_growth:.0%}', 'Scenario': f'{growth:.0%}'},
        {'Assumption': 'Simulated stock factor', 'Baseline': f'{base_stock_factor:.0%}', 'Scenario': f'{stock_factor:.0%}'},
    ])
    st.dataframe(assumptions, hide_index=True, width='stretch')
    comparison = pd.DataFrame([
        {'Metric': name, 'Baseline': baseline_metrics[name],
         'Scenario': scenario_metrics[name],
         'Change': scenario_metrics[name] - baseline_metrics[name],
         'Change %': ((scenario_metrics[name] / baseline_metrics[name] - 1) * 100
                      if baseline_metrics[name] else np.nan)}
        for name in baseline_metrics
    ])
    c1, c2, c3 = st.columns(3)
    c1.metric('Network target value — scenario',
              f"₹{scenario_metrics['Network target value (INR)']:,.0f}",
              f"₹{scenario_metrics['Network target value (INR)'] - baseline_metrics['Network target value (INR)']:+,.0f}",
              delta_color='off')
    c2.metric('Below-target combinations — scenario',
              f"{scenario_metrics['Below-target combinations']:,.0f}",
              f"{scenario_metrics['Below-target combinations'] - baseline_metrics['Below-target combinations']:+,.0f}",
              delta_color='off')
    c3.metric('DC pooling potential — scenario',
              f"{scenario_metrics['DC pooling potential (units)']:,.0f} units",
              f"{scenario_metrics['DC pooling potential (units)'] - baseline_metrics['DC pooling potential (units)']:+,.0f} units",
              delta_color='off')
    st.subheader('Detailed comparison')
    st.dataframe(comparison.style.format({
        'Baseline': '{:,.2f}', 'Scenario': '{:,.2f}',
        'Change': '{:+,.2f}', 'Change %': '{:+.1f}%', 
    }, na_rep='N/A'), hide_index=True, width='stretch')
    selected = st.selectbox('Compare a business metric', list(baseline_metrics))
    fig = px.bar(pd.DataFrame({
        'Case': ['Baseline', 'Proposed scenario'],
        'Value': [baseline_metrics[selected], scenario_metrics[selected]]
    }), x='Case', y='Value', color='Case',
        color_discrete_sequence=[BLUE, TEAL],
        title=selected, text_auto=',.2f')
    chart(fig)
    download('Download scenario comparison (CSV)', comparison, 'scenario_comparison.csv')
    st.caption('Target values are indicative planning estimates, not measured savings or actual inventory. '
               'Stock positions are simulated. A higher target value is not automatically better or worse.')

with t1:
    st.subheader('Executive intelligence')
    if len(low): st.warning(f'{len(low)} product–store combinations are below target. Review replenishment of {low.reorder_qty.sum():,.0f} units in these combinations.')
    else: st.success('No combinations are below the 15% alert threshold.')
    st.info(f'{len(high)} combinations are above target; review excess stock before placing new orders. Estimated DC pooling potential: {b.buffer_saving.sum():,.0f} units.')
    l,r=st.columns([3,2])
    with l:
        chart(px.bar(a.groupby(['dc','status'],as_index=False).size(),x='dc',y='size',color='status',color_discrete_map=COLORS,barmode='group',labels={'size':'Product–store combinations','dc':'Distribution centre'},title='Stock risk by distribution centre'))
    with r:
        chart(px.pie(a,names='status',hole=.65,color='status',color_discrete_map=COLORS,title='Inventory health mix'))
    st.subheader('Inventory risk heatmap')
    heat=a.assign(location=a.dc+' / '+a.store,coverage=np.where(a.target_stock>0,a.simulated_stock/a.target_stock.replace(0,np.nan)*100,np.nan)).pivot(index='sku',columns='location',values='coverage')
    chart(px.imshow(heat,aspect='auto',color_continuous_scale=[[0,RED],[.425,RED],[.5,TEAL],[.575,AMBER],[1,AMBER]],zmin=0,zmax=200,labels={'color':'% of target'},title='Stock as percentage of target (hover for exact value)'))
    st.caption('Below 85%: shortage alert; above 115%: excess alert. Zero target is shown as missing. Heatmap colors are indicative gradients.')
with t2:
    st.subheader('Demand forecasting & validation')
    h=df.groupby('date').demand.sum().sort_index(); horizon=st.slider('Forecast horizon (weeks)',4,26,12)
    future=pd.date_range(h.index[-1]+pd.Timedelta(weeks=1),periods=horizon,freq='W-MON')
    pred=h.shift(1).rolling(8).mean(); valid=pred.notna(); denom=h[valid].abs().sum()
    c=st.columns(3); c[0].metric('Weekly forecast',f'{h.tail(8).mean():,.0f} units'); c[1].metric('Rolling WAPE',f'{100*(h[valid]-pred[valid]).abs().sum()/denom:.1f}%' if denom else 'N/A'); c[2].metric('Forecast horizon',f'{horizon} weeks')
    fig=go.Figure(); fig.add_scatter(x=h.index,y=h.values,name='Historical demand',line=dict(color=BLUE)); fig.add_scatter(x=[h.index[-1],*future],y=[h.iloc[-1],*([h.tail(8).mean()]*horizon)],name='Forecast',line=dict(color=TEAL,dash='dash')); fig.update_layout(title='Historical demand and moving-average forecast',yaxis_title='Units'); chart(fig)
    download('Download forecast',pd.DataFrame({'date':future,'forecast_units':h.tail(8).mean()}),'forecast.csv')
    st.caption('Eight-week moving average with rolling one-step backtest. Historical error does not guarantee future accuracy; missing weeks are not imputed.')
with t3:
    st.subheader('Multi-echelon inventory network')
    dcs=sorted(a.dc.unique()); locations=a[['dc','store']].drop_duplicates(); labels=['Supplier (illustrative)']+dcs+[f'{r.dc} / {r.store}' for r in locations.itertuples()]; sources=[]; targets=[]; values=[]
    for i,dc in enumerate(dcs):
        qty=float(a.loc[a.dc==dc,'weekly_forecast'].sum()); sources.append(0); targets.append(i+1); values.append(qty)
    for j,r in enumerate(locations.itertuples()):
        sources.append(dcs.index(r.dc)+1); targets.append(1+len(dcs)+j); values.append(float(a.loc[(a.dc==r.dc)&(a.store==r.store),'weekly_forecast'].sum()))
    fig=go.Figure(go.Sankey(node=dict(label=labels,pad=18,color=[NAVY]+[BLUE]*len(dcs)+[TEAL]*len(locations)),link=dict(source=sources,target=targets,value=values))); fig.update_layout(title='Illustrative weekly demand flow (units)'); chart(fig)
    pooled=b.groupby('dc',as_index=False)[['pooled_buffer','independent_buffer']].sum().melt(id_vars='dc',var_name='method',value_name='units'); pooled['method']=pooled.method.map({'pooled_buffer':'Pooled buffer','independent_buffer':'Independent buffers'})
    chart(px.bar(pooled,x='dc',y='units',color='method',barmode='group',color_discrete_sequence=[TEAL,BLUE],title='DC safety stock: pooled vs independent'))
    table(b); download('Download DC plan',b,'dc_plan.csv')
    st.info('MEIO-inspired two-echelon heuristic using observed demand covariance. Not a globally optimized solver; no supply constraints or end-to-end service simulation.')
with t4:
    st.subheader('Long-range inventory planning')
    base=a.weekly_forecast.sum()*52; value=a.target_value.sum()+(b.target_stock*b.unit_cost).sum()
    p=pd.DataFrame([{'year':f'Year {i}','annual_demand':base*(1+growth)**i,'indicative_network_stock_value':value*(1+growth)**i} for i in range(1,4)])
    l,r=st.columns(2)
    with l: chart(px.bar(p,x='year',y='annual_demand',title='Annual demand scenario',color_discrete_sequence=[BLUE]))
    with r: chart(px.bar(p,x='year',y='indicative_network_stock_value',title='Inventory investment scenario (₹)',color_discrete_sequence=[TEAL]))
    table(p); download('Download 3-year plan',p,'three_year_plan.csv'); st.caption('Assumes constant costs and lead times with proportional stock scaling. Scenario, not a financial forecast.')
with t5:
    st.subheader('Prioritized inventory actions')
    a['recommendation']=np.select([a.status=='Below target',a.status=='Above target'],['Review replenishment','Review transfer / pause orders'],default='Monitor')
    status=st.multiselect('Risk status',list(COLORS),default=list(COLORS)); view=a[a.status.isin(status)].sort_values('reorder_qty',ascending=False)
    table(view[['sku','dc','store','weekly_forecast','safety_stock','target_stock','simulated_stock','status','reorder_qty','excess_value','recommendation']]); download('Download action plan',view,'store_actions.csv')
    st.caption('Recommendations are rule-based decision support, not automatic orders. Below target does not establish an actual stockout.')
st.divider()
  
st.markdown("""
<div style="text-align:center; padding:18px 8px 6px;">
  <div style="font-weight:700; margin-bottom:12px;">Built by Vikrant Thenge | Operations &amp; Decision Analytics</div>
  <a href="https://github.com/Vikrantthenge" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:inline-block;margin:4px;">
    <img alt="GitHub" src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&amp;logo=github&amp;logoColor=white" />
  </a>
  <a href="https://www.linkedin.com/in/vthenge/" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:inline-block;margin:4px;">
    <img alt="LinkedIn" src="https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&amp;logo=linkedin&amp;logoColor=white" />
  </a>
</div>
""", unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center; width:100%; padding:4px 8px 12px; color:#777; font-size:0.85rem;">
  Portfolio demonstration &bull; Python &middot; Streamlit &middot; Plotly &bull; Forecasting &amp; inventory planning
</div>
""", unsafe_allow_html=True)
