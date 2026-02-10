import streamlit as st
import pandas as pd

st.set_page_config(page_title="CGSpace Agent Demo", layout="wide")

st.title("Agente CGSpace – Demo inicial en Streamlit Cloud")

st.write("""
Bienvenida/o  

Esta es una primera prueba de despliegue en **Streamlit Cloud**.  
Más adelante aquí pondremos:

- un chat para que el usuario haga preguntas,
- búsqueda en CGSpace (API),
- estadísticas y resúmenes.

Por ahora, esto solo confirma que el despliegue funciona.
""")

data = [
    {"Título": "Documento de prueba 1", "Año": 2021},
    {"Título": "Documento de prueba 2", "Año": 2022},
]
df = pd.DataFrame(data)

st.subheader("Ejemplo de tabla")
st.dataframe(df, use_container_width=True)
