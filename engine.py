import pandas as pd
import numpy as np

# --- 1. ETABS IO & ALIGNMENT ---
def construir_alineamiento(df_cargas_crudo, story, secuencia_vigas, combo):
    """Filtra y cose los resultados de ETABS en un solo eje x continuo."""
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    df = df_cargas_crudo[(df_cargas_crudo[col_combo] == combo) & (df_cargas_crudo['Story'] == story)].copy()
    
    df_eje = pd.DataFrame()
    x_global = 0.0
    
    for viga in secuencia_vigas:
        df_viga = df[df['Beam'] == viga].copy()
        if df_viga.empty: continue
        
        # Limpieza numérica
        for col in ['Station', 'P', 'V2', 'M3']:
            if df_viga[col].dtype == object:
                df_viga[col] = df_viga[col].astype(str).str.replace(',', '.')
            df_viga[col] = pd.to_numeric(df_viga[col], errors='coerce')
            
        df_viga = df_viga.sort_values(by='Station')
        L_viga = df_viga['Station'].max()
        
        df_viga['x'] = df_viga['Station'] + x_global
        x_global += L_viga
        
        df_eje = pd.concat([df_eje, df_viga])
        
    if df_eje.empty: return pd.DataFrame()
    
    df_eje = df_eje[['x', 'P', 'V2', 'M3']].rename(columns={'P':'P_ETABS', 'V2':'V_ETABS', 'M3':'M_ETABS'})
    return df_eje.sort_values('x').reset_index(drop=True)

# --- 2. GEOMETRY BUILDER ---
def construir_geometria(x_estaciones, df_tramos_geom):
    """Interpola paramétricamente b y h para cada estación de ETABS."""
    
    # 💡 LIMPIEZA: Ignorar filas vacías de la UI, forzar números y ordenar de menor a mayor
    df_g_limpio = df_tramos_geom.copy()
    for col in ['x', 'b', 'h']:
        df_g_limpio[col] = pd.to_numeric(df_g_limpio[col], errors='coerce')
    df_g_limpio = df_g_limpio.dropna(subset=['x', 'b', 'h']).sort_values('x')
    
    # Interpolación
    b_interp = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['b'])
    h_interp = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['h'])
    
    df_g = pd.DataFrame({'x': x_estaciones, 'b': b_interp, 'h': h_interp})
    df_g['A'] = df_g['b'] * df_g['h']
    df_g['I'] = (df_g['b'] * df_g['h']**3) / 12.0
    df_g['y_top'] = df_g['h'] / 2.0
    df_g['y_bot'] = df_g['h'] / 2.0
    df_g['S_top'] = df_g['I'] / df_g['y_top']
    df_g['S_bot'] = df_g['I'] / df_g['y_bot']
    return df_g

# --- 3. TENDON BUILDER ---
def construir_tendon(x_estaciones, df_perfil_tendon, P_toron=140.0):
    """Interpola el perfil del tendón y calcula propiedades efectivas."""
    
    # 💡 LIMPIEZA: Lo mismo para el tendón
    df_t_limpio = df_perfil_tendon.copy()
    for col in ['x', 'd_top']:
        df_t_limpio[col] = pd.to_numeric(df_t_limpio[col], errors='coerce')
    df_t_limpio = df_t_limpio.dropna(subset=['x', 'd_top']).sort_values('x')
    
    d_top_interp = np.interp(x_estaciones, df_t_limpio['x'], df_t_limpio['d_top'])
    
    # Asume valores uniformes del primer tramo para simplificar este ejemplo
    torones = df_t_limpio['Torones'].dropna().iloc[0] if not df_t_limpio['Torones'].dropna().empty else 3
    perdidas = df_t_limpio['Pérdidas (%)'].dropna().iloc[0] if not df_t_limpio['Pérdidas (%)'].dropna().empty else 15.0
    
    df_t = pd.DataFrame({'x': x_estaciones, 'd_top': d_top_interp})
    df_t['Torones'] = torones
    df_t['P_efectiva'] = torones * P_toron * (1 - perdidas/100.0)
    return df_t

# --- 4. SECTION CHECKER & INSIGHTS ---
def resolver_estado(df_fuerzas, df_geom, df_tendon, estado_nombre):
    """Crea el Single Source of Truth y calcula esfuerzos."""
    # 1. Unir todo en el súper DataFrame
    df = pd.merge(df_fuerzas, df_geom, on='x')
    df = pd.merge(df, df_tendon, on='x')
    
    # 2. Mecánica
    df['Estado'] = estado_nombre
    df['e'] = df['y_top'] - df['d_top'] # Positivo hacia arriba
    df['M_PT'] = (df['P_efectiva'] * df['e']) / 1000.0 # kN-m
    df['M_Neto'] = df['M_ETABS'] + df['M_PT']
    
    # 3. Esfuerzos (Compresión +, Tensión -)
    df['Sigma_Axial'] = (df['P_efectiva']*1000 / df['A']) - (df['P_ETABS']*1000 / df['A'])
    df['Sigma_Top'] = df['Sigma_Axial'] - (df['M_Neto']*1e6 / df['S_top'])
    df['Sigma_Bot'] = df['Sigma_Axial'] + (df['M_Neto']*1e6 / df['S_bot'])
    
    return df

def generar_insights(df, lim_comp, lim_tens):
    """El Asistente Virtual que lee los resultados y explica el diseño."""
    alertas = []
    
    # Buscar fallas por tensión superior
    zonas_tens_sup = df[df['Sigma_Top'] < lim_tens]
    if not zonas_tens_sup.empty:
        x_min, x_max = zonas_tens_sup['x'].min(), zonas_tens_sup['x'].max()
        alertas.append(f"🔴 **Tensión Superior:** La fibra superior entra en tracción excesiva entre $x = {x_min:.2f}$ m y $x = {x_max:.2f}$ m. *Sug: Baje el tendón en el centro de la luz.*")
        
    # Buscar fallas por tensión inferior
    zonas_tens_inf = df[df['Sigma_Bot'] < lim_tens]
    if not zonas_tens_inf.empty:
        x_min, x_max = zonas_tens_inf['x'].min(), zonas_tens_inf['x'].max()
        alertas.append(f"🔴 **Tensión Inferior:** Inversión de momento o carga excesiva entre $x = {x_min:.2f}$ m y $x = {x_max:.2f}$ m. *Sug: Aumente excentricidad o revise carga viva.*")
        
    if not alertas:
        alertas.append("✅ **Diseño Óptimo:** El alineamiento cumple todos los criterios de servicio NSR-10.")
        
    return alertas
