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

- A la izquierda escribes una pregunta o tema.
- El agente busca en un subconjunto local de metadatos de CGSpace (archivo CSV).
- A la derecha ves los documentos encontrados, con enlaces al repositorio.

Más adelante, este mismo diseño se puede conectar a la **API de CGSpace** en producción.
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
# Función de búsqueda local (mini "tool" del agente)
# ─────────────────────────────────────────────
def buscar_localmente(query: str, df: pd.DataFrame, max_results: int = 50) -> pd.DataFrame:
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
# Layout: chat (izquierda) + panel de resultados (derecha)
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

        # "Herramienta" del agente: búsqueda en datos locales
        df_resultados = buscar_localmente(user_input, df_base, max_results=50)
        st.session_state.results_df = df_resultados

        # Construir respuesta simple del agente
        if df_resultados.empty:
            respuesta = (
                "He buscado en el subconjunto local de CGSpace y **no encontré documentos** "
                "relacionados con esa consulta.\n\n"
                "Recuerda que este es solo un subconjunto pequeño de ejemplos. "
                "En producción, el agente trabajaría sobre todos los registros de CGSpace."
            )
        else:
            n = len(df_resultados)
            # Años y países presentes
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
                "Puedes ver la lista completa en el panel de la derecha."
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
        st.metric("Documentos encontrados", len(df_res))
        st.dataframe(df_res, use_container_width=True)
