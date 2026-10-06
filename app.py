import io,re,requests
from urllib.parse import quote_plus
import pandas as pd
import streamlit as st

OFFICIAL_XLSX_URL='https://www.andersoncountysc.org/wp-content/uploads/2026/10/2026TSSecondAD.xlsx'
COUNTY='https://www.andersoncountysc.org/'
VIEWER='https://propertyviewer.andersoncountysc.org/'
ACPASS='https://acpass.andersoncountysc.org/'
GIS='https://propertyviewer.andersoncountysc.org/arcgis/rest/services'
PARCEL_PRIMARY=f'{GIS}/Opengov/MAT/MapServer/13/query'
PARCEL_FALLBACK=f'{GIS}/NewPropertyViewer/MapServer/5/query'
ZONING=f'{GIS}/QueryMap/MapServer/9/query'
FLOOD=f'{GIS}/QueryMap/MapServer/18/query'
SALES=f'{GIS}/Parcel_Sales/MapServer/0/query'
EASE=f'{GIS}/NewPropertyViewer/MapServer/8/query'
RIVERS=f'{GIS}/NewPropertyViewer/MapServer/19/query'
OVERLAYS=f'{GIS}/Overlays/MapServer/1/query'

st.set_page_config(page_title='Anderson SC Tax Sale',page_icon='🏠',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container{padding:1rem .75rem 3rem;max-width:1100px}
@media (max-width:700px){.block-container{padding:.65rem .55rem 2.5rem}.stButton>button,.stDownloadButton>button{min-height:3rem;font-size:1rem}.stSelectbox label,.stTextInput label,.stNumberInput label,.stSlider label{font-size:.92rem}.property-card{border:1px solid #ddd;border-radius:14px;padding:.85rem;margin:.65rem 0}.small{font-size:.84rem;color:#666}}
</style>''',unsafe_allow_html=True)

st.title('🏠 Anderson County SC Tax Sale')
st.caption('2026 tax-sale screening • corrected county TMS matching • GIS parcel research')

@st.cache_data(ttl=1800,show_spinner=False)
def get_xlsx():
    r=requests.get(OFFICIAL_XLSX_URL,timeout=45); r.raise_for_status(); return r.content

def load_sheet(data):
    xl=pd.ExcelFile(io.BytesIO(data)); candidates=[]
    for s in xl.sheet_names:
        d=xl.parse(s,header=None)
        candidates.append((s,d))
    # Find the row that looks most like the tax-sale header.
    best=None
    for s,d in candidates:
        for ridx in range(min(60,len(d))):
            vals=' | '.join(str(x).strip().lower() for x in d.iloc[ridx].tolist())
            score=sum(k in vals for k in ['item','owner','property','taxmap','amount due','years due'])
            if best is None or score>best[0]: best=(score,s,ridx)
    if best is None or best[0]<2:
        s,d=max(candidates,key=lambda x:len(x[1]))
        return d
    _,s,ridx=best
    d=dict(candidates)[s]
    d=d.iloc[ridx+1:].copy(); d.columns=[str(x).strip() for x in dict(candidates)[s].iloc[ridx].tolist()]
    return d.reset_index(drop=True)

def find_col(df, patterns):
    for c in df.columns:
        name=str(c).strip().lower()
        if any(re.search(p,name) for p in patterns): return c
    return None

def textcol(df,c):
    return df[c].fillna('').astype(str) if c else pd.Series('',index=df.index)

def numcol(df,c):
    if not c: return pd.Series(float('nan'),index=df.index)
    return pd.to_numeric(df[c].astype(str).str.replace(r'[$,% ,]','',regex=True),errors='coerce')

def digits(x): return re.sub(r'[^0-9]','',str(x))

def canonical_tms(x):
    d=digits(x)
    # Excel commonly turns 0450001008 into 450001008.0.
    if len(d)==9: d=d.zfill(10)
    if len(d)==10: return f'{d[:3]}-{d[3:5]}-{d[5:7]}-{d[7:]}'
    if len(d)==11 and '-' in str(x): return str(x)
    if len(d)==11: return str(x)
    return ''

def normalized_key(x):
    c=canonical_tms(x)
    return digits(c) if c else digits(x)

@st.cache_data(ttl=1800,show_spinner=False)
def gis_query(url, where, outfields='*'):
    p={'where':where,'outFields':outfields,'returnGeometry':'true','outSR':'4326','f':'json'}
    try:
        r=requests.get(url,params=p,timeout=35)
        if r.status_code!=200: return [],f'HTTP {r.status_code}'
        j=r.json()
        if 'error' in j: return [],str(j['error'])
        return j.get('features',[]),''
    except Exception as e:
        return [],str(e)

@st.cache_data(ttl=1800,show_spinner=False)
def parcel_lookup(keys):
    keys=list(dict.fromkeys([k for k in keys if k]))
    rows=[]; errors=[]; source=''
    # County's Opengov parcel layer exposes TMS, TMS_PAD, Long and Lat and polygon geometry.
    for start in range(0,len(keys),60):
        batch=keys[start:start+60]
        quoted=','.join("'"+k.replace("'","''")+"'" for k in batch)
        where=f"TMS IN ({quoted}) OR TMS_PAD IN ({quoted})"
        feats,err=gis_query(PARCEL_PRIMARY,where)
        if err: errors.append(f'Opengov batch {start//60+1}: {err}')
        if feats:
            source='Opengov/MAT Parcels'
            for f in feats:
                a=f.get('attributes',{}).copy(); a['_geom']=f.get('geometry',{})
                a['_source']=source
                a['_matchkey']=normalized_key(a.get('TMS') or a.get('TMS_PAD'))
                rows.append(a)
    # Fallback to the NewPropertyViewer parcel layer if the first layer returns nothing.
    missing=[k for k in keys if not any(r.get('_matchkey')==k for r in rows)]
    for start in range(0,len(missing),60):
        batch=missing[start:start+60]
        quoted=','.join("'"+canonical_tms(k).replace("'","''")+"'" for k in batch)
        where=f"TMS IN ({quoted})"
        feats,err=gis_query(PARCEL_FALLBACK,where)
        if err: errors.append(f'NewPropertyViewer batch {start//60+1}: {err}')
        if feats:
            source='NewPropertyViewer Parcels'
            for f in feats:
                a=f.get('attributes',{}).copy(); a['_geom']=f.get('geometry',{})
                a['_source']=source
                a['_matchkey']=normalized_key(a.get('TMS'))
                rows.append(a)
    return rows,source,errors

def centroid_from_geom(g):
    if not isinstance(g,dict): return None,None
    if g.get('x') is not None and g.get('y') is not None: return float(g['y']),float(g['x'])
    rings=g.get('rings') or []
    pts=[p for ring in rings for p in ring if isinstance(p,(list,tuple)) and len(p)>=2]
    if not pts: return None,None
    return sum(p[1] for p in pts)/len(pts),sum(p[0] for p in pts)/len(pts)

@st.cache_data(ttl=1800,show_spinner=False)
def spatial_enrich(points):
    out={}
    for key,lat,lon in points:
        geom={'x':lon,'y':lat}
        item={}
        for name,url,distance in [('zoning',ZONING,15),('flood',FLOOD,15),('easement',EASE,15),('rivers',RIVERS,100),('lakes',OVERLAYS,100),('sales',SALES,2000)]:
            p={'where':'1=1','outFields':'*','returnGeometry':'false','outSR':'4326','f':'json','geometry':str(geom).replace("'",'"'),'geometryType':'esriGeometryPoint','inSR':'4326','spatialRel':'esriSpatialRelIntersects','distance':distance,'units':'esriSRUnit_Meter'}
            try:
                j=requests.get(url,params=p,timeout=20).json(); item[name]=[f.get('attributes',{}) for f in j.get('features',[])]
            except Exception: item[name]=[]
        out[key]=item
    return out

if 'data' not in st.session_state: st.session_state.data=None
if 'fav' not in st.session_state: st.session_state.fav=set()
if 'notes' not in st.session_state: st.session_state.notes={}

with st.expander('⚙️ Data & county research links'):
    up=st.file_uploader('Upload county 2026 Excel',type=['xlsx','xls'])
    c1,c2=st.columns(2)
    if c1.button('Load official 2026 list',use_container_width=True):
        try:
            with st.spinner('Downloading official 2026 tax-sale list…'): st.session_state.data=get_xlsx()
            st.rerun()
        except Exception as e: st.error(f'Could not load the county spreadsheet: {e}')
    c2.markdown(f'[County tax-sale information]({COUNTY})  •  [ACPASS]({ACPASS})  •  [Property Viewer]({VIEWER})')
if up: st.session_state.data=up.getvalue()

if not st.session_state.data:
    st.info('Load the official 2026 tax-sale spreadsheet to begin.')
    st.stop()

raw=load_sheet(st.session_state.data)
raw.columns=[str(c).strip() for c in raw.columns]
T=find_col(raw,[r'\btms\b',r'tax.?map',r'map.?number'])
O=find_col(raw,[r'current.?owner',r'owner',r'taxpayer'])
A=find_col(raw,[r'property.?description',r'property.?address',r'street',r'location',r'address'])
C=find_col(raw,[r'\bcity\b',r'town'])
B=find_col(raw,[r'amount.?due',r'opening.?bid',r'minimum.?bid',r'open.?bid'])
AV=find_col(raw,[r'assessed',r'market.?value',r'appraised'])
AC=find_col(raw,[r'acre'])
I=find_col(raw,[r'\bitem\b',r'sale.?no'])
TY=find_col(raw,[r'years.?due',r'tax.?year',r'delin'])
PT=find_col(raw,[r'property.?type',r'type',r'mobile'])

df=pd.DataFrame(index=raw.index)
df['TMS']=textcol(raw,T)
df['Item']=textcol(raw,I)
df['Owner']=textcol(raw,O)
df['Address']=textcol(raw,A)
df['City']=textcol(raw,C)
df['Opening Bid']=numcol(raw,B)
df['Assessed']=numcol(raw,AV)
df['Acres']=numcol(raw,AC)
df['Tax Year']=textcol(raw,TY)
df['Type']=textcol(raw,PT)
df['TMS_CANONICAL']=df.TMS.map(canonical_tms)
df['TMS_KEY']=df.TMS_CANONICAL.map(normalized_key)
# If acreage is embedded in the property description, extract it.
missing_acres=df['Acres'].isna()
extracted=df['Address'].str.extract(r'(\d+(?:\.\d+)?)\s*(?:A|AC|ACRES)\b',flags=re.I,expand=False)
df.loc[missing_acres,'Acres']=pd.to_numeric(extracted[missing_acres],errors='coerce')
df['Mobile']=(df.Type+' '+df.Address).str.lower().str.contains(r'mobile|manufactured|mh\b',regex=True)

with st.expander('🔎 GIS diagnostics',expanded=True):
    st.write(f'Tax-sale rows loaded: **{len(df):,}**')
    st.write(f'Rows with canonical TMS: **{df.TMS_CANONICAL.ne("").sum():,}**')
    example=df.loc[df.TMS_CANONICAL.ne(''),'TMS_CANONICAL'].iloc[0] if df.TMS_CANONICAL.ne('').any() else 'none'
    st.write(f'Example canonical TMS: **{example}**')
    if example=='045-00-01-008': st.success('TMS conversion check passed: 450001008.0 → 045-00-01-008')

with st.spinner('Matching tax-sale TMS numbers to Anderson County GIS parcels…'):
    pars,source,errors=parcel_lookup(df.TMS_KEY.tolist())

pd_gis=pd.DataFrame([p for p in pars if p.get('_matchkey')])
if len(pd_gis):
    pd_gis=pd_gis.drop_duplicates('_matchkey')
    def gfield(patterns): return find_col(pd_gis,patterns)
    def pick(*names):
        for n in names:
            if n in pd_gis.columns: return n
        return None
    addrcol=pick('PHYS_ADDR') or gfield([r'phys.?addr',r'address'])
    valcol=pick('MRKT_VALUE') or gfield([r'mrkt.?value',r'market.?value'])
    acg=pick('ACRES') or gfield([r'^acres$'])
    latcol=pick('Lat') or pick('LAT')
    loncol=pick('Long') or pick('LON')
    outg=pd.DataFrame({'TMS_KEY':pd_gis['_matchkey']})
    outg['GIS Address']=pd_gis[addrcol] if addrcol else pd.NA
    outg['GIS Market']=pd.to_numeric(pd_gis[valcol],errors='coerce') if valcol else pd.NA
    outg['GIS Acres']=pd.to_numeric(pd_gis[acg],errors='coerce') if acg else pd.NA
    outg['GIS Ratio']=pd_gis['RATIO'] if 'RATIO' in pd_gis.columns else pd.NA
    outg['_lat']=pd.to_numeric(pd_gis[latcol],errors='coerce') if latcol else pd.NA
    outg['_lon']=pd.to_numeric(pd_gis[loncol],errors='coerce') if loncol else pd.NA
    outg['_geom']=pd_gis['_geom']
    outg['_source']=pd_gis['_source']
    df=df.merge(outg.drop_duplicates('TMS_KEY'),on='TMS_KEY',how='left')
else:
    for c in ['GIS Address','GIS Market','GIS Acres','GIS Ratio','_lat','_lon','_geom','_source']: df[c]=pd.NA

with st.expander('📊 GIS match results'):
    matched=df['GIS Market'].notna() | df['_lat'].notna() | df['_geom'].notna()
    st.metric('GIS matched',int(matched.sum()))
    st.write(f'GIS source: **{source or "none"}**')
    if errors: st.warning('GIS request diagnostics: '+' | '.join(errors[:4]))
    if matched.any():
        ex=df.loc[matched,['TMS','TMS_CANONICAL','GIS Address','GIS Market','_lat','_lon']].head(5).copy()
        st.dataframe(ex,use_container_width=True,hide_index=True)
    else:
        st.error('No GIS parcels matched. The app is showing the exact request errors above instead of silently hiding them.')

df['Research Address']=df['Address'].where(df['Address'].str.strip().ne(''),df['GIS Address'].fillna(''))
df['Bid/Assessed']=df['Opening Bid']/df['Assessed'].replace(0,pd.NA)
df['Bid/Market']=df['Opening Bid']/pd.to_numeric(df['GIS Market'],errors='coerce').replace(0,pd.NA)
df['Equity Gap']=pd.to_numeric(df['GIS Market'],errors='coerce')-df['Opening Bid']

with st.expander('🔎 Filters',expanded=True):
    q=st.text_input('Search TMS, owner, address, city, item',placeholder='e.g. 045-00-01-008')
    c1,c2=st.columns(2)
    bmax=int(df['Opening Bid'].max()) if df['Opening Bid'].notna().any() else 0
    br=c1.slider('Opening bid range',0,max(1,bmax),(0,max(1,bmax)))
    rm=c2.number_input('Maximum bid / GIS market (%)',0.,500.,50.,5.)
    c3,c4=st.columns(2)
    ma=c3.number_input('Minimum acres',0.,10000.,0.,.1)
    mx=c4.number_input('Maximum acres',0.,10000.,10000.,.1)
    c5,c6=st.columns(2)
    max_gis=float(pd.to_numeric(df['GIS Market'],errors='coerce').max() or 0)
    minval=c5.number_input('Minimum GIS market value',0.,max(1.,max_gis),0.,1000.)
    typ=c6.selectbox('Property type',['All','Land / real estate','Mobile homes'])

mask=pd.Series(True,index=df.index)
if q:
    s=df.fillna('').astype(str).agg(' | '.join,axis=1).str.lower(); mask &= s.str.contains(re.escape(q.lower()),regex=True,na=False)
mask &= (df['Opening Bid'].between(*br) | df['Opening Bid'].isna())
mask &= df['Acres'].fillna(0).between(ma,mx)
mask &= pd.to_numeric(df['GIS Market'],errors='coerce').fillna(0)>=minval
mask &= ((df['Bid/Market'].fillna(0)*100<=rm)|df['Bid/Market'].isna())
if typ=='Mobile homes': mask &= df.Mobile
if typ=='Land / real estate': mask &= ~df.Mobile
r=df.loc[mask].copy()

# Lightweight automated score.
def txtblob(x): return str(x).lower()
def score(row):
    s=50.; bm=row['Bid/Market']
    if pd.notna(bm): s+=max(-35,min(35,(.25-float(bm))*100))
    elif pd.notna(row['Bid/Assessed']): s+=max(-30,min(30,(.35-float(row['Bid/Assessed']))*70))
    if pd.notna(row['Acres']): s+=min(12,float(row['Acres'])*1.5)
    if row.Mobile: s-=12
    if pd.isna(row['GIS Market']): s-=10
    if row['_geom'] is not pd.NA and isinstance(row['_geom'],dict): s+=3
    return round(max(0,min(100,s)))
def risk_for(row):
    flags=[]
    if pd.isna(row['GIS Market']): flags.append('NO GIS VALUE')
    if pd.isna(row['_lat']) or pd.isna(row['_lon']): flags.append('NO GIS LOCATION')
    if row.Mobile: flags.append('MOBILE')
    return ' / '.join(flags) if flags else 'LOWER AUTOMATED RISK'
r['Deal Score']=r.apply(score,axis=1); r['Risk']=r.apply(risk_for,axis=1); r=r.sort_values(['Deal Score','Bid/Market'],ascending=[False,True])

m1,m2,m3=st.columns(3); m1.metric('Matches',len(r)); m2.metric('GIS matched',int((r['GIS Market'].notna() | r['_lat'].notna()).sum())); m3.metric('With parcel geometry',int(r['_geom'].apply(lambda x:isinstance(x,dict)).sum()))

st.subheader('🏆 Top opportunities')
if len(r)==0: st.warning('No properties match the current filters.')
else:
    for i,idx in enumerate(r.index[:50]):
        row=r.loc[idx]
        bid=f"${row['Opening Bid']:,.0f}" if pd.notna(row['Opening Bid']) else '—'
        val=f"${row['GIS Market']:,.0f}" if pd.notna(row['GIS Market']) else '—'
        acres=f"{row['Acres']:.2f}" if pd.notna(row['Acres']) else '—'
        with st.container(border=True):
            st.markdown(f"**#{i+1}  {row['TMS_CANONICAL'] or row['TMS']}**  ·  **Score {int(row['Deal Score'])}/100**")
            st.markdown(f"{row['Owner'] or 'Unknown owner'}  \n{row['Research Address'] or 'No address listed'}")
            a,b,c=st.columns(3); a.metric('Opening',bid); b.metric('GIS value',val); c.metric('Acres',acres)
            st.caption(f"Risk: {row['Risk']}")

st.subheader('📍 Research a property')
if len(r):
    idx=st.selectbox('Choose property',r.index.tolist(),format_func=lambda i:f"{r.loc[i,'TMS_CANONICAL'] or r.loc[i,'TMS']} • {r.loc[i,'Owner']} • {r.loc[i,'Research Address']}")
    row=r.loc[idx]
    st.markdown(f"### {row['TMS_CANONICAL'] or row['TMS']} — {row['Owner'] or 'Unknown owner'}")
    st.write(row['Research Address'] or 'No address listed')
    if pd.notna(row['_lat']) and pd.notna(row['_lon']):
        street=f'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={row._lat},{row._lon}'
        maps=f'https://www.google.com/maps/search/?api=1&query={quote_plus(str(row["Research Address"])+", Anderson County, SC")}'
        a,b=st.columns(2); a.link_button('🚗 Street View',street,use_container_width=True); b.link_button('🗺️ Google Maps',maps,use_container_width=True)
    a,b=st.columns(2); a.link_button('🏛️ County Property Viewer',VIEWER,use_container_width=True); b.link_button('📑 ACPASS',ACPASS,use_container_width=True)
    st.markdown(f"**GIS source:** {row['_source'] if pd.notna(row['_source']) else 'none'}")
    if isinstance(row['_geom'],dict):
        st.success('County parcel boundary matched.')
    else: st.warning('No county parcel boundary for this TMS.')

st.divider()
st.subheader('💰 Maximum Bid Calculator')
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
    recs=[]
    for i,prop in r.iterrows():
        value=pd.to_numeric(prop['GIS Market'],errors='coerce')
        if pd.isna(value) or value<=0: value=pd.to_numeric(prop['Assessed'],errors='coerce')
        if pd.isna(value) or value<=0: recs.append([i,None,None,'PASS — insufficient value data']); continue
        risk=float(risk_reserve_pct)
        if pd.isna(prop['_lat']): risk+=5
        if prop.Mobile: risk+=5
        value=float(value); tx=value*float(transaction_cost_pct)/100
        maximum=max(0.,min(value-float(repair_budget)-float(holding_cost)-value*risk/100-tx-float(target_margin),value*float(max_ltv_pct)/100))
        opening=float(prop['Opening Bid']) if pd.notna(prop['Opening Bid']) else 0
        if maximum<opening: rec='PASS — opening bid exceeds model maximum'
        elif maximum<opening*1.10: rec='CAUTION — little bidding room'
        elif maximum>=opening*1.50: rec='STRONG — substantial bidding room'
        else: rec='BID — within model'
        recs.append([i,value,maximum,rec])
    bid_df=pd.DataFrame(recs,columns=['_idx','Estimated Value','Maximum Bid','Bid Recommendation']).set_index('_idx')
    res=r.join(bid_df)
    sel=st.selectbox('Detailed maximum-bid calculation',res.index.tolist(),format_func=lambda i:f"{res.loc[i,'TMS_CANONICAL'] or res.loc[i,'TMS']} • Max ${res.loc[i,'Maximum Bid']:,.0f}" if pd.notna(res.loc[i,'Maximum Bid']) else f"{res.loc[i,'TMS_CANONICAL']} • insufficient value")
    rb=res.loc[sel]
    if pd.notna(rb['Maximum Bid']):
        st.info(f"${rb['Estimated Value']:,.0f} estimated value − ${repair_budget:,.0f} repairs − ${holding_cost:,.0f} holding − risk reserve − transaction reserve − ${target_margin:,.0f} desired margin = **${rb['Maximum Bid']:,.0f} max bid**.")

out=r.copy(); out['Favorite']=False; out['Notes']=''
st.download_button('📥 Download ranked shortlist CSV',out.to_csv(index=False).encode('utf-8-sig'),'anderson_2026_ranked_shortlist_v7.csv','text/csv',use_container_width=True)
st.caption('Screening signals must be independently verified before bidding. Tax-sale properties are sold as-is/where-is.')
