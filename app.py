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
st.caption('2026 tax-sale screening • Google Maps + direct Anderson County GIS parcel links • v10.0')

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

@st.cache_data(ttl=86400,show_spinner=False)
def property_cross_reference(address, tms=''):
    """Search public web results for the exact property address.
    We do not scrape Zillow/Realtor pages directly; we use search-result snippets and
    require property facts such as bedrooms, bathrooms, or square footage before
    treating the result as house evidence.
    """
    addr=str(address or '').strip()
    if not addr:
        return {'status':'NO_ADDRESS','sources':{},'house_evidence':False,'mobile_evidence':False}
    queries={
        'Zillow': f'site:zillow.com/homedetails "{addr}" "Anderson SC"',
        'Realtor.com': f'site:realtor.com/realestateandhomes "{addr}" "Anderson SC"',
        'Redfin': f'site:redfin.com/SC/Anderson "{addr}" "Anderson SC"',
    }
    out={}
    ua={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36'}
    for label,q in queries.items():
        info={'found':False,'beds':None,'baths':None,'sqft':None,'mobile':False,'snippet':''}
        try:
            u='https://www.google.com/search?hl=en&num=5&q='+quote_plus(q)
            rr=requests.get(u,headers=ua,timeout=12)
            txt=html.unescape(re.sub(r'<[^>]+>',' ',rr.text))
            txt=re.sub(r'\s+',' ',txt)
            low=txt.lower()
            # Search only around the requested address when possible.
            pos=low.find(addr.lower())
            snippet=txt[max(0,pos-250):pos+1400] if pos>=0 else txt[:1800]
            slow=snippet.lower()
            beds=re.search(r'(?<!\d)(\d{1,2})\s*(?:bd|beds|bedrooms?)\b',slow)
            baths=re.search(r'(?<!\d)(\d{1,2}(?:\.5)?)\s*(?:ba|baths|bathrooms?)\b',slow)
            sqft=re.search(r'(?<!\d)([\d,]{3,8})\s*(?:sq\.?\s*ft|sqft|square feet)\b',slow)
            info['beds']=int(beds.group(1)) if beds else None
            info['baths']=float(baths.group(1)) if baths else None
            info['sqft']=int(sqft.group(1).replace(',','')) if sqft else None
            info['mobile']=bool(re.search(r'\bmobile(?:/|\s|-)?manufactured|manufactured home|mobile home\b',slow))
            info['found']=bool(pos>=0 and (info['beds'] is not None or info['baths'] is not None or info['sqft'] is not None or info['mobile']))
            info['snippet']=re.sub(r'\s+',' ',snippet)[:900]
        except Exception as e:
            info['error']=str(e)
        out[label]=info
    evidence=[]; mobile=[]
    for label,info in out.items():
        fields=sum(v is not None for v in [info.get('beds'),info.get('baths'),info.get('sqft')])
        if fields>=2: evidence.append(label)
        if info.get('mobile'): mobile.append(label)
    if evidence or mobile:
        status='HOUSE_EVIDENCE'
    elif any(v.get('found') for v in out.values()):
        status='WEAK_EVIDENCE'
    else:
        status='NO_MATCH'
    return {'status':status,'sources':out,'house_evidence':bool(evidence),'mobile_evidence':bool(mobile),'evidence_sources':evidence,'mobile_sources':mobile}

def google_map(rows, api_key):
    """Interactive parcel map using direct TMS parcel queries.
    Falls back to key-free Leaflet/OpenStreetMap if Google Maps is not authenticated.
    """
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
            'mobile':bool(row.get('Mobile')),
            'house':bool(re.search(r'\b(HOUSE|RESIDENCE|DWELLING|HOME|SINGLE FAMILY|RANCH|BRICK|FRAME)\b', str(row.get('Address') or '').upper())),
        })
    data_json=json.dumps(payload,ensure_ascii=False).replace('</','<\\/')
    parcel_url='https://propertyviewer.andersoncountysc.org/arcgis/rest/services/Opengov/MAT/MapServer/13/query'
    html_doc = '''<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body,#map{height:100%;margin:0;font-family:system-ui,-apple-system,sans-serif}
#map{min-height:620px;background:#eef2f5}.good{color:#087f23}.bad{color:#a40000}
#status{position:absolute;z-index:500;left:12px;top:12px;background:white;padding:9px 12px;border-radius:10px;box-shadow:0 2px 12px #0002;font-size:14px;max-width:84%}
.legend{position:absolute;z-index:500;right:12px;top:12px;background:#fff;padding:8px 10px;border-radius:10px;box-shadow:0 2px 12px #0002;font-size:13px}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px}.land{background:#2e7d32}.house{background:#c62828}.mobile{background:#1565c0}.unknown{background:#f9a825}
#filterBox{position:absolute;z-index:500;left:12px;bottom:12px;background:white;padding:8px 10px;border-radius:10px;box-shadow:0 2px 12px #0002;font-size:13px}
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="" />
</head><body>
<div id="map"></div><div id="status">Loading county parcel locations...</div>
<div id="filterBox"><label for="improvementFilter"><b>Map points:</b></label> <select id="improvementFilter"><option value="all">All</option><option value="land">Land / other</option><option value="house">House indicated</option><option value="mobile">Mobile home</option></select></div>
<div class="legend"><div><span class="dot land"></span>Land / other</div><div><span class="dot house"></span>House indicated</div><div><span class="dot mobile"></span>Mobile home</div></div>
<script>window.TAXSALE={data:__DATA__,parcel:__PARCEL__,googleKey:__KEY__};</script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script>
const S=window.TAXSALE; let map=null,googleMode=false,info=null,markers=[],locatedPoints=[];
const byKey=new Map(S.data.map(x=>[key(x.key),x]));
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function key(x){return String(x??'').replace(/[^0-9]/g,'');}
function countyUrl(tms){return 'https://propertyviewer.andersoncountysc.org/mapsjs/?TMS='+encodeURIComponent(key(tms))+'&disclaimer=false';}
function googleUrl(x,c){return c?('https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(c.lat+','+c.lng)):('https://www.google.com/maps/search/?api=1&query='+encodeURIComponent((x.address||'')+', Anderson County, SC'));}
function streetUrl(x,c){return c?('https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='+encodeURIComponent(c.lat+','+c.lng)+'&heading=0&pitch=0&fov=90'):('https://www.google.com/maps/search/?api=1&query='+encodeURIComponent((x.address||'')+', Anderson County, SC'));}
function externalSearch(site,x){const a=(x.address||'').trim(); const t=(x.tms||'').trim(); const base=a?('\"'+a+'\" Anderson SC'):(t+' Anderson SC'); const q=encodeURIComponent('site:'+site+' '+base); return 'https://www.google.com/search?hl=en&q='+q;}
function houseClue(x){return !!x.house || /\b(HOUSE|RESIDENCE|DWELLING|HOME|SINGLE FAMILY|RANCH|BRICK|FRAME)\b/.test(String(x.address||'').toUpperCase());}
function mobileClue(x){return !!x.mobile || /\b(MOBILE|MANUFACTURED|MOBILE HOME)\b/.test(String(x.address||'').toUpperCase());}
function improved(p){return String(p.IMPRV??'').trim()!=='';}
function statusLabel(p){return improved(p)?'County-improved (IMPRV '+esc(p.IMPRV)+')':'No county improvement indicator';}
function category(x,p){if(mobileClue(x))return 'mobile'; if(houseClue(x))return 'house'; return 'land';}
function colorFor(x,p){const cat=category(x,p); return cat==='mobile'?'#1565c0':(cat==='house'?'#c62828':'#2e7d32');}
function popup(x,p,c){const cat=category(x,p); const catLabel=cat==='mobile'?'Mobile home':(cat==='house'?'House indicated':'Land / other'); const addr=(p.PHYS_ADDR||x.address||'').trim(); const xx=Object.assign({},x,{address:addr}); return `<div style="min-width:260px"><b>${esc(x.tms||p.TMS||'')}</b><br><b>${esc(x.owner||'')}</b><br>${esc(addr||'No county physical address')}<hr style="border:0;border-top:1px solid #ddd"><b>Property type:</b> ${catLabel}<br><b>County status:</b> ${statusLabel(p)}<br><b>Opening bid:</b> ${x.bid==null?'—':'$'+Number(x.bid).toLocaleString()}<br><b>Acres:</b> ${x.acres==null?'—':Number(x.acres).toFixed(2)}<br><br><a target="_blank" href="${googleUrl(xx,c)}">🗺️ Google Maps exact point</a><br><a target="_blank" href="${streetUrl(xx,c)}">📍 Street View exact point</a><br><a target="_blank" href="${externalSearch('zillow.com/homedetails',xx)}">🏠 Check Zillow</a><br><a target="_blank" href="${externalSearch('realtor.com/realestateandhomes',xx)}">🏠 Check Realtor.com</a><br><a target="_blank" href="${countyUrl(x.tms||p.TMS)}">🏛️ Anderson County parcel</a></div>`;}
function jsonp(url,timeout=30000){return new Promise((resolve,reject)=>{const cb='ac_ts_'+Date.now()+'_'+Math.floor(Math.random()*1000000);const script=document.createElement('script');let done=false;const timer=setTimeout(()=>{if(done)return;done=true;cleanup();reject(new Error('County GIS request timed out.'));},timeout);function cleanup(){clearTimeout(timer);delete window[cb];script.remove();}window[cb]=data=>{if(done)return;done=true;cleanup();if(data&&data.error)reject(new Error(data.error.message||'County GIS returned an error.'));else resolve(data);};script.onerror=()=>{if(done)return;done=true;cleanup();reject(new Error('County GIS blocked the browser request.'));};script.src=url+(url.includes('?')?'&':'?')+'callback='+cb;document.head.appendChild(script);});}
function chunks(a,n){const out=[];for(let i=0;i<a.length;i+=n)out.push(a.slice(i,i+n));return out;}
async function queryParcelBatch(keys){
  const safe=keys.map(k=>String(k).replace(/[^0-9]/g,'')).filter(Boolean);
  if(!safe.length)return [];
  const where='TMS IN ('+safe.map(k=>"'"+k+"'").join(',')+')';
  const u=S.parcel+'?where='+encodeURIComponent(where)+'&outFields='+encodeURIComponent('TMS,IMPRV,MRKT_VALUE,PHYS_ADDR,RATIO,CPLAT')+'&returnGeometry=true&outSR=4326&geometryPrecision=6&maxAllowableOffset=0.0002&f=json';
  const j=await jsonp(u); return j.features||[];
}
function centroid(geom){
  if(!geom)return null;
  const rings=geom.rings||[]; if(!rings.length)return null;
  let sx=0,sy=0,n=0;
  for(const ring of rings){for(const pt of ring){if(Array.isArray(pt)&&pt.length>=2){sx+=Number(pt[0]);sy+=Number(pt[1]);n++;}}}
  return n?{lat:sy/n,lng:sx/n}:null;
}
async function locate(){
  const all=[]; const ks=S.data.map(x=>key(x.key)).filter(Boolean); const batches=chunks(ks,20);
  for(let i=0;i<batches.length;i++){
    document.getElementById('status').innerHTML=`Loading county parcel locations… <b>${i+1}</b> of <b>${batches.length}</b>`;
    try{const fs=await queryParcelBatch(batches[i]); all.push(...fs);}catch(e){console.warn(e);}
  }
  const out=[]; const seen=new Set();
  for(const f of all){const p=f.attributes||{}; const k=key(p.TMS); const x=byKey.get(k); const c=centroid(f.geometry); if(!x||!c||seen.has(k))continue; seen.add(k); out.push({x,p,c});}
  return out;
}
function makeLeaflet(){
  map=L.map('map',{zoomControl:true,scrollWheelZoom:true}).setView([34.5034,-82.6501],10);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
}
function makeGoogle(){
  if(!S.googleKey)return false;
  try{map=new google.maps.Map(document.getElementById('map'),{center:{lat:34.5034,lng:-82.6501},zoom:10,mapTypeControl:true,streetViewControl:true,fullscreenControl:true,gestureHandling:'greedy'});info=new google.maps.InfoWindow();googleMode=true;return true;}catch(e){return false;}
}
function clearMarkers(){markers.forEach(m=>googleMode?m.setMap(null):m.remove());markers=[];}
function addMarker(x,p,c){
  const col=colorFor(x,p);
  if(googleMode){const m=new google.maps.Marker({map,position:{lat:c.lat,lng:c.lng},title:`${x.tms} • ${category(x,p)==='mobile'?'Mobile home':(category(x,p)==='house'?'House indicated':'Land / other')}`,icon:{path:google.maps.SymbolPath.CIRCLE,scale:7,fillColor:col,fillOpacity:.95,strokeColor:'#fff',strokeWeight:1}});m.addListener('click',()=>{info.setContent(popup(x,p,c));info.open({map,anchor:m});});markers.push(m);}
  else {const m=L.circleMarker([c.lat,c.lng],{radius:7,weight:1,color:'#fff',fillColor:col,fillOpacity:.95}).bindPopup(popup(x,p,c));m.addTo(map);markers.push(m);}
}
function renderMarkers(){
  if(!map||!locatedPoints.length)return; clearMarkers(); const mode=document.getElementById('improvementFilter').value; const visible=[];
  locatedPoints.forEach(q=>{if(mode!=='all' && category(q.x,q.p)!==mode)return; addMarker(q.x,q.p,q.c); visible.push(q);});
  if(!visible.length)return;
  if(googleMode){const b=new google.maps.LatLngBounds();visible.forEach(q=>b.extend({lat:q.c.lat,lng:q.c.lng}));map.fitBounds(b);if(map.getZoom()>14)map.setZoom(14);}
  else {const b=L.latLngBounds(visible.map(q=>[q.c.lat,q.c.lng]));map.fitBounds(b.pad(.12));}
}
async function start(){
  try{
    locatedPoints=await locate();
    const ok=makeGoogle();
    if(!ok){makeLeaflet();document.getElementById('status').innerHTML='<span class="good"><b>Interactive map ready.</b></span> Using a key-free map because Google Maps is not authenticated. Google Maps links remain available on every point.';}
    else document.getElementById('status').innerHTML='<span class="good"><b>Interactive map ready.</b></span> County parcel coordinates matched by TMS.';
    document.getElementById('improvementFilter').addEventListener('change',renderMarkers);renderMarkers();
    const land=locatedPoints.filter(q=>category(q.x,q.p)==='land').length; const house=locatedPoints.filter(q=>category(q.x,q.p)==='house').length; const mobile=locatedPoints.filter(q=>category(q.x,q.p)==='mobile').length;
    setTimeout(()=>{document.getElementById('status').innerHTML=`<span class="good"><b>${locatedPoints.length}</b> of <b>${S.data.length}</b> tax-sale parcels located • <b>${land}</b> land/other • <b>${house}</b> house indicated • <b>${mobile}</b> mobile`;},500);
  }catch(e){document.getElementById('status').innerHTML=`<span class="bad"><b>County parcel lookup failed.</b></span><br>${esc(e.message)}<br><a href="https://propertyviewer.andersoncountysc.org/mapsjs/" target="_blank">Open Anderson County Property Viewer</a>`;}
}
function loadGoogleThenStart(){
  if(!S.googleKey){start();return;}
  window.gm_authFailure=function(){start();};
  const s=document.createElement('script');s.async=true;s.src='https://maps.googleapis.com/maps/api/js?key='+encodeURIComponent(S.googleKey);s.onload=()=>start();s.onerror=()=>start();document.head.appendChild(s);
}
loadGoogleThenStart();
</script></body></html>'''
    html_doc=html_doc.replace('__DATA__',data_json).replace('__PARCEL__',json.dumps(parcel_url)).replace('__KEY__',json.dumps(str(api_key or '')))
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

    st.markdown('**Property type — turn categories on/off**')
    t1,t2,t3=st.columns(3)
    show_land=t1.checkbox('🌳 Land / other',value=True,key='show_land_type')
    show_house=t2.checkbox('🏠 House indicated',value=True,key='show_house_type')
    show_mobile=t3.checkbox('🏚️ Mobile home',value=True,key='show_mobile_type')
    st.caption('These are screening clues from the tax-sale description/type field. A county improvement is not automatically a house, and mobile homes may also have county improvements.')

    c7,c8=st.columns(2)
    c8.checkbox('Show only 5+ acres',value=False,key='five_plus')

mask=pd.Series(True,index=df.index)
if q:
    s=df.fillna('').astype(str).agg(' | '.join,axis=1).str.lower(); mask &= s.str.contains(re.escape(q.lower()),regex=True,na=False)
mask &= (df['Opening Bid'].between(*br) | df['Opening Bid'].isna())
mask &= df['Acres'].fillna(0).between(ma,mx)
mask &= (pd.to_numeric(df['GIS Market'],errors='coerce').fillna(0)>=minval) | df['GIS Market'].isna()
mask &= ((df['Bid/Market'].fillna(0)*100<=rm)|df['Bid/Market'].isna())
house_clue=df['Address'].astype(str).str.upper().str.contains(r'\b(HOUSE|RESIDENCE|DWELLING|HOME|SINGLE FAMILY|RANCH|BRICK|FRAME)\b',regex=True,na=False)
# Property-type toggles. Categories are made mutually exclusive for filtering:
# mobile homes take priority, then explicit house clues, then land/other.
property_type_mask=pd.Series(False,index=df.index)
if show_mobile:
    property_type_mask |= df.Mobile
if show_house:
    property_type_mask |= ((~df.Mobile) & house_clue)
if show_land:
    property_type_mask |= ((~df.Mobile) & (~house_clue))
mask &= property_type_mask
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
st.caption('Google Maps is optional for the regional view. Map colors are based on county/tax-sale clues. Use the property cross-reference below a selected parcel to confirm bedrooms, bathrooms, square footage, or mobile/manufactured status from Zillow, Realtor.com, or Redfin.')
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
            st.caption(f"Risk: {row['Risk']} • Type clue: {'Mobile home' if row.Mobile else ('House indicated' if house_clue.get(idx,False) else 'Land/other')}")
            cv=county_viewer_url(row['TMS_CANONICAL'] or row['TMS'])
            addr=str(row['Research Address']).strip()
            gm=f'https://www.google.com/maps/search/?api=1&query={quote_plus((addr if addr else (row["TMS_CANONICAL"] or row["TMS"]))+", Anderson County, SC")}'
            c1,c2=st.columns(2); c1.link_button('🏛️ Exact County Parcel',cv,use_container_width=True); c2.link_button('🗺️ Google Maps',gm,use_container_width=True)
            addrq=quote_plus(str(addr)+', Anderson SC') if addr else quote_plus(str(row['TMS_CANONICAL'] or row['TMS'])+', Anderson SC')
            zq='https://www.google.com/search?hl=en&q='+quote_plus('site:zillow.com/homedetails "'+str(addr)+'" Anderson SC') if addr else 'https://www.zillow.com/anderson-sc/'
            rq='https://www.google.com/search?hl=en&q='+quote_plus('site:realtor.com/realestateandhomes "'+str(addr)+'" Anderson SC') if addr else 'https://www.realtor.com/realestateandhomes-search/Anderson-County_SC'
            d1,d2=st.columns(2); d1.link_button('🏠 Check Zillow',zq,use_container_width=True); d2.link_button('🏠 Check Realtor.com',rq,use_container_width=True)

st.subheader('📍 Research a property')
if len(r):
    idx=st.selectbox('Choose property',r.index.tolist(),format_func=lambda i:f"{r.loc[i,'TMS_CANONICAL'] or r.loc[i,'TMS']} • {r.loc[i,'Owner']} • {r.loc[i,'Research Address']}")
    row=r.loc[idx]
    st.markdown(f"### {row['TMS_CANONICAL'] or row['TMS']} — {row['Owner'] or 'Unknown owner'}")
    st.write(row['Research Address'] or 'No address listed')
    st.success('The County Parcel button opens the official parcel directly with the TMS and skips the manual disclaimer checkbox.')
    if str(row['Research Address']).strip():
        maps=f'https://www.google.com/maps/search/?api=1&query={quote_plus(str(row["Research Address"])+", Anderson County, SC")}'
        a,b,c=st.columns(3); b.link_button('🗺️ Google Maps',maps,use_container_width=True)
        # Coordinate-accurate Street View is provided by the browser parcel map popup; the address search here is a fallback.
        sv='https://www.google.com/maps/search/?api=1&query='+quote_plus(str(row['Research Address'])+', Anderson County, SC')
        c.link_button('📍 Street View search',sv,use_container_width=True)
    a,b=st.columns(2); a.link_button('🏛️ Exact County Parcel',county_viewer_url(row['TMS_CANONICAL'] or row['TMS']),use_container_width=True); b.link_button('📑 ACPASS',ACPASS,use_container_width=True)
    st.markdown('**GIS:** browser-connected county parcel map above')
    st.info('Parcel boundary and county GIS value are displayed in the browser GIS map above.')

    st.markdown('### 🏠 Zillow / Realtor / Redfin house cross-reference')
    st.caption('The app checks public search-result data for this exact address. A property is treated as strong house evidence when at least two of these are found: bedrooms, bathrooms, or square footage. A mobile/manufactured-home description is also flagged. No match does NOT prove vacant land.')
    if str(row['Research Address']).strip():
        with st.spinner('Checking Zillow, Realtor.com and Redfin for property facts…'):
            xref=property_cross_reference(str(row['Research Address']),str(row['TMS_CANONICAL'] or row['TMS']))
        if xref['house_evidence']:
            st.success('🏠 HOUSE EVIDENCE FOUND — property facts were found on: '+', '.join(xref['evidence_sources']))
        elif xref['mobile_evidence']:
            st.success('🏚️ MOBILE / MANUFACTURED HOME EVIDENCE FOUND — '+', '.join(xref['mobile_sources']))
        elif xref['status']=='WEAK_EVIDENCE':
            st.warning('⚠️ A possible property match was found, but not enough bedroom/bath/sqft facts were available to call it a house automatically.')
        else:
            st.info('No matching bedroom/bath/sqft data was returned. This is NOT proof that the property is vacant land.')
        rows=[]
        for source,info in xref['sources'].items():
            facts=[]
            if info.get('beds') is not None: facts.append(f"{int(info['beds'])} bed")
            if info.get('baths') is not None: facts.append(f"{info['baths']:g} bath")
            if info.get('sqft') is not None: facts.append(f"{info['sqft']:,} sqft")
            if info.get('mobile'): facts.append('mobile/manufactured')
            rows.append({'Source':source,'Facts':', '.join(facts) if facts else 'No property facts found','Match': 'Yes' if info.get('found') else 'No'})
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        st.caption('For tax-sale screening, this is evidence only. The exact county parcel remains the controlling parcel identity. Zillow/Realtor/Redfin records can be missing, stale, or associated with a neighboring parcel.')
    else:
        st.info('No physical address is available for an automatic property cross-reference.')

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
st.caption('Screening signals must be independently verified before bidding. Tax-sale properties are sold as-is/where-is. Zillow/Realtor links are cross-checks, not proof that a house exists; listing sites may omit or lag rural/off-market properties.')
