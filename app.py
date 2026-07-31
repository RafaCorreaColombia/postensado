import streamlit as st
import pandas as pd
from engine import construir_alineamiento, construir_geometria, construir_tendon, resolver_estado, generar_insights
from plots import plot_master_alignment

st.set_page_config(page_title="PT Beam Studio", layout="wide")
st.title("🏗️ PT Beam Studio")
st.markdown("Diseño, reconstrucción y auditoría de alineamientos continuos postensados.")

# --- MOCKUP DE DATOS (Fase de Pruebas sin CSV) ---
# Simulamos que ya leímos el ETABS y el usuario armó la viga de 10m
x_estaciones = np.linspace(0, 10, 21) 
df_fuerzas = pd.DataFrame({'x': x_estaciones, 'P_ETABS': 0.0, 'V_ETABS': 50.0, 'M_ETABS': -45 * (x_estaciones/5)**2 + 100})

# --- UI: DEFINICIÓN PARAMÉTRICA ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📐 Geometría Paramétrica (Tramos)")
    geom_init = pd.DataFrame({"x": [0.0, 10.0], "b": [250.0, 250.0], "h": [100.0, 500.0]})
    df_geom_param = st.data_editor(geom_init, num_rows="dynamic", use_container_width=True)

with col2:
    st.subheader("➰ Perfil del Tendón (Control Points)")
    tendon_init = pd.DataFrame({"x": [0.0, 5.0, 10.0], "d_top": [50.0, 400.0, 50.0], "Torones": [3, 3, 3], "Pérdidas (%)": [15, 15, 15]})
    df_tendon_param = st.data_editor(tendon_init, num_rows="dynamic", use_container_width=True)

# --- ENSAMBLAJE DE ALIGNMENT DATA (Single Source of Truth) ---
df_geom = construir_geometria(df_fuerzas['x'], df_geom_param)
df_tendon = construir_tendon(df_fuerzas['x'], df_tendon_param)

# Evaluamos un Estado de Servicio (Mockup f'c=28)
df_master = resolver_estado(df_fuerzas, df_geom, df_tendon, "Servicio Sostenido (D+PT)")

# --- RESULTADOS Y GRÁFICAS ---
st.markdown("---")
st.header("🧠 Asistente de Diseño")

# El programa lee el df_master y te dice dónde falla
alertas = generar_insights(df_master, lim_comp=12.6, lim_tens=-3.28)
for alerta in alertas:
    st.markdown(alerta)

# La gráfica maestra
fig = plot_master_alignment(df_master, lim_comp=12.6, lim_tens=-3.28)
st.plotly_chart(fig, use_container_width=True)
