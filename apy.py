
import streamlit as st
import pandas as pd
import altair as alt
import numpy as np

st.set_page_config(page_title="SENSESBIT SaaS Dashboard", layout="wide")

# ----------------------------- Helpers -----------------------------
@st.cache_data
def read_book(file):
    # Lee Excel con todas las hojas
    return pd.read_excel(file, sheet_name=None, engine="openpyxl")

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = (df.columns
                    .str.strip()
                    .str.replace(r"\s*\(optional\)", "", regex=True)
                    .str.replace(r"\s*\(€\)", " €", regex=True)
                    .str.replace(r"\s*\(inferred\s*€\)", " €", regex=True))
    # Renombres habituales
    ren = {
        "Real MRR  €": "Real MRR €",
        "MRR Calculated  €": "MRR Calculated €",
        "Price MRR  €": "Price MRR €",
        "CAC optional  €": "CAC (optional €)",
    }
    for k,v in ren.items():
        if k in df.columns:
            df.rename(columns={k:v}, inplace=True)
    return df

def ensure_active_customers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Active Customers" not in df.columns:
        # Cálculo robusto por plan
        for c in ["New Customers", "Lost Customers"]:
            if c not in df.columns:
                df[c] = 0
        df = df.sort_values(["Plan","Date"])
        df["Active Customers"] = (
            df.groupby("Plan")["New Customers"].cumsum()
            - df.groupby("Plan")["Lost Customers"].cumsum()
        )
        df["Active Customers"] = df["Active Customers"].clip(lower=0)
    return df

def build_prices_maps(df_prices: pd.DataFrame):
    price_map = {}
    gm_map = {}
    if isinstance(df_prices, pd.DataFrame) and not df_prices.empty:
        if "Plan" in df_prices.columns:
            dfp = df_prices.copy()
            if "Price MRR €" in dfp.columns:
                price_map = dfp.set_index("Plan")["Price MRR €"].to_dict()
            # Gross Margin %
            gm_col = None
            if "Gross Margin %" in dfp.columns:
                gm_col = "Gross Margin %"
            elif "Gross Margin" in dfp.columns:
                gm_col = "Gross Margin"
            if gm_col:
                # Acepta 0-1 o 0-100
                gm_series = dfp.set_index("Plan")[gm_col].astype(float)
                gm_series = gm_series.apply(lambda x: x/100.0 if x>1.0 else x)
                gm_map = gm_series.to_dict()
    return price_map, gm_map

def ensure_mrr_arr(df: pd.DataFrame, price_map: dict) -> pd.DataFrame:
    df = df.copy()
    # Real MRR
    if "Real MRR €" not in df.columns:
        if "MRR Calculated €" in df.columns:
            df["Real MRR €"] = df["MRR Calculated €"]
        elif price_map and "Active Customers" in df.columns:
            df["Real MRR €"] = df["Plan"].map(price_map).fillna(0) * df["Active Customers"].fillna(0)
        else:
            df["Real MRR €"] = 0.0
    # ARR
    if "ARR" not in df.columns:
        df["ARR"] = df["Real MRR €"] * 12.0
    return df

def compute_arpa(df: pd.DataFrame) -> pd.Series:
    # ARPA mensual: MRR/Active
    ac = df["Active Customers"].replace({0: np.nan})
    arpa = df["Real MRR €"] / ac
    return arpa.fillna(0.0)

def compute_logo_churn(df: pd.DataFrame) -> pd.Series:
    # ActiveStart ≈ ActiveEnd - New + Lost (por plan, mes a mes)
    # Trabajamos sobre copia ordenada por plan/fecha
    df = df.sort_values(["Plan","Date"]).copy()
    active_end = df["Active Customers"].fillna(0)
    new = df.get("New Customers", pd.Series(0, index=df.index)).fillna(0)
    lost = df.get("Lost Customers", pd.Series(0, index=df.index)).fillna(0)
    active_start = (active_end - new + lost).clip(lower=0)
    denom = active_start.replace({0: np.nan})
    churn = lost / denom
    return churn.fillna(0.0).clip(lower=0, upper=1)

def compute_gross_margin_per_row(df: pd.DataFrame, gm_map: dict, default_gm=0.80) -> pd.Series:
    gm = df["Plan"].map(gm_map) if gm_map else pd.Series(default_gm, index=df.index)
    gm = gm.fillna(default_gm).astype(float)
    # Aseguramos 0-1
    gm = gm.apply(lambda x: x/100.0 if x>1.0 else x)
    return gm.clip(lower=0, upper=1)

def compute_cac_series(df: pd.DataFrame) -> pd.Series:
    # Prioriza CAC (optional €); si no, calcula: Spend/New
    if "CAC (optional €)" in df.columns:
        base = df["CAC (optional €)"].astype(float)
    else:
        spend = df.get("Sales & Marketing Spend €", pd.Series(np.nan, index=df.index)).astype(float)
        new = df.get("New Customers", pd.Series(0, index=df.index)).astype(float)
        base = spend / new.replace({0: np.nan})
    return base.replace([np.inf, -np.inf], np.nan)

def safe_last(df: pd.DataFrame, col: str, default=0):
    try:
        val = df[col].iloc[-1]
        if pd.isna(val):
            return default
        return val
    except Exception:
        return default

# ----------------------------- UI / File upload -----------------------------
st.title("📊 SENSESBIT SaaS Dashboard")
uploaded = st.file_uploader("Sube tu Excel (.xlsx) con hojas **Data** y **Prices**", type=["xlsx"])
if not uploaded:
    st.info("Sube tu archivo para comenzar. Soporta columnas opcionales y calcula ARPA, LTV y CAC si faltan.")
    st.stop()

book = read_book(uploaded)
df_data = normalize_cols(book.get("Data"))
df_prices = normalize_cols(book.get("Prices"))

# Validación mínima
needed = ["Date","Plan","New Customers","Lost Customers"]
miss = [c for c in needed if c not in df_data.columns]
if miss:
    st.error(f"Faltan columnas en hoja Data: {miss}")
    st.stop()

# Tipos y orden
df_data["Date"] = pd.to_datetime(df_data["Date"], errors="coerce")
df_data = df_data.dropna(subset=["Date"]).sort_values(["Plan","Date"]).reset_index(drop=True)

# Activos, MRR, ARR
df_data = ensure_active_customers(df_data)
price_map, gm_map = build_prices_maps(df_prices)
df_data = ensure_mrr_arr(df_data, price_map)

# Dimensiones auxiliares
df_data["Year"] = df_data["Date"].dt.year
df_data["Month"] = df_data["Date"].dt.month
df_data["MonthName"] = df_data["Date"].dt.strftime("%B")

# ----------------------------- LTV & CAC -----------------------------
# ARPA
df_data["ARPA €"] = compute_arpa(df_data)
# Churn mensual
df_data["Logo Churn % (monthly)"] = compute_logo_churn(df_data)
# Gross Margin por fila
df_data["Gross Margin % (used)"] = compute_gross_margin_per_row(df_data, gm_map, default_gm=0.80)
# LTV mensual
with np.errstate(divide='ignore', invalid='ignore'):
    ltv = (df_data["ARPA €"] * df_data["Gross Margin % (used)"]) / df_data["Logo Churn % (monthly)"].replace({0: np.nan})
df_data["LTV € (monthly)"] = ltv.replace([np.inf, -np.inf], np.nan)

# CAC
# Normaliza nombre de spend si viene con €
if "Sales & Marketing Spend (€)" in df_data.columns and "Sales & Marketing Spend €" not in df_data.columns:
    df_data.rename(columns={"Sales & Marketing Spend (€)":"Sales & Marketing Spend €"}, inplace=True)
df_data["CAC €"] = compute_cac_series(df_data)

# LTV/CAC
df_data["LTV/CAC"] = np.where((df_data["LTV € (monthly)"].notna()) & (df_data["CAC €"].notna()) & (df_data["CAC €"]>0),
                              df_data["LTV € (monthly)"] / df_data["CAC €"], np.nan)

# ----------------------------- Sidebar filtros -----------------------------
st.sidebar.header("Filtros")
years = sorted(df_data["Year"].unique().tolist())
months = list(pd.Series(df_data["MonthName"].unique()).sort_values())
plans = sorted(df_data["Plan"].dropna().unique().tolist())

sel_years = st.sidebar.multiselect("Años", years, default=years)
sel_months = st.sidebar.multiselect("Meses", months, default=months)
sel_plan = st.sidebar.selectbox("Plan", ["(Todos)"] + plans, index=0)
components_all = ["New MRR (€)", "Expansion MRR €", "Churned MRR (€)", "Downgraded MRR €"]
sel_components = st.sidebar.multiselect("Componentes Net New", options=components_all, default=components_all)
apply_to_kpis = st.sidebar.checkbox("Aplicar filtros a KPIs superiores", value=True)

def apply_filters(df):
    mask = df["Year"].isin(sel_years) & df["MonthName"].isin(sel_months)
    if sel_plan != "(Todos)":
        mask &= df["Plan"].eq(sel_plan)
    return df.loc[mask].copy()

df_f = apply_filters(df_data)

# ----------------------------- KPIs -----------------------------
kpi_src = df_f if apply_to_kpis else df_data
if kpi_src.empty:
    st.warning("No hay datos para los filtros seleccionados.")
else:
    last_date = kpi_src["Date"].max()
    last = kpi_src[kpi_src["Date"] == last_date]
    active_total = int(last["Active Customers"].sum()) if "Active Customers" in last else 0
    mrr_total = float(last["Real MRR €"].sum()) if "Real MRR €" in last else 0.0
    arr_total = mrr_total * 12.0
    # LTV/CAC (mezcla: media ponderada por MRR)
    ltv_mean = np.nan
    cac_mean = np.nan
    if "LTV € (monthly)" in last:
        ltv_mean = np.average(last["LTV € (monthly)"].dropna(), weights=last["Real MRR €"].reindex(last.index, fill_value=0)) if last["LTV € (monthly)"].notna().any() else np.nan
    if "CAC €" in last:
        # CAC medio ponderado por nuevos clientes
        weights = last.get("New Customers", pd.Series(0, index=last.index)).astype(float)
        cac_mean = np.average(last["CAC €"].dropna(), weights=weights.reindex(last.index, fill_value=0)) if last["CAC €"].notna().any() and weights.sum()>0 else np.nan
    ltv_cac_ratio = ltv_mean / cac_mean if (pd.notna(ltv_mean) and pd.notna(cac_mean) and cac_mean>0) else np.nan

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Clientes activos (últ. mes)", active_total)
    c2.metric("MRR total (últ. mes)", f"{mrr_total:,.0f} €")
    c3.metric("ARR total (últ. mes)", f"{arr_total:,.0f} €")
    c4.metric("LTV mensual (medio)", "-" if pd.isna(ltv_mean) else f"{ltv_mean:,.0f} €")
    c5.metric("LTV/CAC", "-" if pd.isna(ltv_cac_ratio) else f"{ltv_cac_ratio:,.2f}")

# ----------------------------- Gráficos Net New -----------------------------
st.subheader("📈 Net New MRR (seleccionable)")
if df_f.empty:
    st.info("No hay datos tras aplicar filtros.")
else:
    melt_cols = [c for c in sel_components if c in df_f.columns]
    if melt_cols:
        melted = df_f.melt(id_vars=["Date"], value_vars=melt_cols, var_name="Tipo", value_name="Valor")
        ch = alt.Chart(melted).mark_area(opacity=0.6).encode(
            x="Date:T", y="Valor:Q", color="Tipo:N", tooltip=["Date:T","Tipo","Valor"]
        ).properties(height=260)
        st.altair_chart(ch, use_container_width=True)
    else:
        st.info("No hay columnas de componentes presentes para graficar.")

# ----------------------------- MRR por Plan -----------------------------
st.subheader("📉 Evolución de MRR Real por Plan")
if "Real MRR €" in df_f.columns:
    mrr_ts = df_f.groupby(["Date","Plan"], as_index=False)["Real MRR €"].sum()
    ch2 = alt.Chart(mrr_ts).mark_line(point=True).encode(
        x="Date:T", y="Real MRR €:Q", color="Plan:N", tooltip=["Date:T","Plan","Real MRR €:Q"]
    ).properties(height=260)
    st.altair_chart(ch2, use_container_width=True)
else:
    st.info("No se encontró 'Real MRR €'.")

# ----------------------------- LTV y CAC Charts -----------------------------
st.subheader("💸 LTV (mensual) y CAC por Plan")
metrics_long = []
if "LTV € (monthly)" in df_f.columns:
    metrics_long.append("LTV € (monthly)")
if "CAC €" in df_f.columns:
    metrics_long.append("CAC €")

if metrics_long:
    toplot = df_f[["Date","Plan"] + metrics_long].melt(id_vars=["Date","Plan"], var_name="Métrica", value_name="€")
    ch3 = alt.Chart(toplot.dropna()).mark_line(point=True).encode(
        x="Date:T", y="€:Q", color="Plan:N", row="Métrica:N",
        tooltip=["Date:T","Plan","Métrica","€:Q"]
    ).properties(height=200)
    st.altair_chart(ch3, use_container_width=True)
else:
    st.info("No hay suficientes columnas para graficar LTV/CAC.")

# ----------------------------- Cohortes -----------------------------
st.subheader("👥 Cohortes por año de alta")
id_col = None
for candidate in ["Customer ID","CustomerID","Client ID","ID"]:
    if candidate in df_data.columns:
        id_col = candidate
        break

if id_col:
    first_seen = df_data.groupby(id_col)["Date"].min().dt.year.rename("Cohort")
    df_id = df_data[[id_col,"Date","Plan","Active Customers"]].copy()
    df_id = df_id.merge(first_seen, left_on=id_col, right_index=True, how="left")
    df_id["Year"] = df_id["Date"].dt.year
    df_id["ActiveFlag"] = (df_id["Active Customers"] > 0).astype(int)
    cohort_pivot = df_id.pivot_table(index="Cohort", columns="Year", values="ActiveFlag", aggfunc="sum").fillna(0).astype(int)
    st.dataframe(cohort_pivot, use_container_width=True)
else:
    coh = (df_data.groupby("Year").agg(
        New_Customers=("New Customers","sum"),
        Active_EndOfYear=("Active Customers","last"),
        MRR_EndOfYear=("Real MRR €","last"),
        LTV_Monthly_Avg=("LTV € (monthly)","mean"),
        CAC_Avg=("CAC €","mean")
    ).reset_index())
    st.dataframe(coh, use_container_width=True)

st.caption("Notas: LTV es mensual (ARPA * gross margin / churn). Añade 'Gross Margin %' en Prices y 'Sales & Marketing Spend (€)' o 'CAC (optional €)' en Data para métricas más precisas.")
