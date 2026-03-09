"""
CGSpace Explorer
════════════════
Diseño ejecutivo limpio para donantes e investigadores.

Características:
  • Pantalla de inicio con estadísticas generales del repositorio
  • Sidebar: elige fuente (CSV o API), filtro de años, luego busca
  • Gráficos interactivos: clic en país o tema filtra la tabla
  • Panel de detalle al seleccionar un documento
  • Fuentes separadas: CSV (175k docs) o API CGSpace en vivo
"""

import streamlit as st
import pandas as pd
import requests
from collections import Counter
import plotly.express as px

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="CGSpace Explorer",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Tipografía y espaciado general */
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }
h1 { font-size: 1.8rem !important; font-weight: 700; color: #14532d; }
h2 { font-size: 1.2rem !important; font-weight: 600; color: #166534; }
h3 { font-size: 1rem !important; font-weight: 600; color: #1a1a1a; }

/* Métricas */
[data-testid="stMetric"] {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
[data-testid="stMetric"] label {
    font-size: 0.7rem !important;
    color: #6b7280 !important;
    text-transform: uppercase;
    letter-spacing: .05em;
}
[data-testid="stMetricValue"] {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #15803d !important;
}

/* Tarjeta de detalle de documento */
.doc-card {
    background: #f8fafc;
    border-left: 4px solid #16a34a;
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.2rem;
    margin-top: 0.5rem;
}
.doc-card h4 { margin: 0 0 0.4rem 0; font-size: 1rem; color: #14532d; }
.doc-card p  { margin: 0.15rem 0; font-size: 0.82rem; color: #374151; }
.doc-tag {
    display: inline-block;
    background: #dcfce7;
    color: #166534;
    border-radius: 999px;
    padding: 0.15rem 0.6rem;
    font-size: 0.72rem;
    margin: 0.1rem 0.15rem 0.1rem 0;
}

/* Filtro activo badge */
.filter-badge {
    background: #fef9c3;
    border: 1px solid #fde047;
    border-radius: 6px;
    padding: 0.3rem 0.7rem;
    font-size: 0.78rem;
    color: #713f12;
    display: inline-block;
    margin-bottom: 0.5rem;
}

/* Sidebar */
section[data-testid="stSidebar"] { background: #f9fafb; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════
RDS_PATH    = "base_cgspace_completa.rds"
CGSPACE_API = "https://cgspace.cgiar.org/server/api/discover/search/objects"

CSV_SEARCH_FIELDS = [
    "title", "author", "agrovoc_subject",
    "country", "investor_funder_sponsor", "repository_collection",
]

# ═══════════════════════════════════════════════════════════════
# SINÓNIMOS ES → EN
# ═══════════════════════════════════════════════════════════════
SINONIMOS: dict[str, list[str]] = {
    "agroecología":          ["agroecology", "sustainable farming", "organic farming"],
    "agroecologia":          ["agroecology", "sustainable farming", "organic farming"],
    "café":                  ["coffee", "coffea"],
    "cafe":                  ["coffee", "coffea"],
    "roya":                  ["coffee rust", "leaf rust", "hemileia vastatrix"],
    "cambio climático":      ["climate change", "global warming", "climate variability"],
    "cambio climatico":      ["climate change", "global warming", "climate variability"],
    "sequía":                ["drought", "water stress"],
    "sequia":                ["drought", "water stress"],
    "biodiversidad":         ["biodiversity", "species diversity", "genetic resources"],
    "seguridad alimentaria": ["food security", "food systems", "nutrition"],
    "género":                ["gender", "women", "female farmers"],
    "genero":                ["gender", "women", "female farmers"],
    "maíz":                  ["maize", "corn", "zea mays"],
    "maiz":                  ["maize", "corn", "zea mays"],
    "arroz":                 ["rice", "oryza"],
    "trigo":                 ["wheat", "triticum"],
    "frijol":                ["bean", "phaseolus", "legume"],
    "suelo":                 ["soil", "soil health", "land degradation"],
    "agua":                  ["water", "irrigation", "watershed"],
    "ganadería":             ["livestock", "cattle", "animal husbandry"],
    "ganaderia":             ["livestock", "cattle", "animal husbandry"],
    "fertilizante":          ["fertilizer", "nutrient management"],
    "plagas":                ["pest", "pest management", "ipm"],
    "semillas":              ["seeds", "seed systems", "plant breeding"],
    "variedades":            ["varieties", "cultivars", "crop improvement"],
    "bosque":                ["forest", "deforestation", "agroforestry"],
    "áfrica":                ["africa", "sub-saharan africa", "east africa", "west africa"],
    "africa":                ["africa", "sub-saharan africa", "east africa", "west africa"],
    "asia":                  ["asia", "south asia", "southeast asia"],
    "latinoamérica":         ["latin america", "south america", "central america"],
    "latinoamerica":         ["latin america", "south america", "central america"],
    "smallholder":           ["smallholder", "small-scale farmer", "family farm"],
    "nutrición":             ["nutrition", "malnutrition", "dietary"],
    "nutricion":             ["nutrition", "malnutrition", "dietary"],
}

def expandir_consulta(query: str) -> list[str]:
    q = query.strip().lower()
    terminos = [query.strip()]
    if q in SINONIMOS:
        terminos.extend(SINONIMOS[q])
    for clave, sins in SINONIMOS.items():
        if clave in q and clave != q:
            terminos.extend(sins)
    vistos, unicos = set(), []
    for t in terminos:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            unicos.append(t)
    return unicos

# ═══════════════════════════════════════════════════════════════
# CARGA DE DATOS (RDS)
# ═══════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Cargando repositorio…")
def cargar_datos() -> pd.DataFrame:
    try:
        import pyreadr
        resultado = pyreadr.read_r(RDS_PATH)
        df = resultado[None] if None in resultado else list(resultado.values())[0]
        if "year" in df.columns:
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
        if "handle" in df.columns:
            def norm_handle(h):
                if pd.isna(h): return None
                h = str(h).strip()
                return h if h.startswith("http") else f"https://cgspace.cgiar.org/handle/{h}"
            df["handle"] = df["handle"].apply(norm_handle)
        return df.reset_index(drop=True)
    except FileNotFoundError:
        st.error(f"Archivo `{RDS_PATH}` no encontrado. Colócalo junto a cgspace_app.py")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer RDS: {e}")
        return pd.DataFrame()

DF_FULL = cargar_datos()  # DataFrame completo, solo lectura

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE ANÁLISIS
# ═══════════════════════════════════════════════════════════════
def extraer_temas(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    if "agrovoc_subject" not in df.columns or df.empty:
        return pd.DataFrame(columns=["Tema", "Docs"])
    temas = []
    for v in df["agrovoc_subject"].dropna():
        temas.extend([t.strip() for t in str(v).split(",") if t.strip()])
    if not temas:
        return pd.DataFrame(columns=["Tema", "Docs"])
    data = Counter(temas).most_common(top_n)
    return pd.DataFrame(data, columns=["Tema", "Docs"])

def conteo_paises(df: pd.DataFrame) -> pd.DataFrame:
    if "country" not in df.columns or df.empty:
        return pd.DataFrame(columns=["País", "Docs"])
    c = df["country"].dropna().value_counts().reset_index()
    c.columns = ["País", "Docs"]
    return c

def stats_generales(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return {
        "total":    len(df),
        "paises":   df["country"].dropna().nunique() if "country" in df.columns else 0,
        "años":     (int(df["year"].min()), int(df["year"].max()))
                    if "year" in df.columns and df["year"].notna().any() else (0, 0),
        "tipos":    df["type"].dropna().nunique() if "type" in df.columns else 0,
        "funders":  df["investor_funder_sponsor"].dropna().nunique()
                    if "investor_funder_sponsor" in df.columns else 0,
    }

# ═══════════════════════════════════════════════════════════════
# BÚSQUEDAS
# ═══════════════════════════════════════════════════════════════
def buscar_csv(terminos: list[str], year_range: tuple, max_results: int = 500) -> pd.DataFrame:
    df = DF_FULL
    if df.empty or not terminos:
        return pd.DataFrame()

    # Filtro por año ANTES de buscar texto (más eficiente)
    if "year" in df.columns and year_range:
        df = df[df["year"].between(year_range[0], year_range[1])]

    campos = [c for c in CSV_SEARCH_FIELDS if c in df.columns]
    if not campos:
        return pd.DataFrame()

    mask = pd.Series(False, index=df.index)
    for t in terminos:
        tl = t.lower()
        for col in campos:
            mask |= df[col].astype(str).str.lower().str.contains(tl, na=False, regex=False)

    resultado = df[mask].copy()
    if "year" in resultado.columns:
        resultado = resultado.sort_values("year", ascending=False)
    return resultado.head(max_results).reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner="Consultando CGSpace API…")
def buscar_api(terminos_tuple: tuple, year_min: int, year_max: int) -> pd.DataFrame:
    """Cache-friendly: recibe tupla en lugar de lista."""
    terminos = list(terminos_tuple)
    if not terminos:
        return pd.DataFrame()

    todos, handles_vistos = [], set()

    for termino in terminos[:3]:
        for page in range(3):          # hasta 3 páginas por término
            try:
                resp = requests.get(
                    CGSPACE_API,
                    params={"query": termino, "page": page, "size": 50},
                    timeout=30,
                )
                resp.raise_for_status()
                objects = (resp.json()
                           .get("_embedded", {})
                           .get("searchResult", {})
                           .get("_embedded", {})
                           .get("objects", []))
                if not objects:
                    break
                for obj in objects:
                    idx   = obj.get("_embedded", {}).get("indexableObject", {})
                    handle = idx.get("handle")
                    if not handle or handle in handles_vistos:
                        continue
                    handles_vistos.add(handle)
                    parsed = _parsear_api(idx)
                    if parsed:
                        todos.append(parsed)
            except Exception:
                break

    if not todos:
        return pd.DataFrame()

    df = pd.DataFrame(todos)

    # Filtro de relevancia
    def relevante(row):
        txt = row.get("_txt", "")
        return any(t.lower() in txt for t in terminos) if txt else True

    df = df[df.apply(relevante, axis=1)].drop(columns=["_txt"], errors="ignore")

    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        # Aplicar filtro de año del sidebar
        df = df[df["year"].between(year_min, year_max)]
        df = df.sort_values("year", ascending=False)

    return df.reset_index(drop=True)


def _parsear_api(idx: dict) -> dict | None:
    meta   = idx.get("metadata", {})
    handle = idx.get("handle")

    titulo = next(
        (meta[k][0].get("value") for k in ["dc.title", "dcterms.title"] if k in meta),
        idx.get("name"),
    )
    if not titulo:
        return None

    year = None
    for k in ["dcterms.issued", "dc.date.issued"]:
        if k in meta:
            for e in meta[k]:
                v = str(e.get("value", ""))
                if len(v) >= 4 and v[:4].isdigit():
                    c = int(v[:4])
                    if 1970 <= c <= 2025:
                        year = c
                        break
        if year:
            break

    pais = next(
        (meta[k][0].get("value") for k in
         ["cg.country", "cg.coverage.country", "dc.coverage.spatial"] if k in meta),
        None,
    )
    temas = next(
        ([e.get("value", "") for e in meta[k] if e.get("value")]
         for k in ["cg.subject.cgiar", "cg.subject", "dc.subject"] if k in meta),
        [],
    )
    tipo = next(
        (meta[k][0].get("value") for k in ["dc.type", "dcterms.type"] if k in meta),
        None,
    )
    funder_vals = next(
        ([e.get("value", "") for e in meta[k] if e.get("value")]
         for k in ["cg.contributor.funder", "dc.contributor.funder"] if k in meta),
        [],
    )

    return {
        "title":                   titulo,
        "year":                    year,
        "type":                    tipo,
        "country":                 pais,
        "agrovoc_subject":         ", ".join(temas) if temas else None,
        "investor_funder_sponsor": "; ".join(funder_vals[:3]) if funder_vals else None,
        "handle":                  f"https://cgspace.cgiar.org/handle/{handle}" if handle else None,
        "_txt":                    (titulo + " " + " ".join(temas)).lower(),
    }

# ═══════════════════════════════════════════════════════════════
# ESTADO DE SESIÓN
# ═══════════════════════════════════════════════════════════════
for k, v in {
    "resultados":        pd.DataFrame(),
    "last_query":        "",
    "terminos":          [],
    "fuente_usada":      "",
    "filtro_pais":       None,   # país seleccionado en el mapa
    "filtro_tema":       None,   # tema seleccionado en el gráfico
    "doc_seleccionado":  None,   # índice del doc para el panel de detalle
    "modo":              "inicio",  # "inicio" | "resultados"
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🌱 CGSpace Explorer")
    st.markdown("---")

    # 1. Fuente
    st.markdown("### 1 · Fuente de datos")
    fuente = st.radio(
        "fuente",
        ["📂  Base local (175k docs)", "🌐  API CGSpace (en vivo)"],
        label_visibility="collapsed",
        help="La base local es más completa y rápida. La API trae documentos en tiempo real.",
    )
    usar_csv = fuente.startswith("📂")

    st.markdown("---")

    # 2. Filtro de años
    st.markdown("### 2 · Rango de años")
    if not DF_FULL.empty and "year" in DF_FULL.columns and DF_FULL["year"].notna().any():
        año_global_min = int(DF_FULL["year"].min())
        año_global_max = int(DF_FULL["year"].max())
    else:
        año_global_min, año_global_max = 1970, 2025

    year_range = st.slider(
        "años",
        min_value=año_global_min,
        max_value=año_global_max,
        value=(2000, año_global_max),
        label_visibility="collapsed",
    )
    st.caption(f"Buscando en: **{year_range[0]} – {year_range[1]}**")

    st.markdown("---")

    # 3. Consulta
    st.markdown("### 3 · Búsqueda")
    query_input = st.text_input(
        "consulta",
        placeholder="Ej: agroecología, gender Kenya, drought…",
        label_visibility="collapsed",
    )
    buscar_btn = st.button("🔍  Buscar", use_container_width=True, type="primary")

    # Ejecutar búsqueda
    if buscar_btn and query_input.strip():
        terminos = expandir_consulta(query_input)
        st.session_state.last_query       = query_input
        st.session_state.terminos         = terminos
        st.session_state.filtro_pais      = None
        st.session_state.filtro_tema      = None
        st.session_state.doc_seleccionado = None
        st.session_state.modo             = "resultados"

        if usar_csv:
            with st.spinner("Buscando en base local…"):
                df_res = buscar_csv(terminos, year_range)
            st.session_state.fuente_usada = "Base local (CSV)"
        else:
            with st.spinner("Consultando API…"):
                df_res = buscar_api(tuple(terminos), year_range[0], year_range[1])
            st.session_state.fuente_usada = "API CGSpace"

        st.session_state.resultados = df_res

    # Botón volver al inicio
    if st.session_state.modo == "resultados":
        st.markdown("---")
        if st.button("← Volver al inicio", use_container_width=True):
            st.session_state.modo             = "inicio"
            st.session_state.resultados       = pd.DataFrame()
            st.session_state.last_query       = ""
            st.session_state.filtro_pais      = None
            st.session_state.filtro_tema      = None
            st.session_state.doc_seleccionado = None

    # Términos expandidos
    if st.session_state.terminos and len(st.session_state.terminos) > 1:
        st.markdown("---")
        st.markdown("**Términos usados:**")
        st.caption("  ·  ".join(st.session_state.terminos[:6]))

    # Info repositorio
    if not DF_FULL.empty:
        st.markdown("---")
        st.caption(f"📦 Repositorio local: **{len(DF_FULL):,}** documentos")


# ═══════════════════════════════════════════════════════════════
# PANTALLA DE INICIO
# ═══════════════════════════════════════════════════════════════
def pantalla_inicio():
    st.markdown("# CGSpace Explorer")
    st.markdown("Explora la producción de conocimiento de CGIAR. Usa el panel izquierdo para buscar.")
    st.markdown("---")

    if DF_FULL.empty:
        st.info("Base de datos no cargada. Verifica que el archivo RDS esté en la carpeta correcta.")
        return

    stats = stats_generales(DF_FULL)

    # KPIs globales
    st.markdown("## Resumen del repositorio")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total de documentos",  f"{stats['total']:,}")
    k2.metric("Países cubiertos",     stats["paises"])
    k3.metric("Período",              f"{stats['años'][0]} – {stats['años'][1]}")
    k4.metric("Tipos de documento",   stats["tipos"])
    k5.metric("Financiadores únicos", stats["funders"])

    st.markdown("---")

    col_izq, col_der = st.columns([1.1, 0.9])

    with col_izq:
        st.markdown("### Distribución geográfica")
        cp = conteo_paises(DF_FULL)
        if not cp.empty:
            fig = px.choropleth(
                cp, locations="País", locationmode="country names",
                color="Docs", color_continuous_scale="Greens",
                height=340,
            )
            fig.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                              coloraxis_colorbar=dict(title="Docs"))
            st.plotly_chart(fig, use_container_width=True, key="mapa_inicio")

            st.dataframe(
                cp.head(10),
                use_container_width=True, hide_index=True, height=200,
                column_config={"Docs": st.column_config.ProgressColumn(
                    "Docs", format="%d", min_value=0, max_value=int(cp["Docs"].max())
                )},
            )

    with col_der:
        st.markdown("### Publicaciones por año")
        if "year" in DF_FULL.columns and DF_FULL["year"].notna().any():
            pa = DF_FULL.groupby("year").size().reset_index(name="Docs").sort_values("year")
            fig2 = px.area(pa, x="year", y="Docs",
                           color_discrete_sequence=["#16a34a"], height=220)
            fig2.update_layout(margin=dict(l=0, r=0, t=5, b=0), xaxis_title="")
            fig2.update_traces(line_color="#16a34a", fillcolor="rgba(22,163,74,0.15)")
            st.plotly_chart(fig2, use_container_width=True, key="timeline_inicio")

        st.markdown("### Temas más frecuentes")
        dt = extraer_temas(DF_FULL, top_n=12)
        if not dt.empty:
            fig3 = px.bar(dt.sort_values("Docs"), x="Docs", y="Tema",
                          orientation="h", color="Docs",
                          color_continuous_scale="Greens", height=330)
            fig3.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                               coloraxis_showscale=False, yaxis_title="")
            st.plotly_chart(fig3, use_container_width=True, key="temas_inicio")

    st.markdown("---")

    # Top financiadores
    if "investor_funder_sponsor" in DF_FULL.columns:
        st.markdown("### Top financiadores")
        funders = []
        for v in DF_FULL["investor_funder_sponsor"].dropna():
            funders.extend([f.strip() for f in str(v).split(";") if f.strip()])
        if funders:
            df_f = pd.DataFrame(Counter(funders).most_common(10), columns=["Financiador", "Docs"])
            fig4 = px.bar(df_f.sort_values("Docs"), x="Docs", y="Financiador",
                          orientation="h", color_discrete_sequence=["#15803d"], height=280)
            fig4.update_layout(margin=dict(l=0, r=0, t=5, b=0), yaxis_title="")
            st.plotly_chart(fig4, use_container_width=True, key="funders_inicio")

    st.markdown("---")
    st.info("👈 Usa el panel izquierdo para buscar por tema, país, autor o cualquier término.")


# ═══════════════════════════════════════════════════════════════
# PANTALLA DE RESULTADOS
# ═══════════════════════════════════════════════════════════════
def pantalla_resultados():
    df_raw = st.session_state.resultados

    # Header
    st.markdown(f"# Resultados para «{st.session_state.last_query}»")
    st.caption(f"Fuente: **{st.session_state.fuente_usada}**  ·  "
               f"Términos: {', '.join(st.session_state.terminos[:5])}")
    st.markdown("---")

    if df_raw.empty:
        st.warning("No se encontraron documentos. Intenta con otros términos o amplía el rango de años.")
        return

    # ── Filtros activos (país y tema, seleccionados desde gráficos) ──
    df = df_raw.copy()
    filtros_activos = []

    if st.session_state.filtro_pais:
        df = df[df["country"] == st.session_state.filtro_pais]
        filtros_activos.append(f"País: {st.session_state.filtro_pais}")

    if st.session_state.filtro_tema:
        df = df[df["agrovoc_subject"].astype(str).str.contains(
            st.session_state.filtro_tema, case=False, na=False
        )]
        filtros_activos.append(f"Tema: {st.session_state.filtro_tema}")

    # Mostrar badges de filtros activos + botón limpiar
    if filtros_activos:
        col_b, col_clear = st.columns([4, 1])
        with col_b:
            badges = "  ".join([f'<span class="filter-badge">✕ {f}</span>' for f in filtros_activos])
            st.markdown(badges, unsafe_allow_html=True)
        with col_clear:
            if st.button("Limpiar filtros"):
                st.session_state.filtro_pais = None
                st.session_state.filtro_tema = None
                st.rerun()

    # ── KPIs (siempre reflejan df filtrado) ──
    total   = len(df)
    n_pais  = df["country"].dropna().nunique() if "country" in df.columns else 0
    n_tipos = df["type"].dropna().nunique()    if "type"    in df.columns else 0
    año_max = int(df["year"].max()) if "year" in df.columns and df["year"].notna().any() else "N/D"
    año_min = int(df["year"].min()) if "year" in df.columns and df["year"].notna().any() else "N/D"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Documentos",  f"{total:,}")
    k2.metric("Países",      n_pais)
    k3.metric("Tipos",       n_tipos)
    k4.metric("Período",     f"{año_min}–{año_max}" if isinstance(año_min, int) else "N/D")

    st.markdown("---")

    # ── Visualizaciones interactivas ──
    col_izq, col_der = st.columns([1.1, 0.9])

    with col_izq:
        st.markdown("### 🌍 Por país  *(clic para filtrar)*")
        cp = conteo_paises(df)
        if not cp.empty:
            fig_mapa = px.choropleth(
                cp, locations="País", locationmode="country names",
                color="Docs", color_continuous_scale="Greens", height=320,
                custom_data=["País"],
            )
            fig_mapa.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                                   coloraxis_colorbar=dict(title=""))
            fig_mapa.update_traces(
                hovertemplate="<b>%{customdata[0]}</b><br>Docs: %{z}<extra></extra>"
            )
            sel_mapa = st.plotly_chart(
                fig_mapa, use_container_width=True,
                on_select="rerun", key="mapa_res",
            )
            # Capturar selección del mapa
            if sel_mapa and sel_mapa.get("selection", {}).get("points"):
                pais_click = sel_mapa["selection"]["points"][0].get("location")
                if pais_click and pais_click != st.session_state.filtro_pais:
                    st.session_state.filtro_pais = pais_click
                    st.rerun()

            # Tabla top países (clic para filtrar)
            st.markdown("**Top países** — selecciona para filtrar")
            for _, row in cp.head(8).iterrows():
                pais_n, docs_n = row["País"], int(row["Docs"])
                activo = st.session_state.filtro_pais == pais_n
                label  = f"{'✓ ' if activo else ''}{pais_n}  ({docs_n:,} docs)"
                if st.button(label, key=f"btn_pais_{pais_n}",
                             type="primary" if activo else "secondary",
                             use_container_width=True):
                    if activo:
                        st.session_state.filtro_pais = None
                    else:
                        st.session_state.filtro_pais = pais_n
                    st.rerun()
        else:
            st.info("Sin datos de países.")

    with col_der:
        # Timeline
        st.markdown("### 📅 Por año")
        if "year" in df.columns and df["year"].notna().any():
            pa = df.groupby("year").size().reset_index(name="Docs").sort_values("year")
            fig_t = px.bar(pa, x="year", y="Docs",
                           color_discrete_sequence=["#16a34a"], height=210)
            fig_t.update_layout(margin=dict(l=0, r=0, t=5, b=0), xaxis_title="")
            st.plotly_chart(fig_t, use_container_width=True, key="timeline_res")

        # Temas (clic para filtrar)
        st.markdown("### 🏷️ Temas  *(clic para filtrar)*")
        dt = extraer_temas(df, top_n=12)
        if not dt.empty:
            fig_temas = px.bar(
                dt.sort_values("Docs"), x="Docs", y="Tema",
                orientation="h", color="Docs",
                color_continuous_scale="Greens", height=310,
                custom_data=["Tema"],
            )
            fig_temas.update_layout(margin=dict(l=0, r=0, t=5, b=0),
                                    coloraxis_showscale=False, yaxis_title="")
            sel_temas = st.plotly_chart(
                fig_temas, use_container_width=True,
                on_select="rerun", key="temas_res",
            )
            if sel_temas and sel_temas.get("selection", {}).get("points"):
                tema_click = sel_temas["selection"]["points"][0].get("y")
                if tema_click and tema_click != st.session_state.filtro_tema:
                    st.session_state.filtro_tema = tema_click
                    st.rerun()

    st.markdown("---")

    # ── Tabla de documentos ──
    st.markdown(f"### 📄 Documentos ({total:,})")

    cols_tabla = [c for c in ["title", "year", "type", "country",
                               "agrovoc_subject", "investor_funder_sponsor"]
                  if c in df.columns]

    evento = st.dataframe(
        df[cols_tabla].reset_index(drop=True),
        use_container_width=True,
        height=400,
        on_select="rerun",
        selection_mode="single-row",
        key="tabla_docs",
        column_config={
            "title":                   st.column_config.TextColumn("Título", width="large"),
            "year":                    st.column_config.NumberColumn("Año", format="%d", width="small"),
            "type":                    st.column_config.TextColumn("Tipo", width="medium"),
            "country":                 st.column_config.TextColumn("País", width="small"),
            "agrovoc_subject":         st.column_config.TextColumn("Temas", width="large"),
            "investor_funder_sponsor": st.column_config.TextColumn("Financiador", width="medium"),
        },
    )

    # Capturar fila seleccionada
    filas_sel = evento.get("selection", {}).get("rows", []) if evento else []
    if filas_sel:
        st.session_state.doc_seleccionado = filas_sel[0]

    # ── Panel de detalle del documento ──
    if st.session_state.doc_seleccionado is not None:
        idx = st.session_state.doc_seleccionado
        if idx < len(df):
            doc = df.iloc[idx]
            titulo   = doc.get("title", "Sin título")
            año      = int(doc["year"]) if pd.notna(doc.get("year")) else "N/D"
            tipo     = doc.get("type", "N/D")
            pais     = doc.get("country", "N/D")
            temas_d  = doc.get("agrovoc_subject", "")
            funder   = doc.get("investor_funder_sponsor", "")
            handle   = doc.get("handle", None)

            temas_tags = ""
            if temas_d and str(temas_d) != "nan":
                temas_tags = "".join(
                    f'<span class="doc-tag">{t.strip()}</span>'
                    for t in str(temas_d).split(",") if t.strip()
                )

            enlace_html = (f'<a href="{handle}" target="_blank" '
                           f'style="color:#16a34a;font-weight:600;">🔗 Ver en CGSpace</a>'
                           if handle else "")

            st.markdown(f"""
            <div class="doc-card">
                <h4>{titulo}</h4>
                <p>📅 <strong>{año}</strong> &nbsp;·&nbsp;
                   📁 <strong>{tipo}</strong> &nbsp;·&nbsp;
                   🌍 <strong>{pais}</strong></p>
                {"<p>💰 " + str(funder)[:120] + ("…" if len(str(funder)) > 120 else "") + "</p>" if funder and str(funder) != "nan" else ""}
                <p style="margin-top:0.4rem">{temas_tags}</p>
                <p style="margin-top:0.5rem">{enlace_html}</p>
            </div>
            """, unsafe_allow_html=True)

            if st.button("✕ Cerrar detalle", key="cerrar_detalle"):
                st.session_state.doc_seleccionado = None
                st.rerun()

    st.markdown("---")

    # ── Descarga ──
    cols_desc = [c for c in ["title", "year", "type", "country",
                              "agrovoc_subject", "investor_funder_sponsor", "handle"]
                 if c in df.columns]
    csv_bytes = df[cols_desc].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Descargar resultados (CSV)",
        data=csv_bytes,
        file_name=f"cgspace_{st.session_state.last_query[:25].replace(' ', '_')}.csv",
        mime="text/csv",
    )


# ═══════════════════════════════════════════════════════════════
# ROUTER PRINCIPAL
# ═══════════════════════════════════════════════════════════════
if st.session_state.modo == "inicio":
    pantalla_inicio()
else:
    pantalla_resultados()
