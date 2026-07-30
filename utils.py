import pandas as pd
import numpy as np

def cruzar_geometria_y_cargas(df_geometria, df_cargas, combo_seleccionado):
    """
    Cruza la geometría del .e2k con los resultados de fuerzas del CSV de ETABS.
    
    Parámetros:
    df_geometria (pd.DataFrame): DataFrame parseado del e2k (columnas: 'Frame', 'Station (m)', 'b (mm)', 'h (mm)')
    df_cargas (pd.DataFrame): DataFrame exportado de ETABS (columnas esperadas: 'Story', 'Label', 'UniqueName', 'OutputCase', 'StepType', 'Station', 'P', 'V2', 'V3', 'T', 'M2', 'M3')
    combo_seleccionado (str): El nombre de la combinación de carga a filtrar (ej. 'D+L+PT')
    
    Retorna:
    pd.DataFrame: Un DataFrame consolidado con geometría y fuerzas listas para calcular esfuerzos.
    """
    
    # 1. Filtrar las cargas por la combinación solicitada
    # Asumimos que la columna de ETABS se llama 'OutputCase' o 'Load Case/Combo'
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas.columns else 'Load Case/Combo'
    df_cargas_filtrado = df_cargas[df_cargas[col_combo] == combo_seleccionado].copy()
    
    if df_cargas_filtrado.empty:
        raise ValueError(f"No se encontraron resultados para la combinación: {combo_seleccionado}")

    # 2. Renombrar y estandarizar columnas clave para el cruce
    # ETABS a veces exporta el ID del frame como 'UniqueName' o 'Label'
    col_frame_id = 'UniqueName' if 'UniqueName' in df_cargas.columns else 'Label'
    df_cargas_filtrado = df_cargas_filtrado.rename(columns={
        col_frame_id: 'Frame', 
        'Station': 'Station_Load' # Renombramos para evitar conflictos directos
    })
    
    # Asegurar tipos de datos correctos
    df_cargas_filtrado['Station_Load'] = pd.to_numeric(df_cargas_filtrado['Station_Load'], errors='coerce')
    df_geometria['Station (m)'] = pd.to_numeric(df_geometria['Station (m)'], errors='coerce')
    
    # Ordenar por Frame y Estación (Requisito estricto para merge_asof)
    df_cargas_filtrado = df_cargas_filtrado.sort_values(by=['Frame', 'Station_Load'])
    df_geometria = df_geometria.sort_values(by=['Frame', 'Station (m)'])
    
    # 3. El Cruce Inteligente (merge_asof)
    # Por cada fila de df_geometria, buscará la fila en df_cargas_filtrado con el mismo 'Frame'
    # y con la 'Station_Load' más cercana a 'Station (m)', tolerando hasta 5 cm (0.05m) de diferencia.
    
    df_fusionado = pd.merge_asof(
        df_geometria,
        df_cargas_filtrado[['Frame', 'Station_Load', 'P', 'V2', 'M3']], # Seleccionamos solo las fuerzas necesarias
        left_on='Station (m)',
        right_on='Station_Load',
        by='Frame',
        direction='nearest',
        tolerance=0.05 # Tolerancia de 5 cm para variaciones de redondeo en estaciones
    )
    
    # 4. Limpieza Final
    # Identificar si algunas estaciones no encontraron fuerzas (quedarán como NaN)
    nulos = df_fusionado['P'].isna().sum()
    if nulos > 0:
        print(f"Advertencia: {nulos} estaciones no encontraron fuerzas cercanas en el CSV.")
        df_fusionado = df_fusionado.dropna(subset=['P']) # Opcional: eliminar filas sin fuerzas
        
    df_fusionado = df_fusionado.drop(columns=['Station_Load'])
    
    return df_fusionado
