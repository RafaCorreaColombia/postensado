import pandas as pd
import numpy as np

# --- 1. ETABS IO & ALIGNMENT (MULTIESTADO) ---
def construir_alineamiento(df_cargas_crudo, story, secuencia_vigas, mapeo_combos):
    """
    Filtra y cose los resultados de ETABS en un solo eje continuo.
    Itera sobre el diccionario mapeo_combos para ensamblar todos los estados.
    """
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    df_total = pd.DataFrame()
    
    for estado, combo in mapeo_combos.items():
        if combo == "Ninguno": 
            continue
            
        df_combo = df_cargas_crudo[(df_cargas_crudo[col_combo] == combo) & (df_cargas_crudo['Story'] == story)].copy()
        df_eje = pd.DataFrame()
        x_global = 0.0
        
        for viga in secuencia_vigas:
            df_viga = df_combo[df_combo['Beam'] == viga].copy()
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
            
        if not df_eje.empty:
            df_eje = df_eje[['x', 'P', 'V2', 'M3']].rename(columns={'P':'P_ETABS', 'V2':'V_ETABS', 'M3':'M_ETABS'})
            df_eje['Estado'] = estado # Etiqueta vital para separar Transferencia de Servicio
            df_total = pd.concat([df_total, df_eje.sort_values('x').reset_index(drop=True)])
            
    return df_total

# --- 2. GEOMETRY BUILDER ---
def construir_geometria(x_estaciones, df_tramos_geom):
    """Interpola paramétricamente b y h para cada estación (Sección Bruta)."""
    df_g_limpio = df_tramos_geom.copy()
    for col in ['x', 'b', 'h']:
        df_g_limpio[col] = pd.to_numeric(df_g_limpio[col], errors='coerce')
    df_g_limpio = df_g_limpio.dropna(subset=['x', 'b', 'h']).sort_values('x')
    
    b_interp = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['b'])
    h_interp = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['h'])
    
    df_g = pd.DataFrame({'x': x_estaciones, 'b': b_interp, 'h': h_interp})
    df_g['A_bruta'] = df_g['b'] * df_g['h']
    df_g['I_bruta'] = (df_g['b'] * df_g['h']**3) / 12.0
    df_g['y_top'] = df_g['h'] / 2.0
    df_g['y_bot'] = df_g['h'] / 2.0
    return df_g

# --- 3. TENDON BUILDER ---
def construir_tendon(x_estaciones, df_perfil_tendon, P_toron=140.0):
    """Interpola el perfil del tendón y calcula propiedades efectivas."""
    df_t_limpio = df_perfil_tendon.copy()
    for col in ['x', 'd_top']:
        df_t_limpio[col] = pd.to_numeric(df_t_limpio[col], errors='coerce')
    df_t_limpio = df_t_limpio.dropna(subset=['x', 'd_top']).sort_values('x')
    
    d_top_interp = np.interp(x_estaciones, df_t_limpio['x'], df_t_limpio['d_top'])
    
    torones = df_t_limpio['Torones'].dropna().iloc[0] if not df_t_limpio['Torones'].dropna().empty else 3
    perdidas = df_t_limpio['Pérdidas (%)'].dropna().iloc[0] if not df_t_limpio['Pérdidas (%)'].dropna().empty else 15.0
    
    df_t = pd.DataFrame({'x': x_estaciones, 'd_top': d_top_interp})
    df_t['Torones'] = torones
    df_t['P_efectiva'] = torones * P_toron * (1 - perdidas/100.0)
    
    # En transferencia asumimos que las pérdidas aún no han ocurrido (o son mínimas)
    # Por simplicidad, recalculamos un P_transferencia asumiendo 0% de pérdidas a largo plazo
    df_t['P_transferencia'] = torones * P_toron 
    
    return df_t

# --- 4. SECTION CHECKER & INSIGHTS (NSR-10) ---
def resolver_multiestado(df_fuerzas_multi, df_geom, df_tendon, diametro_ducto=0.0):
    """
    Crea el Single Source of Truth y calcula esfuerzos, 
    aplicando descuentos de ductos (NSR-10 C.18.2.6) solo en Transferencia.
    """
    # 1. Unir todo en el súper DataFrame iterativo
    df = pd.merge(df_fuerzas_multi, df_geom, on='x')
    df = pd.merge(df, df_tendon, on='x')
    
    # 2. Mecánica y Excentricidad
    df['e'] = df['y_top'] - df['d_top'] # Positivo hacia arriba
    
    # Aplicar la fuerza correcta según el estado
    df['P_aplicada'] = np.where(df['Estado'] == 'Transferencia', df['P_transferencia'], df['P_efectiva'])
    df['M_PT'] = (df['P_aplicada'] * df['e']) / 1000.0 # kN-m
    df['M_Neto'] = df['M_ETABS'] + df['M_PT']
    
    # 3. NSR-10 C.18.2.6: Descuento de ductos antes de la adherencia (Transferencia)
    # Asumimos que los ductos se agrupan en un ducto equivalente para el cálculo de inercias
    A_ducto = np.pi * (diametro_ducto**2) / 4.0
    # Teorema de Steiner: Inercia del ducto respecto al eje neutro bruto de la sección
    I_ducto_esp = A_ducto * (df['e']**2) 
    
    df['A_calc'] = np.where(df['Estado'] == 'Transferencia', df['A_bruta'] - A_ducto, df['A_bruta'])
    df['I_calc'] = np.where(df['Estado'] == 'Transferencia', df['I_bruta'] - I_ducto_esp, df['I_bruta'])
    
    # Módulos de sección calculados
    df['S_top_calc'] = df['I_calc'] / df['y_top']
    df['S_bot_calc'] = df['I_calc'] / df['y_bot']
    
    # 4. Esfuerzos Finales (Compresión +, Tensión -)
    df['Sigma_Axial'] = (df['P_aplicada']*1000 / df['A_calc']) - (df['P_ETABS']*1000 / df['A_calc'])
    df['Sigma_Top'] = df['Sigma_Axial'] - (df['M_Neto']*1e6 / df['S_top_calc'])
    df['Sigma_Bot'] = df['Sigma_Axial'] + (df['M_Neto']*1e6 / df['S_bot_calc'])
    
    return df

def generar_insights(df, fc, fci):
    """
    Auditor Virtual: Verifica límites de compresión y valida la Clase U (C.18.3.4).
    """
    alertas = []
    estados = df['Estado'].unique()
    
    lim_comp_transf = 0.60 * fci
    lim_tens_transf = -0.25 * np.sqrt(fci)
    lim_comp_serv = 0.45 * fc
    lim_tens_serv = -0.62 * np.sqrt(fc)
    
    for estado in estados:
        df_est = df[df['Estado'] == estado]
        if df_est.empty: continue
        
        lim_c = lim_comp_transf if estado == 'Transferencia' else lim_comp_serv
        lim_t = lim_tens_transf if estado == 'Transferencia' else lim_tens_serv
        
        # Verificación Clase U (Tracción)
        fallas_tens_sup = df_est[df_est['Sigma_Top'] < lim_t]
        fallas_tens_inf = df_est[df_est['Sigma_Bot'] < lim_t]
        
        if not fallas_tens_sup.empty:
            alertas.append(f"🔴 **[{estado}] Límite Clase U Excedido:** Tensión en fibra superior supera {lim_t:.2f} MPa. *La teoría elástica pierde validez (sección fisurada Clase T o C).*")
        if not fallas_tens_inf.empty:
            alertas.append(f"🔴 **[{estado}] Límite Clase U Excedido:** Tensión en fibra inferior supera {lim_t:.2f} MPa.")
            
        # Verificación Compresión
        fallas_comp_sup = df_est[df_est['Sigma_Top'] > lim_c]
        fallas_comp_inf = df_est[df_est['Sigma_Bot'] > lim_c]
        
        if not fallas_comp_sup.empty or not fallas_comp_inf.empty:
            alertas.append(f"🟠 **[{estado}] Límite Compresión Excedido:** Esfuerzo supera {lim_c:.2f} MPa. *Sug: Revisa la sección geométrica o disminuye la fuerza del PT.*")
            
    if not alertas:
        alertas.append("✅ **Diseño Óptimo (Clase U):** Todos los estados cumplen los límites elásticos de servicio NSR-10 (C.18.4).")
        
    return alertas
