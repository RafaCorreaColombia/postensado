import pandas as pd
import numpy as np

def cruzar_geometria_y_cargas(df_geometria, df_cargas, combo_seleccionado, story_seleccionado, beam_seleccionado):
    """
    Cruza la geometría con las fuerzas del CSV de ETABS usando Story y Beam (Etiqueta).
    """
    # 1. Filtrar las cargas por la combinación y por el Story/Beam seleccionado por el usuario
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas.columns else 'Load Case/Combo'
    
    df_cargas_filtrado = df_cargas[
        (df_cargas[col_combo] == combo_seleccionado) & 
        (df_cargas['Story'] == story_seleccionado) & 
        (df_cargas['Beam'] == beam_seleccionado)
    ].copy()
    
    if df_cargas_filtrado.empty:
        raise ValueError(f"No se encontraron resultados para el Story: {story_seleccionado}, Beam: {beam_seleccionado} y Combo: {combo_seleccionado}")

    # 2. Renombrar la estación de carga para evitar conflictos en el merge
    df_cargas_filtrado = df_cargas_filtrado.rename(columns={'Station': 'Station_Load'})
    
    # Asegurar tipos de datos numéricos
    df_cargas_filtrado['Station_Load'] = pd.to_numeric(df_cargas_filtrado['Station_Load'], errors='coerce')
    df_geometria['Station (m)'] = pd.to_numeric(df_geometria['Station (m)'], errors='coerce')
    
    # Ordenar estrictamente para merge_asof
    df_cargas_filtrado = df_cargas_filtrado.sort_values(by=['Station_Load'])
    df_geometria = df_geometria.sort_values(by=['Station (m)'])
    
    # 3. Cruce inteligente por proximidad de estación (tolerancia de 5 cm)
    df_fusionado = pd.merge_asof(
        df_geometria,
        df_cargas_filtrado[['Station_Load', 'P', 'V2', 'M3']],
        left_on='Station (m)',
        right_on='Station_Load',
        direction='nearest',
        tolerance=0.05
    )
    
    # Limpieza de nulos
    if df_fusionado['P'].isna().sum() > 0:
        df_fusionado = df_fusionado.dropna(subset=['P'])
        
    df_fusionado = df_fusionado.drop(columns=['Station_Load'], errors='ignore')
    return df_fusionado
