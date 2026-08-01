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
