import pandas as pd
import numpy as np

def cruzar_geometria_y_cargas(df_geometria, df_cargas, combo_seleccionado, story_seleccionado, beam_seleccionado):
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas.columns else 'Load Case/Combo'
    
    df_cargas_filtrado = df_cargas[
        (df_cargas[col_combo] == combo_seleccionado) & 
        (df_cargas['Story'] == story_seleccionado) & 
        (df_cargas['Beam'] == beam_seleccionado)
    ].copy()
    
    if df_cargas_filtrado.empty:
        raise ValueError(f"No se encontraron resultados para el Story: {story_seleccionado}, Beam: {beam_seleccionado} y Combo: {combo_seleccionado}")

    df_cargas_filtrado = df_cargas_filtrado.rename(columns={'Station': 'Station_Load'})
    
    # 💡 FORZAR CONVERSIÓN NUMÉRICA ESTRICTA EN EL CSV DE ETABS
    for col in ['Station_Load', 'P', 'V2', 'M3']:
        if col in df_cargas_filtrado.columns:
            # Reemplazar comas por puntos por si ETABS exporta con formato regional europeo
            if df_cargas_filtrado[col].dtype == object:
                df_cargas_filtrado[col] = df_cargas_filtrado[col].astype(str).str.replace(',', '.')
            df_cargas_filtrado[col] = pd.to_numeric(df_cargas_filtrado[col], errors='coerce')
            
    df_geometria['Station (m)'] = pd.to_numeric(df_geometria['Station (m)'], errors='coerce')
    
    df_cargas_filtrado = df_cargas_filtrado.sort_values(by=['Station_Load'])
    df_geometria = df_geometria.sort_values(by=['Station (m)'])
    
    df_fusionado = pd.merge_asof(
        df_geometria,
        df_cargas_filtrado[['Station_Load', 'P', 'V2', 'M3']],
        left_on='Station (m)',
        right_on='Station_Load',
        direction='nearest',
        tolerance=0.05
    )
    
    if df_fusionado['P'].isna().sum() > 0:
        df_fusionado = df_fusionado.dropna(subset=['P'])
        
    df_fusionado = df_fusionado.drop(columns=['Station_Load'], errors='ignore')
    
    df_fusionado = df_fusionado.rename(columns={
        "P": "P_Frame (kN)",
        "V2": "V2 (kN)",
        "M3": "M3 (kN-m)"
    })
    
    return df_fusionado
