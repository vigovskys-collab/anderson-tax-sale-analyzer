import io,re,requests
from urllib.parse import quote_plus
import pandas as pd
import streamlit as st

OFFICIAL_XLSX_URL='https://www.andersoncountysc.org/wp-content/uploads/2026/10/2026TSSecondAD.xlsx'
BASE='https://propertyviewer.andersoncountysc.org/arcgis/rest/services'
PARCEL=f'{BASE}/NewPropertyViewer/MapServer/5/query'
ZONING=f'{BASE}/QueryMap/MapServer/9/query'
FLOOD=f'{BASE}/QueryMap/MapServer/18/query'
SALES=f'{BASE}/Parcel_Sales/MapServer/0/query'
EASE=f'{BASE}/NewPropertyViewer/MapServer/8/query'
RIVERS=f'{BASE}/NewPropertyViewer/MapServer/19/query'
OVERLAYS=f'{BASE}/Overlays/MapServer/1/query'
COUNTY='https://www.andersoncountysc.org/'
VIEWER='https://propertyviewer.andersoncountysc.org/'
ACPASS='https://acpass.andersoncountysc.org/'

st.set_page_config(page_title='Anderson SC Tax Sale Analyzer',page_icon='🏠',layout='wide')
st.title('🏠 Anderson County SC — 2026 Tax Sale Deal Finder')
st.caption('Screening and due-diligence assistant built around the county’s published tax-sale list and live GIS services.')

@st.cache_data(ttl=1800,show_spinner=False)
def get_xlsx():
 r=requests.get(OFFICIAL_XLSX_URL,timeout=30); r.raise_for_status(); return r.content

def xls(data):
 xl=pd.ExcelFile(io.BytesIO(data)); fs=[]
 for s in xl.sheet_names:
  d=xl.parse(s)
  if len(d): fs.append(d.assign(__sheet=s))
 return sorted(fs,key=len,reverse=True)[0]

def fc(df,ps):
 for c in df.columns:
  if any(re.search(p,str(c).lower()) for p in ps): return c
 return None

def tx(df,c): return df[c].fillna('').astype(str) if c else pd.Series('',index=df.index)
def nu(df,c): return pd.to_numeric(df[c].astype(str).str.replace(r'[$,% ,]','',regex=True),errors='coerce') if c else pd.Series(float('nan'),index=df.index)
def nt(x): return re.sub(r'[^0-9]','',str(x))

@st.cache_data(ttl=1800,show_spinner=False)
def county_query(url,where='1=1',out='*',geometry=None,distance=None):
 p={'where':where,'outFields':out,'returnGeometry':'true','outSR':'4326','f':'json'}
 if geometry:
  p.update({'geometry':str(geometry).replace("'",'"'),'geometryType':'esriGeometryPoint','inSR':'4326','spatialRel':'esriSpatialRelIntersects'})
  if distance is not None: p.update({'distance':distance,'units':'esriSRUnit_Meter'})
 try:
  r=requests.get(url,params=p,timeout=20); j=r.json(); return [f.get('attributes',{}) for f in j.get('features',[])]
 except Exception: return []

@st.cache_data(ttl=1800,show_spinner=False)
def parcel_lookup(tms):
 rows=[]
 for i in range(0,len(tms),80):
  vals=tms[i:i+80]; where='TMS IN ('+','.join("'"+str(v).replace("'","''")+"'" for v in vals)+')'
  p={'where':where,'outFields':'*','returnGeometry':'true','outSR':'4326','f':'json'}
  try:
   j=requests.get(PARCEL,params=p,timeout=30).json()
   for f in j.get('features',[]):
    a=f.get('attributes',{}); g=f.get('geometry',{}); a['_geom']=g
    # centroid-ish point for map / links
    if 'x' in g: a['_lon'],a['_lat']=g['x'],g['y']
    elif 'rings' in g:
     pts=[p for ring in g['rings'] for p in ring]
     if pts: a['_lon']=sum(p[0] for p in pts)/len(pts); a['_lat']=sum(p[1] for p in pts)/len(pts)
    rows.append(a)
  except Exception: pass
 return rows

@st.cache_data(ttl=1800,show_spinner=False)
def enrich(points):
 out=[]
 for key,lat,lon in points:
  geom={'x':lon,'y':lat}
  z=county_query(ZONING,geometry=geom,distance=15)
  f=county_query(FLOOD,geometry=geom,distance=15)
  e=county_query(EASE,geometry=geom,distance=15)
  rv=county_query(RIVERS,geometry=geom,distance=100)
  lake=county_query(OVERLAYS,geometry=geom,distance=100)
  sales=county_query(SALES,geometry=geom,distance=2000)
  out.append({'TMS_KEY':key,'zoning':z,'flood':f,'easement':e,'rivers':rv,'lakes':lake,'sales':sales})
 return out

if 'data' not in st.session_state: st.session_state.data=None
if 'fav' not in st.session_state: st.session_state.fav=set()
if 'notes' not in st.session_state: st.session_state.notes={}
with st.sidebar:
 st.header('Data')
 up=st.file_uploader('Upload county 2026 Excel',type=['xlsx','xls'])
 if st.button('Load official 2026 list',use_container_width=True):
  try: st.session_state.data=get_xlsx(); st.success('Loaded official list.')
  except Exception as e: st.error(e)
 st.divider(); st.markdown(f'[County tax-sale information]({COUNTY})'); st.markdown(f'[ACPASS]({ACPASS})'); st.markdown(f'[Property Viewer]({VIEWER})')
if up: st.session_state.data=up.getvalue()
if not st.session_state.data:
 st.info('Load the official 2026 spreadsheet to begin.'); st.stop()
raw=xls(st.session_state.data); raw.columns=[str(c).strip() for c in raw.columns]
T=fc(raw,[r'\btms\b',r'tax.?map',r'map.?number']); O=fc(raw,[r'owner',r'taxpayer']); A=fc(raw,[r'property.?address',r'street',r'location',r'address']); C=fc(raw,[r'\bcity\b',r'town']); B=fc(raw,[r'opening.?bid',r'minimum.?bid',r'open.?bid']); AV=fc(raw,[r'assessed',r'market.?value',r'appraised']); AC=fc(raw,[r'acre']); I=fc(raw,[r'\bitem\b',r'sale.?no']); TY=fc(raw,[r'tax.?year',r'delinq']); PT=fc(raw,[r'property.?type',r'type',r'mobile'])
df=pd.DataFrame(index=raw.index)
df['TMS']=tx(raw,T); df['Item']=tx(raw,I); df['Owner']=tx(raw,O); df['Address']=tx(raw,A); df['City']=tx(raw,C); df['Opening Bid']=nu(raw,B); df['Assessed']=nu(raw,AV); df['Acres']=nu(raw,AC); df['Tax Year']=tx(raw,TY); df['Type']=tx(raw,PT)
df['TMS_KEY']=df.TMS.map(nt); df['Mobile']=(df.Type+' '+df.Address).str.lower().str.contains(r'mobile|manufactured|mh\b',regex=True)
pars=parcel_lookup([x for x in dict.fromkeys(df.TMS_KEY) if x])
pd_gis=pd.DataFrame(pars)
if len(pd_gis):
 pd_gis['TMS_KEY']=pd_gis.get('TMS','').map(nt)
 # discover likely market/address fields dynamically
 def gcol(patterns): return fc(pd_gis,patterns)
 for new,pats in [('GIS Address',[r'phys.?addr',r'address']),('GIS Market',[r'mrkt.?value',r'market.?value']),('GIS Acres',[r'acres?',r'gis_acres']),('GIS Ratio',[r'^ratio$'])]:
  c=gcol(pats); pd_gis[new]=pd_gis[c] if c else pd.NA
 for c in ['_lat','_lon']:
  if c not in pd_gis: pd_gis[c]=pd.NA
 cols=['TMS_KEY','GIS Address','GIS Market','GIS Acres','GIS Ratio','_lat','_lon']
 df=df.merge(pd_gis[cols].drop_duplicates('TMS_KEY'),on='TMS_KEY',how='left')
else:
 for c in ['GIS Address','GIS Market','GIS Acres','GIS Ratio','_lat','_lon']: df[c]=pd.NA

df['Research Address']=df.Address.where(df.Address.str.strip().ne(''),df['GIS Address'].fillna(''))
df['Bid/Assessed']=df['Opening Bid']/df['Assessed'].replace(0,pd.NA)
df['Bid/Market']=df['Opening Bid']/pd.to_numeric(df['GIS Market'],errors='coerce').replace(0,pd.NA)
df['Equity Gap']=pd.to_numeric(df['GIS Market'],errors='coerce')-df['Opening Bid']

# Only enrich top candidates after initial filtering, keeping the app responsive.
with st.expander('🔎 Deal filters',expanded=True):
 q=st.text_input('Search TMS, owner, address, city, item')
 c1,c2,c3,c4=st.columns(4)
 bmax=int(df['Opening Bid'].max()) if df['Opening Bid'].notna().any() else 0
 br=c1.slider('Opening bid',0,max(1,bmax),(0,max(1,bmax)))
 rm=c2.number_input('Maximum bid / GIS market (%)',0.,500.,35.,5.)
 ma=c3.number_input('Minimum acres',0.,10000.,0.,.1)
 typ=c4.selectbox('Property type',['All','Land / real estate','Mobile homes'])
 c5,c6,c7=st.columns(3)
 minval=c5.number_input('Minimum GIS market value',0.,float(pd.to_numeric(df['GIS Market'],errors='coerce').max() or 0),0.,1000.)
 favonly=c6.checkbox('Favorites only')
 topn=c7.number_input('Analyze GIS details for top N',10,500,100,10)
mask=pd.Series(True,index=df.index)
if q:
 s=df.fillna('').astype(str).agg(' | '.join,axis=1).str.lower(); mask &= s.str.contains(re.escape(q.lower()),regex=True,na=False)
mask &= df['Opening Bid'].between(*br) | df['Opening Bid'].isna(); mask &= df['Acres'].fillna(0)>=ma; mask &= pd.to_numeric(df['GIS Market'],errors='coerce').fillna(0)>=minval; mask &= (df['Bid/Market'].fillna(0)*100<=rm)|df['Bid/Market'].isna()
if typ=='Mobile homes': mask &= df.Mobile
if typ=='Land / real estate': mask &= ~df.Mobile
if favonly: mask &= df.index.isin(st.session_state.fav)
r=df.loc[mask].copy()
r=r.sort_values('Bid/Market',na_position='last')
points=[]
for idx,row in r.head(int(topn)).iterrows():
 if pd.notna(row._lat) and pd.notna(row._lon): points.append((row.TMS_KEY,float(row._lat),float(row._lon)))
en= enrich(points) if points else []
enmap={x['TMS_KEY']:x for x in en}

def txtblob(items):
 return ' '.join(' '.join(str(v) for v in d.values() if v is not None) for d in items).lower()
def score(row):
 s=50.; bm=row['Bid/Market']
 if pd.notna(bm): s+=max(-35,min(35,(.25-float(bm))*100))
 elif pd.notna(row['Bid/Assessed']): s+=max(-30,min(30,(.35-float(row['Bid/Assessed']))*70))
 if pd.notna(row['Acres']): s+=min(12,float(row['Acres'])*1.5)
 info=enmap.get(row.TMS_KEY,{})
 fb=txtblob(info.get('flood',[])); zb=txtblob(info.get('zoning',[])); eb=txtblob(info.get('easement',[]));
 if fb: s-=25
 if eb: s-=8
 if row.Mobile: s-=12
 if row['Opening Bid']<5000: s+=5
 return round(max(0,min(100,s)))
r['Deal Score']=r.apply(score,axis=1)
r['Risk']=''
for idx,row in r.iterrows():
 info=enmap.get(row.TMS_KEY,{})
 flags=[]
 if txtblob(info.get('flood',[])): flags.append('FLOOD')
 if txtblob(info.get('easement',[])): flags.append('EASEMENT')
 if txtblob(info.get('rivers',[])): flags.append('WATER')
 if row.Mobile: flags.append('MOBILE')
 if pd.isna(row['GIS Market']): flags.append('NO GIS VALUE')
 r.loc[idx,'Risk']=' / '.join(flags) if flags else 'LOWER AUTOMATED RISK'
r=r.sort_values(['Deal Score','Bid/Market'],ascending=[False,True])

m1,m2,m3,m4=st.columns(4); m1.metric('Matches',len(r)); m2.metric('GIS matched',int(r['GIS Market'].notna().sum())); m3.metric('Top score',int(r['Deal Score'].max()) if len(r) else 0); m4.metric('Favorites',len(st.session_state.fav))
st.subheader('🏆 Ranked opportunities')
show=r[['TMS','Item','Owner','Research Address','Opening Bid','GIS Market','Acres','Bid/Market','Equity Gap','Deal Score','Risk']].copy()
for c in ['Opening Bid','GIS Market','Equity Gap']: show[c]=show[c].map(lambda x:f'${x:,.0f}' if pd.notna(x) else '—')
show['Bid/Market']=show['Bid/Market'].map(lambda x:f'{x*100:.1f}%' if pd.notna(x) else '—')
show['Acres']=show['Acres'].map(lambda x:f'{x:.2f}' if pd.notna(x) else '—')
st.dataframe(show,use_container_width=True,hide_index=True,height=430)

if len(r):
 st.subheader('📍 Research a property')
 idx=st.selectbox('Property',r.index.tolist(),format_func=lambda i:f"{r.loc[i,'TMS']} | {r.loc[i,'Owner']} | {r.loc[i,'Research Address']}")
 row=df.loc[idx]; info=enmap.get(row.TMS_KEY,{})
 l,rr=st.columns([2,1])
 with l:
  st.write(f"**Owner:** {row.Owner or '—'}"); st.write(f"**TMS:** {row.TMS or '—'}"); st.write(f"**Address:** {row['Research Address'] or '—'}")
  for label,c in [('Opening bid','Opening Bid'),('Assessed','Assessed'),('GIS market value','GIS Market'),('Acreage','Acres')]:
   v=row[c]; st.write(f"**{label}:** {('$'+format(v,',.0f')) if pd.notna(v) and c!='Acres' else (format(v,'.2f') if pd.notna(v) else '—')}")
  st.write(f"**Deal score:** {score(row)}/100"); st.write(f"**Automated risk:** {r.loc[idx,'Risk']}")
  note=st.text_area('Research notes',st.session_state.notes.get(str(idx),''),height=120); st.session_state.notes[str(idx)]=note
  if idx in st.session_state.fav:
   if st.button('☆ Remove favorite'): st.session_state.fav.remove(idx); st.rerun()
  else:
   if st.button('★ Add favorite'): st.session_state.fav.add(idx); st.rerun()
 with rr:
  if pd.notna(row._lat) and pd.notna(row._lon):
   street=f'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={row._lat},{row._lon}'
   maps=f'https://www.google.com/maps/search/?api=1&query={quote_plus(str(row["Research Address"])+", Anderson County, SC")}'
   st.markdown(f'### [🚗 Live Street View]({street})'); st.markdown(f'[🗺️ Google Maps]({maps})')
  st.markdown(f'[🏛️ County Property Viewer]({VIEWER})'); st.markdown(f'[📑 ACPASS]({ACPASS})')
  def section(title,key):
   vals=info.get(key,[])
   st.markdown('**'+title+'**')
   if not vals: st.write('No spatial match returned.')
   else:
    for v in vals[:5]: st.write('• '+' | '.join(f'{k}: {v}' for k,v in v.items() if v not in (None,'')))
  section('Zoning','zoning'); section('Flood hazard','flood'); section('Access easement','easement'); section('Water / streams','rivers')
  sales=info.get('sales',[])
  st.markdown('**Nearby parcel sales (within ~2 km)**')
  if sales:
   for s in sales[:10]: st.write('• '+ ' | '.join(f'{k}: {v}' for k,v in s.items() if v not in (None,'')))
  else: st.write('No nearby sales returned by the county GIS service.')

st.divider(); out=r.copy(); out['Favorite']=out.index.isin(st.session_state.fav); out['Notes']=out.index.map(lambda i:st.session_state.notes.get(str(i),'')); 
st.divider()
st.subheader("💰 Maximum Bid & Bidding Strategy")
st.caption("Transparent planning model. Change the assumptions to match your strategy; this is not an appraisal or guarantee of profit.")

bc1, bc2, bc3 = st.columns(3)
with bc1:
    target_margin = st.number_input("Desired profit / equity margin ($)", 0.0, 10000000.0, 20000.0, 2500.0)
    repair_budget = st.number_input("Repairs / cleanup reserve ($)", 0.0, 10000000.0, 10000.0, 1000.0)
with bc2:
    transaction_cost_pct = st.number_input("Transaction / closing reserve (%)", 0.0, 25.0, 3.0, 0.5)
    holding_cost = st.number_input("Holding / carrying reserve ($)", 0.0, 10000000.0, 5000.0, 1000.0)
with bc3:
    risk_reserve_pct = st.number_input("Base risk reserve (%)", 0.0, 50.0, 10.0, 1.0)
    max_ltv_pct = st.number_input("Maximum bid as % of estimated value", 1.0, 100.0, 50.0, 5.0)

if len(res):
    bid_records = []
    for i, r in res.iterrows():
        value = r["Market Value"] if pd.notna(r["Market Value"]) and r["Market Value"] > 0 else r["Assessed"]
        if pd.isna(value) or value <= 0:
            bid_records.append([i, None, None, None, "PASS — insufficient value data"])
            continue

        risk_pct = float(risk_reserve_pct)
        risk_reasons = []
        if bool(r.get("Flood Risk", False)):
            risk_pct += 7; risk_reasons.append("flood")
        if bool(r.get("Access Risk", False)):
            risk_pct += 5; risk_reasons.append("access")
        if bool(r.get("Water Proximity", False)):
            risk_pct += 3; risk_reasons.append("water")
        if bool(r.get("Zoning", False)):
            risk_pct += 2; risk_reasons.append("zoning")
        if bool(r.get("Mobile", False)):
            risk_pct += 5; risk_reasons.append("mobile")

        value = float(value)
        risk_dollars = value * risk_pct / 100
        transaction_dollars = value * float(transaction_cost_pct) / 100
        formula_max = value - float(repair_budget) - float(holding_cost) - risk_dollars - transaction_dollars - float(target_margin)
        value_cap = value * float(max_ltv_pct) / 100
        maximum = max(0.0, min(formula_max, value_cap))

        opening = float(r["Opening Bid"]) if pd.notna(r["Opening Bid"]) else 0
        if maximum < opening:
            rec = "PASS — opening bid exceeds model maximum"
        elif maximum < opening * 1.10:
            rec = "CAUTION — little bidding room"
        elif maximum >= opening * 1.50:
            rec = "STRONG — substantial bidding room"
        else:
            rec = "BID — within model"

        bid_records.append([i, value, maximum, risk_pct, rec])

    bid_df = pd.DataFrame(
        bid_records,
        columns=["_bid_idx", "Estimated Value", "Maximum Bid", "Risk Reserve %", "Bid Recommendation"]
    ).set_index("_bid_idx")
    res = res.drop(columns=["Estimated Value", "Maximum Bid", "Risk Reserve %", "Bid Recommendation"], errors="ignore")
    res = res.join(bid_df)

    bidshow = res[[
        "TMS","Owner","Research Address","Opening Bid","Estimated Value",
        "Maximum Bid","Deal Score","Risk Reserve %","Bid Recommendation"
    ]].copy()
    for c in ["Opening Bid","Estimated Value","Maximum Bid"]:
        bidshow[c] = bidshow[c].map(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
    bidshow["Risk Reserve %"] = bidshow["Risk Reserve %"].map(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")
    st.markdown("#### Ranked bidding sheet")
    st.dataframe(bidshow, use_container_width=True, hide_index=True, height=420)

    selected_bid_idx = st.selectbox(
        "Detailed maximum-bid calculation",
        res.index.tolist(),
        format_func=lambda i: f"{res.loc[i,'TMS']} | {res.loc[i,'Owner']} | Max: ${res.loc[i,'Maximum Bid']:,.0f}" if pd.notna(res.loc[i,"Maximum Bid"]) else f"{res.loc[i,'TMS']} | insufficient value data"
    )
    rb = res.loc[selected_bid_idx]

    if pd.notna(rb["Maximum Bid"]):
        value = float(rb["Estimated Value"])
        maximum = float(rb["Maximum Bid"])
        opening = float(rb["Opening Bid"]) if pd.notna(rb["Opening Bid"]) else 0
        risk_pct = float(rb["Risk Reserve %"])
        risk_dollars = value * risk_pct / 100
        tx_dollars = value * float(transaction_cost_pct) / 100

        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Estimated value", f"${value:,.0f}")
        m2.metric("Repairs", f"${repair_budget:,.0f}")
        m3.metric("Risk reserve", f"${risk_dollars:,.0f}")
        m4.metric("Desired margin", f"${target_margin:,.0f}")
        m5.metric("MAX BID", f"${maximum:,.0f}")

        if opening:
            st.write(f"**Opening bid:** ${opening:,.0f}  •  **Bidding room:** ${max(0, maximum-opening):,.0f}")
        st.info(
            f"${value:,.0f} estimated value − ${repair_budget:,.0f} repairs − "
            f"${holding_cost:,.0f} holding − ${risk_dollars:,.0f} risk reserve − "
            f"${tx_dollars:,.0f} transaction reserve − ${target_margin:,.0f} desired margin "
            f"= **${maximum:,.0f} maximum bid**, capped at {max_ltv_pct:.0f}% of estimated value."
        )
    else:
        st.warning("This property does not have enough value information for the maximum-bid model.")

st.download_button('📥 Download ranked shortlist CSV',out.to_csv(index=False).encode('utf-8-sig'),'anderson_2026_ranked_shortlist.csv','text/csv')
st.caption('Automated flags are screening signals, not title, legal, environmental, zoning, valuation, or investment conclusions. Verify each parcel independently before bidding.')
