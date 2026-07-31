import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def plot_master_alignment(df, lim_comp, lim_tens):
    """
    Construye la gráfica maestra de 4 paneles sincronizados.
    Muestra geometría física, equilibrio axial, equilibrio a flexión y esfuerzos netos.
    """
    # Crear figura de 4 filas compartiendo el mismo eje X
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        subplot_titles=(
            "1. Perfil Longitudinal y Trazado del Tendón", 
            "2. Equilibrio de Fuerzas Axiales (kN)", 
            "3. Equilibrio de Momentos (kN-m)", 
            "4. Envolvente de Esfuerzos (MPa)"
        ),
        row_heights=[0.3, 0.2, 0.25, 0.25] # Proporciones de las gráficas
    )
    
    x = df['x']
    
    # =========================================================================
    # ROW 1: Geometría Física y Tendón
    # =========================================================================
    y_top = np.zeros(len(df))     # Fibra superior como y=0 de referencia
    y_bot = -df['h']              # Fibra inferior
    y_cg = -df['y_cg']            # Eje Neutro
    y_tendon = -df['d_top']       # Perfil del tendón
    
    # Masa de concreto (Relleno entre top y bot)
    fig.add_trace(go.Scatter(
        x=x, y=y_top, mode='lines', line=dict(color='black', width=2), 
        name='Fibra Superior', showlegend=False
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=x, y=y_bot, mode='lines', line=dict(color='black', width=2), 
        fill='tonexty', fillcolor='rgba(200, 200, 200, 0.3)', 
        name='Masa de Concreto', showlegend=False
    ), row=1, col=1)
    
    # Eje Neutro
    fig.add_trace(go.Scatter(
        x=x, y=y_cg, mode='lines', line=dict(color='gray', width=1, dash='dashdot'), 
        name='Eje Neutro (CG)'
    ), row=1, col=1)
    
    # Tendón (Con marcadores para ver la discretización y Hover para la excentricidad)
    customdata_tendon = np.stack((df['d_top'], df['e']), axis=-1)
    hovertemplate_tendon = "x: %{x:.2f} m<br>d_top: %{customdata[0]:.1f} mm<br>Excentricidad (e): %{customdata[1]:.1f} mm"
    
    fig.add_trace(go.Scatter(
        x=x, y=y_tendon, mode='lines+markers', 
        line=dict(color='#D32F2F', width=2), 
        marker=dict(size=6, color='#D32F2F'), 
        name='Tendón PT',
        customdata=customdata_tendon,
        hovertemplate=hovertemplate_tendon
    ), row=1, col=1)

    # =========================================================================
    # ROW 2: Equilibrio Axial
    # =========================================================================
    fig.add_trace(go.Scatter(
        x=x, y=df['P_Frame'], mode='lines', 
        line=dict(color='gray', width=2), 
        fill='tozeroy', fillcolor='rgba(128,128,128,0.2)', 
        name='Axial Modelo (ETABS)'
    ), row=2, col=1)
    
    fig.add_trace(go.Scatter(
        x=x, y=df['P_PT'], mode='lines', 
        line=dict(color='#FF9800', width=2), 
        name='Fuerza PT (Pe)'
    ), row=2, col=1)
    
    fig.add_trace(go.Scatter(
        x=x, y=df['P_Neto'], mode='lines', 
        line=dict(color='#1976D2', width=3), 
        name='Axial Neto (PT - Modelo)'
    ), row=2, col=1)
    
    # =========================================================================
    # ROW 3: Equilibrio de Momentos (El Panel Didáctico)
    # =========================================================================
    # M_ETABS relleno
    fig.add_trace(go.Scatter(
        x=x, y=df['M_Frame'], mode='lines', 
        line=dict(color='gray', width=2), 
        fill='tozeroy', fillcolor='rgba(128,128,128,0.3)', 
        name='Momento Modelo (ETABS)'
    ), row=3, col=1)
    
    # M_PT relleno (Hover didáctico desglosando M = P*e)
    customdata_mpt = np.stack((df['P_PT'], df['e']), axis=-1)
    hovertemplate_mpt = (
        "x: %{x:.2f} m<br>"
        "P_efectiva: %{customdata[0]:.1f} kN<br>"
        "Excentricidad (e): %{customdata[1]:.1f} mm<br>"
        "<b>M_PT: %{y:.1f} kN-m</b>"
    )
    
    fig.add_trace(go.Scatter(
        x=x, y=df['M_PT'], mode='lines', 
        line=dict(color='#FF9800', width=2), 
        fill='tozeroy', fillcolor='rgba(255,152,0,0.3)', 
        name='Momento Restitutivo PT',
        customdata=customdata_mpt, 
        hovertemplate=hovertemplate_mpt
    ), row=3, col=1)
    
    # Momento Neto Grueso
    fig.add_trace(go.Scatter(
        x=x, y=df['M_Neto'], mode='lines', 
        line=dict(color='#0288D1', width=3), 
        name='Momento Neto'
    ), row=3, col=1)

    # =========================================================================
    # ROW 4: Esfuerzos de Servicio
    # =========================================================================
    fig.add_trace(go.Scatter(
        x=x, y=df['Sigma_Top'], mode='lines', 
        line=dict(color='#2196F3', width=2), 
        name='σ Superior (Top)'
    ), row=4, col=1)
    
    fig.add_trace(go.Scatter(
        x=x, y=df['Sigma_Bot'], mode='lines', 
        line=dict(color='#F44336', width=2), 
        name='σ Inferior (Bot)'
    ), row=4, col=1)
    
    # Líneas límite horizontales
    fig.add_hline(y=lim_comp, line_dash="dash", line_color="green", row=4, col=1, annotation_text=f"Lím. Compresión ({lim_comp:.1f})")
    fig.add_hline(y=lim_tens, line_dash="dash", line_color="red", row=4, col=1, annotation_text=f"Lím. Tensión (Clase U: {lim_tens:.1f})")
    fig.add_hline(y=0, line_color="black", row=4, col=1, opacity=0.5)

    # =========================================================================
    # Ajustes visuales de la figura
    # =========================================================================
    fig.update_layout(
        height=1000, 
        hovermode="x unified", # Esto activa el tooltip sincronizado en todos los gráficos a la vez
        title_text=f"Auditoría Visual: {df['Estado'].iloc[0]}",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    fig.update_yaxes(title_text="Elevación (mm)", row=1, col=1)
    fig.update_yaxes(title_text="Fuerza (kN)", row=2, col=1)
    fig.update_yaxes(title_text="Momento (kN-m)", row=3, col=1)
    fig.update_yaxes(title_text="Esfuerzo (MPa)", row=4, col=1)
    fig.update_xaxes(title_text="Estación Global del Eje (m)", row=4, col=1)
    
    return fig
