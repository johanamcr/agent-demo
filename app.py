"""
CGSpace Explorer – Multifunctional Landscapes Science Program
=============================================================
Scoped exclusively to: CGIAR Science Program on Multifunctional Landscapes
"""

import streamlit as st
import pandas as pd
import requests
from collections import Counter
import plotly.express as px

st.set_page_config(
    page_title="CGSpace Explorer – Multifunctional Landscapes SP",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }
h1 { font-size: 1.8rem !important; font-weight: 700; color: #14532d; }
h2 { font-size: 1.2rem !important; font-weight: 600; color: #166534; }
h3 { font-size: 1rem !important; font-weight: 600; color: #1a1a1a; }
[data-testid="stMetric"] {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 10px; padding: 0.8rem 1rem;
}
[data-testid="stMetric"] label {
    font-size: 0.7rem !important; color: #6b7280 !important;
    text-transform: uppercase; letter-spacing: .05em;
}
[data-testid="stMetricValue"] {
    font-size: 1.6rem !important; font-weight: 700 !important; color: #15803d !important;
}
.doc-card {
    background: #f8fafc; border-left: 4px solid #16a34a;
    border-radius: 0 8px 8px 0; padding: 1rem 1.2rem; margin-top: 0.5rem;
}
.doc-card h4 { margin: 0 0 0.4rem 0; font-size: 1rem; color: #14532d; }
.doc-card p  { margin: 0.15rem 0; font-size: 0.82rem; color: #374151; }
.doc-tag {
    display: inline-block; background: #dcfce7; color: #166534;
    border-radius: 999px; padding: 0.15rem 0.6rem; font-size: 0.72rem;
    margin: 0.1rem 0.15rem 0.1rem 0;
}
.filter-badge {
    background: #fef9c3; border: 1px solid #fde047; border-radius: 6px;
    padding: 0.3rem 0.7rem; font-size: 0.78rem; color: #713f12;
    display: inline-block; margin-bottom: 0.5rem;
}
.sp-banner {
    background: linear-gradient(90deg, #14532d 0%, #166534 100%);
    color: white; border-radius: 10px; padding: 0.7rem 1.2rem;
    font-size: 0.85rem; margin-bottom: 1rem;
}
section[data-testid="stSidebar"] { background: #f9fafb; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────
RDS_PATH         = "base_cgspace_completa.rds"
CGSPACE_API      = "https://cgspace.cgiar.org/server/api/discover/search/objects"
ML_SP_COLLECTION = "CGIAR Science Program on Multifunctional Landscapes"
SEARCH_FIELDS    = ["title", "author", "agrovoc_subject", "country", "investor_funder_sponsor"]

# ── Synonyms ───────────────────────────────────────────────────
SYNONYMS: dict[str, list[str]] = {
    "agroecologia":          ["agroecology", "sustainable farming", "organic farming"],
    "agroecología":          ["agroecology", "sustainable farming", "organic farming"],
    "cafe":                  ["coffee", "coffea"],
    "café":                  ["coffee", "coffea"],
    "roya":                  ["coffee rust", "leaf rust", "hemileia vastatrix"],
    "cambio climatico":      ["climate change", "global warming", "climate variability"],
    "cambio climático":      ["climate change", "global warming", "climate variability"],
    "sequia":                ["drought", "water stress"],
    "sequía":                ["drought", "water stress"],
    "biodiversidad":         ["biodiversity", "species diversity", "genetic resources"],
    "seguridad alimentaria": ["food security", "food systems", "nutrition"],
    "genero":                ["gender", "women", "female farmers"],
    "género":                ["gender", "women", "female farmers"],
    "maiz":                  ["maize", "corn", "zea mays"],
    "maíz":                  ["maize", "corn", "zea mays"],
    "arroz":                 ["rice", "oryza"],
    "trigo":                 ["wheat", "triticum"],
    "frijol":                ["bean", "phaseolus", "legume"],
    "suelo":                 ["soil", "soil health", "land degradation"],
    "agua":                  ["water", "irrigation", "watershed"],
    "ganaderia":             ["livestock", "cattle", "animal husbandry"],
    "ganadería":             ["livestock", "cattle", "animal husbandry"],
    "fertilizante":          ["fertilizer", "nutrient management"],
    "plagas":                ["pest", "pest management", "ipm"],
    "semillas":              ["seeds", "seed systems", "plant breeding"],
    "variedades":            ["varieties", "cultivars", "crop improvement"],
    "bosque":                ["forest", "deforestation", "agroforestry"],
    "paisaje":               ["landscape", "multifunctional landscape", "land use"],
    "paisajes":              ["landscapes", "multifunctional landscapes"],
    "africa":                ["africa", "sub-saharan africa", "east africa", "west africa"],
    "áfrica":                ["africa", "sub-saharan africa", "east africa", "west africa"],
    "asia":                  ["asia", "south asia", "southeast asia"],
    "latinoamerica":         ["latin america", "south america", "central america"],
    "latinoamérica":         ["latin america", "south america", "central america"],
    "smallholder":           ["smallholder", "small-scale farmer", "family farm"],
    "nutricion":             ["nutrition", "malnutrition", "dietary"],
    "nutrición":             ["nutrition", "malnutrition", "dietary"],
}

def expand_query(query: str) -> list[str]:
    q = query.strip().lower()
    terms = [query.strip()]
    if q in SYNONYMS:
        terms.extend(SYNONYMS[q])
    for key, syns in SYNONYMS.items():
        if key in q and key != q:
            terms.extend(syns)
    seen, unique = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    return unique

# ── Load data ──────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading Multifunctional Landscapes dataset…")
def load_data() -> pd.DataFrame:
    try:
        import pyreadr
        result = pyreadr.read_r(RDS_PATH)
        df = result[None] if None in result else list(result.values())[0]
        # Filter to ML SP only
        if "repository_collection" in df.columns:
            df = df[
                df["repository_collection"].astype(str)
                .str.contains(ML_SP_COLLECTION, case=False, na=False)
            ].copy()
        if "year" in df.columns:
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
        if "handle" in df.columns:
            def norm(h):
                if pd.isna(h): return None
                h = str(h).strip()
                return h if h.startswith("http") else f"https://cgspace.cgiar.org/handle/{h}"
            df["handle"] = df["handle"].apply(norm)
        return df.reset_index(drop=True)
    except FileNotFoundError:
        st.error(f"File `{RDS_PATH}` not found. Place it in the same folder as cgspace_app.py")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error reading RDS: {e}")
        return pd.DataFrame()

DF_FULL = load_data()

# ── Analysis helpers ───────────────────────────────────────────
def extract_topics(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    if "agrovoc_subject" not in df.columns or df.empty:
        return pd.DataFrame(columns=["Topic", "Docs"])
    topics = []
    for v in df["agrovoc_subject"].dropna():
        topics.extend([t.strip() for t in str(v).split(",") if t.strip()])
    if not topics:
        return pd.DataFrame(columns=["Topic", "Docs"])
    return pd.DataFrame(Counter(topics).most_common(top_n), columns=["Topic", "Docs"])

def country_counts(df: pd.DataFrame) -> pd.DataFrame:
    if "country" not in df.columns or df.empty:
        return pd.DataFrame(columns=["Country", "Docs"])
    c = df["country"].dropna().value_counts().reset_index()
    c.columns = ["Country", "Docs"]
    return c

def repo_stats(df: pd.DataFrame) -> dict:
    if df.empty: return {}
    return {
        "total":     len(df),
        "countries": df["country"].dropna().nunique() if "country" in df.columns else 0,
        "years":     (int(df["year"].min()), int(df["year"].max()))
                     if "year" in df.columns and df["year"].notna().any() else (0, 0),
        "types":     df["type"].dropna().nunique() if "type" in df.columns else 0,
        "funders":   df["investor_funder_sponsor"].dropna().nunique()
                     if "investor_funder_sponsor" in df.columns else 0,
    }

# ── Search: local ──────────────────────────────────────────────
def search_local(terms: list[str], year_range: tuple, max_results: int = 500) -> pd.DataFrame:
    df = DF_FULL
    if df.empty or not terms: return pd.DataFrame()
    if "year" in df.columns and year_range:
        df = df[df["year"].between(year_range[0], year_range[1])]
    fields = [c for c in SEARCH_FIELDS if c in df.columns]
    if not fields: return pd.DataFrame()
    mask = pd.Series(False, index=df.index)
    for t in terms:
        tl = t.lower()
        for col in fields:
            mask |= df[col].astype(str).str.lower().str.contains(tl, na=False, regex=False)
    result = df[mask].copy()
    if "year" in result.columns:
        result = result.sort_values("year", ascending=False)
    return result.head(max_results).reset_index(drop=True)

# ── Search: API ────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Querying CGSpace API – Multifunctional Landscapes…")
def search_api(terms_tuple: tuple, year_min: int, year_max: int) -> pd.DataFrame:
    terms = list(terms_tuple)
    if not terms: return pd.DataFrame()
    scoped = [f'{t} "Multifunctional Landscapes"' for t in terms[:2]] + terms[:2]
    all_items, seen_handles = [], set()
    for term in scoped[:4]:
        for page in range(3):
            try:
                resp = requests.get(CGSPACE_API,
                    params={"query": term, "page": page, "size": 50}, timeout=30)
                resp.raise_for_status()
                objects = (resp.json().get("_embedded", {})
                           .get("searchResult", {}).get("_embedded", {}).get("objects", []))
                if not objects: break
                for obj in objects:
                    idx = obj.get("_embedded", {}).get("indexableObject", {})
                    handle = idx.get("handle")
                    if not handle or handle in seen_handles: continue
                    seen_handles.add(handle)
                    parsed = _parse_api_item(idx)
                    if parsed: all_items.append(parsed)
            except Exception:
                break
    if not all_items: return pd.DataFrame()
    df = pd.DataFrame(all_items)
    def is_relevant(row):
        txt = row.get("_txt", "")
        return any(t.lower() in txt for t in terms) if txt else True
    df = df[df.apply(is_relevant, axis=1)].drop(columns=["_txt"], errors="ignore")
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df[df["year"].between(year_min, year_max)]
        df = df.sort_values("year", ascending=False)
    return df.reset_index(drop=True)

def _parse_api_item(idx: dict) -> dict | None:
    meta = idx.get("metadata", {})
    handle = idx.get("handle")
    title = next((meta[k][0].get("value") for k in ["dc.title", "dcterms.title"] if k in meta), idx.get("name"))
    if not title: return None
    year = None
    for k in ["dcterms.issued", "dc.date.issued"]:
        if k in meta:
            for e in meta[k]:
                v = str(e.get("value", ""))
                if len(v) >= 4 and v[:4].isdigit():
                    c = int(v[:4])
                    if 1970 <= c <= 2025: year = c; break
        if year: break
    country = next((meta[k][0].get("value") for k in
        ["cg.country", "cg.coverage.country", "dc.coverage.spatial"] if k in meta), None)
    topics = next(([e.get("value","") for e in meta[k] if e.get("value")]
        for k in ["cg.subject.cgiar","cg.subject","dc.subject"] if k in meta), [])
    doc_type = next((meta[k][0].get("value") for k in ["dc.type","dcterms.type"] if k in meta), None)
    funders = next(([e.get("value","") for e in meta[k] if e.get("value")]
        for k in ["cg.contributor.funder","dc.contributor.funder"] if k in meta), [])
    return {
        "title": title, "year": year, "type": doc_type, "country": country,
        "agrovoc_subject": ", ".join(topics) if topics else None,
        "investor_funder_sponsor": "; ".join(funders[:3]) if funders else None,
        "handle": f"https://cgspace.cgiar.org/handle/{handle}" if handle else None,
        "_txt": (title + " " + " ".join(topics)).lower(),
    }

# ── Session state ──────────────────────────────────────────────
for k, v in {
    "results": pd.DataFrame(), "last_query": "", "terms": [],
    "source_used": "", "filter_country": None, "filter_topic": None,
    "selected_doc": None, "mode": "home",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌿 CGSpace Explorer")
    st.markdown(
        '<div style="font-size:0.72rem;color:#6b7280;line-height:1.5;">'
        'Multifunctional Landscapes<br>Science Program · CGIAR</div>',
        unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("**1 · Data source**")
    source = st.radio("source",
        ["📂  Local dataset (RDS)", "🌐  CGSpace API (live)"],
        label_visibility="collapsed",
        help="Local dataset is faster and complete. API retrieves live results.")
    use_local = source.startswith("📂")
    st.markdown("---")

    st.markdown("**2 · Year range**")
    if not DF_FULL.empty and "year" in DF_FULL.columns and DF_FULL["year"].notna().any():
        global_min = int(DF_FULL["year"].min())
        global_max = int(DF_FULL["year"].max())
    else:
        global_min, global_max = 1990, 2025
    year_range = st.slider("years", min_value=global_min, max_value=global_max,
        value=(2000, global_max), label_visibility="collapsed")
    st.caption(f"Searching: **{year_range[0]} – {year_range[1]}**")
    st.markdown("---")

    st.markdown("**3 · Search**")
    query_input = st.text_input("query",
        placeholder="e.g. landscape restoration, gender, drought…",
        label_visibility="collapsed")
    search_btn = st.button("🔍  Search", use_container_width=True, type="primary")

    if search_btn and query_input.strip():
        terms = expand_query(query_input)
        st.session_state.update({
            "last_query": query_input, "terms": terms,
            "filter_country": None, "filter_topic": None,
            "selected_doc": None, "mode": "results",
        })
        if use_local:
            with st.spinner("Searching local dataset…"):
                st.session_state.results = search_local(terms, year_range)
            st.session_state.source_used = "Local dataset (RDS)"
        else:
            with st.spinner("Querying API…"):
                st.session_state.results = search_api(tuple(terms), year_range[0], year_range[1])
            st.session_state.source_used = "CGSpace API"

    if st.session_state.mode == "results":
        st.markdown("---")
        if st.button("← Back to overview", use_container_width=True):
            st.session_state.update({
                "mode": "home", "results": pd.DataFrame(), "last_query": "",
                "filter_country": None, "filter_topic": None, "selected_doc": None,
            })

    if st.session_state.terms and len(st.session_state.terms) > 1:
        st.markdown("---")
        st.markdown("**Search terms used:**")
        st.caption("  ·  ".join(st.session_state.terms[:6]))

    if not DF_FULL.empty:
        st.markdown("---")
        st.caption(f"📦 ML SP dataset: **{len(DF_FULL):,}** documents")

# ── Home screen ────────────────────────────────────────────────
def show_home():
    st.markdown("# CGSpace Explorer")
    st.markdown(
        '<div class="sp-banner">🌿 &nbsp;'
        '<strong>Multifunctional Landscapes Science Program</strong>'
        ' &nbsp;·&nbsp; CGIAR</div>', unsafe_allow_html=True)
    st.markdown(
        "Explore the full knowledge output of the CGIAR Science Program on "
        "Multifunctional Landscapes. Use the sidebar to search by topic, "
        "country, author, or any keyword.")
    st.markdown("---")

    if DF_FULL.empty:
        st.info("Dataset not loaded. Make sure `base_cgspace_completa.rds` "
                "is in the same folder as `cgspace_app.py`.")
        return

    stats = repo_stats(DF_FULL)
    st.markdown("### Program overview")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total documents",   f"{stats['total']:,}")
    k2.metric("Countries covered", stats["countries"])
    k3.metric("Period",            f"{stats['years'][0]} – {stats['years'][1]}")
    k4.metric("Document types",    stats["types"])
    k5.metric("Unique funders",    stats["funders"])
    st.markdown("---")

    col_l, col_r = st.columns([1.1, 0.9])
    with col_l:
        st.markdown("### Geographic distribution")
        cp = country_counts(DF_FULL)
        if not cp.empty:
            fig = px.choropleth(cp, locations="Country", locationmode="country names",
                color="Docs", color_continuous_scale="Greens", height=340)
            fig.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                              coloraxis_colorbar=dict(title="Docs"))
            st.plotly_chart(fig, use_container_width=True, key="map_home")
            st.dataframe(cp.head(10), use_container_width=True, hide_index=True, height=200,
                column_config={"Docs": st.column_config.ProgressColumn(
                    "Docs", format="%d", min_value=0, max_value=int(cp["Docs"].max()))})

    with col_r:
        st.markdown("### Publications over time")
        if "year" in DF_FULL.columns and DF_FULL["year"].notna().any():
            py = DF_FULL.groupby("year").size().reset_index(name="Docs").sort_values("year")
            fig2 = px.area(py, x="year", y="Docs",
                           color_discrete_sequence=["#16a34a"], height=220)
            fig2.update_layout(margin=dict(l=0, r=0, t=5, b=0), xaxis_title="")
            fig2.update_traces(line_color="#16a34a", fillcolor="rgba(22,163,74,0.15)")
            st.plotly_chart(fig2, use_container_width=True, key="timeline_home")

        st.markdown("### Most frequent topics")
        dt = extract_topics(DF_FULL, top_n=12)
        if not dt.empty:
            fig3 = px.bar(dt.sort_values("Docs"), x="Docs", y="Topic",
                orientation="h", color="Docs", color_continuous_scale="Greens", height=330)
            fig3.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                               coloraxis_showscale=False, yaxis_title="")
            st.plotly_chart(fig3, use_container_width=True, key="topics_home")

    st.markdown("---")
    if "investor_funder_sponsor" in DF_FULL.columns:
        st.markdown("### Top funders")
        funders = []
        for v in DF_FULL["investor_funder_sponsor"].dropna():
            funders.extend([f.strip() for f in str(v).split(";") if f.strip()])
        if funders:
            df_f = pd.DataFrame(Counter(funders).most_common(10), columns=["Funder", "Docs"])
            fig4 = px.bar(df_f.sort_values("Docs"), x="Docs", y="Funder",
                orientation="h", color_discrete_sequence=["#15803d"], height=280)
            fig4.update_layout(margin=dict(l=0, r=0, t=5, b=0), yaxis_title="")
            st.plotly_chart(fig4, use_container_width=True, key="funders_home")

    st.markdown("---")
    st.info("👈 Use the sidebar to search within the Multifunctional Landscapes Science Program.")

# ── Results screen ─────────────────────────────────────────────
def show_results():
    df_raw = st.session_state.results
    st.markdown(f"# Results for \"{st.session_state.last_query}\"")
    st.markdown(
        '<div class="sp-banner">🌿 &nbsp;'
        'Multifunctional Landscapes Science Program · CGIAR</div>',
        unsafe_allow_html=True)
    st.caption(f"Source: **{st.session_state.source_used}**  ·  "
               f"Terms searched: {', '.join(st.session_state.terms[:5])}")
    st.markdown("---")

    if df_raw.empty:
        st.warning("No documents found. Try different keywords or widen the year range.")
        return

    df = df_raw.copy()
    active_filters = []
    if st.session_state.filter_country:
        df = df[df["country"] == st.session_state.filter_country]
        active_filters.append(f"Country: {st.session_state.filter_country}")
    if st.session_state.filter_topic:
        df = df[df["agrovoc_subject"].astype(str).str.contains(
            st.session_state.filter_topic, case=False, na=False)]
        active_filters.append(f"Topic: {st.session_state.filter_topic}")

    if active_filters:
        col_b, col_clr = st.columns([4, 1])
        with col_b:
            st.markdown("  ".join(
                [f'<span class="filter-badge">✕ {f}</span>' for f in active_filters]
            ), unsafe_allow_html=True)
        with col_clr:
            if st.button("Clear filters"):
                st.session_state.filter_country = None
                st.session_state.filter_topic   = None
                st.rerun()

    total   = len(df)
    n_ctry  = df["country"].dropna().nunique() if "country" in df.columns else 0
    n_types = df["type"].dropna().nunique()    if "type"    in df.columns else 0
    yr_max  = int(df["year"].max()) if "year" in df.columns and df["year"].notna().any() else "N/D"
    yr_min  = int(df["year"].min()) if "year" in df.columns and df["year"].notna().any() else "N/D"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Documents",      f"{total:,}")
    k2.metric("Countries",      n_ctry)
    k3.metric("Document types", n_types)
    k4.metric("Period",         f"{yr_min}–{yr_max}" if isinstance(yr_min, int) else "N/D")
    st.markdown("---")

    col_l, col_r = st.columns([1.1, 0.9])
    with col_l:
        st.markdown("### 🌍 By country  *(click to filter)*")
        cp = country_counts(df)
        if not cp.empty:
            fig_map = px.choropleth(cp, locations="Country", locationmode="country names",
                color="Docs", color_continuous_scale="Greens", height=310,
                custom_data=["Country"])
            fig_map.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                                  coloraxis_colorbar=dict(title=""))
            fig_map.update_traces(
                hovertemplate="<b>%{customdata[0]}</b><br>Docs: %{z}<extra></extra>")
            sel_map = st.plotly_chart(fig_map, use_container_width=True,
                                      on_select="rerun", key="map_res")
            if sel_map and sel_map.get("selection", {}).get("points"):
                clicked = sel_map["selection"]["points"][0].get("location")
                if clicked and clicked != st.session_state.filter_country:
                    st.session_state.filter_country = clicked
                    st.rerun()
            st.markdown("**Top countries** — click to filter")
            for _, row in cp.head(8).iterrows():
                ctry, docs = row["Country"], int(row["Docs"])
                active = st.session_state.filter_country == ctry
                if st.button(f"{'✓ ' if active else ''}{ctry}  ({docs:,})",
                             key=f"btn_c_{ctry}",
                             type="primary" if active else "secondary",
                             use_container_width=True):
                    st.session_state.filter_country = None if active else ctry
                    st.rerun()
        else:
            st.info("No country data available.")

    with col_r:
        st.markdown("### 📅 By year")
        if "year" in df.columns and df["year"].notna().any():
            py = df.groupby("year").size().reset_index(name="Docs").sort_values("year")
            fig_t = px.bar(py, x="year", y="Docs",
                           color_discrete_sequence=["#16a34a"], height=200)
            fig_t.update_layout(margin=dict(l=0, r=0, t=5, b=0), xaxis_title="")
            st.plotly_chart(fig_t, use_container_width=True, key="timeline_res")

        st.markdown("### 🏷️ Topics  *(click to filter)*")
        dt = extract_topics(df, top_n=12)
        if not dt.empty:
            fig_top = px.bar(dt.sort_values("Docs"), x="Docs", y="Topic",
                orientation="h", color="Docs", color_continuous_scale="Greens",
                height=310, custom_data=["Topic"])
            fig_top.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                                  coloraxis_showscale=False, yaxis_title="")
            sel_top = st.plotly_chart(fig_top, use_container_width=True,
                                      on_select="rerun", key="topics_res")
            if sel_top and sel_top.get("selection", {}).get("points"):
                clicked_t = sel_top["selection"]["points"][0].get("y")
                if clicked_t and clicked_t != st.session_state.filter_topic:
                    st.session_state.filter_topic = clicked_t
                    st.rerun()
        else:
            st.info("No topic data available.")

    st.markdown("---")
    st.markdown(f"### 📄 Documents ({total:,})")

    cols_table = [c for c in [
        "title", "year", "type", "country",
        "agrovoc_subject", "investor_funder_sponsor", "handle",
    ] if c in df.columns]

    event = st.dataframe(
        df[cols_table].reset_index(drop=True),
        use_container_width=True, height=400,
        on_select="rerun", selection_mode="single-row", key="table_docs",
        column_config={
            "title":                   st.column_config.TextColumn("Title", width="large"),
            "year":                    st.column_config.NumberColumn("Year", format="%d", width="small"),
            "type":                    st.column_config.TextColumn("Type", width="medium"),
            "country":                 st.column_config.TextColumn("Country", width="small"),
            "agrovoc_subject":         st.column_config.TextColumn("Topics", width="large"),
            "investor_funder_sponsor": st.column_config.TextColumn("Funder", width="medium"),
            "handle":                  st.column_config.LinkColumn("Link", width="small",
                                                                    display_text="🔗 View"),
        },
    )

    rows_sel = event.get("selection", {}).get("rows", []) if event else []
    if rows_sel:
        st.session_state.selected_doc = rows_sel[0]

    if st.session_state.selected_doc is not None:
        idx = st.session_state.selected_doc
        if idx < len(df):
            doc      = df.iloc[idx]
            title    = doc.get("title", "Untitled")
            year     = int(doc["year"]) if pd.notna(doc.get("year")) else "N/D"
            doc_type = doc.get("type", "N/D")
            country  = doc.get("country", "N/D")
            topics   = doc.get("agrovoc_subject", "")
            funder   = doc.get("investor_funder_sponsor", "")
            handle   = doc.get("handle", None)
            topic_tags = "".join(
                f'<span class="doc-tag">{t.strip()}</span>'
                for t in str(topics).split(",") if t.strip()
            ) if topics and str(topics) != "nan" else ""
            funder_str = str(funder) if funder and str(funder) != "nan" else ""
            link_html  = (f'<a href="{handle}" target="_blank" '
                          f'style="color:#16a34a;font-weight:600;">🔗 View on CGSpace</a>'
                          if handle else "")
            st.markdown(f"""
            <div class="doc-card">
                <h4>{title}</h4>
                <p>📅 <strong>{year}</strong> &nbsp;·&nbsp;
                   📁 <strong>{doc_type}</strong> &nbsp;·&nbsp;
                   🌍 <strong>{country}</strong></p>
                {"<p>💰 " + funder_str[:140] + ("…" if len(funder_str)>140 else "") + "</p>"
                 if funder_str else ""}
                <p style="margin-top:0.4rem">{topic_tags}</p>
                <p style="margin-top:0.5rem">{link_html}</p>
            </div>""", unsafe_allow_html=True)
            if st.button("✕ Close detail", key="close_detail"):
                st.session_state.selected_doc = None
                st.rerun()

    st.markdown("---")
    st.download_button(
        label="⬇️ Download results (CSV)",
        data=df[cols_table].to_csv(index=False).encode("utf-8"),
        file_name=f"mlsp_{st.session_state.last_query[:25].replace(' ','_')}.csv",
        mime="text/csv",
    )

# ── Router ─────────────────────────────────────────────────────
if st.session_state.mode == "home":
    show_home()
else:
    show_results()
