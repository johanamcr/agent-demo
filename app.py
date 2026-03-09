import streamlit as st
import pandas as pd
import requests
from collections import Counter

# ─────────────────────────────────────────────
# Configuración general
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Agente CGSpace – Executive Brief",
    layout="wide"
)

st.title("Agente CGSpace – Executive Brief")
st.caption(
    "Exploración y síntesis de documentos de CGSpace para uso interno y comunicación con donantes."
)

# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
fuente_datos = st.sidebar.radio(
    "Fuente de datos",
    ["CSV local (demo estable)", "API CGSpace (experimental)"],
    index=0,
)

st.sidebar.info(
    "• CSV local: estable, ideal para demos.\n"
    "• API CGSpace: consulta CGSpace en vivo y puede fallar si el servidor limita peticiones."
)

consulta_sidebar = st.sidebar.text_input(
    "Consulta rápida",
    placeholder="Ej. coffee rust in Colombia"
)

ejecutar_sidebar = st.sidebar.button("Consultar")

CGSPACE_API_URL = "https://cgspace.cgiar.org/server/api/discover/search/objects"

# ─────────────────────────────────────────────
# Carga de datos locales
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=True)
def cargar_datos_locales() -> pd.DataFrame:
    df = pd.read_csv("cgspace_demo.csv")
    if "Año" in df.columns:
        df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
    return df


df_base = cargar_datos_locales()

# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────
def normalizar_query(query: str) -> str:
    """
    Limpieza simple de consulta libre.
    """
    if not query:
        return ""
    return " ".join(str(query).strip().split())


def buscar_localmente(query: str, df: pd.DataFrame, max_results: int = 200) -> pd.DataFrame:
    """
    Búsqueda simple por contiene sobre varias columnas.
    """
    if not query or df.empty:
        return pd.DataFrame()

    q = query.lower()

    columnas_texto = []
    for col in ["Título", "País", "PalabrasClave"]:
        if col in df.columns:
            columnas_texto.append(col)

    if not columnas_texto:
        return pd.DataFrame()

    mask = False
    for col in columnas_texto:
        mask = mask | df[col].astype(str).str.lower().str.contains(q, na=False)

    resultados = df[mask].copy()

    if "Año" in resultados.columns:
        resultados = resultados.sort_values("Año", ascending=False)

    return resultados.head(max_results)


@st.cache_data(ttl=600, show_spinner=True)
def buscar_en_cgspace_api(query: str, page: int = 0, size: int = 50) -> pd.DataFrame:
    """
    Consulta la API REST de CGSpace (DSpace 7).
    """
    if not query:
        return pd.DataFrame()

    params = {
        "query": query,
        "page": page,
        "size": size,
        "sort": "dcterms.issued,desc",
    }

    resp = requests.get(CGSPACE_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    objects = (
        data.get("_embedded", {})
        .get("searchResult", {})
        .get("_embedded", {})
        .get("objects", [])
    )

    filas = []
    for obj in objects:
        indexable = obj.get("_embedded", {}).get("indexableObject", {})
        metadata = indexable.get("metadata", {})
        handle = indexable.get("handle")
        enlace = f"https://cgspace.cgiar.org/handle/{handle}" if handle else None

        titulo = None
        if "dc.title" in metadata:
            titulo = metadata["dc.title"][0].get("value")
        elif "dcterms.title" in metadata:
            titulo = metadata["dcterms.title"][0].get("value")
        else:
            titulo = indexable.get("name")

        año = None
        for key in ["dcterms.issued", "dc.date.issued"]:
            if key in metadata:
                v = metadata[key][0].get("value", "")
                if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
                    año = int(v[:4])
                    break

        pais = None
        for key in ["cg.country", "cg.coverage.country", "dc.coverage.spatial"]:
            if key in metadata:
                pais = metadata[key][0].get("value")
                break

        palabras = []
        for key in ["cg.subject", "dc.subject", "dcterms.subject"]:
            if key in metadata:
                palabras = [entry.get("value") for entry in metadata[key]]
                break

        filas.append(
            {
                "Título": titulo,
                "Año": año,
                "País": pais,
                "Enlace": enlace,
                "PalabrasClave": "; ".join(palabras) if palabras else None,
            }
        )

    df = pd.DataFrame(filas)
    if "Año" in df.columns:
        df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
    return df


def extraer_temas_frecuentes(df: pd.DataFrame, top_n: int = 5):
    if "PalabrasClave" not in df.columns or df.empty:
        return []

    temas = []
    for val in df["PalabrasClave"].dropna():
        partes = [x.strip() for x in str(val).split(";") if x.strip()]
        temas.extend(partes)

    if not temas:
        return []

    conteo = Counter(temas)
    return [tema for tema, _ in conteo.most_common(top_n)]


def obtener_titulo_destacado(df: pd.DataFrame):
    if df.empty or "Título" not in df.columns:
        return "N/D"
    titulos = df["Título"].dropna().tolist()
    return titulos[0] if titulos else "N/D"


def generar_hallazgos_clave(df: pd.DataFrame):
    hallazgos = []

    if df.empty:
        return ["No se identificaron hallazgos porque no hubo resultados para la consulta."]

    n = len(df)
    hallazgos.append(f"Se identificaron **{n} documentos** relacionados con la consulta.")

    if "Año" in df.columns and df["Año"].notna().any():
        hallazgos.append(
            f"El rango temporal de los resultados va de **{int(df['Año'].min())}** a **{int(df['Año'].max())}**."
        )

    if "País" in df.columns and df["País"].dropna().any():
        paises = df["País"].dropna().unique().tolist()
        hallazgos.append(
            f"Los resultados cubren **{len(paises)} países**. Entre ellos: {', '.join(paises[:5])}."
        )

    temas = extraer_temas_frecuentes(df, top_n=5)
    if temas:
        hallazgos.append(
            f"Los temas más visibles en los metadatos son: **{', '.join(temas)}**."
        )

    titulo = obtener_titulo_destacado(df)
    if titulo != "N/D":
        hallazgos.append(f"Un documento destacado es: **{titulo}**.")

    return hallazgos


def generar_resumen_ejecutivo(df: pd.DataFrame, query: str, fuente: str) -> str:
    if df.empty:
        return (
            f"No se encontraron documentos para la consulta **{query}** "
            f"en la fuente **{fuente}**."
        )

    n = len(df)

    if "Año" in df.columns and df["Año"].notna().any():
        año_min = int(df["Año"].min())
        año_max = int(df["Año"].max())
        texto_años = f"entre **{año_min}** y **{año_max}**"
    else:
        texto_años = "sin rango temporal identificado"

    if "País" in df.columns:
        paises = df["País"].dropna().unique().tolist()
        num_paises = len(paises)
        paises_txt = ", ".join(paises[:5]) if paises else "sin países identificados"
    else:
        num_paises = 0
        paises_txt = "sin países identificados"

    temas = extraer_temas_frecuentes(df, top_n=5)
    temas_txt = ", ".join(temas) if temas else "sin palabras clave disponibles"

    titulos = df["Título"].dropna().head(3).tolist() if "Título" in df.columns else []
    titulos_txt = "; ".join(titulos) if titulos else "sin títulos destacados"

    resumen = (
        f"Para la consulta **{query}**, el agente identificó **{n} documentos** "
        f"en la fuente **{fuente}**, con registros publicados {texto_años}. "
        f"Los resultados abarcan **{num_paises} países** y muestran presencia de temas como "
        f"**{temas_txt}**. Entre los documentos destacados se encuentran: {titulos_txt}. "
        f"Los países más visibles en esta consulta son: {paises_txt}."
    )
    return resumen


def ejecutar_consulta(query: str, fuente: str):
    query = normalizar_query(query)

    if not query:
        return pd.DataFrame(), "No se ingresó una consulta.", "consulta vacía"

    try:
        if fuente == "CSV local (demo estable)":
            df_resultados = buscar_localmente(query, df_base, max_results=200)
            origen = "subconjunto local (CSV)"
        else:
            df_resultados = buscar_en_cgspace_api(query, page=0, size=50)
            origen = "API de CGSpace"

        resumen = generar_resumen_ejecutivo(df_resultados, query, origen)
        return df_resultados, resumen, origen

    except Exception as e:
        df_resultados = pd.DataFrame()
        resumen = (
            f"No fue posible consultar la fuente **{fuente}**.\n\n"
            f"Error técnico: `{type(e).__name__}: {e}`"
        )
        return df_resultados, resumen, fuente


# ─────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

if "results_df" not in st.session_state:
    st.session_state.results_df = df_base.copy()

if "last_query" not in st.session_state:
    st.session_state.last_query = "consulta inicial"

if "summary_text" not in st.session_state:
    st.session_state.summary_text = "Aquí aparecerá el resumen ejecutivo de la consulta."

if "source_used" not in st.session_state:
    st.session_state.source_used = "CSV local (demo estable)"

# Ejecutar desde sidebar
if ejecutar_sidebar and consulta_sidebar.strip():
    df_resultados, resumen, origen = ejecutar_consulta(consulta_sidebar, fuente_datos)
    st.session_state.results_df = df_resultados
    st.session_state.last_query = consulta_sidebar
    st.session_state.summary_text = resumen
    st.session_state.source_used = origen

# ─────────────────────────────────────────────
# Tabs principales
# ─────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Executive Brief", "Explore Documents", "Chat Assistant"])

# ─────────────────────────────────────────────
# TAB 1: Executive Brief
# ─────────────────────────────────────────────
with tab1:
    df_res = st.session_state.results_df.copy()

    st.markdown("## Executive Brief")
    st.write(f"**Consulta actual:** {st.session_state.last_query}")
    st.write(f"**Fuente usada:** {st.session_state.source_used}")

    # KPIs
    c1, c2, c3, c4, c5 = st.columns(5)

    total_docs = len(df_res)

    if "País" in df_res.columns and not df_res.empty:
        total_paises = df_res["País"].dropna().nunique()
    else:
        total_paises = 0

    if "Año" in df_res.columns and not df_res.empty and df_res["Año"].notna().any():
        año_reciente = int(df_res["Año"].max())
    else:
        año_reciente = "N/D"

    temas = extraer_temas_frecuentes(df_res, top_n=1)
    tema_principal = temas[0] if temas else "N/D"

    titulo_destacado = obtener_titulo_destacado(df_res)

    c1.metric("Documentos", total_docs)
    c2.metric("Países", total_paises)
    c3.metric("Año más reciente", año_reciente)
    c4.metric("Tema principal", tema_principal)
    c5.metric("Fuente", "CSV" if "CSV" in st.session_state.source_used else "API")

    st.markdown("### Resumen ejecutivo")
    st.info(st.session_state.summary_text)

    left, right = st.columns([1, 1])

    with left:
        st.markdown("### Hallazgos clave")
        for h in generar_hallazgos_clave(df_res):
            st.markdown(f"- {h}")

        st.markdown("### Título destacado")
        st.success(titulo_destacado)

        temas_top = extraer_temas_frecuentes(df_res, top_n=5)
        st.markdown("### Temas detectados")
        if temas_top:
            st.write(", ".join(temas_top))
        else:
            st.write("No se detectaron temas en los metadatos.")

    with right:
        st.markdown("### Documentos por año")
        if "Año" in df_res.columns and not df_res.empty and df_res["Año"].notna().any():
            docs_por_anio = df_res.groupby("Año").size().reset_index(name="Documentos")
            docs_por_anio = docs_por_anio.sort_values("Año")
            st.bar_chart(docs_por_anio.set_index("Año"))
        else:
            st.info("No hay datos suficientes para mostrar el gráfico por año.")

# ─────────────────────────────────────────────
# TAB 2: Explore Documents
# ─────────────────────────────────────────────
with tab2:
    st.markdown("## Explore Documents")

    query_explore = st.text_input(
        "Haz una nueva consulta",
        value=st.session_state.last_query if st.session_state.last_query != "consulta inicial" else "",
        placeholder="Ej. climate change in Africa"
    )

    colb1, colb2 = st.columns([1, 1])
    run_explore = colb1.button("Buscar en esta pestaña")
    use_current = colb2.button("Usar consulta actual")

    if run_explore and query_explore.strip():
        df_resultados, resumen, origen = ejecutar_consulta(query_explore, fuente_datos)
        st.session_state.results_df = df_resultados
        st.session_state.last_query = query_explore
        st.session_state.summary_text = resumen
        st.session_state.source_used = origen

    if use_current:
        query_explore = st.session_state.last_query

    df_exp = st.session_state.results_df.copy()

    if df_exp.empty:
        st.info("No hay resultados para mostrar. Ejecuta una consulta.")
    else:
        with st.expander("Filtros (año, país)", expanded=True):
            f1, f2 = st.columns(2)

            if "Año" in df_exp.columns and df_exp["Año"].notna().any():
                años_validos = sorted(df_exp["Año"].dropna().unique().tolist())
                if len(años_validos) > 1:
                    min_year = int(min(años_validos))
                    max_year = int(max(años_validos))
                    year_range = f1.slider(
                        "Rango de años",
                        min_value=min_year,
                        max_value=max_year,
                        value=(min_year, max_year),
                        step=1,
                        key="explore_year_slider"
                    )
                    df_exp = df_exp[
                        (df_exp["Año"] >= year_range[0]) &
                        (df_exp["Año"] <= year_range[1])
                    ]
                else:
                    f1.write(f"Todos los resultados son del año **{int(años_validos[0])}**.")
            else:
                f1.write("No hay información de año en los resultados.")

            if "País" in df_exp.columns:
                paises_unicos = sorted(df_exp["País"].dropna().unique().tolist())
                if paises_unicos:
                    paises_sel = f2.multiselect(
                        "Filtrar por país",
                        options=paises_unicos,
                        default=paises_unicos,
                        key="explore_country_filter"
                    )
                    if paises_sel:
                        df_exp = df_exp[df_exp["País"].isin(paises_sel)]
                else:
                    f2.write("No hay países disponibles para filtrar.")

        m1, m2, m3 = st.columns(3)
        m1.metric("Documentos encontrados", len(df_exp))

        if "Año" in df_exp.columns and not df_exp.empty and df_exp["Año"].notna().any():
            m2.metric("Año más reciente", int(df_exp["Año"].max()))
        else:
            m2.metric("Año más reciente", "N/D")

        if "País" in df_exp.columns and not df_exp.empty:
            m3.metric("Nº de países", df_exp["País"].nunique())
        else:
            m3.metric("Nº de países", "N/D")

        st.markdown("### Lista de documentos")
        st.dataframe(df_exp, use_container_width=True)

# ─────────────────────────────────────────────
# TAB 3: Chat Assistant
# ─────────────────────────────────────────────
with tab3:
    st.markdown("## Chat Assistant")
    st.write(
        "Usa esta pestaña para escribir consultas libres. "
        "El agente devolverá una respuesta breve y actualizará el Executive Brief."
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(
        "Escribe una consulta libre (ej. Muéstrame qué se ha trabajado sobre coffee rust en Colombia)"
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        df_resultados, resumen, origen = ejecutar_consulta(user_input, fuente_datos)
        st.session_state.results_df = df_resultados
        st.session_state.last_query = user_input
        st.session_state.summary_text = resumen
        st.session_state.source_used = origen

        if df_resultados.empty:
            respuesta = (
                f"He procesado tu consulta en la fuente **{origen}**, "
                "pero no encontré resultados relevantes."
            )
        else:
            respuesta = (
                f"He encontrado **{len(df_resultados)} documentos** en la fuente **{origen}**.\n\n"
                "Actualicé el **Executive Brief** con un resumen ejecutivo, hallazgos clave "
                "y visualizaciones para esta consulta."
            )

        st.session_state.messages.append({"role": "assistant", "content": respuesta})
        with st.chat_message("assistant"):
            st.markdown(respuesta)
