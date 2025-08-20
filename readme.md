# 📊 SENSESBIT SaaS Dashboard

Dashboard interactivo para analizar métricas SaaS (clientes activos, MRR, ARR, churn, expansión, cohortes).

## 🚀 Cómo usarlo

1. Clona el repo en tu máquina o crea uno en GitHub.
2. Sube el repo a [Streamlit Cloud](https://share.streamlit.io/).
3. En "Advanced Settings" selecciona **Python 3.12**.
4. Sube tu Excel (`SaaS_Final_Template_COMPLETO.xlsx` o `Template.xlsx`) desde el sidebar.

## 📂 Archivos
- `app.py` → Código principal del dashboard.
- `requirements.txt` → Dependencias de Python.
- `README.md` → Documentación básica.
- `.streamlit/config.toml` → Configuración visual.

## 📈 Funcionalidades
- KPIs principales: clientes activos, MRR, ARR.
- Filtros dinámicos: año, mes, plan, tipo de evento (churn, expansión, downgrade).
- Gráficos de evolución.
- Cohortes de retención.
