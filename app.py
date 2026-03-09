"""
CGSpace Explorer
================
Dos fuentes de búsqueda independientes:
  1. CSV local  – 175k documentos, búsqueda instantánea en título/autor/agrovoc/país/funder
  2. API CGSpace – consulta en vivo con expansión de términos y filtro de relevancia

Una sola fuente de verdad por tab: KPIs, gráficos y tabla siempre reflejan
exactamente los mismos documentos filtrados.
"""

import streamlit as st
import pandas as pd
import requests
from collections import Counter
import plotly.express as px
import pyreadr

# ─────────────────────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CGSpace Explorer",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.stMetric label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: .04em; }
.stMetric [data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; color: #15803d; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────
RDS_PATH    = "base_cgspace_completa.rds"  # archivo RDS exportado desde R
CGSPACE_API = "https://cgspace.cgiar.org/server/api/discover/search/objects"

# Campos del CSV en los que se hace la búsqueda de texto
CSV_SEARCH_FIELDS = [
    "title", "author", "agrovoc_subject",
    "country", "investor_funder_sponsor", "repository_collection",
]

# ─────────────────────────────────────────────────────────────
# Diccionario de sinónimos ES → EN
# ─────────────────────────────────────────────────────────────
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
    """Devuelve la consulta original + sinónimos, sin duplicados."""
    q = query.strip().lower()
    terminos = [query.strip()]

    if q in SINONIMOS:
        terminos.extend(SINONIMOS[q])

    for clave, sinonimos in SINONIMOS.items():
        if clave in q and clave != q:
            terminos.extend(sinonimos)

    vistos, unicos = set(), []
    for t in terminos:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            unicos.append(t)
    return unicos


# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
# Carga del RDS (cacheada — solo se lee una vez)
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando base de datos local…")
def cargar_datos() -> pd.DataFrame:
    """
    Lee el archivo RDS exportado desde R con pyreadr.
    pyreadr.read_r() devuelve un dict; el df está bajo la clave None.
    """
    try:
        resultado = pyreadr.read_r(RDS_PATH)
        df = resultado[None] if None in resultado else list(resultado.values())[0]
        if "year" in df.columns:
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
        if "handle" in df.columns:
            def normalizar_handle(h):
                if pd.isna(h): return None
                h = str(h).strip()
                return h if h.startswith("http") else f"https://cgspace.cgiar.org/handle/{h}"
            df["handle"] = df["handle"].apply(normalizar_handle)
        return df.reset_index(drop=True)
    except FileNotFoundError:
        st.error(f"Archivo no encontrado: `{RDS_PATH}`. Colócalo junto a cgspace_app.py")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer el RDS: {e}")
        return pd.DataFrame()

df_csv_global = cargar_datos()


# ─────────────────────────────────────────────────────────────
# BÚSQUEDA EN CSV
# ─────────────────────────────────────────────────────────────
def buscar_csv(terminos: list[str], max_results: int = 500) -> pd.DataFrame:
    """
    Un documento aparece si AL MENOS UN término está presente
    en cualquiera de los campos de CSV_SEARCH_FIELDS.
    """
    df = df_csv_global
    if df.empty or not terminos:
        return pd.DataFrame()

    campos = [c for c in CSV_SEARCH_FIELDS if c in df.columns]
    if not campos:
        return pd.DataFrame()

    mask = pd.Series(False, index=df.index)
    for termino in terminos:
        t = termino.lower()
        for col in campos:
            mask |= df[col].astype(str).str.lower().str.contains(t, na=False, regex=False)

    resultado = df[mask].copy()
    if "year" in resultado.columns:
        resultado = resultado.sort_values("year", ascending=False)

    return resultado.head(max_results).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# BÚSQUEDA EN API CGSPACE
# ─────────────────────────────────────────────────────────────
def _parsear_item_api(indexable: dict) -> dict | None:
    metadata = indexable.get("metadata", {})
    handle   = indexable.get("handle")
    enlace   = f"https://cgspace.cgiar.org/handle/{handle}" if handle else None

    # Título
    titulo = None
    for key in ["dc.title", "dcterms.title"]:
        if key in metadata:
            titulo = metadata[key][0].get("value")
            break
    if not titulo:
        titulo = indexable.get("name")
    if not titulo:
        return None

    # Año (solo 1970-2025)
    year = None
    for key in ["dcterms.issued", "dc.date.issued"]:
        if key in metadata:
            for entry in metadata[key]:
                v = str(entry.get("value", ""))
                if len(v) >= 4 and v[:4].isdigit():
                    c = int(v[:4])
                    if 1970 <= c <= 2025:
                        year = c
                        break
        if year:
            break

    # País
    pais = None
    for key in ["cg.country", "cg.coverage.country", "dc.coverage.spatial"]:
        if key in metadata:
            vals = [e.get("value", "") for e in metadata[key] if e.get("value")]
            if vals:
                pais = vals[0]
                break

    # Temas
    temas = []
    for key in ["cg.subject.cgiar", "cg.subject", "dc.subject", "dcterms.subject"]:
        if key in metadata:
            temas = [e.get("value", "") for e in metadata[key] if e.get("value")]
            if temas:
                break

    # Tipo
    tipo = None
    for key in ["dc.type", "dcterms.type"]:
        if key in metadata:
            tipo = metadata[key][0].get("value")
            break

    # Financiador
    funder = None
    for key in ["cg.contributor.funder", "dc.contributor.funder"]:
        if key in metadata:
            vals = [e.get("value", "") for e in metadata[key] if e.get("value")]
            if vals:
                funder = "; ".join(vals[:3])
                break

    return {
        "title":                   titulo,
        "year":                    year,
        "type":                    tipo,
        "country":                 pais,
        "agrovoc_subject":         ", ".join(temas) if temas else None,
        "investor_funder_sponsor": funder,
        "handle":                  enlace,
        "_texto":                  (titulo + " " + " ".join(temas)).lower(),
    }


@st.cache_data(ttl=600, show_spinner="Consultando CGSpace API…")
def buscar_api(terminos: list[str], pages_per_term: int = 2, size: int = 50) -> pd.DataFrame:
    """
    Sin sort por fecha → distribución real de años.
    Filtra post-fetch para garantizar relevancia real.
    """
    if not terminos:
        return pd.DataFrame()

    todos: list[dict] = []
    handles_vistos: set[str] = set()

    for termino in terminos[:3]:
        for page in range(pages_per_term):
            try:
                resp = requests.get(
                    CGSPACE_API,
                    params={"query": termino, "page": page, "size": size},
                    timeout=30,
                )
                resp.raise_for_status()
                objects = (
                    resp.json()
                    .get("_embedded", {})
                    .get("searchResult", {})
                    .get("_embedded", {})
                    .get("objects", [])
                )
                if not objects:
                    break
                for obj in objects:
                    indexable = obj.get("_embedded", {}).get("indexableObject", {})
                    handle    = indexable.get("handle")
                    if not handle or handle in handles_vistos:
                        continue
                    handles_vistos.add(handle)
                    parsed = _parsear_item_api(indexable)
                    if parsed:
                        todos.append(parsed)
            except Exception:
                break

    if not todos:
        return pd.DataFrame()

    df = pd.DataFrame(todos)

    # Filtro de relevancia: al menos un término en título o temas
    def es_relevante(row):
        texto = row.get("_texto", "")
        return any(t.lower() in texto for t in terminos) if texto else True

    df = df[df.apply(es_relevante, axis=1)].drop(columns=["_texto"], errors="ignore")

    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df.sort_values("year", ascending=False)

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# Funciones de análisis
# ─────────────────────────────────────────────────────────────
def extraer_temas(df: pd.DataFrame, top_n: int = 15) -> list[tuple[str, int]]:
    col = "agrovoc_subject"
    if col not in df.columns or df.empty:
        return []
    temas = []
    for val in df[col].dropna():
        temas.extend([t.strip() for t in str(val).split(",") if t.strip()])
    return Counter(temas).most_common(top_n)


def aplicar_filtros(df, year_range, paises_sel, tipos_sel) -> pd.DataFrame:
    out = df.copy()
    if year_range and "year" in out.columns and out["year"].notna().any():
        out = out[out["year"].between(year_range[0], year_range[1])]
    if paises_sel and "country" in out.columns:
        out = out[out["country"].isin(paises_sel)]
    if tipos_sel and "type" in out.columns:
        out = out[out["type"].isin(tipos_sel)]
    return out


# ─────────────────────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────────────────────
for k, v in {
    "df_csv_results": pd.DataFrame(),
    "df_api_results": pd.DataFrame(),
    "last_query":     "",
    "terminos":       [],
    "chat_history":   [],
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌱 CGSpace Explorer")
    st.markdown("---")
    st.markdown("### Búsqueda")

    query_input = st.text_input(
        "Consulta",
        placeholder="Ej: agroecología, gender, drought Kenya",
        label_visibility="collapsed",
    )
    buscar_btn = st.button("🔍  Buscar en ambas fuentes", use_container_width=True, type="primary")

    if buscar_btn and query_input.strip():
        terminos = expandir_consulta(query_input)
        st.session_state.last_query = query_input
        st.session_state.terminos   = terminos

        with st.spinner("Buscando en CSV…"):
            st.session_state.df_csv_results = buscar_csv(terminos)
        with st.spinner("Consultando API…"):
            st.session_state.df_api_results = buscar_api(terminos)

    if st.session_state.terminos:
        st.markdown("**Términos buscados:**")
        st.caption("  ·  ".join(st.session_state.terminos[:6]))
        if len(st.session_state.terminos) > 6:
            st.caption(f"… y {len(st.session_state.terminos)-6} más")

    st.markdown("---")
    if not df_csv_global.empty:
        st.markdown(f"📂 **Base local:** {len(df_csv_global):,} docs")
    else:
        st.warning(f"RDS no encontrado.\nRuta esperada: `{RDS_PATH}`")


# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
st.markdown("# CGSpace Explorer")
if st.session_state.last_query:
    st.caption(f"Consulta: **{st.session_state.last_query}**")
else:
    st.caption("Introduce una búsqueda en el panel izquierdo para comenzar.")
st.markdown("---")

tab_csv, tab_api, tab_chat = st.tabs([
    "📂  Base local (CSV)",
    "🌐  API CGSpace (en vivo)",
    "💬  Consultas libres",
])


# ─────────────────────────────────────────────────────────────
# Función reutilizable de renderizado
# ─────────────────────────────────────────────────────────────
def render_resultados(df_raw: pd.DataFrame, fuente_label: str, tab_key: str):
    """
    Renderiza filtros → KPIs → visualizaciones → tabla para un DataFrame.
    Todo lo que se muestra en pantalla proviene del mismo df filtrado.
    """
    if df_raw.empty and not st.session_state.last_query:
        st.info("👈 Introduce una búsqueda en el panel izquierdo.")
        return

    if df_raw.empty:
        st.warning(
            f"No se encontraron documentos para **{st.session_state.last_query}** "
            f"en {fuente_label}. Prueba con otros términos."
        )
        return

    # ── Filtros ──
    with st.expander("⚙️ Filtros", expanded=False):
        fc1, fc2, fc3 = st.columns(3)

        year_range = None
        if "year" in df_raw.columns and df_raw["year"].notna().any():
            años = sorted(df_raw["year"].dropna().astype(int).unique().tolist())
            if len(años) > 1:
                year_range = fc1.slider(
                    "Rango de años",
                    min_value=min(años), max_value=max(años),
                    value=(min(años), max(años)),
                    key=f"{tab_key}_year",
                )
            else:
                fc1.write(f"Año: **{años[0]}**")

        paises_sel = None
        if "country" in df_raw.columns:
            paises = sorted(df_raw["country"].dropna().unique().tolist())
            if paises:
                paises_sel = fc2.multiselect(
                    "País", paises, default=paises, key=f"{tab_key}_pais"
                )

        tipos_sel = None
        if "type" in df_raw.columns:
            tipos = sorted(df_raw["type"].dropna().unique().tolist())
            if tipos:
                tipos_sel = fc3.multiselect(
                    "Tipo", tipos, default=tipos, key=f"{tab_key}_tipo"
                )

    # df es la ÚNICA fuente de verdad a partir de aquí
    df = aplicar_filtros(df_raw, year_range, paises_sel, tipos_sel)

    # ── KPIs ──
    total    = len(df)
    n_paises = df["country"].dropna().nunique() if "country" in df.columns else 0
    n_tipos  = df["type"].dropna().nunique()    if "type"    in df.columns else 0
    año_max  = int(df["year"].max()) if "year" in df.columns and df["year"].notna().any() else "N/D"
    año_min  = int(df["year"].min()) if "year" in df.columns and df["year"].notna().any() else "N/D"
    temas_t1 = extraer_temas(df, top_n=1)
    tema_1   = temas_t1[0][0] if temas_t1 else "N/D"

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Documentos",       f"{total:,}")
    k2.metric("Países",           n_paises)
    k3.metric("Tipos de doc.",    n_tipos)
    k4.metric("Período",          f"{año_min}–{año_max}" if isinstance(año_min, int) else "N/D")
    k5.metric("Tema principal",   tema_1)

    st.markdown("---")

    # ── Visualizaciones ──
    col_izq, col_der = st.columns([1.15, 0.85])

    with col_izq:
        st.markdown("#### 🌍 Documentos por país")
        if "country" in df.columns and df["country"].notna().any():
            conteo = (
                df["country"].dropna()
                .value_counts()
                .reset_index()
                .rename(columns={"country": "País", "count": "Documentos"})
            )
            fig_mapa = px.choropleth(
                conteo,
                locations="País",
                locationmode="country names",
                color="Documentos",
                color_continuous_scale="Greens",
                height=340,
            )
            fig_mapa.update_layout(
                margin=dict(l=0, r=0, t=5, b=0),
                coloraxis_colorbar=dict(title=""),
            )
            st.plotly_chart(fig_mapa, use_container_width=True, key=f"{tab_key}_mapa")

            st.dataframe(
                conteo.head(10),
                use_container_width=True,
                hide_index=True,
                height=220,
                column_config={
                    "Documentos": st.column_config.ProgressColumn(
                        "Documentos", format="%d",
                        min_value=0, max_value=int(conteo["Documentos"].max()),
                    )
                },
            )
        else:
            st.info("Sin datos de países en esta búsqueda.")

    with col_der:
        st.markdown("#### 📅 Publicaciones por año")
        if "year" in df.columns and df["year"].notna().any():
            docs_año = (
                df.groupby("year").size()
                .reset_index(name="Documentos")
                .sort_values("year")
            )
            fig_t = px.bar(
                docs_año, x="year", y="Documentos",
                color_discrete_sequence=["#16a34a"],
                height=220,
            )
            fig_t.update_layout(margin=dict(l=0, r=0, t=5, b=0), xaxis_title="")
            st.plotly_chart(fig_t, use_container_width=True, key=f"{tab_key}_timeline")
        else:
            st.info("Sin datos de año.")

        st.markdown("#### 🏷️ Temas más frecuentes")
        temas_lista = extraer_temas(df, top_n=12)
        if temas_lista:
            df_t = pd.DataFrame(temas_lista, columns=["Tema", "Docs"])
            fig_temas = px.bar(
                df_t.sort_values("Docs"),
                x="Docs", y="Tema",
                orientation="h",
                color="Docs",
                color_continuous_scale="Greens",
                height=320,
            )
            fig_temas.update_layout(
                margin=dict(l=0, r=0, t=5, b=0),
                coloraxis_showscale=False,
                yaxis_title="",
            )
            st.plotly_chart(fig_temas, use_container_width=True, key=f"{tab_key}_temas")
        else:
            st.info("Sin palabras clave disponibles.")

    st.markdown("---")

    # ── Tabla ──
    st.markdown(f"#### 📄 Documentos ({total:,})")

    cols_tabla = [c for c in [
        "title", "year", "type", "country",
        "agrovoc_subject", "investor_funder_sponsor", "handle",
    ] if c in df.columns]

    st.dataframe(
        df[cols_tabla].reset_index(drop=True),
        use_container_width=True,
        height=440,
        column_config={
            "title":                   st.column_config.TextColumn("Título", width="large"),
            "year":                    st.column_config.NumberColumn("Año", format="%d", width="small"),
            "type":                    st.column_config.TextColumn("Tipo", width="medium"),
            "country":                 st.column_config.TextColumn("País", width="medium"),
            "agrovoc_subject":         st.column_config.TextColumn("Temas (AGROVOC)", width="large"),
            "investor_funder_sponsor": st.column_config.TextColumn("Financiador", width="medium"),
            "handle":                  st.column_config.LinkColumn("Enlace", width="small"),
        },
    )

    csv_bytes = df[cols_tabla].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Descargar resultados (CSV)",
        data=csv_bytes,
        file_name=f"cgspace_{fuente_label.replace(' ', '_')}_{st.session_state.last_query[:20].replace(' ', '_')}.csv",
        mime="text/csv",
        key=f"{tab_key}_download",
    )


# ═════════════════════════════════════════════════════════════
# TAB 1 – CSV LOCAL
# ═════════════════════════════════════════════════════════════
with tab_csv:
    n = len(st.session_state.df_csv_results)
    if n:
        st.success(f"**{n:,} documentos** encontrados en la base local.")
    render_resultados(st.session_state.df_csv_results, "Base local (CSV)", "csv")


# ═════════════════════════════════════════════════════════════
# TAB 2 – API CGSPACE
# ═════════════════════════════════════════════════════════════
with tab_api:
    n = len(st.session_state.df_api_results)
    if n:
        st.success(f"**{n:,} documentos** encontrados en la API de CGSpace.")
    render_resultados(st.session_state.df_api_results, "API CGSpace", "api")


# ═════════════════════════════════════════════════════════════
# TAB 3 – CHAT
# ═════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("## Consultas libres")
    st.caption(
        "Escribe en lenguaje natural. El sistema buscará en ambas fuentes "
        "y actualizará las pestañas de resultados."
    )

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(
        "Ej: documentos sobre café y cambio climático en Centroamérica"
    )

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        terminos = expandir_consulta(user_input)
        st.session_state.last_query = user_input
        st.session_state.terminos   = terminos

        with st.spinner("Buscando…"):
            df_c = buscar_csv(terminos)
            df_a = buscar_api(terminos)

        st.session_state.df_csv_results = df_c
        st.session_state.df_api_results = df_a

        partes = []

        if not df_c.empty:
            años_c   = (f"{int(df_c['year'].min())}–{int(df_c['year'].max())}"
                        if "year" in df_c.columns and df_c["year"].notna().any() else "N/D")
            paises_c = df_c["country"].dropna().nunique() if "country" in df_c.columns else 0
            partes.append(
                f"**Base local:** {len(df_c):,} documentos · {paises_c} países · {años_c}"
            )
        else:
            partes.append("**Base local:** sin resultados.")

        if not df_a.empty:
            años_a = (f"{int(df_a['year'].min())}–{int(df_a['year'].max())}"
                      if "year" in df_a.columns and df_a["year"].notna().any() else "N/D")
            partes.append(f"**API CGSpace:** {len(df_a):,} documentos · {años_a}")
        else:
            partes.append("**API CGSpace:** sin resultados o servicio no disponible.")

        respuesta = (
            "\n\n".join(partes)
            + f"\n\nTérminos buscados: `{', '.join(terminos[:5])}`\n\n"
            "Ve a **Base local** o **API CGSpace** para explorar los resultados."
        )

        st.session_state.chat_history.append({"role": "assistant", "content": respuesta})
        with st.chat_message("assistant"):
            st.markdown(respuesta)
