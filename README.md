# ACF Delta Share Monitoring

Checks that every ACF Delta Share matches its signed data-sharing agreement (MOU, ISA or amendment).
The project reads the agreement PDFs with Databricks AI functions, compares what each agreement permits
with what each share actually exposes and who queried it, and publishes the result to:

* compliance tables in Unity Catalog,
* a Genie space for natural-language questions, and
* a Databricks App (Streamlit) for reviewing findings, drafting fixes and drafting new agreements.

Everything is packaged as a **Declarative Automation Bundle**: one `databricks bundle deploy` creates the schema,
the volume, the job and the app in your workspace.

The project runs in two modes, chosen with the bundle variable `use_synthetic_data`:

| Mode | `use_synthetic_data` | What it uses |
| --- | --- | --- |
| Demo | `"true"` (default, `dev` target) | 11 generated agreement PDFs, 9 generated ACF source tables, a generated share inventory and generated recipient activity. Nothing real is read or changed. |
| Real | `"false"` (`prod` target) | Your own agreement PDFs, your own source tables, your real Delta Shares and recipients (Delta Sharing API) and real audit events. |

---

## How it works

```
agreement PDFs ──► 04 ai_parse_document / ai_classify / ai_extract ──► sharing_agreements, agreement_data_elements
                   05 ai_prep_search + Vector Search ──────────────► agreement_chunks(_index), search_agreements()
Delta Shares ────► 03 share inventory (synthetic or Delta Sharing API) ► share_inventory, share_objects, share_grants, share_recipients
system tables ───► 06 lineage, column tags, privileges, audit ──────► mv_shared_columns, mv_source_*, mv_delta_sharing_activity
                   07 compare permitted vs shared vs used ─────────► share_compliance_findings, share_compliance_summary
                   08 Genie space  ·  app/ Streamlit app
```

The job `acf-share-monitoring` runs notebooks `01` → `08` in order on serverless compute. Its parameters come from the
bundle variables, and `src/00_config` reads them, so you never edit a notebook to configure the project.

## Repository layout

```
databricks.yml                         bundle settings: variables and the dev / prod targets  <-- the only file you edit
resources/
  acf_share_monitoring.schema.yml      project schema
  agreements.volume.yml                volume for the agreement PDFs
  acf_share_monitoring.job.yml         job: notebooks 01-08, parameters, daily schedule (paused by default)
  acf_share_monitoring.app.yml         app: settings, permissions on the warehouse / model endpoint / volume, user scopes
src/                                   notebooks (Python source format) and the PDF generator
app/                                   Streamlit app source
```

| Notebook | What it does | Main outputs (in the project schema) |
| --- | --- | --- |
| `00_config` | Reads the job parameters, validates them, creates the schema and volume if missing. Every notebook starts with `%run ./00_config`. | none |
| `_agreements_spec` | Specification of the synthetic world: source tables and identifier columns, the 11 agreements, the shares and the mismatch each share is built to show. | none |
| `01_generate_agreements` | *Demo only.* Renders 11 synthetic agreements (7 typed PDFs, 4 scanned handwritten forms) with `src/generator/`. | PDFs in the volume |
| `02_source_tables` | *Demo only.* Creates 9 synthetic ACF datasets (AFCARS, NCANDS, Head Start, TANF, ...) and tags identifier columns `acf_identifier = direct / indirect`. | `foster_care_afcars`, `tanf_recipients`, ... |
| `03_share_inventory` | Demo: builds the objects each synthetic share exposes and a synthetic share inventory. Real: reads shares, objects, grants and recipients from the Delta Sharing API. | `share_inventory`, `share_objects`, `share_grants`, `share_recipients` |
| `04_parse_classify_extract` | Parses every PDF (OCR for scans), classifies it and extracts terms, dates, signatories and permitted data elements with confidence scores. Demo mode also scores the extraction. | `parsed_agreements`, `sharing_agreements`, `agreement_data_elements`, `agreement_signatories`, `agreement_field_confidence` |
| `05_vector_index` | Chunks the agreements with `ai_prep_search`, builds a Vector Search index, creates the Genie-safe `search_agreements()` function. | `agreement_chunks`, `agreement_chunks_index`, `search_agreements` |
| `06_system_table_views` | Materialized views over system tables: columns each recipient receives, refresh cadence, who can read and who read the source tables, recipient activity. Demo mode adds synthetic recipient queries for the 60 days up to today. | `mv_shared_columns`, `mv_source_refresh_activity`, `mv_source_access_grants`, `mv_source_table_reads`, `mv_delta_sharing_activity`, `mv_agreement_permitted_columns` |
| `07_compliance_findings` | One row per issue: over-sharing, under-sharing, expired agreement, access after expiration, wrong recipient, no agreement, ... Demo mode checks every planted scenario is detected. | `share_compliance_findings`, `share_compliance_summary` |
| `08_create_genie_space` | Creates or updates the Genie space `genie_title` and outputs its ID. | Genie space |

Tables and notebooks starting with `_` are demo-only helpers; the compliance views never read them.

The app has five pages: Home, Compliance findings, Remediation (fix SQL plus an AI-drafted amendment or notice),
Draft MOU / ISA, and Ask Genie. It runs SQL, Genie, model serving and Vector Search **as the signed-in user**.
The SQL it generates for share owners (`ALTER SHARE`, `REVOKE`) is shown for review and never executed.

---

## Install checklist

### A. Prerequisites

- [ ] A recent Databricks CLI on your machine (`databricks --version`; upgrade if `bundle validate` rejects a field), authenticated to the workspace (`databricks auth login --host <workspace-url>`).
      Or deploy from the workspace UI from a Git folder that holds this repo.
- [ ] Unity Catalog workspace with **serverless** jobs and notebooks (environment version 3 or later).
- [ ] AI functions available in your region: `ai_parse_document`, `ai_classify`, `ai_extract`, `ai_prep_search` (Beta), `ai_query`.
- [ ] `USE CATALOG` and `CREATE SCHEMA` on the catalog you'll use.
- [ ] A **SQL warehouse** (note its ID), a **Vector Search endpoint**, an **embedding endpoint** (default `databricks-gte-large-en`) and a **chat model endpoint** (default `databricks-claude-sonnet-5-5`).
- [ ] `SELECT` on `system.access.audit`, `system.access.table_lineage`, `system.access.column_lineage`, `system.lakeflow.jobs`, `system.lakeflow.job_run_timeline` and `system.information_schema.*`.
- [ ] Permission to create jobs, Databricks Apps and Genie spaces.
- [ ] Real mode only: `USE SHARE` / `USE RECIPIENT` (or ownership of the shares and recipients you monitor) and `SELECT` on the source tables.

### B. Configure `databricks.yml`

- [ ] Clone this repo (locally or into a workspace Git folder).
- [ ] Under `targets:`, set `workspace.host` for each target you'll deploy to.
- [ ] For each target, set the required variables: `catalog`, `warehouse_id`, `vs_endpoint` (and `schema` if you don't want `acf_share_monitoring`).
      The `dev` values in the repo are for the original demo workspace; replace them. In `prod`, replace every `<FILL_IN: ...>`.
- [ ] Choose the mode per target with `use_synthetic_data` (`"true"` demo, `"false"` real). See [Synthetic data switch](#synthetic-data-switch).
- [ ] Optional: `embedding_model`, `llm_endpoint`, `genie_title` (must be unique in the workspace), `job_schedule_status` (`UNPAUSED` runs daily at 06:00 ET).
- [ ] Prod only: consider `run_as` with a service principal (commented in `databricks.yml`).
- [ ] Check the configuration: `databricks bundle validate --strict -t dev`.

### C. Deploy and run

- [ ] `databricks bundle deploy -t dev` creates the schema, volume, job and app.
      In `dev` (development mode) the job is prefixed `[dev <you>]`, the schema `dev_<you>_`, and the app is `acfsm-<you>`.
- [ ] `databricks bundle run acf_share_monitoring_job -t dev` runs the pipeline. The slowest steps are `04` (AI extraction) and `05` (index sync, up to about 40 minutes).
- [ ] In demo mode, check the job's `compliance_findings` task: its last cell must show `matches = true` for every share.
- [ ] Open the output of the `create_genie_space` task and copy the **Genie space ID**.

### D. Connect the app to Genie and start it

- [ ] Set `genie_space_id: <id>` under the target's `variables` in `databricks.yml`.
- [ ] `databricks bundle deploy -t dev`, then `databricks bundle run acf_share_monitoring_app -t dev` to start the app.
- [ ] Give app users access: `CAN_USE` on the app, `USE CATALOG` / `USE SCHEMA` / `SELECT` on the project schema, `CAN USE` on the warehouse, `CAN QUERY` on the chat endpoint and the vector index, and `CAN RUN` on the Genie space.
      Each user is asked once to consent to the app's scopes (SQL, Genie, model serving, Vector Search).

### E. Verify

- [ ] `SELECT compliance_status, count(*) FROM <catalog>.<schema>.share_compliance_summary GROUP BY 1` returns rows.
- [ ] In Genie, ask "Which shares are out of compliance with their agreements?".
- [ ] In the app, Home shows the KPIs and Compliance findings lists the issues. If a setting is missing, the app lists it instead of loading.

---

## Synthetic data switch

**Turn synthetic data ON (demo mode)**
1. Set `use_synthetic_data: "true"` for the target in `databricks.yml`.
2. `databricks bundle deploy -t <target>`, then run the job.

`01` and `02` generate the PDFs and source tables, `03` builds a synthetic share inventory, `06` generates recipient
activity for the 60 days up to today, and `04` / `07` check results against the generator's ground truth.

**Turn synthetic data OFF (real mode)**
1. Upload your signed agreement PDFs to `/Volumes/<catalog>/<schema>/sample_mous/agreements/`, or set `agreements_path`.
   Each agreement should list its shared data elements as table + column (like Appendix C of the synthetic agreements).
2. Set `source_catalog` / `source_schema` to where the ACF tables your shares expose live, and `share_name_prefix` (default `acf_`).
3. Tag identifier columns on those tables so over-sharing is rated correctly:
   `ALTER TABLE <table> ALTER COLUMN <column> SET TAGS ('acf_identifier' = 'direct')` (or `'indirect'`).
4. Set `use_synthetic_data: "false"`.
5. `databricks bundle deploy -t <target>`, then run the job. The `generate_agreements` and `source_tables` tasks finish with a "Skipped" message; that's expected.

**Switching modes:** use a separate target, or at least a separate `schema`, for each mode. Real mode doesn't delete the
synthetic tables and views a demo run created, so sharing a schema leaves demo objects next to real ones.

---

## Running a notebook by hand

You can open any notebook in `src/` and run it interactively. Without job parameters, `00_config` falls back to the
defaults written in its sections 1 and 2, so replace the `<FILL_IN: ...>` defaults there (or create notebook widgets
with the parameter names, e.g. `catalog`, `schema`) before running.

## Notes and limitations

* **Demo dates.** The synthetic agreements have fixed dates (`src/_agreements_spec`), while recipient activity always ends today.
  The planted scenarios stay valid until **June 14, 2027**, when the earliest active agreement (ACF-NIH-2025-031) expires;
  after that the reconciliation check in `07` fails until the dates in the spec are moved forward.
* **Two copies of the spec.** `src/_agreements_spec` (notebooks) and `src/generator/agreements_spec.py` (PDF generator) must stay identical.
* **Genie space.** It is created by the job (not as a bundle resource) because it needs the tables the job creates.
  `bundle destroy` doesn't delete it; delete it in the Genie UI if needed.
* **`bundle destroy`** drops the project schema (and every table in it), the volume, the job and the app.
* **Pre-created schema.** If an admin creates the schema for you, delete `resources/acf_share_monitoring.schema.yml`, set `schema`, and replace
  `${resources.schemas.acf_share_monitoring.name}` with `${var.schema}` in the job, volume and app files.
* **Source tables in one schema.** The lineage, tag and privilege views in `06` look for source tables in `source_catalog.source_schema`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `bundle validate`: variable has no value | Set it under the target's `variables` in `databricks.yml`. |
| `ValueError: 00_config is not configured` | Running by hand: replace the `<FILL_IN>` defaults in `00_config`. In the job: check the job parameters. |
| `generate_agreements` fails with `generator failed` | Make sure `src/generator/` was deployed with the bundle and the `%pip install` cell ran. |
| `parse_classify_extract`: no agreement PDFs found | Real mode: upload PDFs to the agreements folder. Demo mode: rerun from `generate_agreements`. |
| `share_inventory` warning: no Delta Shares found | Check `share_name_prefix` and your `USE SHARE` privilege. |
| `vector_index`: index did not finish syncing | Check the Vector Search endpoint is online and `embedding_model` exists, then repair the run from that task. |
| Permission errors on `system.*` | Ask an admin for `SELECT` on the system schemas in the prerequisites. |
| App says "This app is not configured yet" | Set the listed values as bundle variables, then `bundle deploy`. |
| App deploy fails: name already exists | App names are unique per workspace. Change `name` in `resources/acf_share_monitoring.app.yml` (dev) or the `prod` override. |
