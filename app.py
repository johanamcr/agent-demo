"""
CGSpace Explorer – versión mejorada
====================================
Mejoras principales:
  - Una sola fuente de verdad: KPIs, gráficos y tabla muestran exactamente los mismos documentos.
  - Búsqueda enriquecida: sinónimos automáticos + búsqueda en múltiples campos del API.
  - Filtros inteligentes post-búsqueda: región/país, año, tipo de documento.
  - Visualizaciones: mapa de países (plotly), timeline, nube de temas, tabla descargable.
  - Lenguaje limpio para donantes: sin referencias a "agente".
"""

import streamlit as st
import pandas as pd
import requests
from collections import Counter
import plotly.express as px

# ──────────────────────────────────────────────
# Configuración general
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="CGSpace Explorer",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS mínimo para pulir la UI
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    .stMetric label { font-size: 0.78rem; color: #6b7280; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# Sinónimos / expansión de consulta
# ──────────────────────────────────────────────
SINONIMOS: dict[str, list[str]] = {
    # Español → inglés (CGSpace indexa en inglés)
    "agroecología": ["agroecology", "sustainable farming", "organic farming", "ecological agriculture"],
    "agroecologia": ["agroecology", "sustainable farming", "organic farming"],
    "café": ["coffee", "coffea"],
    "cafe": ["coffee", "coffea"],
    "roya": ["coffee rust", "leaf rust", "hemileia vastatrix"],
    "cambio climático": ["climate change", "global warming", "climate variability"],
    "cambio climatico": ["climate change", "global warming", "climate variability"],
    "sequía": ["drought", "water stress", "dry season"],
    "sequia": ["drought", "water stress"],
    "biodiversidad": ["biodiversity", "species diversity", "genetic resources"],
    "seguridad alimentaria": ["food security", "food systems", "nutrition"],
    "género": ["gender", "women", "female farmers"],
    "genero": ["gender", "women", "female farmers"],
    "maíz": ["maize", "corn", "zea mays"],
    "maiz": ["maize", "corn", "zea mays"],
    "arroz": ["rice", "oryza"],
    "trigo": ["wheat", "triticum"],
    "frijol": ["bean", "phaseolus", "legume"],
    "frijoles": ["bean", "phaseolus", "legume"],
    "suelo": ["soil", "soil health", "land degradation"],
    "agua": ["water", "irrigation", "watershed"],
    "ganadería": ["livestock", "cattle", "animal husbandry"],
    "ganaderia": ["livestock", "cattle", "animal husbandry"],
    "fertilizante": ["fertilizer", "nutrient management", "soil fertility"],
    "plagas": ["pest", "pest management", "integrated pest management"],
    "semillas": ["seeds", "seed systems", "plant breeding"],
    "variedades": ["varieties", "cultivars", "crop improvement"],
    "bosque": ["forest", "deforestation", "agroforestry"],
    "Colombia": ["Colombia"],
    "Africa": ["Africa", "Sub-Saharan Africa", "East Africa", "West Africa"],
    "África": ["Africa", "Sub-Saharan Africa", "East Africa", "West Africa"],
    "Asia": ["Asia", "South Asia", "Southeast Asia"],
    "smallholder": ["smallholder", "small-scale farmer", "family farm"],
}

CGSPACE_API = "https://cgspace.cgiar.org/server/api/discover/search/objects"


def expandir_consulta(query: str) -> list[str]:
    """
    Devuelve lista de términos de búsqueda: la consulta original + sinónimos encontrados.
    """
    terminos = [query.strip()]
    q_lower = query.lower().strip()

    # Coincidencias exactas
    if q_lower in SINONIMOS:
        terminos.extend(SINONIMOS[q_lower])

    # Coincidencias parciales (la consulta contiene la clave)
    for clave, sinonimos in SINONIMOS.items():
        if clave in q_lower and clave != q_lower:
            terminos.extend(sinonimos)

    # Eliminar duplicados manteniendo orden
    vistos = set()
    unicos = []
    for t in terminos:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            unicos.append(t)

    return unicos


# ──────────────────────────────────────────────
# Carga CSV local
# ──────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def cargar_csv() -> pd.DataFrame:
    try:
        df = pd.read_csv("cgspace_demo.csv")
        if "Año" in df.columns:
            df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
        return df
    except FileNotFoundError:
        return pd.DataFrame()


df_csv = cargar_csv()


# ──────────────────────────────────────────────
# Búsqueda local (CSV) – búsqueda expandida
# ──────────────────────────────────────────────
def buscar_local(terminos: list[str], df: pd.DataFrame, max_results: int = 300) -> pd.DataFrame:
    if df.empty or not terminos:
        return pd.DataFrame()

    cols = [c for c in ["Título", "País", "PalabrasClave", "Resumen", "Autores"] if c in df.columns]
    if not cols:
        return pd.DataFrame()

    mask = pd.Series([False] * len(df), index=df.index)
    for termino in terminos:
        t = termino.lower()
        for col in cols:
            mask |= df[col].astype(str).str.lower().str.contains(t, na=False)

    resultado = df[mask].copy()
    if "Año" in resultado.columns:
        resultado = resultado.sort_values("Año", ascending=False)
    return resultado.head(max_results)


# ──────────────────────────────────────────────
# Búsqueda API CGSpace – búsqueda expandida
# ──────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def buscar_api(terminos: list[str], size: int = 100) -> pd.DataFrame:
    """
    Lanza hasta 3 búsquedas con los términos más relevantes y une resultados.
    Cada llamada busca en múltiples campos: título, abstract, subjects, country.
    """
    if not terminos:
        return pd.DataFrame()

    todos: list[dict] = []
    handles_vistos: set[str] = set()

    # Buscar los 3 primeros términos (original + top sinónimos)
    for termino in terminos[:3]:
        params = {
            "query": termino,
            "page": 0,
            "size": size,
            "sort": "dcterms.issued,desc",
            # DSpace 7 permite scope=* para buscar en todos los campos
            "searchFilter": "scope=*",
        }
        try:
            resp = requests.get(CGSPACE_API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            objects = (
                data.get("_embedded", {})
                .get("searchResult", {})
                .get("_embedded", {})
                .get("objects", [])
            )

            for obj in objects:
                indexable = obj.get("_embedded", {}).get("indexableObject", {})
                handle = indexable.get("handle")
                if handle in handles_vistos:
                    continue
                handles_vistos.add(handle)

                metadata = indexable.get("metadata", {})
                enlace = f"https://cgspace.cgiar.org/handle/{handle}" if handle else None

                # Título
                titulo = None
                for key in ["dc.title", "dcterms.title"]:
                    if key in metadata:
                        titulo = metadata[key][0].get("value")
                        break
                if not titulo:
                    titulo = indexable.get("name")

                # Año
                año = None
                for key in ["dcterms.issued", "dc.date.issued"]:
                    if key in metadata:
                        v = metadata[key][0].get("value", "")
                        if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
                            año = int(v[:4])
                            break

                # País
                pais = None
                for key in ["cg.country", "cg.coverage.country", "dc.coverage.spatial"]:
                    if key in metadata:
                        pais = metadata[key][0].get("value")
                        break

                # Palabras clave
                palabras = []
                for key in ["cg.subject", "dc.subject", "dcterms.subject"]:
                    if key in metadata:
                        palabras = [e.get("value", "") for e in metadata[key]]
                        break

                # Abstract
                abstract = None
                for key in ["dc.description.abstract", "dcterms.abstract"]:
                    if key in metadata:
                        abstract = metadata[key][0].get("value")
                        break

                # Tipo de documento
                tipo = None
                for key in ["dc.type", "dcterms.type"]:
                    if key in metadata:
                        tipo = metadata[key][0].get("value")
                        break

                # Autores
                autores = []
                for key in ["dc.contributor.author", "dcterms.creator"]:
                    if key in metadata:
                        autores = [e.get("value", "") for e in metadata[key]]
                        break

                todos.append({
                    "Título": titulo,
                    "Año": año,
                    "País": pais,
                    "Tipo": tipo,
                    "PalabrasClave": "; ".join(palabras) if palabras else None,
                    "Autores": "; ".join(autores[:3]) if autores else None,
                    "Abstract": abstract[:300] + "..." if abstract and len(abstract) > 300 else abstract,
                    "Enlace": enlace,
                })

        except Exception:
            continue  # Si una sub-búsqueda falla, continuar con la siguiente

    if not todos:
        return pd.DataFrame()

    df = pd.DataFrame(todos)
    if "Año" in df.columns:
        df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
        df = df.sort_values("Año", ascending=False)

    return df.reset_index(drop=True)


# ──────────────────────────────────────────────
# Función principal de búsqueda
# ──────────────────────────────────────────────
def ejecutar_busqueda(query: str, fuente: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Retorna (df_resultados, terminos_usados).
    df_resultados es la única fuente de verdad para todos los componentes.
    """
    query = query.strip()
    if not query:
        return pd.DataFrame(), []

    terminos = expandir_consulta(query)

    if fuente == "CSV local":
        if df_csv.empty:
            return pd.DataFrame(), terminos
        df = buscar_local(terminos, df_csv)
    else:  # API + CSV como respaldo
        df = buscar_api(terminos)
        if df.empty and not df_csv.empty:
            df = buscar_local(terminos, df_csv)

    return df, terminos


# ──────────────────────────────────────────────
# Funciones de análisis
# ──────────────────────────────────────────────
def temas_frecuentes(df: pd.DataFrame, top_n: int = 20) -> list[tuple[str, int]]:
    if "PalabrasClave" not in df.columns or df.empty:
        return []
    temas = []
    for val in df["PalabrasClave"].dropna():
        temas.extend([x.strip() for x in str(val).split(";") if x.strip()])
    return Counter(temas).most_common(top_n)


# ──────────────────────────────────────────────
# Estado de sesión
# ──────────────────────────────────────────────
for key, default in [
    ("df_results", pd.DataFrame()),
    ("last_query", ""),
    ("terminos_usados", []),
    ("fuente_usada", ""),
    ("chat_history", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 CGSpace Explorer")
    st.markdown("---")

    fuente = st.radio(
        "Fuente de datos",
        ["API CGSpace + CSV respaldo", "CSV local"],
        index=0,
        help="API CGSpace consulta el repositorio en vivo. CSV local es más estable para demos.",
    )

    st.markdown("### Búsqueda rápida")
    query_sidebar = st.text_input(
        "Consulta",
        placeholder="Ej. agroecología en Colombia",
        label_visibility="collapsed",
    )

    buscar_btn = st.button("Buscar", use_container_width=True, type="primary")

    if buscar_btn and query_sidebar.strip():
        with st.spinner("Buscando..."):
            df_res, terminos = ejecutar_busqueda(query_sidebar, fuente)
        st.session_state.df_results = df_res
        st.session_state.last_query = query_sidebar
        st.session_state.terminos_usados = terminos
        st.session_state.fuente_usada = fuente

    # Mostrar términos expandidos
    if st.session_state.terminos_usados and len(st.session_state.terminos_usados) > 1:
        st.markdown("**Términos de búsqueda usados:**")
        st.caption(" · ".join(st.session_state.terminos_usados[:6]))

    st.markdown("---")
    st.markdown("**Filtros rápidos**")
    st.caption("Aplican sobre los resultados actuales.")


# ──────────────────────────────────────────────
# Header principal
# ──────────────────────────────────────────────
st.markdown("# CGSpace Explorer")
st.caption(
    "Explora la producción de conocimiento de CGIAR. "
    "Busca por tema, país, año o tipo de documento."
)
st.markdown("---")

# ──────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────
tab_resumen, tab_docs, tab_chat = st.tabs([
    "📊 Resumen & Visualizaciones",
    "📄 Documentos",
    "💬 Consultas libres",
])


# ══════════════════════════════════════════════
# TAB 1 – Resumen & Visualizaciones
# ══════════════════════════════════════════════
with tab_resumen:

    df = st.session_state.df_results.copy()

    # ── Si no hay búsqueda aún ──
    if df.empty and not st.session_state.last_query:
        st.info(
            "👈 Escribe una consulta en la barra lateral para explorar los documentos de CGSpace.\n\n"
            "**Ejemplos:** `agroecología`, `coffee rust Colombia`, `climate change Africa`, `food security`"
        )
        st.stop()

    # ── Sin resultados ──
    if df.empty:
        st.warning(
            f"No se encontraron documentos para **{st.session_state.last_query}**. "
            "Intenta con otros términos."
        )
        st.stop()

    # ── Filtros post-búsqueda ──
    with st.expander("⚙️ Filtros", expanded=False):
        fc1, fc2, fc3 = st.columns(3)

        # Año
        if "Año" in df.columns and df["Año"].notna().any():
            años = sorted(df["Año"].dropna().unique().astype(int).tolist())
            if len(años) > 1:
                year_range = fc1.slider(
                    "Rango de años",
                    min_value=min(años), max_value=max(años),
                    value=(min(años), max(años)),
                    key="res_year",
                )
                df = df[df["Año"].between(year_range[0], year_range[1])]

        # País
        if "País" in df.columns:
            paises = sorted(df["País"].dropna().unique().tolist())
            if paises:
                sel_paises = fc2.multiselect("País / Región", paises, default=paises, key="res_pais")
                if sel_paises:
                    df = df[df["País"].isin(sel_paises)]

        # Tipo
        if "Tipo" in df.columns:
            tipos = sorted(df["Tipo"].dropna().unique().tolist())
            if tipos:
                sel_tipos = fc3.multiselect("Tipo de documento", tipos, default=tipos, key="res_tipo")
                if sel_tipos:
                    df = df[df["Tipo"].isin(sel_tipos)]

    # ── KPIs — todos calculados sobre df (filtrado) ──
    total = len(df)
    n_paises = df["País"].dropna().nunique() if "País" in df.columns else 0
    año_max = int(df["Año"].max()) if "Año" in df.columns and df["Año"].notna().any() else "N/D"
    año_min = int(df["Año"].min()) if "Año" in df.columns and df["Año"].notna().any() else "N/D"
    temas_top = temas_frecuentes(df, top_n=1)
    tema_1 = temas_top[0][0] if temas_top else "N/D"

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Documentos", total)
    k2.metric("Países", n_paises)
    k3.metric("Año más reciente", año_max)
    k4.metric("Período cubierto", f"{año_min} – {año_max}" if isinstance(año_min, int) else "N/D")
    k5.metric("Tema principal", tema_1)

    st.caption(
        f"Consulta: **{st.session_state.last_query}** · "
        f"Fuente: {st.session_state.fuente_usada} · "
        f"Términos usados: {', '.join(st.session_state.terminos_usados[:4])}"
    )

    st.markdown("---")

    # ── Visualizaciones ──
    col_izq, col_der = st.columns([1.1, 0.9])

    # — Mapa de países —
    with col_izq:
        st.markdown("#### 🌍 Documentos por país")
        if "País" in df.columns and df["País"].notna().any():
            conteo_pais = (
                df["País"]
                .dropna()
                .value_counts()
                .reset_index()
                .rename(columns={"País": "País", "count": "Documentos"})
            )
            fig_mapa = px.choropleth(
                conteo_pais,
                locations="País",
                locationmode="country names",
                color="Documentos",
                color_continuous_scale="Greens",
                title="",
                height=380,
            )
            fig_mapa.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                coloraxis_colorbar=dict(title="Docs"),
            )
            st.plotly_chart(fig_mapa, use_container_width=True)

            # Top 5 países como tabla compacta
            st.dataframe(
                conteo_pais.head(8).rename(columns={"País": "País", "Documentos": "Docs"}),
                use_container_width=True,
                hide_index=True,
                height=200,
            )
        else:
            st.info("Sin datos de países disponibles.")

    # — Timeline —
    with col_der:
        st.markdown("#### 📅 Publicaciones por año")
        if "Año" in df.columns and df["Año"].notna().any():
            docs_año = (
                df.groupby("Año")
                .size()
                .reset_index(name="Documentos")
                .sort_values("Año")
            )
            fig_time = px.bar(
                docs_año,
                x="Año", y="Documentos",
                color_discrete_sequence=["#16a34a"],
                height=250,
            )
            fig_time.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="",
                yaxis_title="Docs",
            )
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.info("Sin datos de año disponibles.")

        st.markdown("#### 🏷️ Temas más frecuentes")
        temas_lista = temas_frecuentes(df, top_n=15)
        if temas_lista:
            df_temas = pd.DataFrame(temas_lista, columns=["Tema", "Frecuencia"])
            fig_temas = px.bar(
                df_temas.sort_values("Frecuencia"),
                x="Frecuencia", y="Tema",
                orientation="h",
                color="Frecuencia",
                color_continuous_scale="Greens",
                height=350,
            )
            fig_temas.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                showlegend=False,
                coloraxis_showscale=False,
                yaxis_title="",
            )
            st.plotly_chart(fig_temas, use_container_width=True)
        else:
            st.info("Sin palabras clave en los metadatos.")


# ══════════════════════════════════════════════
# TAB 2 – Documentos
# ══════════════════════════════════════════════
with tab_docs:
    st.markdown("## Documentos encontrados")

    df_docs = st.session_state.df_results.copy()

    if df_docs.empty:
        st.info("Realiza una búsqueda para ver los documentos.")
    else:
        # Filtros independientes en esta tab (no afectan la tab de resumen)
        with st.expander("⚙️ Filtros", expanded=True):
            d1, d2, d3 = st.columns(3)

            if "Año" in df_docs.columns and df_docs["Año"].notna().any():
                años_d = sorted(df_docs["Año"].dropna().unique().astype(int).tolist())
                if len(años_d) > 1:
                    yr = d1.slider(
                        "Años",
                        min_value=min(años_d), max_value=max(años_d),
                        value=(min(años_d), max(años_d)),
                        key="docs_year",
                    )
                    df_docs = df_docs[df_docs["Año"].between(yr[0], yr[1])]

            if "País" in df_docs.columns:
                paises_d = sorted(df_docs["País"].dropna().unique().tolist())
                if paises_d:
                    sp = d2.multiselect("País", paises_d, default=paises_d, key="docs_pais")
                    if sp:
                        df_docs = df_docs[df_docs["País"].isin(sp)]

            if "Tipo" in df_docs.columns:
                tipos_d = sorted(df_docs["Tipo"].dropna().unique().tolist())
                if tipos_d:
                    st_d = d3.multiselect("Tipo", tipos_d, default=tipos_d, key="docs_tipo")
                    if st_d:
                        df_docs = df_docs[df_docs["Tipo"].isin(st_d)]

        st.markdown(f"**{len(df_docs)} documentos** coinciden con los filtros.")

        # Columnas a mostrar (las que existan)
        cols_mostrar = [
            c for c in ["Título", "Año", "País", "Tipo", "Autores", "PalabrasClave", "Abstract", "Enlace"]
            if c in df_docs.columns
        ]

        # Tabla interactiva
        st.dataframe(
            df_docs[cols_mostrar].reset_index(drop=True),
            use_container_width=True,
            height=500,
            column_config={
                "Enlace": st.column_config.LinkColumn("Enlace"),
                "Título": st.column_config.TextColumn("Título", width="large"),
                "Abstract": st.column_config.TextColumn("Abstract", width="medium"),
            },
        )

        # Descarga
        csv_bytes = df_docs[cols_mostrar].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Descargar resultados (CSV)",
            data=csv_bytes,
            file_name=f"cgspace_{st.session_state.last_query[:30].replace(' ', '_')}.csv",
            mime="text/csv",
        )


# ══════════════════════════════════════════════
# TAB 3 – Chat / Consultas libres
# ══════════════════════════════════════════════
with tab_chat:
    st.markdown("## Consultas libres")
    st.caption(
        "Escribe en lenguaje natural. El sistema interpretará tu consulta, "
        "buscará en CGSpace y actualizará las visualizaciones."
    )

    # Historial
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ej: Documentos sobre café y cambio climático en Centroamérica")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.spinner("Buscando..."):
            df_new, terminos_new = ejecutar_busqueda(user_input, fuente)

        st.session_state.df_results = df_new
        st.session_state.last_query = user_input
        st.session_state.terminos_usados = terminos_new
        st.session_state.fuente_usada = fuente

        if df_new.empty:
            respuesta = (
                f"No se encontraron documentos para **{user_input}**.\n\n"
                f"Términos buscados: {', '.join(terminos_new)}.\n\n"
                "Prueba con términos más generales o en inglés."
            )
        else:
            n = len(df_new)
            paises_n = df_new["País"].dropna().nunique() if "País" in df_new.columns else 0
            año_r = int(df_new["Año"].max()) if "Año" in df_new.columns and df_new["Año"].notna().any() else "N/D"
            temas_n = temas_frecuentes(df_new, top_n=3)
            temas_str = ", ".join([t[0] for t in temas_n]) if temas_n else "sin etiquetas"

            respuesta = (
                f"Se encontraron **{n} documentos** en {st.session_state.fuente_usada}.\n\n"
                f"- **Países cubiertos:** {paises_n}\n"
                f"- **Publicación más reciente:** {año_r}\n"
                f"- **Temas predominantes:** {temas_str}\n\n"
                f"Las visualizaciones y la tabla se han actualizado. "
                f"Ve a las pestañas **Resumen** o **Documentos** para explorar los resultados."
            )

        st.session_state.chat_history.append({"role": "assistant", "content": respuesta})
        with st.chat_message("assistant"):
            st.markdown(respuesta)
