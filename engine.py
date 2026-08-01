import pandas as pd
import numpy as np

# --- 1. ETABS IO & ALIGNMENT ---
def construir_alineamiento(df_cargas_crudo, story, secuencia_vigas, mapeo_combos):
    """Filtra y cose los resultados de ETABS en un solo eje continuo para múltiples estados."""
    col_combo = 'OutputCase' if 'OutputCase' in df_cargas_crudo.columns else 'Load Case/Combo'
    df_total = pd.DataFrame()
    
    for estado, combo in mapeo_combos.items():
        if combo == "Ninguno": continue
            
        df_combo = df_cargas_crudo[(df_cargas_crudo[col_combo] == combo) & (df_cargas_crudo['Story'] == story)].copy()
        df_eje = pd.DataFrame()
        x_global = 0.0
        
        for viga in secuencia_vigas:
            df_viga = df_combo[df_combo['Beam'] == viga].copy()
            if df_viga.empty: continue
            
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
            df_eje = df_eje[['x', 'P', 'V2', 'M3']].rename(columns={'P':'P_Frame', 'V2':'V_Frame', 'M3':'M_Frame'})
            df_eje['Estado'] = estado
            df_total = pd.concat([df_total, df_eje.sort_values('x').reset_index(drop=True)])
            
    return df_total

# --- 2. SECTION BUILDER (SECCIÓN T RIGUROSA - MEDIDA DESDE EL TOP) ---
def construir_propiedades_seccion(x_estaciones, df_tramos_geom, diametro_ducto=0.0):
    """
    Calcula propiedades geométricas para sección T/L medida desde la fibra superior hacia abajo (y=0 arriba).
    """
    df_g_limpio = df_tramos_geom.copy()
    
    cols_num = ['x', 'b_w', 'h_w', 'b_lado', 'h_f']
    for col in cols_num:
        if col in df_g_limpio.columns:
            df_g_limpio[col] = pd.to_numeric(df_g_limpio[col], errors='coerce')
            
    df_g_limpio = df_g_limpio.dropna(subset=['x', 'b_w', 'h_w']).sort_values('x')
    
    # 1. Interpolación de componentes
    b_w = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['b_w'])
    h_w = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['h_w'])
    b_lado = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['b_lado']) if 'b_lado' in df_g_limpio.columns else np.zeros(len(x_estaciones))
    h_f = np.interp(x_estaciones, df_g_limpio['x'], df_g_limpio['h_f']) if 'h_f' in df_g_limpio.columns else np.zeros(len(x_estaciones))
    
    df_g = pd.DataFrame({'x': x_estaciones, 'b_w': b_w, 'h_w': h_w, 'b_lado': b_lado, 'h_f': h_f})
    df_g['h'] = df_g['h_w'] # Peralte total
    
    # Ancho total del ala (b_w + a cada lado)
    b_total = df_g['b_w'] + 2.0 * df_g['b_lado']
    
    # 2. Desglose de Componentes de la Sección T (Desde el Top y=0)
    # A. Ala (Flange): Ancho b_total, Altura h_f
    A_flange = b_total * df_g['h_f']
    y_flange = df_g['h_f'] / 2.0  # Centroide del ala desde arriba
    
    # B. Alma restante (Web): Ancho b_w, Altura (h_w - h_f)
    h_web_real = np.maximum(df_g['h_w'] - df_g['h_f'], 0.0) # Evitar alturas negativas
    A_web = df_g['b_w'] * h_web_real
    y_web = df_g['h_f'] + (h_web_real / 2.0)  # Centroide del alma desde arriba
    
    # 3. Propiedades Brutas Totales
    df_g['A_bruta'] = A_flange + A_web
    
    # Centroide de la sección T medido desde la fibra superior (y_cg)
    df_g['y_cg'] = np.where(df_g['A_bruta'] > 0, 
                            (A_flange * y_flange + A_web * y_web) / df_g['A_bruta'], 
                            df_g['h_w'] / 2.0)
    
    # 4. Inercia Bruta (Teorema de Steiner respecto al eje y_cg de la sección T)
    I_flange = (b_total * df_g['h_f']**3) / 12.0 + A_flange * (df_g['y_cg'] - y_flange)**2
    I_web = (df_g['b_w'] * h_web_real**3) / 12.0 + A_web * (df_g['y_cg'] - y_web)**2
    df_g['I_bruta'] = I_flange + I_web
    
    # 5. Descuento de Ductos (NSR-10 C.18.2.6)
    A_ducto = np.pi * (diametro_ducto**2) / 4.0
    df_g['A_ducto'] = A_ducto
    
    return df_g

# --- 3. TENDON BUILDER ---
def construir_tendon(x_estaciones, df_perfil_tendon, P_toron=140.0):
    """Genera el cable como una entidad separada considerando pérdidas iniciales y a largo plazo."""
    df_t_limpio = df_perfil_tendon.copy()
    
    for col in ['x', 'd_top']:
        if col in df_t_limpio.columns:
            df_t_limpio[col] = pd.to_numeric(df_t_limpio[col], errors='coerce')
            
    df_t_limpio = df_t_limpio.dropna(subset=['x', 'd_top']).sort_values('x')
    
    d_top_interp = np.interp(x_estaciones, df_t_limpio['x'], df_t_limpio['d_top'])
    
    torones = df_t_limpio['Torones'].dropna().iloc[0] if 'Torones' in df_t_limpio.columns and not df_t_limpio['Torones'].dropna().empty else 3
    
    # 1. Leer Pérdida Inicial (%) con valores por defecto (12.5%) o compatibilidad hacia atrás
    if 'Pérdida Inicial (%)' in df_t_limpio.columns and not df_t_limpio['Pérdida Inicial (%)'].dropna().empty:
        p_ini = df_t_limpio['Pérdida Inicial (%)'].dropna().iloc[0]
    elif 'Pérdidas (%)' in df_t_limpio.columns and not df_t_limpio['Pérdidas (%)'].dropna().empty:
        p_ini = df_t_limpio['Pérdidas (%)'].dropna().iloc[0]
    else:
        p_ini = 12.5
        
    # 2. Leer Pérdida a Largo Plazo (%) con valor por defecto (6.25%)
    if 'Pérdida Largo Plazo (%)' in df_t_limpio.columns and not df_t_limpio['Pérdida Largo Plazo (%)'].dropna().empty:
        p_lp = df_t_limpio['Pérdida Largo Plazo (%)'].dropna().iloc[0]
    else:
        p_lp = 6.25
    
    df_t = pd.DataFrame({'x': x_estaciones, 'd_top': d_top_interp})
    df_t['Torones'] = torones
    
    # Fuerza total inicial en el gato (Jacking Force)
    P_jacking = torones * P_toron
    
    # --- MATEMÁTICA DE PÉRDIDAS ---
    # Transferencia: Se descuenta la pérdida inicial apenas se suelta el gato (ej. 12.5%)
    df_t['P_PT_Transfer'] = P_jacking * (1.0 - p_ini / 100.0)
    
    # Servicio / Final: A partir de la fuerza de transferencia, se aplica la pérdida a largo plazo (ej. 6.25%)
    df_t['P_PT_Final'] = df_t['P_PT_Transfer'] * (1.0 - p_lp / 100.0)
    
    return df_t

# --- 4. ENGINE (MECÁNICA Y ÁRBOL DE RESULTANTES) ---
def resolver_multiestado(df_fuerzas_multi, df_geom, df_tendon):
    """Crea el Single Source of Truth y calcula esfuerzos basados en Resultantes Netas."""
    df = pd.merge(df_fuerzas_multi, df_geom, on='x')
    df = pd.merge(df, df_tendon, on='x')
    
    # --- A. MECÁNICA PURA E INERCIAS ---
    df['P_PT'] = np.where(df['Estado'] == 'Transferencia', df['P_PT_Transfer'], df['P_PT_Final'])
    
    # Excentricidad geométrica pura
    df['e'] = df['y_cg'] - df['d_top'] 
    
    # Propiedades de Sección (Descuento de ductos en Transferencia)
    df['A_calc'] = np.where(df['Estado'] == 'Transferencia', df['A_bruta'] - df['A_ducto'], df['A_bruta'])
    I_ducto_esp = df['A_ducto'] * (df['e']**2)
    df['I_calc'] = np.where(df['Estado'] == 'Transferencia', df['I_bruta'] - I_ducto_esp, df['I_bruta'])
    
    df['S_top'] = df['I_calc'] / df['y_cg']
    df['S_bot'] = df['I_calc'] / (df['h'] - df['y_cg'])
    
    # --- B. ACCIONES NETAS (RESULTANTES ESTRUCTURALES) ---
    df['M_PT'] = (df['P_PT'] * df['e']) / 1000.0 
    
    df['M_Neto'] = df['M_Frame'] + df['M_PT']
    df['P_Neto'] = df['P_PT'] - df['P_Frame'] 
    
    # --- C. ÁRBOL DE CONTRIBUCIONES (Estrictamente para tablas de auditoría) ---
    df['Sigma_Axial_PT'] = (df['P_PT'] * 1000.0) / df['A_calc']
    df['Sigma_Axial_Frame'] = -(df['P_Frame'] * 1000.0) / df['A_calc']
    
    # Asumiendo Convención Clásica: M positivo (+) tracciona abajo y comprime arriba
    df['Sigma_M_Frame_Top'] = (df['M_Frame'] * 1e6) / df['S_top']
    df['Sigma_M_Frame_Bot'] = -(df['M_Frame'] * 1e6) / df['S_bot']
    
    df['Sigma_M_PT_Top'] = (df['M_PT'] * 1e6) / df['S_top']
    df['Sigma_M_PT_Bot'] = -(df['M_PT'] * 1e6) / df['S_bot']

    # --- D. CÁLCULO DEFINITIVO DE ESFUERZOS (El enfoque robusto) ---
    # 1. Axial Neto
    df['Sigma_Axial'] = (df['P_Neto'] * 1000.0) / df['A_calc']
    
    # 2. Flexión Neta
    # Convención: Si M_Neto es negativo (Hogging), M_Neto/S_top da negativo (Tensión arriba).
    # -M_Neto/S_bot da positivo (Compresión abajo).
    df['Sigma_Flex_Top'] = (df['M_Neto'] * 1e6) / df['S_top']
    df['Sigma_Flex_Bot'] = -(df['M_Neto'] * 1e6) / df['S_bot']
    
    # 3. Superposición Final Limpia
    df['Sigma_Top'] = df['Sigma_Axial'] + df['Sigma_Flex_Top']
    df['Sigma_Bot'] = df['Sigma_Axial'] + df['Sigma_Flex_Bot']
    
    return df

# --- 5. AUDITOR DE SERVICIO ESTRUCTURADO ---
def generar_insights(df, fc, fci):
    """Devuelve un DataFrame estructurado con los chequeos normativos diferenciando estados de servicio."""
    chequeos = []
    estados = df['Estado'].unique()
    
    # 💡 Límites ajustados según NSR-10 C.18.4
    limites = {
        'Transferencia': {
            'Compresión': 0.60 * fci, 
            'Tensión': -0.25 * np.sqrt(fci)
        },
        'Servicio 1 (Permanente)': {
            'Compresión': 0.45 * fc, 
            'Tensión': -0.62 * np.sqrt(fc)
        },
        'Servicio 2 (Total)': {
            'Compresión': 0.60 * fc, 
            'Tensión': -0.62 * np.sqrt(fc)
        }
    }
    
    for estado in estados:
        df_e = df[df['Estado'] == estado]
        if df_e.empty: continue
            
        # Buscar límites según el nombre exacto del estado (con fallback por seguridad)
        lim_comp = limites.get(estado, limites['Servicio 1 (Permanente)'])['Compresión']
        lim_tens = limites.get(estado, limites['Servicio 1 (Permanente)'])['Tensión']
        
        for _, row in df_e.iterrows():
            # Chequeo Top
            if row['Sigma_Top'] > lim_comp:
                chequeos.append({'Estado': estado, 'x (m)': row['x'], 'Fibra': 'Superior', 'Tipo': 'Compresión', 'Valor': row['Sigma_Top'], 'Límite': lim_comp, 'Cumple': '❌'})
            elif row['Sigma_Top'] < lim_tens:
                chequeos.append({'Estado': estado, 'x (m)': row['x'], 'Fibra': 'Superior', 'Tipo': 'Tensión (Clase U)', 'Valor': row['Sigma_Top'], 'Límite': lim_tens, 'Cumple': '❌'})
                
            # Chequeo Bot
            if row['Sigma_Bot'] > lim_comp:
                chequeos.append({'Estado': estado, 'x (m)': row['x'], 'Fibra': 'Inferior', 'Tipo': 'Compresión', 'Valor': row['Sigma_Bot'], 'Límite': lim_comp, 'Cumple': '❌'})
            elif row['Sigma_Bot'] < lim_tens:
                chequeos.append({'Estado': estado, 'x (m)': row['x'], 'Fibra': 'Inferior', 'Tipo': 'Tensión (Clase U)', 'Valor': row['Sigma_Bot'], 'Límite': lim_tens, 'Cumple': '❌'})
                
    df_alertas = pd.DataFrame(chequeos)
    return df_alertas
