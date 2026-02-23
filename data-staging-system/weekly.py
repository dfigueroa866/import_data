import pandas as pd
import numpy as np

# =========================
# Config
# =========================
INPUT_PATH = r"C:\Users\Advantus\OneDrive - AdvantusAI\1 M8\Projects\FarmaTodo\stage_ventas_Sanfrancisco16012026.csv"
OUTPUT_PATH = r"C:\Users\Advantus\OneDrive - AdvantusAI\1 M8\Projects\FarmaTodo\ventas_semanal_agg.csv"

TOTAL_PRICE_TOL = 1e-6  # tolerancia por floats

# =========================
# Load
# =========================
if INPUT_PATH.lower().endswith(".csv"):
    df = pd.read_csv(INPUT_PATH, encoding="latin-1")
else:
    df = pd.read_excel(INPUT_PATH)

# =========================
# Fix CSV issues (trailing comma -> Unnamed columns)
# =========================
df = df.loc[:, ~df.columns.str.contains(r"^Unnamed", na=False)]
df.columns = df.columns.str.strip()

# =========================
# Add missing column
# =========================
df["dmd_group"] = "SELL_OUT"

# =========================
# Clean + types
# =========================
print("\n=== VALIDACIÓN 4: Filas antes de limpiar ===")
print("Filas cargadas:", len(df))

# Fecha
df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")

# Numéricos
for c in ["qty", "unit_price", "total_price"]:
    df[c] = (
        df[c].astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    df[c] = pd.to_numeric(df[c], errors="coerce")

# Drop invalid rows (ahora incluye hist_stream)
required = ["start_date", "loc", "dmd_unit", "hist_stream", "qty", "dmd_group"]
df_before_dropna = len(df)
df = df.dropna(subset=required)
df_after_dropna = len(df)

print("\n=== VALIDACIÓN 4: Filas después de dropna ===")
print("Filas antes dropna:", df_before_dropna)
print("Filas después dropna:", df_after_dropna)
print("Filas eliminadas:", df_before_dropna - df_after_dropna)

# =========================
# Week Monday (inicio de semana = lunes)
# =========================
df["week_monday"] = df["start_date"] - pd.to_timedelta(df["start_date"].dt.weekday, unit="D")
df["week_monday"] = df["week_monday"].dt.normalize()

# =========================
# Aggregate (SEMANAL)
# - Se agrega hist_stream como dimensión (queda en el output)
# Headers finales requeridos:
# loc, dmd_unit, dmd_group, hist_stream, start_date, qty, unit_price, total_price
# =========================
agg = (
    df.groupby(["loc", "dmd_unit", "dmd_group", "hist_stream", "week_monday"], as_index=False)
      .agg(
          qty=("qty", "sum"),
          unit_price=("unit_price", "mean"),      # promedio simple dentro de la semana
          total_price=("total_price", "sum"),
      )
      .rename(columns={"week_monday": "start_date"})
      .sort_values(["loc", "dmd_unit", "dmd_group", "hist_stream", "start_date"])
)

# =========================
# VALIDACIONES 1,2,3 + 6
# =========================

# 1) Totales globales qty y total_price
orig_qty = df["qty"].sum()
agg_qty = agg["qty"].sum()

orig_total = df["total_price"].sum()
agg_total = agg["total_price"].sum()

print("\n=== VALIDACIÓN 1: Totales globales ===")
print(f"qty original:   {orig_qty}")
print(f"qty agregado:   {agg_qty}")
print(f"diff qty:       {orig_qty - agg_qty}")

print(f"total original: {orig_total}")
print(f"total agregado: {agg_total}")
print(f"diff total:     {orig_total - agg_total}")

# 2) Validación por loc
chk_loc = (
    df.groupby("loc", as_index=False)
      .agg(qty_orig=("qty", "sum"), total_orig=("total_price", "sum"))
      .merge(
          agg.groupby("loc", as_index=False)
             .agg(qty_agg=("qty", "sum"), total_agg=("total_price", "sum")),
          on="loc",
          how="left"
      )
)

chk_loc["diff_qty"] = chk_loc["qty_orig"] - chk_loc["qty_agg"]
chk_loc["diff_total"] = chk_loc["total_orig"] - chk_loc["total_agg"]

bad_loc = chk_loc[(chk_loc["diff_qty"] != 0) | (chk_loc["diff_total"].abs() > TOTAL_PRICE_TOL)]

print("\n=== VALIDACIÓN 2: Por loc (diferencias) ===")
if bad_loc.empty:
    print("OK: No hay diferencias por loc.")
else:
    print("ATENCIÓN: Hay diferencias por loc (mostrando filas con problema):")
    print(bad_loc.sort_values(["diff_qty", "diff_total"], ascending=[False, False]).head(50))

# 3) Validación por dmd_unit
chk_sku = (
    df.groupby("dmd_unit", as_index=False)
      .agg(qty_orig=("qty", "sum"), total_orig=("total_price", "sum"))
      .merge(
          agg.groupby("dmd_unit", as_index=False)
             .agg(qty_agg=("qty", "sum"), total_agg=("total_price", "sum")),
          on="dmd_unit",
          how="left"
      )
)

chk_sku["diff_qty"] = chk_sku["qty_orig"] - chk_sku["qty_agg"]
chk_sku["diff_total"] = chk_sku["total_orig"] - chk_sku["total_agg"]

bad_sku = chk_sku[(chk_sku["diff_qty"] != 0) | (chk_sku["diff_total"].abs() > TOTAL_PRICE_TOL)]

print("\n=== VALIDACIÓN 3: Por dmd_unit (diferencias) ===")
if bad_sku.empty:
    print("OK: No hay diferencias por dmd_unit.")
else:
    print("ATENCIÓN: Hay diferencias por dmd_unit (mostrando filas con problema):")
    print(bad_sku.sort_values(["diff_qty", "diff_total"], ascending=[False, False]).head(50))

# INFO extra: compresión por agregación
print("\n=== INFO: Compresión por agregación semanal ===")
print(f"Filas originales (post-limpieza): {len(df)}")
print(f"Filas agregadas:                  {len(agg)}")
print(f"Filas consolidadas:               {len(df) - len(agg)}")
print(f"Factor compresión:                {len(df)/len(agg):.2f}x")

# 6) Asserts (reglas de oro)
print("\n=== VALIDACIÓN 6: Asserts (reglas de oro) ===")
assert orig_qty == agg_qty, f"ERROR: qty no cuadra. diff={orig_qty - agg_qty}"

assert abs(orig_total - agg_total) <= TOTAL_PRICE_TOL, (
    f"ERROR: total_price no cuadra dentro de tolerancia. diff={orig_total - agg_total}"
)

assert bad_loc.empty, "ERROR: Hay diferencias por loc. Revisa bad_loc impreso arriba."
assert bad_sku.empty, "ERROR: Hay diferencias por dmd_unit. Revisa bad_sku impreso arriba."

print("OK: Validaciones pasaron. La agregación conserva qty y total_price.")

# =========================
# Save
# =========================
agg.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
print(f"\nOK: {len(agg):,} filas agregadas -> {OUTPUT_PATH}")
