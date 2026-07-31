import streamlit as st
import pandas as pd
import numpy as np

# Importamos tu nuevo motor estructural
from engine import construir_alineamiento, construir_geometria, construir_tendon, resolver_estado, generar_insights
from plots import plot_master_alignment

st.set_page_config(page_title="PT Beam Studio", layout="wide")
st.title("🏗️ PT Beam Studio")
st.markdown("Diseño, reconstrucción y auditoría de alineamientos continuos postensados.")

# --- 1. BARRA LATERAL (ARCHIVOS Y NORMAS) ---
with st.sidebar:
    st.header("1. Archivos del Modelo")
    # El E2K lo dejamos preparado para la siguiente fase de desarrollo
    e2k_file = st.file_uploader("Subir E2K (Geometría - Fase 2)", type=['e2k'])
    csv_file = st.file_uploader("Subir CSV de Fuerzas (ETABS)", type=['csv'])
    
    st.header("2. Materiales NSR-10")
    fc = st.number_input("f'c (MPa) [Servicio]", value=28.0)
    fci = st.number_input("f'ci (MPa) [Transferencia]", value=21.0)
    P_toron = st.number_input("Fuerza Gato por Torón (kN)", value=140.0)

# --- 2. FLUJO PRINCIPAL ---
if csv_file is not None:
    # 2.1 Búsqueda inteligente de la cabecera del CSV
    lineas = csv_file.getvalue().decode("utf-8").splitlines()
    fila_encabezado = next((i for i, l in enumerate(lineas) if "Load Case/Combo" in l or "OutputCase" in l), 0)
    csv_file.seek(0)
    
    df_cargas_crudo = pd.read_csv(csv_file, skiprows=fila_encabezado, low_memory=False)
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    df_cargas_crudo = df_cargas_crudo.dropna(subset=[col_combo])

    # 2.2 Selectores del Alineamiento
    st.header("1. Definición del Alineamiento y Estados")
    col_alig, col_est = st.columns(2)
    
    with col_alig:
        st.subheader("Alineamiento Estructural")
        stories = df_cargas_crudo['Story'].dropna().unique().tolist()
        story_elegido = st.selectbox("Seleccionar Piso:", stories)
        
        beams_disponibles = df_cargas_crudo[df_cargas_crudo['Story'] == story_elegido]['Beam'].dropna().unique().tolist()
        
        # El usuario elige qué vigas conforman la línea continua
        secuencia_vigas = st.multiselect(
            "Secuencia de vigas (Eje Continuo):", 
            beams_disponibles, 
            default=beams_disponibles[:min(6, len(beams_disponibles))]
        )
    
    with col_est:
        st.subheader("Asignación Normativa (NSR-10 C.18.4)")
        col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
        combos = ["Ninguno"] + df_cargas_crudo[col_combo].dropna().unique().tolist()
        
        # 1. Estado Inicial (C.18.4.1)
        st.markdown("**1. Etapa de Transferencia (Antes de pérdidas)**")
        combo_transf = st.selectbox("Cargas al transferir (Ej. PP + PT_Transfer):", combos)
        
        # 2. Estados de Servicio (C.18.4.2)
        st.markdown("**2. Etapa de Servicio (Después de pérdidas)**")
        combo_serv1 = st.selectbox("Servicio 1 (Ej. PP+D1+PT_Final):", combos)
        combo_serv2 = st.selectbox("Servicio 2 (Ej. PP+D1+L1+PT_Final):", combos)
        combo_serv3 = st.selectbox("Servicio 3 (Opcional):", combos)
        combo_serv4 = st.selectbox("Servicio 4 (Opcional):", combos)
        
        # Diccionario para enviar al motor
        mapeo_combos = {
            "Transferencia": combo_transf,
            "Servicio 1": combo_serv1,
            "Servicio 2": combo_serv2,
            "Servicio 3": combo_serv3,
            "Servicio 4": combo_serv4
        }
        
        # Filtrar solo los estados que el usuario sí asignó
        mapeo_combos = {k: v for k, v in mapeo_combos.items() if v != "Ninguno"}

    if not secuencia_vigas:
        st.warning("⚠️ Selecciona al menos una viga para construir el eje.")
        st.stop()

    # 2.3 Construir el Eje Longitudinal de Fuerzas (LLama a engine.py)
    try:
        df_fuerzas = construir_alineamiento(df_cargas_crudo, story_elegido, secuencia_vigas, combo_servicio)
    except Exception as e:
        st.error(f"Error al construir el alineamiento: {e}")
        st.stop()
        
    if df_fuerzas.empty:
        st.error(f"No se encontraron fuerzas para el eje seleccionado con el combo '{combo_servicio}'.")
        st.stop()
        
    L_total = df_fuerzas['x'].max()

    # --- 3. MODELADO FÍSICO PARAMÉTRICO ---
    st.markdown("---")
    st.header("2. Modelado Físico del Eje")
    col_g, col_t = st.columns(2)
    
    with col_g:
        st.subheader("📐 Geometría Paramétrica")
        st.info(f"Longitud total detectada: **{L_total:.2f} m**")
        
        # Nota explicativa de unidades para Geometría
        st.caption("💡 **Unidades:** **x** (posición en metros), **b** (ancho en mm), **h** (peralte/altura en mm).")
        
        # Tabla inicial básica
        geom_init = pd.DataFrame({"x": [0.0, L_total], "b": [250.0, 250.0], "h": [500.0, 500.0]})
        df_geom_param = st.data_editor(geom_init, num_rows="dynamic", use_container_width=True, hide_index=True)

    with col_t:
        st.subheader("➰ Perfil del Tendón (Puntos de Control)")
        st.info("Define los cambios de trazado. El motor interpolará el resto.")
        
        # Nota explicativa súper clara sobre d_top
        st.markdown(
            "📐 **¿Qué es `d_top`?** Es el recubrimiento superior. Se mide desde la **fibra superior** de la losa/viga "
            "hacia abajo hasta el centroide del cable. Ingrésalo siempre como un valor **positivo**. "
            "*(No te preocupes por el signo, la gráfica ya sabe dibujarlo hacia abajo).* "
        )
        st.caption("💡 **Unidades:** **x** (metros), **d_top** (mm), **Pérdidas** (%).")
        
        # Tres puntos básicos: inicio, medio, fin
        tendon_init = pd.DataFrame({"x": [0.0, L_total/2, L_total], "d_top": [50.0, 400.0, 50.0], "Torones": [3, 3, 3], "Pérdidas (%)": [15.0, 15.0, 15.0]})
        df_tendon_param = st.data_editor(tendon_init, num_rows="dynamic", use_container_width=True, hide_index=True)

    # --- 4. ENSAMBLAJE (SINGLE SOURCE OF TRUTH) ---
    # Interpolar y cruzar todo
    df_geom = construir_geometria(df_fuerzas['x'], df_geom_param)
    df_tendon = construir_tendon(df_fuerzas['x'], df_tendon_param, P_toron)
    
    # Calcular
    df_master = resolver_estado(df_fuerzas, df_geom, df_tendon, "Servicio")

    # --- 5. RESULTADOS Y AUDITORÍA ---
    st.markdown("---")
    st.header("📊 Auditoría de Servicio y Esfuerzos")
    
    # Límites calculados según normatividad
    lim_comp_val = 0.45 * fc
    lim_tens_val = -0.62 * np.sqrt(fc)
    
    # Inteligencia de diseño
    alertas = generar_insights(df_master, lim_comp_val, lim_tens_val)
    for alerta in alertas:
        st.markdown(alerta)

    # Gráfica maestra sincronizada
    fig = plot_master_alignment(df_master, lim_comp_val, lim_tens_val)
    st.plotly_chart(fig, use_container_width=True)

else:
    # Pantalla de bienvenida cuando no hay archivo
    st.info("💡 Por favor, sube tu tabla de fuerzas CSV de ETABS en la barra lateral para comenzar a diseñar.")
