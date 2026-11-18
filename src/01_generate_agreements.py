# Databricks notebook source
# DBTITLE 1,About this notebook
# MAGIC %md
# MAGIC # 01 — Generate the synthetic agreements
# MAGIC > **Runs only when `USE_SYNTHETIC_DATA = True` in `00_config`.** In real mode this notebook exits immediately and 04 reads your own PDFs from `AGREEMENTS_PATH`.
# MAGIC
# MAGIC Renders 11 synthetic data-sharing agreements from `_agreements_spec`, following the ACF TECH MOU template, into
# MAGIC `/Volumes/.../sample_mous/synthetic_data`:
# MAGIC - **7 typed** agreements: text PDFs with electronic (/s/) signatures.
# MAGIC - **4 handwritten** agreements: printed forms filled in by hand and scanned (image-only PDFs, skew and scanner noise), so `ai_parse_document` must OCR them.
# MAGIC
# MAGIC Each agreement adds **Appendix C. Shared Data Elements**: the tables and columns the partner may receive. The generator script, spec and fonts ship in
# MAGIC the project's `generator/` folder (`GENERATOR_PATH` in `00_config`). `reportlab` is installed below; pillow and numpy come with the runtime.

# COMMAND ----------

# DBTITLE 1,Install PDF generator dependency
# MAGIC %pip install -q "reportlab>=4"

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

# DBTITLE 1,Generate the agreement PDFs
if not USE_SYNTHETIC_DATA:   # real mode: your own agreement PDFs are read from AGREEMENTS_PATH by 04
    dbutils.notebook.exit(f"Skipped: use_synthetic_data = false. Agreements are read from {AGREEMENTS_PATH}.")
import subprocess, sys, shutil, os, json
tmp = "/tmp/acf_agreements"
shutil.rmtree(tmp, ignore_errors=True)
r = subprocess.run([sys.executable, f"{GENERATOR_PATH}/generate_agreements.py", tmp, f"{GENERATOR_PATH}/fonts"],
                   cwd=GENERATOR_PATH, capture_output=True, text=True)
print(r.stdout[-3000:], r.stderr[-3000:])
assert r.returncode == 0, "generator failed"
os.makedirs(AGREEMENTS_PATH, exist_ok=True)
for f in os.listdir(tmp):
    if f.endswith(".pdf"): shutil.copy(f"{tmp}/{f}", f"{AGREEMENTS_PATH}/{f}")
pdfs = sorted(f for f in os.listdir(AGREEMENTS_PATH) if f.endswith(".pdf"))
print(len(pdfs), "agreements in", AGREEMENTS_PATH)
assert len(pdfs) == 11