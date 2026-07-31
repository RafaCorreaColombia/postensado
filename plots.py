import plotly.graph_objects as go
from plotly.subplots import make_subplots

def plot_master_alignment(df, lim_comp, lim_tens):
    """Dibuja Geometría, Momentos y Esfuerzos sincronizados."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("Perfil Longitudinal (Viga y Tendón)", "Equilibrio de Momentos (kN-m)", "Esfuerzos de Servicio (MPa)")
    )
    
    # --- ROW 1: Geometría y Tendón ---
    # Asumimos y_top = 0 para alinear visualmente la cara superior de la losa
    y_top_losa = [0] * len(df)
    y_bot_losa = -df['h']
    y_tendon = -df['d_top']
    
    fig.add_trace(go.Scatter(x=df['x'], y=y_top_losa, mode='lines', line=dict(color='black', width=2), name='Fibras', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['x'], y=y_bot_losa, mode='lines', line=dict(color='black', width=2), fill='tonexty', fillcolor='rgba(200, 200, 200, 0.2)', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['x'], y=y_tendon, mode='lines', line=dict(color='red', width=3, dash='dash'), name='Tendón PT'), row=1, col=1)
    
    # --- ROW 2: Momentos ---
    fig.add_trace(go.Scatter(x=df['x'], y=df['M_ETABS'], line=dict(color='gray', width=2), name='M ETABS'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['x'], y=df['M_PT'], line=dict(color='orange', width=2), name='M Postensado (Pe)'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['x'], y=df['M_Neto'], line=dict(color='blue', width=3), name='M Neto'), row=2, col=1)
    
    # --- ROW 3: Esfuerzos ---
    fig.add_trace(go.Scatter(x=df['x'], y=df['Sigma_Top'], line=dict(color='#2196F3', width=2), name='σ Superior'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df['x'], y=df['Sigma_Bot'], line=dict(color='#F44336', width=2), name='σ Inferior'), row=3, col=1)
    
    # Límites Normativos
    fig.add_hline(y=lim_comp, line_dash="dot", line_color="green", row=3, col=1, annotation_text="Lím. Compresión")
    fig.add_hline(y=lim_tens, line_dash="dot", line_color="red", row=3, col=1, annotation_text="Lím. Tensión")
    fig.add_hline(y=0, line_color="black", row=3, col=1)

    fig.update_layout(height=800, hovermode="x unified", title_text=f"Auditoría: {df['Estado'].iloc[0]}")
    fig.update_yaxes(title_text="Elevación (mm)", row=1, col=1)
    fig.update_yaxes(title_text="Momento (kN-m)", row=2, col=1)
    fig.update_yaxes(title_text="Esfuerzo (MPa)", row=3, col=1)
    fig.update_xaxes(title_text="Estación Global x (m)", row=3, col=1)
    
    return fig
