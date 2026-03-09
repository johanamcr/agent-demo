import streamlit as st
import pandas as pd
import requests
from collections import Counter

# ─────────────────────────────────────────────
# Configuración de la página
# ─────────────────────────────────────────────
st.set_page_config(page_title="Agente CGSpace – Demo", layout="wide")

st.title("Agente CGSpace – Demo con datos locales y API de CGSpace")

st.write(
    """
Este demo muestra cómo podría funcionar un **agente** sobre CGSpace:

- A la izquierda escribes una pregunta o tema.
- El agente puede usar:
  - un **CSV local** con un subconjunto de metadatos (modo estable para demos), o
  - la **API REST de CGSpace** (modo experimental, en vivo).
- A la derecha ves un **resumen ejecutivo**, métricas, filtros, gráfico y la lista de documentos encontrados.

En producción, este mismo diseño se puede ampliar con resúmenes generativos y lectura de abstracts.
"""
)

# Selector de fuente de datos
fuente_datos = st.sidebar.radio(
    "Fuente de datos",
    ["CSV local (demo estable)", "API CGSpace (experimental)"],
    index=0,
)

st.sidebar.info(
    "• CSV local: estable, ideal para demos.\n"
    "• API CGSpace: consulta el repositorio en vivo (puede fallar si hay límites 429)."
)

CGSPACE_API_URL = "https://cgspace.cgiar.org/server/api/discover/search/objects"

# ─────────────────────────────────────────────
# Cargar datos locales
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=True)
def cargar_datos_locales() -> pd.DataFrame:
    df = pd.read_csv("cgspace_demo.csv")
    if "Año" in df.columns:
        df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
    return df


df_base = cargar_datos_locales()

# ─────────────────────────────────────────────
# Búsqueda local
# ─────────────────────────────────────────────
def buscar_localmente(query: str, df: pd.DataFrame, max_results: int = 200) -> pd.DataFrame:
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
        mask = mask | df[col].astype(str).str.lower().str.contains(q)

    resultados = df[mask].copy()

    if "Año" in resultados.columns:
        resultados = resultados.sort_values("Año", ascending=False)

    return resultados.head(max_results)

# ─────────────────────────────────────────────
# Búsqueda API CGSpace
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=True)
def buscar_en_cgspace_api(query: str, page: int = 0, size: int = 50) -> pd.DataFrame:
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

    return pd.DataFrame(filas)

# ─────────────────────────────────────────────
# Resumen automático
# ─────────────────────────────────────────────
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


def generar_resumen_ejecutivo(df: pd.DataFrame, query: str, fuente: str) -> str:
    if df.empty:
        return (
            f"No se encontraron documentos para la consulta **{query}** "
            f"en la fuente **{fuente}**."
        )

    n = len(df)

    # años
    if "Año" in df.columns and df["Año"].notna().any():
        año_min = int(df["Año"].min())
        año_max = int(df["Año"].max())
        texto_años = f"entre **{año_min}** y **{año_max}**"
    else:
        texto_años = "sin rango temporal identificado"

    # países
    if "País" in df.columns:
        paises = df["País"].dropna().unique().tolist()
        num_paises = len(paises)
        paises_txt = ", ".join(paises[:5]) if paises else "sin países identificados"
    else:
        num_paises = 0
        paises_txt = "sin países identificados"

    # temas
    temas = extraer_temas_frecuentes(df, top_n=5)
    temas_txt = ", ".join(temas) if temas else "sin palabras clave disponibles"

    # títulos ejemplo
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

# ─────────────────────────────────────────────
# Layout principal
# ─────────────────────────────────────────────
col_chat, col_panel = st.columns([1, 2])

with col_chat:
    st.subheader("Chat con el agente CGSpace")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(
        "Escribe un tema o pregunta (ej. coffee rust, agroecology, climate change Africa, Colombia)..."
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        try:
            if fuente_datos == "CSV local (demo estable)":
                df_resultados = buscar_localmente(user_input, df_base, max_results=200)
                origen = "subconjunto local (CSV)"
            else:
                df_resultados = buscar_en_cgspace_api(user_input, page=0, size=50)
                origen = "API de CGSpace"
        except Exception as e:
            df_resultados = pd.DataFrame()
            respuesta = (
                "Intenté conectarme a la fuente de datos, pero hubo un error.\n\n"
                f"Mensaje técnico: `{type(e).__name__}: {e}`\n\n"
                "Puedes cambiar de fuente en el menú lateral."
            )
            st.session_state.messages.append({"role": "assistant", "content": respuesta})
            st.session_state.results_df = pd.DataFrame()
            st.session_state.last_query = user_input
            st.session_state.summary_text = "No fue posible generar resumen por error en la consulta."
            with st.chat_message("assistant"):
                st.markdown(respuesta)
        else:
            st.session_state.results_df = df_resultados
            st.session_state.last_query = user_input
            st.session_state.summary_text = generar_resumen_ejecutivo(
                df_resultados, user_input, origen
            )

            if df_resultados.empty:
                respuesta = (
                    f"He buscado en la fuente **{origen}** y no encontré documentos "
                    "relacionados con esa consulta.\n\n"
                    "Prueba con otras palabras clave o cambia la fuente de datos."
                )
            else:
                respuesta = (
                    f"He encontrado **{len(df_resultados)}** documentos en la fuente **{origen}**.\n\n"
                    "En el panel derecho puedes ver un **resumen ejecutivo**, métricas, filtros y la lista de resultados."
                )

            st.session_state.messages.append({"role": "assistant", "content": respuesta})
            with st.chat_message("assistant"):
                st.markdown(respuesta)

with col_panel:
    st.subheader("Resultados y síntesis")

    df_res = st.session_state.results_df

    # ── Resumen ejecutivo ───────────────────────────
    st.markdown("### Resumen ejecutivo")
    st.info(st.session_state.summary_text)

    if df_res is None or df_res.empty:
        st.info(
            "Aquí aparecerán los documentos filtrados.\n\n"
            "Prueba en el chat con temas como **coffee**, **agroecology**, "
            "**climate change**, **Colombia**, etc."
        )
    else:
        # ── Temas detectados ───────────────────────────
        temas_detectados = extraer_temas_frecuentes(df_res, top_n=5)
        if temas_detectados:
            st.markdown("### Temas detectados")
            st.write(", ".join(temas_detectados))

        # ── Filtros ───────────────────────────
        with st.expander("Filtros (año, país)", expanded=True):
            col_f1, col_f2 = st.columns(2)

            if "Año" in df_res.columns and df_res["Año"].notna().any():
                años_validos = sorted(df_res["Año"].dropna().unique().tolist())

                if len(años_validos) > 1:
                    min_year = int(min(años_validos))
                    max_year = int(max(años_validos))
                    year_range = col_f1.slider(
                        "Rango de años",
                        min_value=min_year,
                        max_value=max_year,
                        value=(min_year, max_year),
                        step=1,
                    )
                    df_res = df_res[
                        (df_res["Año"] >= year_range[0])
                        & (df_res["Año"] <= year_range[1])
                    ]
                else:
                    unico = int(años_validos[0])
                    col_f1.write(f"Todos los resultados son del año **{unico}**.")
            else:
                col_f1.write("No hay información de año en los resultados.")

            if "País" in df_res.columns:
                paises_unicos = sorted(df_res["País"].dropna().unique().tolist())
                if paises_unicos:
                    paises_sel = col_f2.multiselect(
                        "Filtrar por país",
                        options=paises_unicos,
                        default=paises_unicos,
                    )
                    if paises_sel:
                        df_res = df_res[df_res["País"].isin(paises_sel)]
                else:
                    col_f2.write("No hay países disponibles para filtrar.")

        # ── Métricas ───────────────────────────
        col_m1, col_m2, col_m3 = st.columns(3)

        col_m1.metric("Documentos encontrados", len(df_res))

        if "Año" in df_res.columns and not df_res.empty and df_res["Año"].notna().any():
            col_m2.metric("Año más reciente", int(df_res["Año"].max()))
        else:
            col_m2.metric("Año más reciente", "N/D")

        if "País" in df_res.columns and not df_res.empty:
            col_m3.metric("Nº de países en resultados", df_res["País"].nunique())
        else:
            col_m3.metric("Nº de países en resultados", "N/D")

        # ── Gráfico ───────────────────────────
        if "Año" in df_res.columns and not df_res.empty and df_res["Año"].notna().any():
            st.markdown("### Documentos por año")
            docs_por_anio = df_res.groupby("Año").size().reset_index(name="Documentos")
            docs_por_anio = docs_por_anio.sort_values("Año")
            st.bar_chart(docs_por_anio.set_index("Año"))

        # ── Tabla ───────────────────────────
        st.markdown("### Lista de documentos")
        st.dataframe(df_res, use_container_width=True)
