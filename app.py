import streamlit as st
import pandas as pd
import requests

# ─────────────────────────────────────────────
# Configuración de la página
# ─────────────────────────────────────────────
st.set_page_config(page_title="Agente CGSpace – Demo", layout="wide")

st.title("Agente CGSpace – Demo con datos locales y API de CGSpace")

st.write(
    """
Este demo muestra cómo podría funcionar un **agente** sobre CGSpace:

- A la izquierda escribes una pregunta o tema (chat).
- El agente puede usar:
  - un **CSV local** con un subconjunto de metadatos (modo estable para demos), o
  - la **API REST de CGSpace** (modo experimental, en vivo).
- A la derecha ves métricas, filtros, gráfico y la lista de documentos encontrados.

En producción, se recomienda usar la API con caché y límites de uso acordados con el equipo de CGSpace.
"""
)

# Selector de fuente de datos
fuente_datos = st.sidebar.radio(
    "Fuente de datos",
    ["CSV local (demo estable)", "API CGSpace (experimental)"],
    index=0,
)
st.sidebar.info(
    "• CSV local: siempre estable, ideal para demos.\n"
    "• API CGSpace: consulta el repositorio en vivo (puede fallar si hay límites 429)."
)

# URL base de la API de CGSpace (DSpace 7)
CGSPACE_API_URL = "https://cgspace.cgiar.org/server/api/discover/search/objects"

# ─────────────────────────────────────────────
# Cargar datos locales de CGSpace desde CSV
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=True)
def cargar_datos_locales() -> pd.DataFrame:
    df = pd.read_csv("cgspace_demo.csv")
    # Aseguramos tipos
    if "Año" in df.columns:
        df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
    return df


df_base = cargar_datos_locales()

# ─────────────────────────────────────────────
# Herramienta del agente: búsqueda local (CSV)
# ─────────────────────────────────────────────
def buscar_localmente(query: str, df: pd.DataFrame, max_results: int = 200) -> pd.DataFrame:
    """
    Busca la query en varias columnas de texto del DataFrame:
    - Título
    - País
    - PalabrasClave

    Es una búsqueda simple (contiene, sin mayúsculas/minúsculas),
    suficiente para una demo estable.
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
        mask = mask | df[col].astype(str).str.lower().str.contains(q)

    resultados = df[mask].copy()

    # Orden por año (más recientes primero) si existe
    if "Año" in resultados.columns:
        resultados = resultados.sort_values("Año", ascending=False)

    return resultados.head(max_results)


# ─────────────────────────────────────────────
# Herramienta del agente: búsqueda en API de CGSpace
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=True)
def buscar_en_cgspace_api(query: str, page: int = 0, size: int = 50) -> pd.DataFrame:
    """
    Llama a la API REST de CGSpace (DSpace 7) usando el endpoint de búsqueda (Discovery).
    Devuelve un DataFrame con columnas: Título, Año, País (si se encuentra), Enlace, PalabrasClave.

    NOTA: La estructura exacta de metadatos puede variar; algunos campos pueden salir vacíos
    y requerir ajuste según la configuración de CGSpace.
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

        # Título
        titulo = None
        if "dc.title" in metadata:
            titulo = metadata["dc.title"][0].get("value")
        elif "dcterms.title" in metadata:
            titulo = metadata["dcterms.title"][0].get("value")
        else:
            titulo = indexable.get("name")

        # Año (intentamos dcterms.issued o dc.date.issued)
        año = None
        for key in ["dcterms.issued", "dc.date.issued"]:
            if key in metadata:
                v = metadata[key][0].get("value", "")
                if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
                    año = int(v[:4])
                    break

        # País (esto depende de cómo CGSpace configure los metadatos)
        pais = None
        for key in ["cg.country", "cg.coverage.country", "dc.coverage.spatial"]:
            if key in metadata:
                pais = metadata[key][0].get("value")
                break

        # Palabras clave (temas)
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
# Estado de sesión: historial de chat y resultados
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

if "results_df" not in st.session_state:
    st.session_state.results_df = df_base.copy()

# ─────────────────────────────────────────────
# Layout principal: chat (izquierda) + panel de datos (derecha)
# ─────────────────────────────────────────────
col_chat, col_panel = st.columns([1, 2])

with col_chat:
    st.subheader("Chat con el agente CGSpace (demo)")

    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Entrada del usuario
    user_input = st.chat_input(
        "Escribe un tema o pregunta (ej. coffee rust, agroecology, climate change Africa, Colombia)..."
    )

    if user_input:
        # Guardar mensaje de usuario
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # 1) Llamar a la herramienta adecuada según la fuente de datos
        try:
            if fuente_datos == "CSV local (demo estable)":
                df_resultados = buscar_localmente(user_input, df_base, max_results=200)
            else:  # API CGSpace
                df_resultados = buscar_en_cgspace_api(user_input, page=0, size=50)
        except Exception as e:
            df_resultados = pd.DataFrame()
            respuesta = (
                "Intenté conectarme a la **API de CGSpace**, pero hubo un error.\n\n"
                f"Mensaje técnico: `{type(e).__name__}: {e}`\n\n"
                "Puedes cambiar a *CSV local (demo estable)* en el menú lateral para seguir usando el agente."
            )
            st.session_state.messages.append({"role": "assistant", "content": respuesta})
            with st.chat_message("assistant"):
                st.markdown(respuesta)
        else:
            st.session_state.results_df = df_resultados

            # 2) Construir respuesta de texto del agente
            if df_resultados.empty:
                if fuente_datos == "CSV local (demo estable)":
                    msg_origen = "subconjunto local de CGSpace (CSV de ejemplo)"
                else:
                    msg_origen = "API de CGSpace"

                respuesta = (
                    f"He buscado en el **{msg_origen}** y no encontré documentos "
                    "relacionados con esa consulta.\n\n"
                    "Si crees que debería haber resultados, prueba con otras palabras clave "
                    "o ajusta los filtros de país/año."
                )
            else:
                n = len(df_resultados)
                if "Año" in df_resultados.columns and df_resultados["Año"].notna().any():
                    años_min = int(df_resultados["Año"].min())
                    años_max = int(df_resultados["Año"].max())
                    rango_años = f"{años_min}–{años_max}"
                else:
                    rango_años = "N/D"

                if "País" in df_resultados.columns:
                    paises = ", ".join(
                        df_resultados["País"].dropna().unique().tolist()
                    ) or "N/D"
                else:
                    paises = "N/D"

                titulos_ejemplo = "- " + "\n- ".join(
                    df_resultados["Título"].dropna().head(3).tolist()
                )

                origen = (
                    "subconjunto local (CSV)"
                    if fuente_datos == "CSV local (demo estable)"
                    else "API de CGSpace"
                )

                respuesta = (
                    f"He encontrado **{n}** documentos en la fuente **{origen}**.\n\n"
                    f"- Rango de años en los resultados: **{rango_años}**\n"
                    f"- Países presentes: **{paises}**\n\n"
                    f"Algunos títulos de ejemplo:\n{titulos_ejemplo}\n\n"
                    "Puedes refinar por año o país en el panel de la derecha."
                )

            st.session_state.messages.append({"role": "assistant", "content": respuesta})
            with st.chat_message("assistant"):
                st.markdown(respuesta)


with col_panel:
    st.subheader("Resultados")

    df_res = st.session_state.results_df

    if df_res is None or df_res.empty:
        st.info(
            "Aquí aparecerán los documentos filtrados.\n\n"
            "Prueba en el chat con temas como **coffee**, **agroecology**, "
            "**climate change**, **Colombia**, etc."
        )
    else:
        # ── Filtros interactivos ───────────────────────────
        with st.expander("Filtros (año, país)", expanded=True):
            col_f1, col_f2 = st.columns(2)

            # Filtro por rango de años
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
                    # Solo hay un año en los resultados → no usamos slider
                    unico = int(años_validos[0])
                    col_f1.write(f"Todos los resultados son del año **{unico}**.")
            else:
                col_f1.write("No hay información de año en los resultados.")

            # Filtro por país
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

        if "Año" in df_res.columns and not df_res.empty:
            col_m2.metric(
                "Año más reciente",
                int(df_res["Año"].max()),
            )
        else:
            col_m2.metric("Año más reciente", "N/D")

        if "País" in df_res.columns and not df_res.empty:
            col_m3.metric(
                "Nº de países en resultados",
                df_res["País"].nunique(),
            )
        else:
            col_m3.metric("Nº de países en resultados", "N/D")

        # ── Gráfico simple: nº de docs por año ───────────────────────────
        if "Año" in df_res.columns and not df_res.empty:
            st.markdown("### Documentos por año")
            docs_por_anio = df_res.groupby("Año").size().reset_index(name="Documentos")
            docs_por_anio = docs_por_anio.sort_values("Año")
            st.bar_chart(docs_por_anio.set_index("Año"))

        # ── Tabla de resultados ───────────────────────────
        st.markdown("### Lista de documentos")
        st.dataframe(df_res, use_container_width=True)
