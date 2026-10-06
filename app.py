import io
import re
from urllib.parse import quote_plus

import folium
import pandas as pd
import requests
import streamlit as st
from folium.plugins import Draw, Fullscreen
from shapely.geometry import Point, shape
from streamlit_folium import st_folium

OFFICIAL_XLSX_URL = "https://www.andersoncountysc.org/wp-content/uploads/2026/10/2026TSSecondAD.xlsx"
BASE = "https://propertyviewer.andersoncountysc.org/arcgis/rest/services"
PARCEL = f"{BASE}/NewPropertyViewer/MapServer/5/query"
ZONING = f"{BASE}/QueryMap/MapServer/9/query"
FLOOD = f"{BASE}/QueryMap/MapServer/18/query"
SALES = f"{BASE}/Parcel_Sales/MapServer/0/query"
EASE = f"{BASE}/NewPropertyViewer/MapServer/8/query"
RIVERS = f"{BASE}/NewPropertyViewer/MapServer/19/query"
LAKES = f"{BASE}/Overlays/MapServer/1/query"
COUNTY = "https://www.andersoncountysc.org/http-anderson-postingpro-net-agreement-aspxstscpy2021cid4acceptscookies1/"
VIEWER = "https://propertyviewer.andersoncountysc.org/"
ACPASS = "https://acpass.andersoncountysc.org/"

st.set_page_config(page_title="Anderson SC Tax Sale Finder", page_icon="🗺️", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container{padding:.7rem .65rem 3rem;max-width:1250px}
.map-wrap{border:1px solid #ddd;border-radius:14px;overflow:hidden}
@media(max-width:700px){.block-container{padding:.55rem .45rem 2rem}.stButton>button,.stDownloadButton>button{min-height:2.8rem}.property-card{padding:.8rem;border:1px solid #ddd;border-radius:13px;margin:.5rem 0}.small{font-size:.82rem;color:#666}}
</style>""", unsafe_allow_html=True)

st.title("🗺️ Anderson County SC — 2026 Tax Sale Finder")
st.caption("Map-first property screening • acreage • opening bid • GIS value • risk flags • maximum-bid planning")

HEADER_TERMS = [
    r"\btms\b", r"tax.?map", r"map.?number", r"owner", r"taxpayer", r"property.?address",
    r"physical.?address", r"situs", r"street", r"location", r"address", r"\bcity\b",
    r"opening.?bid", r"minimum.?bid", r"open.?bid", r"assessed", r"market.?value", r"appraised",
    r"acre", r"\bitem\b", r"sale.?no", r"tax.?year", r"delinq", r"property.?type", r"\btype\b", r"mobile"
]

def header_score(row):
    vals=[str(x).strip().lower() for x in row.tolist()]
    return sum(any(re.search(p,v) for p in HEADER_TERMS) for v in vals if v and v != "nan")

def xls(data):
    xl=pd.ExcelFile(io.BytesIO(data)); candidates=[]
    for s in xl.sheet_names:
        raw=xl.parse(s, header=None)
        if raw.empty: continue
        scan=raw.head(min(50,len(raw)))
        scores=[header_score(scan.iloc[i]) for i in range(len(scan))]
        hdr=max(range(len(scores)), key=lambda i:scores[i])
        score=scores[hdr]
        if score >= 2:
            d=xl.parse(s, header=hdr)
            d.columns=[str(c).strip() for c in d.columns]
            d=d.dropna(how="all")
            d["__sheet"]=s
            candidates.append((score,len(d),d))
    if not candidates:
        d=xl.parse(xl.sheet_names[0])
        d.columns=[str(c).strip() for c in d.columns]
        return d.dropna(how="all")
    candidates.sort(key=lambda x:(x[0],x[1]), reverse=True)
    return candidates[0][2]

def fc(df, patterns):
    if df is None or df.empty: return None
    for c in df.columns:
        if any(re.search(p, str(c).lower()) for p in patterns): return c
    return None

def tx(df,c):
    if not c: return pd.Series("", index=df.index)
    return df[c].fillna("").astype(str).replace({"nan":""})

def nu(df,c):
    if not c: return pd.Series(float("nan"), index=df.index)
    s=df[c].astype(str).str.replace(r"[$,% ,]", "", regex=True).str.replace(r"\(([^)]+)\)", r"-\1", regex=True)
    return pd.to_numeric(s, errors="coerce")

def nt(x):
    # Excel often turns a 9- or 10-digit TMS into a float such as 450001008.0.
    # Remove only a trailing Excel decimal before extracting digits so we do not
    # accidentally turn the TMS into a different parcel number.
    s=str(x).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s=s.split(".",1)[0]
    return re.sub(r"[^0-9]", "", s)

def tms_key(x):
    digits=nt(x)
    if not digits: return ""
    # Anderson TMS values can lose a leading zero when Excel stores them as numbers.
    if len(digits) < 10: digits=digits.zfill(10)
    return digits

def tms_variants(x):
    raw=str(x).strip()
    if raw.lower() in ("", "nan", "none"): return []
    digits=nt(raw)
    canonical=tms_key(raw)
    vals=[]
    for v in (raw,digits,canonical):
        if v and v not in vals: vals.append(v)
    if len(canonical)==10:
        hy=f"{canonical[:3]}-{canonical[3:5]}-{canonical[5:7]}-{canonical[7:]}"
        if hy not in vals: vals.append(hy)
        # Also include the unhyphenated canonical value explicitly.
        if canonical not in vals: vals.append(canonical)
    return vals

def extract_acres(description):
    s=safe_text(description).upper()
    # The county tax-sale description commonly embeds acreage as “2.07 AC”, “.73 AC”, etc.
    m=re.search(r"(?<![A-Z0-9])(?P<n>\d*\.?\d+)\s*(?:ACRES?|AC|A)\b",s)
    if m:
        try: return float(m.group("n"))
        except Exception: pass
    return float("nan")

def fmt_money(x):
    return f"${float(x):,.0f}" if pd.notna(x) else "—"

def safe_text(x):
    if x is None or pd.isna(x): return ""
    return str(x).strip()

def txtblob(items):
    return " ".join(" ".join(str(v) for v in d.values() if v is not None) for d in items).lower()

@st.cache_data(ttl=1800, show_spinner=False)
def get_xlsx():
    r=requests.get(OFFICIAL_XLSX_URL, timeout=45)
    r.raise_for_status(); return r.content

@st.cache_data(ttl=1800, show_spinner=False)
def parcel_lookup(tms_values):
    variants=[]
    for x in tms_values:
        for v in tms_variants(x):
            if v not in variants: variants.append(v)
    rows=[]
    for i in range(0,len(variants),50):
        vals=variants[i:i+50]
        where="TMS IN ("+",".join("'"+v.replace("'","''")+"'" for v in vals)+")"
        p={"where":where,"outFields":"*","returnGeometry":"true","outSR":"4326","f":"json"}
        try:
            j=requests.get(PARCEL, params=p, timeout=45).json()
            for f in j.get("features",[]):
                a=f.get("attributes",{}).copy(); a["_geom"]=f.get("geometry",{})
                g=a["_geom"]
                if "x" in g: a["_lon"],a["_lat"]=g["x"],g["y"]
                elif "rings" in g:
                    pts=[pt for ring in g["rings"] for pt in ring]
                    if pts:
                        a["_lon"]=sum(p[0] for p in pts)/len(pts); a["_lat"]=sum(p[1] for p in pts)/len(pts)
                rows.append(a)
        except Exception:
            continue
    return rows

@st.cache_data(ttl=1800, show_spinner=False)
def spatial_query(url, lat, lon, distance=25):
    p={"where":"1=1","outFields":"*","returnGeometry":"false","outSR":"4326","f":"json",
       "geometry":f"{{\"x\":{lon},\"y\":{lat}}}","geometryType":"esriGeometryPoint","inSR":"4326",
       "spatialRel":"esriSpatialRelIntersects","distance":distance,"units":"esriSRUnit_Meter"}
    try:
        j=requests.get(url, params=p, timeout=20).json()
        return [f.get("attributes",{}) for f in j.get("features",[])]
    except Exception: return []

@st.cache_data(ttl=1800, show_spinner=False)
def enrich(points):
    out=[]
    for key,lat,lon in points:
        out.append({
            "TMS_KEY":key,
            "zoning":spatial_query(ZONING,lat,lon,20),
            "flood":spatial_query(FLOOD,lat,lon,20),
            "easement":spatial_query(EASE,lat,lon,20),
            "rivers":spatial_query(RIVERS,lat,lon,100),
            "lakes":spatial_query(LAKES,lat,lon,100),
            "sales":spatial_query(SALES,lat,lon,2000),
        })
    return out

if "data" not in st.session_state: st.session_state.data=None
if "fav" not in st.session_state: st.session_state.fav=set()
if "notes" not in st.session_state: st.session_state.notes={}
if "map_selection" not in st.session_state: st.session_state.map_selection=None
if "drawn_area" not in st.session_state: st.session_state.drawn_area=None

with st.expander("⚙️ Data source & county links"):
    up=st.file_uploader("Upload the official 2026 Excel list (optional)", type=["xlsx","xls"])
    if st.button("📥 Load official 2026 tax-sale list", use_container_width=True):
        try:
            with st.spinner("Downloading the official county list…"):
                st.session_state.data=get_xlsx()
            st.success("Official list loaded.")
            st.rerun()
        except Exception as e: st.error(f"Could not load the county spreadsheet: {e}")
    st.markdown(f"[County tax-sale page]({COUNTY}) · [ACPASS]({ACPASS}) · [County Property Viewer]({VIEWER})")
if up:
    st.session_state.data=up.getvalue()

if not st.session_state.data:
    st.info("Load the official 2026 spreadsheet to begin. The app then matches the tax-sale TMS numbers to the county GIS parcel layer.")
    st.stop()

raw=xls(st.session_state.data); raw.columns=[str(c).strip() for c in raw.columns]
T=fc(raw,[r"\btms\b",r"tax.?map",r"map.?number"])
O=fc(raw,[r"^owner$",r"current.?owner",r"owner",r"taxpayer"])
A=fc(raw,[r"property.?address",r"physical.?address",r"situs",r"street",r"location",r"address"])
DESC=fc(raw,[r"property.?description",r"description"])
C=fc(raw,[r"\bcity\b",r"town"])
B=fc(raw,[r"opening.?bid",r"minimum.?bid",r"open.?bid",r"amount.?due",r"due.?amount",r"^amount$"])
if B and re.search(r"years?",str(B),re.I): B=None
if not B:
    # 2026 county ad labels the sale amount as AMOUNT DUE / DUE 6%.
    for c in raw.columns:
        name=str(c).strip().lower()
        if ("amount" in name and "due" in name) or name in ("amount due", "amount due 6%", "due 6%"):
            B=c; break
AV=fc(raw,[r"assessed.?value",r"assessed",r"market.?value",r"appraised"])
AC=fc(raw,[r"acres?",r"acreage"])
I=fc(raw,[r"^item$",r"\bitem\b",r"sale.?no"])
TY=fc(raw,[r"tax.?year",r"delinq",r"years?.?due"])
PT=fc(raw,[r"property.?type",r"property.?class",r"type",r"mobile"])

df=pd.DataFrame(index=raw.index)
df["TMS"]=tx(raw,T); df["Item"]=tx(raw,I); df["Owner"]=tx(raw,O)
# The 2026 tax-sale spreadsheet does not have a standalone address column; the
# property description contains the situs/street text and acreage.
df["Address"]=tx(raw,A) if A else tx(raw,DESC)
df["Property Description"]=tx(raw,DESC) if DESC else df["Address"]
df["City"]=tx(raw,C)
df["Opening Bid"]=nu(raw,B); df["Assessed"]=nu(raw,AV)
df["Acres"]=nu(raw,AC) if AC else df["Property Description"].map(extract_acres)
df["Tax Year"]=tx(raw,TY); df["Type"]=tx(raw,PT)
df=df[(df.TMS.str.strip()!="") | (df.Owner.str.strip()!="") | df["Opening Bid"].notna()].copy()
df["TMS_KEY"]=df.TMS.map(tms_key)
df["Mobile"]=(df.Type+" "+df.Address).str.lower().str.contains(r"mobile|manufactured|mh\b",regex=True)

with st.spinner("Matching tax-sale properties to Anderson County GIS parcels…"):
    pars=parcel_lookup([x for x in dict.fromkeys(df.TMS.tolist()) if str(x).strip()])
pd_gis=pd.DataFrame(pars)
if len(pd_gis):
    gis_tms_col=fc(pd_gis,[r"\btms\b",r"tax.?map",r"map.?number",r"parcel.?id"])
    pd_gis["TMS_KEY"]=pd_gis[gis_tms_col].map(tms_key) if gis_tms_col else pd.Series("",index=pd_gis.index)
    for new,pats in [("GIS Address",[r"phys.?addr",r"situs",r"address",r"site.?addr"]),
                     ("GIS Market",[r"market.?value",r"mkt.?value",r"mrkt",r"fair.?market",r"\bmarket\b"]),
                     ("GIS Acres",[r"acres?",r"gis.?acres",r"lot.?size"]),
                     ("GIS Ratio",[r"^ratio$",r"assess.?ratio"])]:
        c=fc(pd_gis,pats); pd_gis[new]=pd_gis[c] if c else pd.NA
    for c in ["_lat","_lon","_geom"]:
        if c not in pd_gis: pd_gis[c]=pd.NA
    keep=["TMS_KEY","GIS Address","GIS Market","GIS Acres","GIS Ratio","_lat","_lon","_geom"]
    df=df.merge(pd_gis[keep].drop_duplicates("TMS_KEY"),on="TMS_KEY",how="left")
else:
    for c in ["GIS Address","GIS Market","GIS Acres","GIS Ratio","_lat","_lon","_geom"]: df[c]=pd.NA

df["GIS Matched"]=df["_geom"].notna() | df["_lat"].notna() | df["GIS Address"].notna() | df["GIS Market"].notna()
df["Research Address"]=df.Address.where(df.Address.str.strip().ne(""),df["GIS Address"].fillna(""))
df["GIS Acres Final"]=pd.to_numeric(df["GIS Acres"],errors="coerce").fillna(pd.to_numeric(df["Acres"],errors="coerce"))
df["Bid/Assessed"]=df["Opening Bid"]/df["Assessed"].replace(0,pd.NA)
df["Bid/Market"]=df["Opening Bid"]/pd.to_numeric(df["GIS Market"],errors="coerce").replace(0,pd.NA)

with st.expander("🧪 Data diagnostics", expanded=False):
    st.write(f"Detected spreadsheet columns — TMS: `{T or 'NOT FOUND'}` · Owner: `{O or 'NOT FOUND'}` · Address: `{A or 'NOT FOUND'}` · Opening bid: `{B or 'NOT FOUND'}` · Value: `{AV or 'NOT FOUND'}` · Acres: `{AC or 'NOT FOUND'}`")
    st.write(f"Rows loaded: **{len(df):,}** · GIS parcel matches: **{int(df['GIS Matched'].sum()):,}**")
    st.write("County GIS parcel fields used: TMS, PHYS_ADDR, MRKT_VALUE, RATIO, CPLAT and parcel geometry.")
    if not T or not B: st.warning("The county 2026 ad uses a compact tabular layout. The app now interprets TAXMAP and AMOUNT DUE / DUE 6% as the TMS and opening-bid fields, and extracts acreage from PROPERTY DESCRIPTION.")
    if len(df) and int(df["GIS Matched"].sum())==0: st.error("No GIS parcel matches were returned. The list can still be screened, but the map/value fields will not be reliable until the TMS match works.")

with st.expander("🔎 Filters", expanded=True):
    q=st.text_input("Search TMS, owner, address, city or item", placeholder="Owner, TMS, street, etc.")
    c1,c2,c3=st.columns(3)
    max_bid=float(df["Opening Bid"].max()) if df["Opening Bid"].notna().any() else 100000
    bid_max=c1.number_input("Maximum opening bid ($)",0.,max(100000.,max_bid),min(max_bid,50000.),1000.)
    min_acres=c2.number_input("Minimum acres",0.,100000.,0.,0.25)
    max_acres=c3.number_input("Maximum acres (0 = no limit)",0.,100000.,0.,0.25)
    c4,c5,c6=st.columns(3)
    min_value=c4.number_input("Minimum GIS market value ($)",0.,100000000.,0.,5000.)
    max_ratio=c5.number_input("Maximum opening bid / GIS value (%)",0.,200.,100.,5.)
    fav_only=c6.checkbox("Favorites only")
    c7,c8=st.columns(2)
    property_filter=c7.selectbox("Property type",["All","Land / real estate","Mobile / manufactured"])
    map_cap=c8.number_input("Maximum properties drawn on map",50,800,350,50)

mask=pd.Series(True,index=df.index)
if q:
    blob=df.fillna("").astype(str).agg(" | ".join,axis=1).str.lower()
    mask &= blob.str.contains(re.escape(q.lower()),regex=True,na=False)
mask &= df["Opening Bid"].fillna(float("inf")) <= bid_max
mask &= df["GIS Acres Final"].fillna(0) >= min_acres
if max_acres>0: mask &= df["GIS Acres Final"].fillna(0) <= max_acres
mask &= pd.to_numeric(df["GIS Market"],errors="coerce").fillna(0) >= min_value
mask &= ((df["Bid/Market"].fillna(0)*100 <= max_ratio) | df["Bid/Market"].isna())
if property_filter=="Mobile / manufactured": mask &= df.Mobile
if property_filter=="Land / real estate": mask &= ~df.Mobile
if fav_only: mask &= df.index.isin(st.session_state.fav)

r=df.loc[mask].copy()
# Score uses only fields available without expensive spatial requests.
def base_score(row):
    s=50.
    bm=row["Bid/Market"]
    if pd.notna(bm): s += max(-35,min(35,(.25-float(bm))*100))
    elif pd.notna(row["Bid/Assessed"]): s += max(-30,min(30,(.35-float(row["Bid/Assessed"]))*70))
    acres=row["GIS Acres Final"]
    if pd.notna(acres): s += min(15,float(acres)*1.2)
    if row.Mobile: s -= 12
    if pd.notna(row["Opening Bid"]) and row["Opening Bid"]<5000: s += 5
    return round(max(0,min(100,s)))
r["Deal Score"]=r.apply(base_score,axis=1)
r=r.sort_values(["Deal Score","Bid/Market"],ascending=[False,True])

m1,m2,m3,m4=st.columns(4)
m1.metric("Filtered",len(r)); m2.metric("GIS matched",int(r["GIS Matched"].sum())); m3.metric("10+ acre",int((r["GIS Acres Final"]>=10).sum())); m4.metric("Favorites",len(st.session_state.fav))

st.subheader("🗺️ Interactive property map")
st.caption("Zoom and pan to an area. Use the draw tool to outline an area of interest; then press the button below to keep only properties inside it.")

map_df=r.dropna(subset=["_lat","_lon"]).copy()
map_df=map_df.head(int(map_cap))
if len(map_df)==0:
    st.warning("No filtered properties have GIS coordinates yet. Check Data diagnostics above.")
else:
    center=[float(map_df["_lat"].mean()),float(map_df["_lon"].mean())]
    fmap=folium.Map(location=center,zoom_start=11,control_scale=True,tiles="OpenStreetMap")
    Fullscreen(position="topleft").add_to(fmap)
    draw=Draw(export=False,position="topleft",draw_options={"polyline":False,"polygon":True,"rectangle":True,"circle":False,"marker":False,"circlemarker":False},edit_options={"edit":True,"remove":True})
    draw.add_to(fmap)
    features=[]
    for idx,row in map_df.iterrows():
        geom=row.get("_geom")
        if isinstance(geom,dict) and geom.get("rings"):
            coords=[]
            for ring in geom["rings"]:
                coords.append([[float(p[0]),float(p[1])] for p in ring])
            # ArcGIS rings are usually polygon rings in lon/lat order after outSR=4326.
            gj={"type":"Feature","properties":{"idx":str(idx),"tms":safe_text(row.TMS)},"geometry":{"type":"Polygon","coordinates":coords}}
            features.append(gj)
    if features:
        folium.GeoJson({"type":"FeatureCollection","features":features},style_function=lambda f:{"color":"#b91c1c","weight":2,"fillColor":"#ef4444","fillOpacity":0.16},highlight_function=lambda f:{"weight":4,"fillOpacity":0.28},tooltip=folium.GeoJsonTooltip(fields=["tms"],aliases=["TMS"]).add_to(fmap) if False else None).add_to(fmap)
    for idx,row in map_df.iterrows():
        popup=(f"<b>{safe_text(row.TMS)}</b><br>{safe_text(row.Owner) or 'Unknown owner'}<br>"
               f"{safe_text(row.Research_Address) if 'Research_Address' in row else safe_text(row['Research Address'])}<br>"
               f"Opening: {fmt_money(row['Opening Bid'])}<br>Acres: {safe_text(row['GIS Acres Final']) or '—'}<br>"
               f"GIS value: {fmt_money(row['GIS Market'])}<br>Score: {int(row['Deal Score'])}/100")
        folium.CircleMarker([float(row._lat),float(row._lon)],radius=5,weight=1,fill=True,fill_opacity=.9,popup=folium.Popup(popup,max_width=280),tooltip=f"{safe_text(row.TMS)} · {fmt_money(row['Opening Bid'])}").add_to(fmap)
    map_result=st_folium(fmap,width=None,height=560,returned_objects=["last_object_clicked","all_drawings","bounds","zoom"],key="taxsale_map")

    if map_result:
        drawings=map_result.get("all_drawings") or []
        if drawings:
            st.session_state.drawn_area=drawings[-1]
    c1,c2,c3=st.columns(3)
    if c1.button("📌 Filter to drawn area",use_container_width=True,disabled=not bool(st.session_state.drawn_area)):
        try:
            geom=shape(st.session_state.drawn_area["geometry"])
            keep=[]
            for idx,row in r.iterrows():
                if pd.notna(row._lat) and pd.notna(row._lon): keep.append(geom.contains(Point(float(row._lon),float(row._lat))))
                else: keep.append(False)
            r=r.loc[keep].copy()
            st.session_state.map_selection=[int(i) for i in r.index]
            st.success(f"Map area filter applied: {len(r)} properties inside the drawn area.")
        except Exception as e:
            st.error(f"Could not apply the drawn area: {e}")
    if c2.button("↺ Clear drawn area",use_container_width=True):
        st.session_state.drawn_area=None; st.session_state.map_selection=None; st.rerun()
    if c3.button("📍 Use visible map area",use_container_width=True):
        b=(map_result or {}).get("bounds") or {}
        try:
            south=b["_southWest"]["lat"]; west=b["_southWest"]["lng"]; north=b["_northEast"]["lat"]; east=b["_northEast"]["lng"]
            keep=r.apply(lambda x: pd.notna(x._lat) and pd.notna(x._lon) and south<=float(x._lat)<=north and west<=float(x._lon)<=east,axis=1)
            st.session_state.map_selection=[int(i) for i in r.index[keep]]
            st.success(f"Visible map-area filter applied: {int(keep.sum())} properties.")
        except Exception as e: st.error(f"Could not use the visible map area: {e}")

if st.session_state.map_selection is not None:
    selected_set=set(st.session_state.map_selection)
    r=r.loc[r.index.isin(selected_set)].copy()
    st.info(f"Map area is active — **{len(r)} properties** remain. Clear it above to return to the normal filters.")

st.subheader("🏆 Best matches")
if len(r)==0:
    st.warning("No properties match the current filters/map area.")
else:
    for i,idx in enumerate(r.index[:40]):
        row=r.loc[idx]
        with st.container(border=True):
            st.markdown(f"**#{i+1} · {safe_text(row.TMS)} · Score {int(row['Deal Score'])}/100**")
            st.write(f"{safe_text(row.Owner) or 'Unknown owner'} — {safe_text(row['Research Address']) or 'No address listed'}")
            a,b,c,d=st.columns(4)
            a.metric("Opening",fmt_money(row["Opening Bid"]))
            b.metric("Acres",f"{float(row['GIS Acres Final']):,.2f}" if pd.notna(row['GIS Acres Final']) else "—")
            c.metric("GIS value",fmt_money(row["GIS Market"]))
            d.metric("Bid / value",f"{float(row['Bid/Market'])*100:.1f}%" if pd.notna(row['Bid/Market']) else "—")

st.subheader("📍 Property research")
if len(r):
    idx=st.selectbox("Select a property",r.index.tolist(),format_func=lambda i:f"{safe_text(r.loc[i,'TMS'])} · {safe_text(r.loc[i,'Owner']) or 'Unknown owner'} · {safe_text(r.loc[i,'Research Address']) or 'No address'}")
    row=r.loc[idx]
    points=[]
    if pd.notna(row._lat) and pd.notna(row._lon): points=[(row.TMS_KEY,float(row._lat),float(row._lon))]
    info=enrich(points)[0] if points else {}
    st.markdown(f"### {safe_text(row.TMS)} — {safe_text(row.Owner) or 'Unknown owner'}")
    st.write(safe_text(row["Research Address"]) or "No address listed")
    a,b,c=st.columns(3); a.metric("Opening bid",fmt_money(row["Opening Bid"])); b.metric("Acres",f"{float(row['GIS Acres Final']):,.2f}" if pd.notna(row['GIS Acres Final']) else "—"); c.metric("GIS value",fmt_money(row["GIS Market"]))
    if pd.notna(row._lat) and pd.notna(row._lon):
        street=f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={row._lat},{row._lon}"
        maps=f"https://www.google.com/maps/search/?api=1&query={quote_plus(str(row['Research Address'])+', Anderson County, SC')}"
        a,b=st.columns(2); a.link_button("🚗 Street View",street,use_container_width=True); b.link_button("🗺️ Google Maps",maps,use_container_width=True)
    a,b=st.columns(2); a.link_button("🏛️ County Property Viewer",VIEWER,use_container_width=True); b.link_button("📑 ACPASS",ACPASS,use_container_width=True)
    risk=[]
    if txtblob(info.get("flood",[])): risk.append("FLOOD")
    if txtblob(info.get("easement",[])): risk.append("EASEMENT")
    if txtblob(info.get("rivers",[])) or txtblob(info.get("lakes",[])): risk.append("WATER")
    if row.Mobile: risk.append("MOBILE")
    st.markdown("**Automated risk:** "+(" / ".join(risk) if risk else "LOWER AUTOMATED RISK"))
    note=st.text_area("Research notes",st.session_state.notes.get(str(idx),""),height=100)
    st.session_state.notes[str(idx)]=note
    if idx in st.session_state.fav:
        if st.button("☆ Remove favorite",use_container_width=True): st.session_state.fav.remove(idx); st.rerun()
    else:
        if st.button("★ Add favorite",use_container_width=True): st.session_state.fav.add(idx); st.rerun()
    with st.expander("🧭 GIS risk details"):
        for title,key in [("Zoning","zoning"),("Flood hazard","flood"),("Access easement","easement"),("Water / streams","rivers"),("Nearby parcel sales","sales")]:
            st.markdown(f"**{title}**")
            vals=info.get(key,[])
            if not vals: st.write("No spatial match returned.")
            else:
                for v in vals[:8]: st.write("• "+" | ".join(f"{k}: {v}" for k,v in v.items() if v not in (None,"")))

st.divider()
st.subheader("💰 Maximum-bid planning")
st.caption("Planning model only — not an appraisal, title opinion, or guarantee of profit.")
a,b,c=st.columns(3)
target_margin=a.number_input("Desired profit / equity margin ($)",0.,10000000.,20000.,2500.)
repair_budget=b.number_input("Repairs / cleanup reserve ($)",0.,10000000.,10000.,1000.)
holding_cost=c.number_input("Holding / carrying reserve ($)",0.,10000000.,5000.,1000.)
a,b,c=st.columns(3)
transaction_cost_pct=a.number_input("Transaction / closing reserve (%)",0.,25.,3.,.5)
risk_reserve_pct=b.number_input("Base risk reserve (%)",0.,50.,10.,1.)
max_ltv_pct=c.number_input("Maximum bid as % of estimated value",1.,100.,50.,5.)

if len(r):
    records=[]
    for i,prop in r.iterrows():
        value=pd.to_numeric(prop["GIS Market"],errors="coerce")
        if pd.isna(value) or value<=0: value=pd.to_numeric(prop["Assessed"],errors="coerce")
        if pd.isna(value) or value<=0:
            records.append([i,None,None,None,"PASS — insufficient value data"]); continue
        risk_pct=float(risk_reserve_pct); info=enrich([(prop.TMS_KEY,float(prop._lat),float(prop._lon))])[0] if pd.notna(prop._lat) and pd.notna(prop._lon) else {}
        if txtblob(info.get("flood",[])): risk_pct+=7
        if txtblob(info.get("easement",[])): risk_pct+=5
        if txtblob(info.get("rivers",[])) or txtblob(info.get("lakes",[])): risk_pct+=3
        if txtblob(info.get("zoning",[])): risk_pct+=2
        if prop.Mobile: risk_pct+=5
        value=float(value); risk=value*risk_pct/100; tx=value*float(transaction_cost_pct)/100
        maximum=max(0.,min(value-float(repair_budget)-float(holding_cost)-risk-tx-float(target_margin),value*float(max_ltv_pct)/100))
        opening=float(prop["Opening Bid"]) if pd.notna(prop["Opening Bid"]) else 0
        rec="PASS — opening bid exceeds model maximum" if maximum<opening else ("CAUTION — little bidding room" if maximum<opening*1.10 else ("STRONG — substantial bidding room" if maximum>=opening*1.50 else "BID — within model"))
        records.append([i,value,maximum,risk_pct,rec])
    bid_df=pd.DataFrame(records,columns=["_idx","Estimated Value","Maximum Bid","Risk Reserve %","Bid Recommendation"]).set_index("_idx")
    res=r.join(bid_df)
    selected=st.selectbox("Detailed maximum-bid calculation",res.index.tolist(),format_func=lambda i:f"{res.loc[i,'TMS']} · max {fmt_money(res.loc[i,'Maximum Bid'])}")
    rr=res.loc[selected]
    if pd.notna(rr["Maximum Bid"]):
        a,b,c=st.columns(3); a.metric("Estimated value",fmt_money(rr["Estimated Value"])); b.metric("MAX BID",fmt_money(rr["Maximum Bid"])); c.metric("Opening bid",fmt_money(rr["Opening Bid"]))
        st.info(f"Estimated value {fmt_money(rr['Estimated Value'])} − repairs {fmt_money(repair_budget)} − holding {fmt_money(holding_cost)} − risk reserve {float(rr['Risk Reserve %']):.1f}% − transaction reserve {float(transaction_cost_pct):.1f}% − desired margin {fmt_money(target_margin)} = **{fmt_money(rr['Maximum Bid'])} model maximum**.")

out=r.copy(); out["Favorite"]=out.index.isin(st.session_state.fav); out["Notes"]=out.index.map(lambda i:st.session_state.notes.get(str(i),""))
st.download_button("📥 Download current shortlist CSV",out.to_csv(index=False).encode("utf-8-sig"),"anderson_2026_tax_sale_shortlist.csv","text/csv",use_container_width=True)
st.caption("Official county tax-sale data is used for the list. GIS information is a screening aid and must be independently verified before bidding; tax-sale properties are sold as-is/where-is.")
