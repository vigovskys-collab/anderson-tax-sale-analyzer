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

st.set_page_config(page_title='Anderson SC Tax Sale',page_icon='🏠',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container{padding:1rem .75rem 3rem;max-width:1100px}
@media (max-width:700px){.block-container{padding:.65rem .55rem 2.5rem}.stButton>button,.stDownloadButton>button{min-height:3rem;font-size:1rem}.stSelectbox label,.stTextInput label,.stNumberInput label,.stSlider label{font-size:.92rem}.metric-card{padding:.75rem;border:1px solid #ddd;border-radius:12px;margin:.45rem 0;background:var(--secondary-background-color)}.property-card{border:1px solid #ddd;border-radius:14px;padding:.85rem;margin:.65rem 0}.small{font-size:.84rem;color:#666}.big{font-size:1.15rem;font-weight:700}.risk{font-weight:600}.action a{display:block;text-decoration:none;padding:.7rem;border:1px solid #ccc;border-radius:10px;text-align:center;margin:.35rem 0}}
</style>''',unsafe_allow_html=True)
st.title('🏠 Anderson County SC Tax Sale')
st.caption('2026 tax-sale screening • mobile-first research • risk flags • maximum-bid planning')

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

def txtblob(items):
    return ' '.join(' '.join(str(v) for v in d.values() if v is not None) for d in items).lower()

@st.cache_data(ttl=1800,show_spinner=False)
def county_query(url,where='1=1',out='*',geometry=None,distance=None):
    p={'where':where,'outFields':out,'returnGeometry':'true','outSR':'4326','f':'json'}
    if geometry:
        p.update({'geometry':str(geometry).replace("'",'"'),'geometryType':'esriGeometryPoint','inSR':'4326','spatialRel':'esriSpatialRelIntersects'})
        if distance is not None: p.update({'distance':distance,'units':'esriSRUnit_Meter'})
    try:
        j=requests.get(url,params=p,timeout=20).json(); return [f.get('attributes',{}) for f in j.get('features',[])]
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
        out.append({'TMS_KEY':key,'zoning':county_query(ZONING,geometry=geom,distance=15),'flood':county_query(FLOOD,geometry=geom,distance=15),'easement':county_query(EASE,geometry=geom,distance=15),'rivers':county_query(RIVERS,geometry=geom,distance=100),'lakes':county_query(OVERLAYS,geometry=geom,distance=100),'sales':county_query(SALES,geometry=geom,distance=2000)})
    return out

if 'data' not in st.session_state: st.session_state.data=None
if 'fav' not in st.session_state: st.session_state.fav=set()
if 'notes' not in st.session_state: st.session_state.notes={}

with st.expander('⚙️ Data & county research links'):
    up=st.file_uploader('Upload county 2026 Excel',type=['xlsx','xls'])
    if st.button('Load official 2026 list',use_container_width=True):
        try:
            with st.spinner('Downloading official 2026 tax-sale list…'):
                st.session_state.data=get_xlsx()
            st.success('Loaded official list.')
        except Exception as e: st.error(f'Could not load the county spreadsheet: {e}')
    st.markdown(f'[County tax-sale information]({COUNTY})  •  [ACPASS]({ACPASS})  •  [Property Viewer]({VIEWER})')
if up: st.session_state.data=up.getvalue()
if not st.session_state.data:
    st.markdown('### Ready to start')
    st.write('Load the official Anderson County 2026 tax-sale spreadsheet to begin.')
    if st.button('📥 Load official 2026 spreadsheet',type='primary',use_container_width=True):
        try:
            with st.spinner('Downloading official 2026 tax-sale list…'):
                st.session_state.data=get_xlsx()
            st.rerun()
        except Exception as e: st.error(f'Could not load the county spreadsheet: {e}')
    st.stop()

raw=xls(st.session_state.data); raw.columns=[str(c).strip() for c in raw.columns]
T=fc(raw,[r'\btms\b',r'tax.?map',r'map.?number']); O=fc(raw,[r'owner',r'taxpayer']); A=fc(raw,[r'property.?address',r'street',r'location',r'address']); C=fc(raw,[r'\bcity\b',r'town']); B=fc(raw,[r'opening.?bid',r'minimum.?bid',r'open.?bid']); AV=fc(raw,[r'assessed',r'market.?value',r'appraised']); AC=fc(raw,[r'acre']); I=fc(raw,[r'\bitem\b',r'sale.?no']); TY=fc(raw,[r'tax.?year',r'delinq']); PT=fc(raw,[r'property.?type',r'type',r'mobile'])
df=pd.DataFrame(index=raw.index)
df['TMS']=tx(raw,T); df['Item']=tx(raw,I); df['Owner']=tx(raw,O); df['Address']=tx(raw,A); df['City']=tx(raw,C); df['Opening Bid']=nu(raw,B); df['Assessed']=nu(raw,AV); df['Acres']=nu(raw,AC); df['Tax Year']=tx(raw,TY); df['Type']=tx(raw,PT)
df['TMS_KEY']=df.TMS.map(nt); df['Mobile']=(df.Type+' '+df.Address).str.lower().str.contains(r'mobile|manufactured|mh\b',regex=True)
pars=parcel_lookup([x for x in dict.fromkeys(df.TMS_KEY) if x]); pd_gis=pd.DataFrame(pars)
if len(pd_gis):
    pd_gis['TMS_KEY']=pd_gis.get('TMS','').map(nt)
    def gcol(patterns): return fc(pd_gis,patterns)
    for new,pats in [('GIS Address',[r'phys.?addr',r'address']),('GIS Market',[r'mrkt.?value',r'market.?value']),('GIS Acres',[r'acres?',r'gis_acres']),('GIS Ratio',[r'^ratio$'])]:
        c=gcol(pats); pd_gis[new]=pd_gis[c] if c else pd.NA
    for c in ['_lat','_lon']:
        if c not in pd_gis: pd_gis[c]=pd.NA
    df=df.merge(pd_gis[['TMS_KEY','GIS Address','GIS Market','GIS Acres','GIS Ratio','_lat','_lon']].drop_duplicates('TMS_KEY'),on='TMS_KEY',how='left')
else:
    for c in ['GIS Address','GIS Market','GIS Acres','GIS Ratio','_lat','_lon']: df[c]=pd.NA

df['Research Address']=df.Address.where(df.Address.str.strip().ne(''),df['GIS Address'].fillna(''))
df['Bid/Assessed']=df['Opening Bid']/df['Assessed'].replace(0,pd.NA); df['Bid/Market']=df['Opening Bid']/pd.to_numeric(df['GIS Market'],errors='coerce').replace(0,pd.NA); df['Equity Gap']=pd.to_numeric(df['GIS Market'],errors='coerce')-df['Opening Bid']

with st.expander('🔎 Filters',expanded=True):
    q=st.text_input('Search TMS, owner, address, city, item',placeholder='e.g. owner name or TMS')
    c1,c2=st.columns(2)
    bmax=int(df['Opening Bid'].max()) if df['Opening Bid'].notna().any() else 0
    br=c1.slider('Opening bid range',0,max(1,bmax),(0,max(1,bmax)))
    rm=c2.number_input('Maximum bid / GIS market (%)',0.,500.,50.,5.)
    c3,c4=st.columns(2)
    ma=c3.number_input('Minimum acres',0.,10000.,0.,.1); typ=c4.selectbox('Property type',['All','Land / real estate','Mobile homes'])
    c5,c6=st.columns(2)
    max_gis=float(pd.to_numeric(df['GIS Market'],errors='coerce').max() or 0)
    minval=c5.number_input('Minimum GIS market value',0.,max(1.,max_gis),0.,1000.); favonly=c6.checkbox('Favorites only')
    topn=st.number_input('GIS details for top N',10,500,100,10)

mask=pd.Series(True,index=df.index)
if q:
    s=df.fillna('').astype(str).agg(' | '.join,axis=1).str.lower(); mask &= s.str.contains(re.escape(q.lower()),regex=True,na=False)
mask &= (df['Opening Bid'].between(*br) | df['Opening Bid'].isna()); mask &= df['Acres'].fillna(0)>=ma; mask &= pd.to_numeric(df['GIS Market'],errors='coerce').fillna(0)>=minval; mask &= ((df['Bid/Market'].fillna(0)*100<=rm)|df['Bid/Market'].isna())
if typ=='Mobile homes': mask &= df.Mobile
if typ=='Land / real estate': mask &= ~df.Mobile
if favonly: mask &= df.index.isin(st.session_state.fav)
r=df.loc[mask].copy().sort_values('Bid/Market',na_position='last')
points=[]
for idx,row in r.head(int(topn)).iterrows():
    if pd.notna(row._lat) and pd.notna(row._lon): points.append((row.TMS_KEY,float(row._lat),float(row._lon)))
en=enrich(points) if points else []; enmap={x['TMS_KEY']:x for x in en}

def score(row):
    s=50.; bm=row['Bid/Market']
    if pd.notna(bm): s+=max(-35,min(35,(.25-float(bm))*100))
    elif pd.notna(row['Bid/Assessed']): s+=max(-30,min(30,(.35-float(row['Bid/Assessed']))*70))
    if pd.notna(row['Acres']): s+=min(12,float(row['Acres'])*1.5)
    info=enmap.get(row.TMS_KEY,{})
    if txtblob(info.get('flood',[])): s-=25
    if txtblob(info.get('easement',[])): s-=8
    if row.Mobile: s-=12
    if row['Opening Bid']<5000: s+=5
    return round(max(0,min(100,s)))

def risk_for(row):
    info=enmap.get(row.TMS_KEY,{ }); flags=[]
    if txtblob(info.get('flood',[])): flags.append('FLOOD')
    if txtblob(info.get('easement',[])): flags.append('EASEMENT')
    if txtblob(info.get('rivers',[])) or txtblob(info.get('lakes',[])): flags.append('WATER')
    if row.Mobile: flags.append('MOBILE')
    if pd.isna(row['GIS Market']): flags.append('NO GIS VALUE')
    return ' / '.join(flags) if flags else 'LOWER AUTOMATED RISK'

r['Deal Score']=r.apply(score,axis=1); r['Risk']=r.apply(risk_for,axis=1); r=r.sort_values(['Deal Score','Bid/Market'],ascending=[False,True])

m1,m2,m3=st.columns(3); m1.metric('Matches',len(r)); m2.metric('GIS matched',int(r['GIS Market'].notna().sum())); m3.metric('Favorites',len(st.session_state.fav))

st.subheader('🏆 Top opportunities')
if len(r)==0: st.warning('No properties match the current filters.')
else:
    # Mobile-first cards
    for i,idx in enumerate(r.index):
        row=r.loc[idx]
        if i>=50: break
        bid=f"${row['Opening Bid']:,.0f}" if pd.notna(row['Opening Bid']) else '—'
        val=f"${row['GIS Market']:,.0f}" if pd.notna(row['GIS Market']) else '—'
        acres=f"{row['Acres']:.2f}" if pd.notna(row['Acres']) else '—'
        with st.container(border=True):
            st.markdown(f"**#{i+1}  {row['TMS']}**  ·  **Score {int(row['Deal Score'])}/100**")
            st.markdown(f"{row['Owner'] or 'Unknown owner'}  \n{row['Research Address'] or 'No address listed'}")
            a,b,c=st.columns(3); a.metric('Opening',bid); b.metric('GIS value',val); c.metric('Acres',acres)
            st.caption(f"Risk: {row['Risk']}")

st.subheader('📍 Research a property')
if len(r):
    idx=st.selectbox('Choose property',r.index.tolist(),format_func=lambda i:f"{r.loc[i,'TMS']} • {r.loc[i,'Owner']} • {r.loc[i,'Research Address']}")
    row=r.loc[idx]; info=enmap.get(row.TMS_KEY,{})
    st.markdown(f"### {row['TMS']} — {row['Owner'] or 'Unknown owner'}")
    st.write(row['Research Address'] or 'No address listed')
    a,b=st.columns(2); a.metric('Opening bid',f"${row['Opening Bid']:,.0f}" if pd.notna(row['Opening Bid']) else '—'); b.metric('Deal score',f"{int(row['Deal Score'])}/100")
    if pd.notna(row._lat) and pd.notna(row._lon):
        street=f'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={row._lat},{row._lon}'
        maps=f'https://www.google.com/maps/search/?api=1&query={quote_plus(str(row["Research Address"])+", Anderson County, SC")}'
        a,b=st.columns(2); a.link_button('🚗 Street View',street,use_container_width=True); b.link_button('🗺️ Google Maps',maps,use_container_width=True)
    a,b=st.columns(2); a.link_button('🏛️ County Property Viewer',VIEWER,use_container_width=True); b.link_button('📑 ACPASS',ACPASS,use_container_width=True)
    st.markdown(f"**Automated risk:** {row['Risk']}")
    note=st.text_area('Research notes',st.session_state.notes.get(str(idx),''),height=110); st.session_state.notes[str(idx)]=note
    if idx in st.session_state.fav:
        if st.button('☆ Remove favorite',use_container_width=True): st.session_state.fav.remove(idx); st.rerun()
    else:
        if st.button('★ Add favorite',use_container_width=True): st.session_state.fav.add(idx); st.rerun()
    with st.expander('🧭 GIS risk details'):
        def section(title,key):
            vals=info.get(key,[]); st.markdown(f'**{title}**')
            if not vals: st.write('No spatial match returned.')
            else:
                for v in vals[:5]: st.write('• '+' | '.join(f'{k}: {v}' for k,v in v.items() if v not in (None,'')))
        section('Zoning','zoning'); section('Flood hazard','flood'); section('Access easement','easement'); section('Water / streams','rivers')
        sales=info.get('sales',[]); st.markdown('**Nearby parcel sales**')
        if sales:
            for s in sales[:10]: st.write('• '+' | '.join(f'{k}: {v}' for k,v in s.items() if v not in (None,'')))
        else: st.write('No nearby sales returned.')

st.divider(); st.subheader('💰 Maximum Bid Calculator')
st.caption('Planning model only — not an appraisal, title opinion, or guarantee of profit.')
bc1,bc2=st.columns(2)
with bc1:
    target_margin=st.number_input('Desired profit / equity margin ($)',0.,10000000.,20000.,2500.)
    repair_budget=st.number_input('Repairs / cleanup reserve ($)',0.,10000000.,10000.,1000.)
    holding_cost=st.number_input('Holding / carrying reserve ($)',0.,10000000.,5000.,1000.)
with bc2:
    transaction_cost_pct=st.number_input('Transaction / closing reserve (%)',0.,25.,3.,.5)
    risk_reserve_pct=st.number_input('Base risk reserve (%)',0.,50.,10.,1.)
    max_ltv_pct=st.number_input('Maximum bid as % of estimated value',1.,100.,50.,5.)

if len(r):
    bid_records=[]
    for i,prop in r.iterrows():
        value=pd.to_numeric(prop['GIS Market'],errors='coerce')
        if pd.isna(value) or value<=0: value=pd.to_numeric(prop['Assessed'],errors='coerce')
        if pd.isna(value) or value<=0:
            bid_records.append([i,None,None,None,'PASS — insufficient value data']); continue
        risk_pct=float(risk_reserve_pct); info=enmap.get(prop.TMS_KEY,{})
        if txtblob(info.get('flood',[])): risk_pct+=7
        if txtblob(info.get('easement',[])): risk_pct+=5
        if txtblob(info.get('rivers',[])) or txtblob(info.get('lakes',[])): risk_pct+=3
        if txtblob(info.get('zoning',[])): risk_pct+=2
        if prop.Mobile: risk_pct+=5
        value=float(value); risk_dollars=value*risk_pct/100; tx=value*float(transaction_cost_pct)/100
        maximum=max(0.,min(value-float(repair_budget)-float(holding_cost)-risk_dollars-tx-float(target_margin),value*float(max_ltv_pct)/100))
        opening=float(prop['Opening Bid']) if pd.notna(prop['Opening Bid']) else 0
        if maximum<opening: rec='PASS — opening bid exceeds model maximum'
        elif maximum<opening*1.10: rec='CAUTION — little bidding room'
        elif maximum>=opening*1.50: rec='STRONG — substantial bidding room'
        else: rec='BID — within model'
        bid_records.append([i,value,maximum,risk_pct,rec])
    bid_df=pd.DataFrame(bid_records,columns=['_bid_idx','Estimated Value','Maximum Bid','Risk Reserve %','Bid Recommendation']).set_index('_bid_idx')
    res=r.join(bid_df)
    selected_bid_idx=st.selectbox('Detailed maximum-bid calculation',res.index.tolist(),format_func=lambda i:f"{res.loc[i,'TMS']} • Max ${res.loc[i,'Maximum Bid']:,.0f}" if pd.notna(res.loc[i,'Maximum Bid']) else f"{res.loc[i,'TMS']} • insufficient value")
    rb=res.loc[selected_bid_idx]
    if pd.notna(rb['Maximum Bid']):
        value=float(rb['Estimated Value']); maximum=float(rb['Maximum Bid']); opening=float(rb['Opening Bid']) if pd.notna(rb['Opening Bid']) else 0; risk_pct=float(rb['Risk Reserve %']); risk_dollars=value*risk_pct/100; tx=value*float(transaction_cost_pct)/100
        a,b=st.columns(2); a.metric('Estimated value',f'${value:,.0f}'); b.metric('MAX BID',f'${maximum:,.0f}')
        a,b=st.columns(2); a.metric('Opening bid',f'${opening:,.0f}'); b.metric('Bidding room',f'${max(0,maximum-opening):,.0f}')
        st.info(f"${value:,.0f} value − ${repair_budget:,.0f} repairs − ${holding_cost:,.0f} holding − ${risk_dollars:,.0f} risk − ${tx:,.0f} transaction − ${target_margin:,.0f} desired margin = **${maximum:,.0f} max bid**.")
    else: st.warning('Not enough value data for this property.')

out=r.copy(); out['Favorite']=out.index.isin(st.session_state.fav); out['Notes']=out.index.map(lambda i:st.session_state.notes.get(str(i),''))
st.download_button('📥 Download ranked shortlist CSV',out.to_csv(index=False).encode('utf-8-sig'),'anderson_2026_ranked_shortlist.csv','text/csv',use_container_width=True)
st.caption('Screening signals must be independently verified before bidding. Tax-sale properties are sold as-is/where-is.')
