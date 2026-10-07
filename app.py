import io,re,requests,json,html
from urllib.parse import quote_plus
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
st.caption('2026 tax-sale screening • Google Maps + direct Anderson County GIS parcel links • v9.5')

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

def county_viewer_url(tms):
    key=normalized_key(tms)
    return f'https://propertyviewer.andersoncountysc.org/mapsjs/?TMS={quote_plus(key)}&disclaimer=false' if key else 'https://propertyviewer.andersoncountysc.org/mapsjs/?disclaimer=false'

def google_map(rows, api_key):

    payload=[]
    for idx,row in rows.iterrows():
        tms=str(row.get('TMS_CANONICAL') or '').strip()
        if not tms: continue
        payload.append({
            'idx':int(idx), 'tms':tms, 'key':normalized_key(tms),
            'owner':str(row.get('Owner') or ''),
            'address':str(row.get('Research Address') or row.get('Address') or ''),
            'bid':None if pd.isna(row.get('Opening Bid')) else float(row.get('Opening Bid')),
            'acres':None if pd.isna(row.get('Acres')) else float(row.get('Acres')),
        })
    data_json=json.dumps(payload,ensure_ascii=False).replace('</','<\\/')
    ssap_url='https://propertyviewer.andersoncountysc.org/arcgis/rest/services/Opengov/MAT/MapServer/0/query'
    viewer_url='https://propertyviewer.andersoncountysc.org/'
    if not api_key:
        st.warning('Enter a Google Maps demo key to display the interactive property points. The county and Google Maps links below still work without it.')
        return
    html_doc = r'''<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body,#map{height:100%;margin:0;font-family:system-ui,-apple-system,sans-serif}#map{min-height:620px;background:#eef2f5}.prop{padding:10px 4px;border-top:1px solid #ddd}.prop a{font-weight:600}#links{padding:12px;background:#fff;max-height:500px;overflow:auto}#status{position:absolute;z-index:5;left:12px;top:12px;background:white;padding:9px 12px;border-radius:10px;box-shadow:0 2px 12px #0002;font-size:14px;max-width:84%}.good{color:#087f23}.bad{color:#a40000}.legend{position:absolute;z-index:5;right:12px;top:12px;background:#fff;padding:8px 10px;border-radius:10px;box-shadow:0 2px 12px #0002;font-size:13px}.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px}.land{background:#2e7d32}.house{background:#c62828}.improved{background:#ef6c00}.unknown{background:#757575}</style></head><body>
<div id="map"></div><div id="status">Loading county parcel points...</div><div style="position:absolute;z-index:5;left:12px;bottom:12px;background:white;padding:8px 10px;border-radius:10px;box-shadow:0 2px 12px #0002;font-size:13px"><label for="improvementFilter"><b>Map points:</b></label> <select id="improvementFilter"><option value="all">All</option><option value="land">Land only</option><option value="improved">County-improved</option><option value="house">House clue</option></select></div><div class="legend"><div><span class="dot land"></span>Land only</div><div><span class="dot house"></span>House clue</div><div><span class="dot improved"></span>County-improved</div></div>
<script>window.TAXSALE={data:__DATA__,ssap:__SSAP__,viewer:__VIEWER__};</script>
<script>
const S=window.TAXSALE; let map,info,markers=[],locatedPoints=[]; const byKey=new Map(S.data.map(x=>[x.key,x]));
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function key(x){return String(x??'').replace(/[^0-9]/g,'');}
function countyUrl(tms){return 'https://propertyviewer.andersoncountysc.org/mapsjs/?TMS='+encodeURIComponent(key(tms))+'&disclaimer=false';}
function googleUrl(x,p){return 'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent((x.address||'')+', Anderson County, SC');}
function streetUrl(x,p){return 'https://www.google.com/maps/@?api=1&map_action=pano&query='+encodeURIComponent((x.address||'')+', Anderson County, SC');}
function improvementLabel(p){const v=String(p.IMPRV??'').trim(); return v ? 'County-improved (IMPRV '+esc(v)+')' : 'Land only / no IMPRV';}
function popup(x,p){return `<div style="min-width:240px"><b>${esc(x.tms||p.TMS||'')}</b><br><b>${esc(x.owner||'')}</b><br>${esc(x.address||'')}<hr style="border:0;border-top:1px solid #ddd"><b>County status:</b> ${improvementLabel(p)}<br><b>Opening bid:</b> ${x.bid==null?'—':'$'+Number(x.bid).toLocaleString()}<br><b>Acres:</b> ${x.acres==null?'—':Number(x.acres).toFixed(2)}<br><br><a target="_blank" href="${googleUrl(x,p)}">🗺️ Google Maps</a><br><a target="_blank" href="${streetUrl(x,p)}">📍 Street View</a><br><a target="_blank" href="${countyUrl(x.tms||p.TMS)}">🏛️ Anderson County parcel</a></div>`;}
function jsonp(url,timeout=25000){return new Promise((resolve,reject)=>{const cb='ssap_cb_'+Date.now()+'_'+Math.floor(Math.random()*1000000);const script=document.createElement('script');let done=false;const timer=setTimeout(()=>{if(done)return;done=true;cleanup();reject(new Error('County coordinate request timed out.'));},timeout);function cleanup(){clearTimeout(timer);delete window[cb];script.remove();}window[cb]=data=>{if(done)return;done=true;cleanup();if(data&&data.error)reject(new Error(data.error.message||'County GIS returned an error.'));else resolve(data);};script.onerror=()=>{if(done)return;done=true;cleanup();reject(new Error('County GIS blocked the browser request.'));};script.src=url+(url.includes('?')?'&':'?')+'callback='+cb;document.head.appendChild(script);});}
async function getAllCountyPoints(){const fields='TMS,TMS_PAD,TMS_PZ,Long,Lat,IMPRV';const u=S.ssap+'?where=1%3D1&outFields='+encodeURIComponent(fields)+'&returnGeometry=false&resultRecordCount=2000&f=json';const j=await jsonp(u);return j.features||[];}
function addMarker(x,p){if(p.Lat==null||p.Long==null)return false;const pos={lat:Number(p.Lat),lng:Number(p.Long)};if(!map)return true;const improved=String(p.IMPRV??'').trim()!=='';const house=/\b(HOUSE|RESIDENCE|DWELLING|HOME)\b/.test(String(x.address||'').toUpperCase());const m=new google.maps.Marker({map,position:pos,title:`${x.tms} • ${house?'House clue':(improved?'County improved':'Land only')}`,icon:{path:google.maps.SymbolPath.CIRCLE,scale:7,fillColor:house?'#c62828':(improved?'#ef6c00':'#2e7d32'),fillOpacity:0.95,strokeColor:'#fff',strokeWeight:1}});m.addListener('click',()=>{info.setContent(popup(x,p));info.open({map,anchor:m});});markers.push(m);return true;}
function matchFeatures(features){const out=[];const seen=new Set();for(const f of features){const p=f.attributes||{};const x=byKey.get(key(p.TMS_PAD))||byKey.get(key(p.TMS_PZ))||byKey.get(key(p.TMS));if(!x||p.Lat==null||p.Long==null||seen.has(x.key))continue;seen.add(x.key);out.push({x,p});}return out;}
function showLinks(located){const panel=document.getElementById('links');panel.innerHTML='<b>Located tax-sale parcels</b><div style="font-size:13px;color:#666;margin:5px 0 10px">Green = no county IMPRV value. Orange = county IMPRV value. IMPRV is an improvement indicator; it is not by itself proof that the improvement is a house.</div>'+located.slice(0,100).map(({x,p})=>`<div class="prop"><b>${esc(x.tms)}</b> — ${esc(x.owner)}<br>${esc(x.address||'')}<br><b>${improvementLabel(p)}</b><br><a target="_blank" href="${googleUrl(x,p)}">🗺️ Google Maps</a> &nbsp; <a target="_blank" href="${streetUrl(x,p)}">📍 Street View</a> &nbsp; <a target="_blank" href="${countyUrl(x.tms)}">🏛️ County</a></div>`).join('');}
async function start(){try{const features=await getAllCountyPoints();locatedPoints=matchFeatures(features);showLinks(locatedPoints);renderMarkers();const improved=locatedPoints.filter(q=>String(q.p.IMPRV??'').trim()!=='').length;document.getElementById('status').innerHTML=`<span class="good"><b>${locatedPoints.length}</b> of <b>${S.data.length}</b> tax-sale parcels located • <b>${improved}</b> with county IMPRV`;}catch(e){document.getElementById('status').innerHTML=`<span class="bad"><b>County coordinate lookup failed.</b></span><br>${esc(e.message)}<br><a href="${S.viewer}" target="_blank">Open Anderson County Property Viewer</a>`;}}
function renderMarkers(){if(!map||!locatedPoints.length)return;markers.forEach(m=>m.setMap(null));markers=[];const bounds=new google.maps.LatLngBounds();const mode=document.getElementById('improvementFilter')?.value||'all';locatedPoints.forEach(({x,p})=>{const improved=String(p.IMPRV??'').trim()!=='';const desc=String(x.address||'').toUpperCase();const house=/\b(HOUSE|RESIDENCE|DWELLING|HOME)\b/.test(desc);if(mode==='land'&&improved)return;if(mode==='improved'&&!improved)return;if(mode==='house'&&!house)return;if(addMarker(x,p))bounds.extend({lat:Number(p.Lat),lng:Number(p.Long)});});if(!bounds.isEmpty()){map.fitBounds(bounds);if(map.getZoom()>14)map.setZoom(14);}}
function initMap(){map=new google.maps.Map(document.getElementById('map'),{center:{lat:34.5034,lng:-82.6501},zoom:10,mapTypeControl:true,streetViewControl:true,fullscreenControl:true,gestureHandling:'greedy'});info=new google.maps.InfoWindow();document.getElementById('improvementFilter').addEventListener('change',renderMarkers);start();}
window.gm_authFailure=function(){document.getElementById('status').innerHTML='<span class="bad"><b>Google Maps could not authenticate this key.</b></span>';};
</script><script async src="https://maps.googleapis.com/maps/api/js?key=__KEY__&loading=async&callback=initMap"></script>
</body></html>'''
    html_doc=html_doc.replace('__DATA__',data_json).replace('__SSAP__',json.dumps(ssap_url)).replace('__VIEWER__',json.dumps(viewer_url)).replace('__KEY__',html.escape(str(api_key),quote=True))
    components.html(html_doc,height=680,scrolling=False)

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
# Prefer an explicit acreage printed in the property description.
# This preserves leading decimals such as '.73 AC' as 0.73 rather than 73.
extracted=df['Address'].astype(str).str.extract(
    r'(?<![0-9])((?:0?\.[0-9]+|[0-9]+(?:\.[0-9]+)?))\s+(?:A|AC|ACRES)\b',
    flags=re.I, expand=False
)
explicit_acres=pd.to_numeric(extracted,errors='coerce')
df.loc[explicit_acres.notna(),'Acres']=explicit_acres[explicit_acres.notna()]
df['Mobile']=(df.Type+' '+df.Address).str.lower().str.contains(r'mobile|manufactured|mh\b',regex=True)

with st.expander('🔎 GIS diagnostics',expanded=True):
    st.write(f'Tax-sale rows loaded: **{len(df):,}**')
    st.write(f'Rows with canonical TMS: **{df.TMS_CANONICAL.ne("").sum():,}**')
    examples=df.loc[df.TMS_CANONICAL.ne(''),'TMS_CANONICAL'].head(3).tolist()
    st.write('Example canonical TMS: **'+(', '.join(examples) if examples else 'none')+'**')
    st.success('Spreadsheet/TMS parsing is working. County parcel research now opens directly in the official viewer using the property TMS; no manual disclaimer click is required.')

# GIS values are intentionally browser-side in v8. Keep columns so the ranking/filter UI remains stable.
for c in ['GIS Address','GIS Market','GIS Acres','GIS Ratio','IMPRV','County Status','_lat','_lon','_geom','_source']:
    df[c]=pd.NA

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
    c5.info('The map uses Anderson County GPS points and its parcel IMPRV indicator. Orange points have a county improvement value; green points have none. IMPRV is not by itself proof of a house.')
    minval=0
    typ=c6.selectbox('Property type clue',['All','Land / no house clue','House indicated','Mobile homes'])
    c7,c8=st.columns(2)
    c8.checkbox('Show only 5+ acres',value=False,key='five_plus')

mask=pd.Series(True,index=df.index)
if q:
    s=df.fillna('').astype(str).agg(' | '.join,axis=1).str.lower(); mask &= s.str.contains(re.escape(q.lower()),regex=True,na=False)
mask &= (df['Opening Bid'].between(*br) | df['Opening Bid'].isna())
mask &= df['Acres'].fillna(0).between(ma,mx)
mask &= (pd.to_numeric(df['GIS Market'],errors='coerce').fillna(0)>=minval) | df['GIS Market'].isna()
mask &= ((df['Bid/Market'].fillna(0)*100<=rm)|df['Bid/Market'].isna())
house_clue=df['Address'].astype(str).str.upper().str.contains(r'\b(HOUSE|RESIDENCE|DWELLING|HOME)\b',regex=True,na=False)
if typ=='Mobile homes': mask &= df.Mobile
if typ=='House indicated': mask &= house_clue
if typ=='Land / no house clue': mask &= (~df.Mobile) & (~house_clue)
if st.session_state.get('five_plus',False): mask &= df['Acres'].fillna(0)>=5
r=df.loc[mask].copy()

# Lightweight automated score.
def txtblob(x): return str(x).lower()
def score(row):
    s=50.; bm=row['Bid/Market']
    if pd.notna(bm): s+=max(-35,min(35,(.25-float(bm))*100))
    elif pd.notna(row['Bid/Assessed']): s+=max(-30,min(30,(.35-float(row['Bid/Assessed']))*70))
    if pd.notna(row['Acres']): s+=min(12,float(row['Acres'])*1.5)
    if row.Mobile: s-=12
    if row['_geom'] is not pd.NA and isinstance(row['_geom'],dict): s+=3
    return round(max(0,min(100,s)))
def risk_for(row):
    flags=[]
    if row.Mobile: flags.append('MOBILE')
    return ' / '.join(flags) if flags else 'LOWER AUTOMATED RISK'
r['Deal Score']=r.apply(score,axis=1); r['Risk']=r.apply(risk_for,axis=1); r=r.sort_values(['Deal Score','Bid/Market'],ascending=[False,True])

m1,m2,m3=st.columns(3); m1.metric('Matches',len(r)); m2.metric('GIS mode','Browser'); m3.metric('Tax-sale parcels',len(r))

st.subheader('🗺️ Google Maps')
st.caption('Google Maps is optional for the regional view. Exact parcel boundaries and parcel details open directly in the official Anderson County Property Viewer, using the TMS and bypassing the disclaimer screen.')
with st.expander('🔑 Optional Google Maps demo key',expanded=False):
    st.write("The embedded map is only a visual convenience. You do not need a Google Maps key to research individual parcels.")
    st.markdown('[Google Maps JavaScript API key information](https://developers.google.com/maps/documentation/javascript/get-api-key)')
    google_maps_key=st.text_input('Google Maps demo key (optional)',type='password',placeholder='AIza…',help='Used only in this current Streamlit session.')
if len(r): google_map(r.head(200),google_maps_key)

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
            st.caption(f"Risk: {row['Risk']} • Type clue: {'Mobile home' if row.Mobile else ('House' if house_clue.get(idx,False) else 'Land/other')}")
            cv=county_viewer_url(row['TMS_CANONICAL'] or row['TMS'])
            addr=str(row['Research Address']).strip()
            gm=f'https://www.google.com/maps/search/?api=1&query={quote_plus((addr if addr else (row["TMS_CANONICAL"] or row["TMS"]))+", Anderson County, SC")}'
            c1,c2=st.columns(2); c1.link_button('🏛️ Exact County Parcel',cv,use_container_width=True); c2.link_button('🗺️ Google Maps',gm,use_container_width=True)

st.subheader('📍 Research a property')
if len(r):
    idx=st.selectbox('Choose property',r.index.tolist(),format_func=lambda i:f"{r.loc[i,'TMS_CANONICAL'] or r.loc[i,'TMS']} • {r.loc[i,'Owner']} • {r.loc[i,'Research Address']}")
    row=r.loc[idx]
    st.markdown(f"### {row['TMS_CANONICAL'] or row['TMS']} — {row['Owner'] or 'Unknown owner'}")
    st.write(row['Research Address'] or 'No address listed')
    st.success('The County Parcel button opens the official parcel directly with the TMS and skips the manual disclaimer checkbox.')
    if str(row['Research Address']).strip():
        maps=f'https://www.google.com/maps/search/?api=1&query={quote_plus(str(row["Research Address"])+", Anderson County, SC")}'
        a,b=st.columns(2); b.link_button('🗺️ Google Maps',maps,use_container_width=True)
    a,b=st.columns(2); a.link_button('🏛️ Exact County Parcel',county_viewer_url(row['TMS_CANONICAL'] or row['TMS']),use_container_width=True); b.link_button('📑 ACPASS',ACPASS,use_container_width=True)
    st.markdown('**GIS:** browser-connected county parcel map above')
    st.info('Parcel boundary and county GIS value are displayed in the browser GIS map above.')

    st.markdown('### 🕯️ Obituary / deceased-owner cross-check')
    owner=str(row['Owner'] or '').strip()
    owner_upper=owner.upper()
    non_person_terms=['LLC','L.L.C','INC','INC.','CORP','CORPORATION','LP','L.P','LLP','L.L.P','TRUST','TRUSTEE','ESTATE','HEIRS','ET AL','CHURCH','MINISTRIES','ASSOCIATION','BANK','COUNTY OF','CITY OF','UNIVERSITY','SCHOOL','COMPANY','CO.']
    looks_like_entity=any(t in owner_upper for t in non_person_terms)
    if not owner:
        st.info('No owner name is available for an obituary search.')
    elif looks_like_entity:
        st.info('This owner appears to be an entity, trust, estate, or organization rather than an individual. An obituary search is usually not meaningful; investigate the entity/estate records instead.')
    else:
        # We intentionally make this an on-demand browser search rather than scraping obituary sites.
        # Obituary indexes are incomplete, and several sources prohibit automated scraping.
        qname=quote_plus(f'"{owner}" Anderson South Carolina obituary')
        qlegacy=quote_plus(f'"{owner}" Anderson SC obituary')
        qe=quote_plus(f'"{owner}" Anderson SC death obituary')
        a,b,c=st.columns(3)
        a.link_button('🔎 Search Legacy',f'https://www.google.com/search?q=site%3Alegacy.com+{qlegacy}',use_container_width=True)
        b.link_button('🔎 Search Echovita',f'https://www.google.com/search?q=site%3Aechovita.com+{qe}',use_container_width=True)
        c.link_button('🔎 Search local web',f'https://www.google.com/search?q={qname}',use_container_width=True)
        a,b=st.columns(2)
        a.link_button('📚 Anderson Library obituary index','https://www.andersonlibrary.org/local-history-genealogy/obituary-index',use_container_width=True)
        b.link_button('📰 Anderson obituaries on Legacy','https://www.legacy.com/us/obituaries/local/south-carolina/anderson',use_container_width=True)
        st.caption('How to interpret results: **Likely deceased** only when the obituary clearly matches the owner’s identity. **No obituary found** does not mean the owner is alive. Verify the person using age, relatives, city, property address, and county/probate records before relying on this flag.')

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
st.download_button('📥 Download ranked shortlist CSV',out.to_csv(index=False).encode('utf-8-sig'),'anderson_2026_ranked_shortlist_v9.csv','text/csv',use_container_width=True)
st.caption('Screening signals must be independently verified before bidding. Tax-sale properties are sold as-is/where-is.')
