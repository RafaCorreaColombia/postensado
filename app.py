import streamlit as st
import pandas as pd
import numpy as np

# Importamos el Súper Motor
from engine import (
    construir_alineamiento, 
    construir_propiedades_seccion, 
    construir_tendon, 
    resolver_multiestado, 
    generar_insights
)
from plots import plot_master_alignment

st.set_page_config(page_title="PT Beam Studio", layout="wide")
st.title("🏗️ PT Beam Studio")
st.markdown("Motor paramétrico de diseño, reconstrucción y auditoría de vigas postensadas (NSR-10).")

# --- 1. BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("1. Carga de Archivos")
    e2k_file = st.file_uploader("Geometría E2K (Fase 2)", type=['e2k'], disabled=False)
    csv_file = st.file_uploader("Fuerzas CSV (ETABS)", type=['csv'])
    
    st.header("2. Materiales NSR-10")
    fc = st.number_input("f'c (MPa) [Servicio]", value=35.0)
    fci = st.number_input("f'ci (MPa) [Transferencia]", value=28.0)
    P_toron = st.number_input("Fuerza por Torón (kN)", value=147.3)
    
    st.header("3. Propiedades Constructivas")
    diametro_ducto = st.number_input("Diámetro del ducto (mm)", value=60.0)

# --- 2. ORQUESTACIÓN DEL EJE ---
if csv_file is not None:
    # 2.1 Lector inteligente de CSV
    lineas = csv_file.getvalue().decode("utf-8").splitlines()
    fila_encabezado = next((i for i, l in enumerate(lineas) if "Load Case/Combo" in l or "OutputCase" in l), 0)
    csv_file.seek(0)
    
    df_cargas_crudo = pd.read_csv(csv_file, skiprows=fila_encabezado, low_memory=False)
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    df_cargas_crudo = df_cargas_crudo.dropna(subset=[col_combo])

    # 2.2 Definición del Alineamiento y Mapeo Multiestado
    st.header("1. Definición del Alineamiento Estructural")
    col_alig, col_est = st.columns([1.2, 1])
    
    with col_alig:
        st.subheader("Conectividad Física")
        stories = df_cargas_crudo['Story'].dropna().unique().tolist()
        story_elegido = st.selectbox("Seleccionar Piso:", stories)
        
        beams_disponibles = df_cargas_crudo[df_cargas_crudo['Story'] == story_elegido]['Beam'].dropna().unique().tolist()
        secuencia_vigas = st.multiselect(
            "Selecciona y ordena los Frames para armar la viga continua:", 
            beams_disponibles, 
            default=beams_disponibles[:min(6, len(beams_disponibles))]
        )
    
    with col_est:
        st.subheader("Estados de Carga (NSR-10 C.18.4)")
        combos = ["Ninguno"] + df_cargas_crudo[col_combo].dropna().unique().tolist()
        
        # Mapeo del ciclo de vida
        mapeo_combos = {
            "Transferencia": st.selectbox("Etapa Transferencia (PP + PT_Transfer):", combos, index=combos.index('s3PPPTransf') if 's3PPPTransf' in combos else 0),
            "Servicio 1 (Permanente)": st.selectbox("Servicio 1 (Ej. PP+D+PT_Final):", combos, index=combos.index('s3PPD1PTfinal') if 's3PPD1PTfinal' in combos else 0),
            "Servicio 2 (Total)": st.selectbox("Servicio 2 (Ej. PP+D+L+PT_Final):", combos, index=combos.index('s3PPD1L1PTfinal') if 's3PPD1L1PTfinal' in combos else 0)
        }

    if not secuencia_vigas:
        st.warning("⚠️ Debes seleccionar al menos una viga.")
        st.stop()

    # 2.3 Construcción paralela del alineamiento (Bugs corregidos)
    df_fuerzas_eje = construir_alineamiento(df_cargas_crudo, story_elegido, secuencia_vigas, mapeo_combos)
    
    if df_fuerzas_eje.empty:
        st.error("No se extrajeron fuerzas válidas para los estados seleccionados.")
        st.stop()
        
    L_total = df_fuerzas_eje['x'].max()

    # --- 3. DISEÑO PARAMÉTRICO ---
    st.markdown("---")
    st.header("2. Diseño Paramétrico del Eje")
    st.markdown("💡 *Agrega filas con `+` para definir variaciones del ala o del alma lungo el eje.*")
    
    col_g, col_t = st.columns(2)
    with col_g:
        st.subheader("📐 Geometría de Sección T (Losa + Viga)")
        st.caption("💡 **Unidades:** **b_w** (ancho alma en mm), **h_w** (peralte viga en mm), **b_lado** (ala efectiva a CADA LADO en mm), **h_f** (espesor losa en mm).")
        
        # Geometría inicial con la losa
        geom_init = pd.DataFrame({
            "x": [0.0, 5.0, L_total], 
            "b_w": [250.0, 250, 250.0], 
            "h_w": [100.0, 500.0, 500.0],
            "b_lado": [300, 300.0, 300.0],  # Ej: 300mm a cada lado = 850mm total de compresión
            "h_f": [100.0, 100, 100.0]       # Losa de 10cm
        })
        df_geom_param = st.data_editor(geom_init, num_rows="dynamic", use_container_width=True, hide_index=True)

    with col_t:
        st.subheader("➰ Perfil del Tendón (PT Builder)")
        st.caption("💡 **Unidades:** **x** (m), **d_top** (mm desde fibra superior de losa), **Pérdidas** (%).")
        tendon_init = pd.DataFrame({
            "x": [0.0, L_total/2, L_total], 
            "d_top": [50.0, 50.0, 250.0], 
            "Torones": [3, 3, 3], 
            "Pérdidas (%)": [18.7, 18.75, 18.75]
        })
        df_tendon_param = st.data_editor(tendon_init, num_rows="dynamic", use_container_width=True, hide_index=True)

    # --- 4. ENSAMBLAJE (RESOLVER ESTADOS) ---
    # Reconstrucción continua
    df_geom = construir_propiedades_seccion(df_fuerzas_eje['x'], df_geom_param, diametro_ducto)
    df_tendon = construir_tendon(df_fuerzas_eje['x'], df_tendon_param, P_toron)
    
    # El Solver Sincronizado
    df_master = resolver_multiestado(df_fuerzas_eje, df_geom, df_tendon)

    # --- 5. RESULTADOS INTERACTIVOS (EXPLORADOR) ---
    st.markdown("---")
    st.header("📊 Explorador de Estados Límite")
    
    # Selector de pestañas por Estado (Radio buttons súper limpios)
    estado_ver_elegido = st.radio("Filtro de Visualización:", df_master['Estado'].unique(), horizontal=True)
    df_plot = df_master[df_master['Estado'] == estado_ver_elegido]
    
    # Límites Normativos
    lim_comp = 0.60 * fci if estado_ver_elegido == 'Transferencia' else 0.45 * fc
    lim_tens = -0.25 * np.sqrt(fci) if estado_ver_elegido == 'Transferencia' else -0.62 * np.sqrt(fc)

    # Gráfica Sincronizada (Las 3 gráficas atadas al mismo eje X)
    fig = plot_master_alignment(df_plot, lim_comp, lim_tens)
    st.plotly_chart(fig, use_container_width=True)
    
    # Auditoría Estructurada
    st.subheader("📝 Auditoría NSR-10")
    df_alertas = generar_insights(df_master, fc, fci)
    
    if df_alertas.empty:
        st.success("✅ **Diseño Óptimo:** La viga no presenta fallas por esfuerzos de flexión en ningún estado (Clase U).")
    else:
        # Mostramos los errores en formato DataFrame rojo/naranja
        st.error(f"🔴 Se detectaron {len(df_alertas)} puntos fuera de norma.")
        st.dataframe(df_alertas, use_container_width=True, hide_index=True)

else:
    st.info("💡 Por favor, sube tu tabla de fuerzas CSV de ETABS en la barra lateral.")
