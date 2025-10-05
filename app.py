import streamlit as st
import pandas as pd
from stravalib import Client
import datetime

# --- CONFIGURACIÓN ---
# Cargar credenciales seguras desde Streamlit
CLIENT_ID = st.secrets["general"]["client_id"]
CLIENT_SECRET = st.secrets["general"]["client_secret"]
REFRESH_TOKEN = st.secrets["general"]["refresh_token"]

@st.cache_data(ttl=3600) # Cache para no llamar a la API en cada recarga (1 hora)
def get_strava_activities():
    """
    Se conecta a la API de Strava, refresca el token y obtiene las últimas 100 actividades.
    """
    client = Client()
    try:
        token_info = client.refresh_access_token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            refresh_token=REFRESH_TOKEN
        )
        client.access_token = token_info["access_token"]
        
        # Pedimos más actividades para tener un mejor análisis
        return list(client.get_activities(limit=100))
    except Exception as e:
        st.error(f"Error al conectar con Strava: {e}")
        return []

def process_activities(activities):
    """
    Procesa la lista de actividades y la convierte en un DataFrame de Pandas,
    enfocándose solo en las carreras (runs).
    """
    processed_data = []
    for act in activities:
        # Nos aseguramos de que la actividad sea de tipo 'Run'
        if act.type != 'Run':
            continue

        # Convertimos el objeto act.type a un string simple para evitar errores.
        activity_type_str = str(act.type)

        distancia_km = round(float(act.distance) / 1000, 2) if act.distance else 0
        
        # --- CORRECCIÓN DEL ERROR AttributeError: 'Duration' object ---
        # El objeto 'moving_time' de stravalib es un objeto 'Duration' que no tiene el método '.total_seconds()'.
        # Se puede convertir directamente a segundos (como un float) usando float().
        moving_time_seconds = float(act.moving_time) if act.moving_time else 0
        tiempo_min = round(moving_time_seconds / 60, 2)
        
        # Calculamos el ritmo en segundos por km para cálculos y gráficas
        ritmo_total_segundos = 0
        if moving_time_seconds > 0 and distancia_km > 0:
            # Usamos los segundos sin redondear para un cálculo de ritmo más preciso
            ritmo_total_segundos = moving_time_seconds / distancia_km
            
        processed_data.append({
            "ID": act.id,
            "Nombre": act.name,
            "Tipo": activity_type_str,
            "Distancia (km)": distancia_km,
            "Tiempo (min)": tiempo_min,
            "Desnivel (m)": float(act.total_elevation_gain) if act.total_elevation_gain else 0,
            "Ritmo (seg/km)": ritmo_total_segundos,
            "Fecha": act.start_date_local.strftime("%Y-%m-%d %H:%M:%S"),
        })
        
    if not processed_data:
        return pd.DataFrame()

    df = pd.DataFrame(processed_data)
    df['Fecha'] = pd.to_datetime(df['Fecha'])
    df = df.sort_values("Fecha", ascending=False).reset_index(drop=True)
    
    # Convertir ritmo de segundos a formato MM:SS para visualización
    df['Ritmo (min/km)'] = df['Ritmo (seg/km)'].apply(
        lambda s: f"{int(s // 60):02d}:{int(s % 60):02d}" if s > 0 else "N/A"
    )
    return df

# --- LAYOUT DE LA APP ---

st.set_page_config(page_title="Dashboard de Running", layout="wide")
st.title("🏃‍♂️ Dashboard de Running Strava")

activities = get_strava_activities()

if not activities:
    st.warning("No se pudieron cargar actividades de Strava.")
else:
    df_runs = process_activities(activities)
    
    if df_runs.empty:
        st.info("No se encontraron actividades de tipo 'Run' en las últimas 100 actividades.")
    else:
        st.success(f"¡Análisis completado! Se encontraron {len(df_runs)} carreras.")

        # --- KPIs / Métricas Principales ---
        st.subheader("Resumen de las últimas carreras")
        
        total_km = df_runs['Distancia (km)'].sum()
        total_time_min = df_runs['Tiempo (min)'].sum()
        total_elevation = df_runs['Desnivel (m)'].sum()
        avg_pace_seconds = df_runs[df_runs['Ritmo (seg/km)'] > 0]['Ritmo (seg/km)'].mean()

        # Formatear tiempo total
        horas = int(total_time_min // 60)
        minutos = int(total_time_min % 60)
        
        # Formatear ritmo promedio
        avg_pace_min = int(avg_pace_seconds // 60)
        avg_pace_sec = int(avg_pace_seconds % 60)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Distancia Total", f"{total_km:.2f} km")
        col2.metric("Tiempo Total", f"{horas}h {minutos}min")
        col3.metric("Desnivel Total", f"{total_elevation:.0f} m")
        col4.metric("Ritmo Promedio", f"{avg_pace_min}:{avg_pace_sec:02d} min/km")

        st.markdown("---")

        # --- Gráficas y Reportes ---
        st.subheader("Análisis de Rendimiento")

        col1, col2 = st.columns(2)

        with col1:
            st.write("📈 **Evolución de Distancia y Desnivel**")
            chart_data = df_runs.set_index("Fecha")[["Distancia (km)", "Desnivel (m)"]].sort_index()
            st.line_chart(chart_data)

        with col2:
            st.write("💨 **Evolución del Ritmo** (segundos por km)")
            # Invertimos el eje y para que un ritmo "menor" (más rápido) aparezca más arriba
            pace_data = df_runs.set_index("Fecha")[["Ritmo (seg/km)"]].sort_index()
            st.line_chart(pace_data)
            st.caption("Nota: Un valor más bajo en el ritmo significa que fue más rápido.")
        
        st.markdown("---")
        
        # --- Reportes de Mejores Marcas ---
        st.subheader("🏆 Mejores Marcas")
        
        # Excluimos carreras muy cortas (ej. < 1km) para que los récords de ritmo sean significativos
        df_significant = df_runs[df_runs['Distancia (km)'] >= 1]
        
        if not df_significant.empty:
            longest_run = df_significant.loc[df_significant['Distancia (km)'].idxmax()]
            fastest_run = df_significant.loc[df_significant[df_significant['Ritmo (seg/km)'] > 0]['Ritmo (seg/km)'].idxmin()]
            most_elevation_run = df_significant.loc[df_significant['Desnivel (m)'].idxmax()]

            col1, col2, col3 = st.columns(3)
            with col1:
                st.info(f"**Carrera más larga**")
                st.write(f"**{longest_run['Nombre']}**")
                st.write(f"📅 {longest_run['Fecha'].strftime('%d-%m-%Y')}")
                st.write(f" distanza: **{longest_run['Distancia (km)']} km**")
            
            with col2:
                st.info(f"**Carrera más rápida (mejor ritmo)**")
                st.write(f"**{fastest_run['Nombre']}**")
                st.write(f"📅 {fastest_run['Fecha'].strftime('%d-%m-%Y')}")
                st.write(f"ritmo: **{fastest_run['Ritmo (min/km)']} min/km**")
            
            with col3:
                st.info(f"**Carrera con más desnivel**")
                st.write(f"**{most_elevation_run['Nombre']}**")
                st.write(f"📅 {most_elevation_run['Fecha'].strftime('%d-%m-%Y')}")
                st.write(f"desnivel: **{most_elevation_run['Desnivel (m)']} m**")
        else:
            st.write("No hay carreras de más de 1km para analizar mejores marcas.")


        # --- Tabla de Datos Completa ---
        st.subheader("Detalle de todas las carreras")
        st.dataframe(df_runs[['Fecha', 'Nombre', 'Distancia (km)', 'Tiempo (min)', 'Ritmo (min/km)', 'Desnivel (m)']], use_container_width=True)

