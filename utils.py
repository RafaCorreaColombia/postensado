import pandas as pd
import numpy as np

def limpiar_csv_etabs(df_cargas):
    """Limpia tipos de datos y estandariza nombres de columnas."""
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas.columns else 'Load Case/Combo'
    df_cargas = df_cargas.rename(columns={col_combo: 'Combo', 'Station': 'Station_Local'})
    
    cols_a_limpiar = ['Station_Local', 'P', 'V2', 'M3']
    for col in cols_a_limpiar:
        if col in df_cargas.columns:
            if df_cargas[col].dtype == object:
                df_cargas[col] = df_cargas[col].astype(str).str.replace(',', '.')
            df_cargas[col] = pd.to_numeric(df_cargas[col], errors='coerce')
            
    return df_cargas.dropna(subset=['Combo'])

def construir_alineamiento_fuerzas(df_cargas_crudo, story, secuencia_vigas, mapeo_combos):
    """
    Cose múltiples Frames de ETABS en una sola viga continua y extrae 
    las combinaciones específicas para cada estado de diseño normativo.
    """
    df = limpiar_csv_etabs(df_cargas_crudo)
    df = df[df['Story'] == story].copy()
    
    resultados_estados = []
    
    # Para cada estado de diseño (Transferencia, Servicio 1, etc.) y su respectivo Combo
    for estado_normativo, combo_asignado in mapeo_combos.items():
        if not combo_asignado:
            continue
            
        df_combo = df[df['Combo'] == combo_asignado].copy()
        
        # Reconstrucción del Eje Longitudinal
        estacion_global_acumulada = 0.0
        df_eje = pd.DataFrame()
        
        for viga in secuencia_vigas:
            df_viga = df_combo[df_combo['Beam'] == viga].copy()
            if df_viga.empty:
                continue
                
            df_viga = df_viga.sort_values(by='Station_Local')
            longitud_viga = df_viga['Station_Local'].max()
            
            # Crear la estación global (0 hasta L_total)
            df_viga['Station_Global (m)'] = df_viga['Station_Local'] + estacion_global_acumulada
            estacion_global_acumulada += longitud_viga
            
            df_eje = pd.concat([df_eje, df_viga])
            
        if not df_eje.empty:
            # Seleccionar y renombrar para la salida final
            df_eje = df_eje[['Station_Global (m)', 'P', 'V2', 'M3']].copy()
            df_eje = df_eje.rename(columns={"P": "P_Frame (kN)", "V2": "V2 (kN)", "M3": "M3 (kN-m)"})
            df_eje['Estado'] = estado_normativo
            resultados_estados.append(df_eje)
            
    if not resultados_estados:
        return pd.DataFrame()
        
    return pd.concat(resultados_estados, ignore_index=True)

def fusionar_geometria_y_tendon(df_fuerzas, df_geom, df_tendon):
    """Cruza la geometría (E2K) y el tendón con el eje de fuerzas global."""
    # En un caso real, la geometría vendría interpolada del E2K global.
    # Aquí hacemos un merge_asof global para asociar b, h, y el tendón a las estaciones de fuerza.
    
    df_fuerzas = df_fuerzas.sort_values('Station_Global (m)')
    df_geom = df_geom.sort_values('Station_Global (m)')
    df_tendon = df_tendon.sort_values('Station_Global (m)')
    
    # 1. Asociar Geometría
    df_check = pd.merge_asof(
        df_fuerzas, df_geom, on='Station_Global (m)', direction='nearest', tolerance=0.1
    )
    # 2. Asociar Tendón
    df_check = pd.merge_asof(
        df_check, df_tendon, on='Station_Global (m)', direction='nearest', tolerance=0.1
    )
    
    return df_check.dropna(subset=['b (mm)', 'Torones'])
