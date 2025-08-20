import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(page_title="SENSESBIT SaaS Dashboard", layout="wide")

# -------------------------------
# Funciones auxiliares
# -------------------------------
@st.cache_data
def load_excel(file):
    return pd.read_excel(file, sheet_name=None, engine="openpyxl")

def ensure_cols(df, cols):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"Faltan columnas obligatorias en hoja Data: {miss}")

def cohort_analysis(df):
    df["YearMonth"] = df["Date"].dt.to_period("M")
    cohort = df.groupby(["YearMonth", "Plan"]).agg(
        clientes_activos=("Active Customers", "sum"),
        MRR=("MRR", "sum"),
    ).reset_index()
    return cohort

# -------------------------------
# Sidebar
# -------------------------------
st.sidebar.header("📊 Filtros")

uploaded = st.sidebar.file_uploader("Sube tu Excel (Template o COMPLETO)", type=["xlsx"])
if not uploaded:
    st.stop()

book = load_excel(uploaded)
df_data = book.get("Data")
df_prices = book.get("Prices")

# Validación
ensure_cols(df_data, ["Date", "Plan", "New Customers", "Lost Customers", "Active Customers"])

# Preparar dataset
df_data["Date"] = pd.to_datetime(df_data["Date"])
df_data = df_data.sort_values("Date")

# Filtros dinámicos
years = st.sidebar.multiselect("Año", sorted(df_data["Date"].dt.year.unique()))
months = st.sidebar.multiselect("Mes", sorted(df_data["Date"].dt.month.unique()))
plans = st.sidebar.multiselect("Plan", df_data["Plan"].unique())
eventos = st.sidebar.multiselect("Evento", ["Churned", "Expansion", "Downgrade"])

df_filtered = df_data.copy()
if years: df_filtered = df_filtered[df_filtered["Date"].dt.year.isin(years)]
if months: df_filtered = df_filtered[df_filtered["Date"].dt.month.isin(months)]
if plans: df_filtered = df_filtered[df_filtered["Plan"].isin(plans)]
if eventos:
    df_filtered = df_filtered[df_filtered["Event"].isin(eventos)]

# -------------------------------
# KPIs principales
# -------------------------------
st.title("📈 Dashboard SaaS - SENSESBIT")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Clientes activos", int(df_filtered["Active Customers"].iloc[-1]))
with col2:
    st.metric("MRR Total", f"€{df_filtered['MRR'].iloc[-1]:,.0f}")
with col3:
    st.metric("ARR Total", f"€{df_filtered['MRR'].iloc[-1]*12:,.0f}")

# -------------------------------
# Gráficos principales
# -------------------------------
st.subheader("Evolución del MRR")
chart_mrr = alt.Chart(df_filtered).mark_line(point=True).encode(
    x="Date:T", y="MRR:Q", color="Plan:N", tooltip=["Date", "MRR", "Plan"]
).interactive()
st.altair_chart(chart_mrr, use_container_width=True)

st.subheader("Clientes Activos")
chart_clients = alt.Chart(df_filtered).mark_line(point=True).encode(
    x="Date:T", y="Active Customers:Q", color="Plan:N"
).interactive()
st.altair_chart(chart_clients, use_container_width=True)

# -------------------------------
# Cohortes
# -------------------------------
st.subheader("Cohortes de Retención")
cohort = cohort_analysis(df_filtered)
chart_cohort = alt.Chart(cohort).mark_line().encode(
    x="YearMonth:T", y="clientes_activos:Q", color="Plan:N"
)
st.altair_chart(chart_cohort, use_container_width=True)
