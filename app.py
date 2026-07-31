import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import construir_alineamiento_fuerzas, fusionar_geometria_y_tendon

st.set_page_config(page_title="Section Checker | ETABS", layout="wide")

st.title("🏗️ Section Checker (Post-procesador Avanzado)")
st.markdown("Verificación de ejes estructurales continuos, geometría inmutable y chequeos multinorma.")

# --- 1. CARGA DE ARCHIVOS ---
with st.sidebar:
    st.header("1. Archivos del Modelo")
    e2k_file = st.file_uploader("Subir E2K (Geometría - Fase 2)", type=['e2k'])
    csv_file = st.file_uploader("Subir CSV de Fuerzas", type=['csv'])
    
    st.header("2. Materiales NSR-10")
    fc = st.number_input("f'c (MPa) [Servicio]", value=28.0)
    fci = st.number_input("f'ci (MPa) [Transferencia]", value=21.0)
    P_toron = st.number_input("Fuerza Gato por Torón (kN)", value=140.0)

if csv_file is None:
    st.info("💡 Por favor, sube tu tabla de fuerzas de ETABS para comenzar.")
    st.stop()

# Leer datos crudos buscando la cabecera real
lineas = csv_file.getvalue().decode("utf-8").splitlines()
fila_encabezado = next((i for i, l in enumerate(lineas) if "Load Case/Combo" in l or "OutputCase" in l), 0)
csv_file.seek(0)
df_cargas_crudo = pd.read_csv(csv_file, skiprows=fila_encabezado, low_memory=False)

# --- 2. CONFIGURACIÓN DEL EJE Y COMBINACIONES ---
st.header("1. Definición del Alineamiento y Combinaciones")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Alineamiento Estructural")
    stories = df_cargas_crudo['Story'].dropna().unique().tolist()
    story_elegido = st.selectbox("Seleccionar Piso:", stories)
    
    beams_disponibles = df_cargas_crudo[df_cargas_crudo['Story'] == story_elegido]['Beam'].dropna().unique().tolist()
    # El usuario selecciona en orden las vigas que conforman el eje continuo
    secuencia_vigas = st.multiselect(
        "Seleccionar secuencia de vigas para el Eje Continuo (Ej. B1, B2, B3...):", 
        beams_disponibles, 
        default=beams_disponibles[:min(6, len(beams_disponibles))]
    )

with col2:
    st.subheader("Asignación de Combinaciones Normativas")
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    combos = [""] + df_cargas_crudo[col_combo].dropna().unique().tolist()
    
    mapeo_combos = {
        "Transferencia (f'ci)": st.selectbox("Combo para Transferencia:", combos, index=combos.index('PT-TRANSFER') if 'PT-TRANSFER' in combos else 0),
        "Servicio Sostenido (D)": st.selectbox("Combo para Servicio Permanente:", combos, index=combos.index('s1PPD1') if 's1PPD1' in combos else 0),
        "Servicio Total (D+L)": st.selectbox("Combo para Servicio Completo:", combos, index=combos.index('s1PPD1L1') if 's1PPD1L1' in combos else 0)
    }

# Construir el Eje
df_fuerzas_eje = construir_alineamiento_fuerzas(df_cargas_crudo, story_elegido, secuencia_vigas, mapeo_combos)

if df_fuerzas_eje.empty:
    st.warning("Selecciona al menos una viga y una combinación para procesar.")
    st.stop()

L_total = df_fuerzas_eje['Station_Global (m)'].max()

# --- 3. GEOMETRÍA Y TENDÓN CONTINUOS ---
st.markdown("---")
st.header("2. Diseño sobre el Eje Continuo")
col_g, col_t = st.columns([1, 1.2])

with col_g:
    st.subheader("Geometría Inmutable (Lectura E2K)")
    st.info(f"Longitud total del eje detectada: **{L_total:.2f} m**")
    # MOCKUP: En el futuro esto lo extrae tu parser E2K
    estaciones_geom = np.linspace(0, L_total, 15)
    df_geom = pd.DataFrame({
        "Station_Global (m)": estaciones_geom,
        "b (mm)": 250.0,
        "h (mm)": 100.0 + 400.0 * (estaciones_geom / L_total) if L_total > 0 else 500.0
    })
    st.dataframe(df_geom, use_container_width=True, hide_index=True)

with col_t:
    st.subheader("Trazado del Tendón (Editable)")
    df_tendon_base = pd.DataFrame({
        "Station_Global (m)": [0.0, L_total/2, L_total],
        "d_top (mm)": [50.0, 300.0, 50.0],
        "Torones": [3, 3, 3],
        "Pérdidas (%)": [15.0, 15.0, 15.0]
    })
    df_tendon_editado = st.data_editor(df_tendon_base, num_rows="dynamic", use_container_width=True, hide_index=True)

# --- 4. MOTOR SÚPER POST-PROCESADOR ---
df_check = fusionar_geometria_y_tendon(df_fuerzas_eje, df_geom, df_tendon_editado)

# Cálculos de sección
df_check["A (mm2)"] = df_check["b (mm)"] * df_check["h (mm)"]
df_check["c_sup (mm)"] = df_check["h (mm)"] / 2.0
df_check["c_inf (mm)"] = df_check["h (mm)"] / 2.0
df_check["S_sup (mm3)"] = (df_check["b (mm)"] * df_check["h (mm)"]**2) / 6.0
df_check["S_inf (mm3)"] = df_check["S_sup (mm3)"]

# Dinámica PT
df_check["P_efectiva (kN)"] = df_check["Torones"] * P_toron * (1 - df_check["Pérdidas (%)"]/100)
df_check["e (mm)"] = df_check["c_sup (mm)"] - df_check["d_top (mm)"]
df_check["Momento_PT (kN-m)"] = (df_check["P_efectiva (kN)"] * df_check["e (mm)"]) / 1000 

# Esfuerzos
df_check["Sigma_Axial"] = (df_check["P_efectiva (kN)"] * 1000 / df_check["A (mm2)"]) - (df_check["P_Frame (kN)"] * 1000 / df_check["A (mm2)"])
df_check["Sigma_M_sup"] = (df_check["M3 (kN-m)"] * 1e6) / df_check["S_sup (mm3)"]
df_check["Sigma_M_inf"] = -(df_check["M3 (kN-m)"] * 1e6) / df_check["S_inf (mm3)"]
df_check["Sigma_PT_sup"] = (df_check["Momento_PT (kN-m)"] * 1e6) / df_check["S_sup (mm3)"]
df_check["Sigma_PT_inf"] = -(df_check["Momento_PT (kN-m)"] * 1e6) / df_check["S_inf (mm3)"]

df_check["Sigma_Top (MPa)"] = df_check["Sigma_Axial"] + df_check["Sigma_M_sup"] + df_check["Sigma_PT_sup"]
df_check["Sigma_Bot (MPa)"] = df_check["Sigma_Axial"] + df_check["Sigma_M_inf"] + df_check["Sigma_PT_inf"]

# --- 5. GRÁFICAS Y VERIFICACIÓN CONTINUA ---
st.markdown("---")
st.header("📊 Verificación Continua del Eje")

estado_ver_elegido = st.radio("Seleccionar Estado a visualizar:", df_check['Estado'].unique(), horizontal=True)
df_plot = df_check[df_check['Estado'] == estado_ver_elegido]

# Límites Dinámicos (Dependen del Estado)
if "Transferencia" in estado_ver_elegido:
    lim_comp = 0.60 * fci
    lim_tens = -0.25 * np.sqrt(fci)
else:
    lim_comp = 0.45 * fc
    lim_tens = -0.62 * np.sqrt(fc)

fig = go.Figure()
fig.add_trace(go.Scatter(x=df_plot["Station_Global (m)"], y=df_plot["Sigma_Top (MPa)"], 
                         mode='lines', name='σ Superior (Top)', line=dict(color='#2196F3', width=3, shape='spline')))
fig.add_trace(go.Scatter(x=df_plot["Station_Global (m)"], y=df_plot["Sigma_Bot (MPa)"], 
                         mode='lines', name='σ Inferior (Bot)', line=dict(color='#F44336', width=3, shape='spline')))
fig.add_hline(y=lim_comp, line_dash="dash", line_color="green", annotation_text=f"Límite Compresión ({lim_comp:.1f})")
fig.add_hline(y=lim_tens, line_dash="dash", line_color="orange", annotation_text=f"Límite Tensión ({lim_tens:.2f})")
fig.add_hline(y=0, line_color="black")

fig.update_layout(title=f"Envolvente de Esfuerzos: {estado_ver_elegido}", xaxis_title="Eje Longitudinal (m)", yaxis_title="Esfuerzo (MPa)", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
