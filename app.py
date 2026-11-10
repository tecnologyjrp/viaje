import streamlit as st
import sqlite3
import urllib.request
import json
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuración de página responsive
st.set_page_config(
    page_title="Planificador de Viaje",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- BASE DE DATOS LOCAL ---
def get_db():
    conn = sqlite3.connect("itinerario_viaje.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS planes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ruta TEXT,
            fechas TEXT,
            viajeros TEXT,
            fecha_creacion TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            categoria TEXT,
            concepto TEXT,
            costo_usd REAL,
            costo_cop REAL,
            moneda_origen TEXT,
            fecha_registro TEXT,
            FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute("SELECT id FROM planes")
    if not cursor.fetchall():
        cursor.execute('''
            INSERT INTO planes (nombre, ruta, fechas, viajeros, fecha_creacion)
            VALUES (?, ?, ?, ?, ?)
        ''', ("Plan Principal", "Cali -> Orlando -> Atlanta -> Cali", "", "4 Adultos, 1 Niña (2 años)", datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
    conn.commit()
    return conn

conn = get_db()
cursor = conn.cursor()

# --- CONSULTA TRM AUTOMÁTICA ---
@st.cache_data(ttl=1800)
def fetch_trm():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if "rates" in data and "COP" in data["rates"]:
                return float(data["rates"]["COP"])
    except Exception:
        pass
    return 4050.0

trm = fetch_trm()

# --- FUNCIÓN GENERADOR DE PDF EN MEMORIA ---
def generate_pdf_bytes(plan_id, plan_name, ruta, fechas, viajeros, trm_val):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=10
    )
    elements.append(Paragraph(f"Itinerario de Viaje - {plan_name}", title_style))

    info_data = [
        ["Ruta:", ruta or "Cali -> Orlando -> Atlanta -> Cali", "Fecha Cotización:", datetime.now().strftime("%Y-%m-%d")],
        ["Fechas:", fechas or "Por definir", "TRM Aplicada:", f"${trm_val:,.2f} COP"],
        ["Viajeros:", viajeros or "Por definir", "ID Cotización:", f"#{plan_id}"]
    ]
    t_info = Table(info_data, colWidths=[65, 230, 110, 135])
    t_info.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#334155')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_info)
    elements.append(Spacer(1, 15))

    table_data = [["Categoría", "Detalle / Concepto", "Moneda", "Costo (USD)", "Costo (COP)"]]
    c = conn.cursor()
    c.execute("SELECT categoria, concepto, moneda_origen, costo_usd, costo_cop FROM gastos WHERE plan_id = ?", (plan_id,))
    rows = c.fetchall()

    total_usd = 0.0
    total_cop = 0.0
    for cat, conc, origen, usd, cop in rows:
        total_usd += usd
        total_cop += cop
        table_data.append([cat, conc, origen or "USD", f"${usd:,.2f}", f"${cop:,.0f}"])

    table_data.append(["TOTALES", "", "", f"${total_usd:,.2f}", f"${total_cop:,.0f}"])

    t_gastos = Table(table_data, colWidths=[90, 210, 50, 90, 100])
    t_gastos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_gastos)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- GESTIÓN DE PLANES ---
cursor.execute("SELECT id, nombre FROM planes ORDER BY id ASC")
planes_db = cursor.fetchall()
planes_dict = {f"[{p[0]}] {p[1]}": p[0] for p in planes_db}

# --- BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.header("📋 Opciones de Viaje")
    plan_seleccionado = st.selectbox("Seleccionar Cotización Activa:", list(planes_dict.keys()))
    plan_id = planes_dict[plan_seleccionado]

    with st.expander("➕ Crear Nueva Cotización"):
        nuevo_nombre = st.text_input("Nombre de la opción:", placeholder="Ej: Opción Hotel + Auto")
        if st.button("Crear Plan", use_container_width=True):
            if nuevo_nombre.strip():
                cursor.execute('''
                    INSERT INTO planes (nombre, ruta, fechas, viajeros, fecha_creacion)
                    VALUES (?, ?, ?, ?, ?)
                ''', (nuevo_nombre.strip(), "Cali -> Orlando -> Atlanta -> Cali", "", "4 Adultos, 1 Niña (2 años)", datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.rerun()

    with st.expander("🗑️ Eliminar Plan Activo"):
        if len(planes_dict) > 1:
            if st.button("Eliminar este plan", type="primary", use_container_width=True):
                cursor.execute("DELETE FROM gastos WHERE plan_id = ?", (plan_id,))
                cursor.execute("DELETE FROM planes WHERE id = ?", (plan_id,))
                conn.commit()
                st.rerun()
        else:
            st.caption("No puedes eliminar el único plan existente.")

    st.markdown("---")
    st.subheader("🔗 Accesos Rápidos")
    st.markdown("""
    * [✈️ Copa Airlines](https://www.copaair.com/)
    * [✈️ Delta Air Lines](https://es.delta.com/)
    * [🏠 Airbnb](https://www.airbnb.com.co/)
    * [🏰 Disney World](https://disneyworld.disney.go.com/es-us/)
    * [🎢 Universal Orlando](https://www.universalorlando.com/web/es/us)
    * [🚗 Rentalcars](https://www.rentalcars.com/)
    * [🛍️ Vineland Outlets](https://www.premiumoutlets.com/outlet/orlando-vineland)
    """)

# --- CONTENIDO PRINCIPAL ---
st.title("🌴 Presupuesto Cali - Orlando - Atlanta")

# Métrica de TRM
col_trm1, col_trm2 = st.columns([3, 1])
with col_trm1:
    st.info(f"**Dólar Oficial Hoy (TRM):** ${trm:,.2f} COP")
with col_trm2:
    if st.button("🔄 Recalcular con TRM", use_container_width=True):
        st.cache_data.clear()
        trm_actual = fetch_trm()
        cursor.execute("SELECT id, costo_usd, costo_cop, moneda_origen FROM gastos")
        for gid, g_usd, g_cop, origen in cursor.fetchall():
            if origen == "COP":
                cursor.execute("UPDATE gastos SET costo_usd = ? WHERE id = ?", (g_cop / trm_actual, gid))
            else:
                cursor.execute("UPDATE gastos SET costo_cop = ? WHERE id = ?", (g_usd * trm_actual, gid))
        conn.commit()
        st.rerun()

# Cargar parámetros del plan
cursor.execute("SELECT nombre, ruta, fechas, viajeros FROM planes WHERE id = ?", (plan_id,))
p_nombre, p_ruta, p_fechas, p_viajeros = cursor.fetchone()

with st.expander("⚙️ Parámetros del Viaje (Ruta, Fechas y Pasajeros)", expanded=True):
    col_r1, col_r2, col_r3 = st.columns([2, 1, 1.5])
    with col_r1:
        edit_ruta = st.text_input("Ruta:", value=p_ruta or "Cali -> Orlando -> Atlanta -> Cali")
    with col_r2:
        edit_fechas = st.text_input("Fechas:", value=p_fechas or "")
    with col_r3:
        edit_viajeros = st.text_input("Viajeros:", value=p_viajeros or "4 Adultos, 1 Niña (2 años)")

    if st.button("💾 Guardar Parámetros", use_container_width=True):
        cursor.execute("UPDATE planes SET ruta = ?, fechas = ?, viajeros = ? WHERE id = ?", 
                       (edit_ruta, edit_fechas, edit_viajeros, plan_id))
        conn.commit()
        st.success("Información guardada.")
        st.rerun()

# Formulario para registrar gasto
st.markdown("### ➕ Registrar Nueva Cotización")
with st.form("form_gasto", clear_on_submit=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 2.5, 1, 1.5])
    with col_f1:
        cat_input = st.selectbox("Categoría:", ["Vuelos", "Alojamiento", "Parques", "Alquiler Auto", "Compras / Outlets", "Otros"])
    with col_f2:
        conc_input = st.text_input("Descripción / Proveedor:", placeholder="Ej: Airbnb Lake Bryan 5 noches")
    with col_f3:
        moneda_input = st.radio("Moneda:", ["USD", "COP"], horizontal=True)
    with col_f4:
        monto_input = st.number_input("Monto:", min_value=0.0, step=10.0, format="%.2f")

    btn_submit = st.form_submit_button("Añadir a la Lista", use_container_width=True)
    if btn_submit:
        if conc_input.strip() and monto_input > 0:
            if moneda_input == "USD":
                c_usd = monto_input
                c_cop = monto_input * trm
            else:
                c_cop = monto_input
                c_usd = monto_input / trm

            cursor.execute('''
                INSERT INTO gastos (plan_id, categoria, concepto, costo_usd, costo_cop, moneda_origen, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (plan_id, cat_input, conc_input.strip(), c_usd, c_cop, moneda_input, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            st.rerun()
        else:
            st.warning("Ingrese una descripción y un monto mayor a cero.")

# Tabla de cotizaciones guardadas
st.markdown("### 📊 Cotizaciones Registradas")
cursor.execute("SELECT id, categoria, concepto, moneda_origen, costo_usd, costo_cop FROM gastos WHERE plan_id = ?", (plan_id,))
gastos = cursor.fetchall()

total_usd = sum(g[4] for g in gastos)
total_cop = sum(g[5] for g in gastos)

# Totales en métricas
col_m1, col_m2 = st.columns(2)
col_m1.metric("Total Estimado (USD)", f"${total_usd:,.2f}")
col_m2.metric("Total Estimado (COP)", f"${total_cop:,.0f}")

if gastos:
    for g_id, g_cat, g_conc, g_origen, g_usd, g_cop in gastos:
        col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([1.5, 3, 1.5, 1.5, 0.8])
        col_c1.write(f"**{g_cat}**")
        col_c2.write(f"{g_conc} `({g_origen})`")
        col_c3.write(f"${g_usd:,.2f} USD")
        col_c4.write(f"${g_cop:,.0f} COP")
        with col_c5:
            if st.button("✕", key=f"del_{g_id}", help="Eliminar este gasto"):
                cursor.execute("DELETE FROM gastos WHERE id = ?", (g_id,))
                conn.commit()
                st.rerun()
else:
    st.info("No hay cotizaciones registradas para este plan aún.")

# Botón de Descarga PDF
st.markdown("---")
pdf_bytes = generate_pdf_bytes(plan_id, p_nombre, edit_ruta, edit_fechas, edit_viajeros, trm)
st.download_button(
    label="📄 Descargar Itinerario en PDF",
    data=pdf_bytes,
    file_name=f"Presupuesto_{p_nombre.replace(' ', '_')}.pdf",
    mime="application/pdf",
    use_container_width=True
)