import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Section Checker | ETABS", layout="wide")

st.title("🏗️ Section Checker (Post-procesador ETABS)")
st.markdown("Auditor de esfuerzos en servicio para secciones estructurales (Concreto, PT, Compuestos).")

# --- 1. BARRA LATERAL: ENTRADAS Y LÍMITES ---
with st.sidebar:
    st.header("1. Materiales y Normativa")
    fc = st.number_input("f'c (MPa)", value=28.0, step=1.0)
    fci = st.number_input("f'ci (MPa) [Transferencia]", value=21.0, step=1.0)
    P_toron = st.number_input("Fuerza por Torón (kN) [Gato]", value=140.0, step=5.0)
    
    st.markdown("---")
    st.markdown("**Límites NSR-10 (Servicio):**")
    lim_comp = 0.45 * fc
    lim_tens = -0.62 * np.sqrt(fc)
    st.write(f"🟢 Compresión Máx: **{lim_comp:.1f} MPa**")
    st.write(f"🔴 Tensión Máx: **{lim_tens:.2f} MPa**")
    
    st.markdown("---")
    st.header("2. Archivos (Opcional)")
    e2k_file = st.file_uploader("Subir .e2k (Geometría)", type=['e2k'])
    csv_file = st.file_uploader("Subir CSV (Fuerzas)", type=['csv'])

# --- 2. GESTIÓN DE DATOS (MODO DEMO VS DATOS REALES) ---
if csv_file is not None:
    # 1. BÚSQUEDA INTELIGENTE DE LA CABECERA EN EL CSV DE ETABS
    lineas = csv_file.getvalue().decode("utf-8").splitlines()
    
    fila_encabezado = 0
    for i, linea in enumerate(lineas):
        if "Load Case/Combo" in linea or "OutputCase" in linea:
            fila_encabezado = i
            break
            
    # 2. Leer el CSV saltando hasta la fila de encabezados encontrada
    csv_file.seek(0)
    df_cargas_crudo = pd.read_csv(csv_file, skiprows=fila_encabezado)
    df_cargas_crudo = df_cargas_crudo.dropna(subset=[df_cargas_crudo.columns[3]])
    
    # Selector dinámico de la combinación dentro del CSV real
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    combos_disponibles = df_cargas_crudo[col_combo].unique().tolist()
    combo_elegido = st.sidebar.selectbox("Seleccionar Combinación de ETABS:", combos_disponibles)
    
    # NOTA: Cuando tengas listo el parser completo de e2k, reemplazas geom_base por tu DataFrame real.
    estaciones = np.linspace(0, 5, 11)
    geom_base = pd.DataFrame({
        "Frame": "9",  # Nota: En tu CSV de ETABS el ID de la viga B1 es '9'
        "Station (m)": estaciones,
        "b (mm)": 250.0,
        "h (mm)": 100.0 + 400.0 * (estaciones / 5.0)
    })
    
    try:
        # AQUÍ ES DONDE LLAMAS A TU ARCHIVO UTILS.PY
        geom_data = cruzar_geometria_y_cargas(geom_base, df_cargas_crudo, combo_elegido)
        st.success(f"¡Cruce exitoso con la combinación '{combo_elegido}'!")
    except Exception as e:
        st.error(f"Error al cruzar datos: {e}")
        geom_data = pd.DataFrame()

else:
    # Modo Demo (El voladizo de Kike para pruebas rápidas sin archivos)
    st.info("💡 Modo Demo activado: Mostrando el voladizo de Kike (5m, peralte variable 100mm a 500mm). Sube tu CSV para usar datos reales.")
    estaciones = np.linspace(0, 5, 11)
    
    geom_data = pd.DataFrame({
        "Station (m)": estaciones,
        "b (mm)": 250.0,
        "h (mm)": 100.0 + 400.0 * (estaciones / 5.0),
        "P_Frame (kN)": 0.0, 
        "M3 (kN-m)": -45.0 * (estaciones / 5.0)**2 
    })

# --- 3. INTERFAZ PRINCIPAL ---
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📋 Geometría y Cargas de ETABS (Solo Lectura)")
    st.dataframe(geom_data, use_container_width=True, hide_index=True)

with col2:
    st.subheader("⚙️ Diseño de Postensado (Editable)")
    st.write("Modifica el trazado del cable, cantidad de torones y pérdidas por estación.")
    
    # Inicializamos la tabla editable basada en las estaciones
    pt_init = pd.DataFrame({
        "Station (m)": geom_data["Station (m)"],
        "d_top (mm)": 50.0,      # Cable pegado arriba por defecto
        "Torones": 3,            # Tu propuesta de 3 torones
        "Pérdidas (%)": 15.0     # Pérdidas típicas a largo plazo
    })
    
    # El usuario solo edita ESTA tabla
    df_pt = st.data_editor(pt_init, use_container_width=True, hide_index=True)

# --- 4. MOTOR DE CÁLCULO (SECTION CHECKER) ---
# Unimos Geometría inmutable + Diseño PT
df = pd.merge(geom_data, df_pt, on="Station (m)")

# Cálculos Estación por Estación
df["A (mm2)"] = df["b (mm)"] * df["h (mm)"]
df["c_sup (mm)"] = df["h (mm)"] / 2.0
df["c_inf (mm)"] = df["h (mm)"] / 2.0
df["I (mm4)"] = (df["b (mm)"] * df["h (mm)"]**3) / 12.0
df["S_sup (mm3)"] = df["I (mm4)"] / df["c_sup (mm)"]
df["S_inf (mm3)"] = df["I (mm4)"] / df["c_inf (mm)"]

# Dinámica del PT
df["P_efectiva (kN)"] = df["Torones"] * P_toron * (1 - df["Pérdidas (%)"]/100)
df["e (mm)"] = df["c_sup (mm)"] - df["d_top (mm)"] # Positivo si está por encima del centroide
df["Momento_PT (kN-m)"] = (df["P_efectiva (kN)"] * df["e (mm)"]) / 1000 # Pe

# Esfuerzos (Convención: Compresión es +, Tensión es -)
# 1. Axiales (PT comprime +, Frame P se asume tracción + en ETABS, por eso restamos)
sigma_axial = (df["P_efectiva (kN)"] * 1000 / df["A (mm2)"]) - (df["P_Frame (kN)"] * 1000 / df["A (mm2)"])

# 2. Flexión por Carga (M3 negativo tracciona arriba, comprime abajo)
sigma_M_sup = (df["M3 (kN-m)"] * 1e6) / df["S_sup (mm3)"] 
sigma_M_inf = -(df["M3 (kN-m)"] * 1e6) / df["S_inf (mm3)"]

# 3. Flexión por PT (e positivo comprime arriba, tracciona abajo)
sigma_PT_sup = (df["Momento_PT (kN-m)"] * 1e6) / df["S_sup (mm3)"]
sigma_PT_inf = -(df["Momento_PT (kN-m)"] * 1e6) / df["S_inf (mm3)"]

# 4. Sumatoria Final
df["Sigma_Top (MPa)"] = sigma_axial + sigma_M_sup + sigma_PT_sup
df["Sigma_Bot (MPa)"] = sigma_axial + sigma_M_inf + sigma_PT_inf

# --- 5. RESULTADOS Y GRÁFICAS ---
st.markdown("---")
st.header("📊 Resultados del Análisis")

tab1, tab2 = st.tabs(["📈 Gráfica de Esfuerzos", "🔍 Tabla Detallada & Diagnóstico"])

with tab1:
    fig = go.Figure()
    # Esfuerzo Superior
    fig.add_trace(go.Scatter(x=df["Station (m)"], y=df["Sigma_Top (MPa)"], 
                             mode='lines+markers', name='σ Superior (Top)', line=dict(color='#2196F3', width=3)))
    # Esfuerzo Inferior
    fig.add_trace(go.Scatter(x=df["Station (m)"], y=df["Sigma_Bot (MPa)"], 
                             mode='lines+markers', name='σ Inferior (Bot)', line=dict(color='#F44336', width=3)))
    
    # Líneas de límite NSR-10
    fig.add_hline(y=lim_comp, line_dash="dash", line_color="green", annotation_text="Lím. Compresión")
    fig.add_hline(y=lim_tens, line_dash="dash", line_color="orange", annotation_text="Lím. Tensión")
    fig.add_hline(y=0, line_color="black", line_width=1) # Eje neutro gráfico
    
    fig.update_layout(title="Esfuerzos Longitudinales vs Límites Normativos",
                      xaxis_title="Estación - Longitud (m)", yaxis_title="Esfuerzo (MPa) [Compresión +, Tensión -]",
                      hovermode="x unified", height=500)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Diagnóstico Intermedio del Postensado")
    # Mostramos los valores intermedios solicitados: P, e, Pe
    df_intermedio = df[["Station (m)", "P_efectiva (kN)", "e (mm)", "Momento_PT (kN-m)", "Sigma_Top (MPa)", "Sigma_Bot (MPa)"]].round(2)
    st.dataframe(df_intermedio, use_container_width=True, hide_index=True)

# --- 6. MÓDULO DE EXPLICABILIDAD (EL EXPERTO VIRTUAL) ---
st.markdown("---")
st.header("🧠 Inteligencia de Diseño (Explicabilidad)")

alertas = []
for index, row in df.iterrows():
    station = row["Station (m)"]
    sig_top = row["Sigma_Top (MPa)"]
    sig_bot = row["Sigma_Bot (MPa)"]
    
    # Chequeos Top
    if sig_top > lim_comp:
        alertas.append(f"🔴 **Estación {station:.2f} m (Fibra Superior):** Alcanza {sig_top:.1f} MPa de compresión, superando el límite de {lim_comp:.1f} MPa. *Sugerencia: Aumenta el peralte 'h', reduce el número de torones, o disminuye la excentricidad 'd_top'.*")
    elif sig_top < lim_tens:
        alertas.append(f"🟠 **Estación {station:.2f} m (Fibra Superior):** Entró en tensión con {sig_top:.2f} MPa, superando el límite de {lim_tens:.2f} MPa. *Sugerencia: El voladizo se está cayendo. Aumenta la excentricidad del cable (reduce d_top) o agrega más torones.*")
        
    # Chequeos Bot
    if sig_bot > lim_comp:
        alertas.append(f"🔴 **Estación {station:.2f} m (Fibra Inferior):** Alcanza {sig_bot:.1f} MPa de compresión. *Sugerencia: Demasiada carga axial o el cable está muy abajo. Revisa la posición del torón.*")
    elif sig_bot < lim_tens:
        alertas.append(f"🟠 **Estación {station:.2f} m (Fibra Inferior):** Entró en tensión con {sig_bot:.2f} MPa. *Sugerencia: El PT está 'levantando' demasiado la viga (Inversión de momento). Disminuye la excentricidad en esta zona, quita torones, o añade acero pasivo inferior.*")

if len(alertas) == 0:
    st.success("✅ **¡Diseño Perfecto!** Todas las estaciones cumplen con los límites de servicio de la NSR-10 Clase U. Puedes enviar los planos de esta sección.")
else:
    st.error("⚠️ **Se detectaron problemas en el diseño:**")
    for alerta in alertas:
        st.markdown(alerta)
