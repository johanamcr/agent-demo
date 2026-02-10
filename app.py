import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────
# Configuración de la página
# ─────────────────────────────────────────────
st.set_page_config(page_title="Agente CGSpace – Demo", layout="wide")

st.title("Agente CGSpace – Demo con datos locales de CGSpace")

st.write(
    """
Este demo muestra cómo podría funcionar un **agente** sobre CGSpace:

- A la izquierda escribes una pregunta o tema (chat).
- El agente busca en un subconjunto local de metadatos de CGSpace (archivo CSV).
- A la derecha ves métricas, filtros, gráfico y la lista de documentos encontrados.

En producción, este mismo diseño se puede conectar a la **API REST de CGSpace**.
"""
)

# ─────────────────────────────────────────────
# Cargar datos locales de CGSpace desde CSV
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=True)
def cargar_datos() -> pd.DataFrame:
    df = pd.read_csv("cgspace_demo.csv")
    # Aseguramos tipos
    if "Año" in df.columns:
        df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
    return df


df_base = cargar_datos()

# ─────────────────────────────────────────────
# Estado de sesión: historial de chat y resultados
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

if "results_df" not in st.session_state:
    st.session_state.results_df = df_base.copy()

# ─────────────────────────────────────────────
# Herramienta del agente: búsqueda local
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

        # 1) Búsqueda primaria en los datos locales (tool del agente)
        df_resultados = buscar_localmente(user_input, df_base, max_results=200)

        # Guardamos sin filtros (después filtramos por país/año en el panel)
        st.session_state.results_df = df_resultados

        # 2) Construir respuesta de texto del agente
        if df_resultados.empty:
            respuesta = (
                "He buscado en el subconjunto local de CGSpace y **no encontré documentos** "
                "relacionados con esa consulta.\n\n"
                "Recuerda que este es solo un subconjunto pequeño de ejemplos. "
                "En producción, el agente trabajaría sobre todos los registros de CGSpace."
            )
        else:
            n = len(df_resultados)
            if "Año" in df_resultados.columns:
                años_min = int(df_resultados["Año"].min())
                años_max = int(df_resultados["Año"].max())
                rango_años = f"{años_min}–{años_max}"
            else:
                rango_años = "N/D"

            if "País" in df_resultados.columns:
                paises = ", ".join(df_resultados["País"].dropna().unique().tolist())
            else:
                paises = "N/D"

            titulos_ejemplo = "- " + "\n- ".join(
                df_resultados["Título"].head(3).tolist()
            )

            respuesta = (
                f"He encontrado **{n}** documentos en el subconjunto local de CGSpace.\n\n"
                f"- Rango de años en los resultados: **{rango_años}**\n"
                f"- Países presentes: **{paises}**\n\n"
                f"Algunos títulos de ejemplo:\n{titulos_ejemplo}\n\n"
                "Puedes refinar por año o país en el panel de la derecha."
            )

        st.session_state.messages.append({"role": "assistant", "content": respuesta})
        with st.chat_message("assistant"):
            st.markdown(respuesta)


with col_panel:
    st.subheader("Resultados (subconjunto local de CGSpace)")

    df_res = st.session_state.results_df

    if df_res is None or df_res.empty:
        st.info(
            "Aquí aparecerán los documentos filtrados del subconjunto local de CGSpace. "
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
