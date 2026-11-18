# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — ACF source tables (synthetic)
# MAGIC > **Runs only when `USE_SYNTHETIC_DATA = True` in `00_config`.** In real mode this notebook exits immediately; your own tables in `SOURCE_CATALOG.SOURCE_SCHEMA` are used, and you tag their identifier columns yourself (see `README.md`).
# MAGIC
# MAGIC Nine synthetic ACF datasets that the agreements cover. Direct identifiers are tagged `acf_identifier = direct` and quasi-identifiers
# MAGIC `acf_identifier = indirect` with Unity Catalog column tags. The compliance views read those tags from `system.information_schema.column_tags`
# MAGIC to rate how serious an over-share is. SSNs use the invalid 9xx range; names come from small fictional lists.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

# DBTITLE 1,Skip in real mode
if not USE_SYNTHETIC_DATA:   # real mode: your own source tables in SOURCE_CATALOG.SOURCE_SCHEMA are used instead
    dbutils.notebook.exit(f"Skipped: use_synthetic_data = false. Source tables are read from {SOURCE_CATALOG}.{SOURCE_SCHEMA}; "
                          "tag their identifier columns with acf_identifier = 'direct' or 'indirect' (see README.md).")

# COMMAND ----------

# MAGIC %run ./_agreements_spec

# COMMAND ----------

STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT",
          "NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]
st = "array(" + ",".join(f"'{s}'" for s in STATES) + ")"
FIRST = "array('Ava','Liam','Mia','Noah','Zoe','Eli','Ivy','Owen','Maya','Leo','Nora','Kai','Luna','Ezra','Aria','Jude','Rosa','Theo','Lena','Omar')"
LAST = "array('Rivera','Chen','Okafor','Patel','Nguyen','Brooks','Haddad','Kowalski','Mensah','Lindgren','Torres','Abebe','Sato','Murphy','Ibrahim','Novak')"
pick = lambda arr, seed, n: f"element_at({arr}, cast(pmod(xxhash64(id, {seed}), {n}) AS INT) + 1)"
u = lambda seed: f"(pmod(xxhash64(id, {seed}), 1000000) / 1000000.0)"          # deterministic uniform [0,1)
d = lambda start, days, seed: f"date_add(DATE'{start}', cast(pmod(xxhash64(id, {seed}), {days}) AS INT))"
def make(name, n, select, comment):
    spark.sql(f"CREATE OR REPLACE TABLE {S}.{name} COMMENT '{comment} SYNTHETIC DATA.' AS SELECT {select} FROM range({n})")
    print(f"{name:28s} {spark.table(f'{S}.{name}').count():>7,} rows")

make("foster_care_afcars", 5000, f"""
  concat('AF', lpad(id, 7, '0')) AS afcars_record_id, {pick(st,1,51)} AS state_code, lpad(cast(pmod(xxhash64(id,2), 999) + 1 AS STRING), 5, '0') AS county_fips,
  concat({pick(FIRST,3,20)}, ' ', {pick(LAST,4,16)}) AS child_name, {d('2008-01-01', 6000, 5)} AS child_dob, cast(pmod(xxhash64(id,6), 17) AS INT) AS age_at_removal,
  {pick("array('F','M')",7,2)} AS sex, {pick("array('White','Black','Hispanic','Asian','American Indian/Alaska Native','Two or more races')",8,6)} AS race_ethnicity,
  {d('2022-01-01', 1400, 9)} AS removal_date, {pick("array('Neglect','Physical abuse','Parental drug use','Caretaker inability to cope','Housing','Sexual abuse')",10,6)} AS removal_reason,
  {pick("array('Foster family (non-relative)','Foster family (relative)','Group home','Institution','Pre-adoptive home','Trial home visit')",11,6)} AS placement_setting,
  cast(pmod(xxhash64(id,12), 6) + 1 AS INT) AS num_placements, {d('2024-01-01', 900, 13)} AS discharge_date,
  {pick("array('Reunification','Adoption','Guardianship','Emancipation','Living with relative')",14,5)} AS discharge_reason,
  cast(pmod(xxhash64(id,15), 1400) + 30 AS INT) AS length_of_stay_days, concat('CW', lpad(cast(pmod(xxhash64(id,16), 900) AS STRING), 4, '0')) AS caseworker_id""",
  "Foster care episodes modeled on AFCARS, one row per removal episode.")
make("child_maltreatment_reports", 8000, f"""
  concat('MR', lpad(id, 8, '0')) AS report_id, {pick(st,21,51)} AS state_code, {d('2024-10-01', 760, 22)} AS report_date,
  {pick("array('Education personnel','Legal/law enforcement','Medical personnel','Social services','Relative','Anonymous')",23,6)} AS report_source,
  {pick("array('Neglect','Physical abuse','Sexual abuse','Psychological maltreatment','Medical neglect')",24,5)} AS maltreatment_type,
  {pick("array('Substantiated','Indicated','Unsubstantiated','Alternative response')",25,4)} AS disposition, cast(pmod(xxhash64(id,26), 18) AS INT) AS child_age,
  {pick("array('F','M')",27,2)} AS child_sex, {u(28)} < 0.35 AS victim_flag, {pick("array('Parent','Relative','Partner of parent','Other','Unknown')",29,5)} AS perpetrator_relationship,
  concat({pick(FIRST,30,20)}, ' ', {pick(LAST,31,16)}) AS child_name, lpad(cast(pmod(xxhash64(id,32), 99950) + 10 AS STRING), 5, '0') AS address_zip""",
  "Child maltreatment reports modeled on NCANDS, one row per report.")
make("head_start_centers", 400, f"""
  concat('HSC', lpad(id, 5, '0')) AS center_id, concat('HSP', lpad(cast(pmod(id, 120) AS STRING), 4, '0')) AS program_id,
  concat({pick("array('Sunrise','Little Oaks','Bright Path','Riverbend','Harbor','Maple Grove','Cedar Hill','Lakeside')",41,8)}, ' Early Learning Center') AS center_name,
  concat(cast(pmod(xxhash64(id,42), 9800) + 100 AS STRING), ' ', {pick("array('Main St','Oak Ave','School Rd','Park Blvd','Elm St','Union Ave')",43,6)}) AS street_address,
  {pick("array('Springfield','Fairview','Riverside','Franklin','Greenville','Madison','Clinton','Georgetown')",44,8)} AS city, {pick(st,45,51)} AS state_code,
  lpad(cast(pmod(xxhash64(id,46), 99950) + 10 AS STRING), 5, '0') AS zip_code, round(25 + {u(47)} * 23, 5) AS latitude, round(-124 + {u(48)} * 57, 5) AS longitude,
  cast(pmod(xxhash64(id,49), 40) AS INT) AS funded_slots_infant_toddler, cast(pmod(xxhash64(id,50), 120) + 20 AS INT) AS funded_slots_preschool,
  {pick("array('Licensed','Licensed','Licensed','Provisional')",51,4)} AS licensing_status, concat('director', id, '@example-headstart.org') AS director_email""",
  "Head Start centers, one row per center.")
make("head_start_enrollment", 6000, f"""
  concat('HSE', lpad(id, 7, '0')) AS enrollment_id, concat('HSP', lpad(cast(pmod(id, 120) AS STRING), 4, '0')) AS program_id,
  concat({pick("array('Community Action','United Families','Metro Early Start','Rural Opportunity')",61,4)}, ' Head Start') AS grantee_name,
  concat('HSC', lpad(cast(pmod(xxhash64(id,62), 400) AS STRING), 5, '0')) AS center_id, {pick(st,63,51)} AS state_code,
  concat({pick(FIRST,64,20)}, ' ', {pick(LAST,65,16)}) AS child_name, {d('2021-01-01', 1500, 66)} AS child_dob, cast(pmod(xxhash64(id,67), 60) AS INT) AS child_age_months,
  {d('2025-08-01', 450, 68)} AS enrollment_date, {pick("array('Center-based','Home-based','Family child care','Combination')",69,4)} AS program_option,
  {u(70)} < 0.13 AS disability_services_flag, {pick("array('Medicaid/CHIP','Private','Uninsured','Other public')",71,4)} AS health_insurance_status,
  {u(72)} < 0.86 AS immunizations_up_to_date, {u(73)} < 0.78 AS dental_exam_completed, cast(pmod(xxhash64(id,74), 180) + 20 AS INT) AS family_income_pct_fpl,
  concat('(555) ', lpad(cast(pmod(xxhash64(id,75), 999) AS STRING), 3, '0'), '-', lpad(cast(pmod(xxhash64(id,76), 9999) AS STRING), 4, '0')) AS parent_phone""",
  "Head Start enrollment, one row per enrolled child.")
make("tanf_recipients", 10000, f"""
  concat('TR', lpad(id, 8, '0')) AS recipient_id, concat('TC', lpad(cast(div(id, 3) AS STRING), 7, '0')) AS case_id, {pick(st,81,51)} AS state_code,
  date_trunc('MONTH', {d('2024-10-01', 760, 82)}) AS benefit_month,
  concat('9', lpad(cast(pmod(xxhash64(id,83), 100) AS STRING), 2, '0'), '-', lpad(cast(pmod(xxhash64(id,84), 100) AS STRING), 2, '0'), '-', lpad(cast(pmod(xxhash64(id,85), 10000) AS STRING), 4, '0')) AS recipient_ssn,
  sha2(concat('salt-', id), 256) AS recipient_ssn_hash, {d('1975-01-01', 18000, 86)} AS date_of_birth, cast(pmod(xxhash64(id,87), 6) + 1 AS INT) AS household_size,
  round(150 + {u(88)} * 750, 2) AS benefit_amount, {pick("array('Meeting requirement','Exempt','Not meeting','Sanctioned')",89,4)} AS work_participation_status,
  {u(90)} < 0.06 AS sanction_flag""", "TANF recipients, one row per recipient per benefit month.")
spark.sql(f"""CREATE OR REPLACE TABLE {S}.tanf_caseload_monthly COMMENT 'TANF caseload and expenditures by state and month (aggregate). SYNTHETIC DATA.' AS
  SELECT s.state_code, m.benefit_month, f AS total_families, round(f * 2.4) AS total_recipients, round(f * 0.7) AS adult_recipients, round(f * 1.7) AS child_recipients,
         round(f * 512.0, 2) AS total_expenditures, round(0.2 + pmod(xxhash64(s.state_code, m.benefit_month), 40) / 100.0, 2) AS work_participation_rate
  FROM (SELECT explode({st}) AS state_code) s
  CROSS JOIN (SELECT explode(sequence(DATE'2024-10-01', DATE'2026-09-01', INTERVAL 1 MONTH)) AS benefit_month) m
  LATERAL VIEW explode(array(cast(pmod(xxhash64(s.state_code), 40000) + 1500 AS BIGINT))) x AS f""")
print("tanf_caseload_monthly", spark.table(f"{S}.tanf_caseload_monthly").count())
make("ccdf_children_served", 7000, f"""
  concat('CC', lpad(id, 8, '0')) AS child_record_id, {pick(st,101,51)} AS state_code, lpad(cast(pmod(xxhash64(id,102), 999) + 1 AS STRING), 5, '0') AS county_fips,
  {d('2015-01-01', 4000, 103)} AS child_dob, {pick("array('0-2','3-5','6-8','9-12')",104,4)} AS child_age_band,
  {pick("array('Licensed center','Licensed family home','License-exempt relative','License-exempt center')",105,4)} AS provider_type,
  {pick("array('Full-time','Part-time','Before/after school')",106,3)} AS care_setting, round(300 + {u(107)} * 1100, 2) AS monthly_subsidy_amount,
  {pick("array('<100% FPL','100-150% FPL','150-200% FPL','>200% FPL')",108,4)} AS family_income_band, {u(109)} < 0.55 AS chip_medicaid_enrolled_flag,
  concat({pick(FIRST,110,20)}, ' ', {pick(LAST,111,16)}) AS parent_name, concat('parent', id, '@example.com') AS parent_email""",
  "Children served by the Child Care and Development Fund (CCDF), one row per child.")
make("child_support_collections", 5000, f"""
  concat('CS', lpad(id, 8, '0')) AS case_id, {pick(st,121,51)} AS state_code, element_at(array(2025, 2026), cast(pmod(xxhash64(id,122), 2) AS INT) + 1) AS fiscal_year,
  cast(pmod(xxhash64(id,123), 4) + 1 AS INT) AS quarter, {pick("array('Current support','Medical support','Arrears only')",124,3)} AS order_type,
  round(200 + {u(125)} * 900, 2) AS current_support_due, round((200 + {u(125)} * 900) * (0.4 + {u(126)} * 0.6), 2) AS current_support_collected,
  round({u(127)} * 400, 2) AS arrears_collected,
  concat('9', lpad(cast(pmod(xxhash64(id,128), 100) AS STRING), 2, '0'), '-', lpad(cast(pmod(xxhash64(id,129), 100) AS STRING), 2, '0'), '-', lpad(cast(pmod(xxhash64(id,130), 10000) AS STRING), 4, '0')) AS noncustodial_parent_ssn,
  concat({pick(FIRST,131,20)}, ' ', {pick(LAST,132,16)}) AS custodial_parent_name, {u(133)} < 0.12 AS interstate_flag""",
  "Child support cases with collections by fiscal quarter, one row per case per quarter.")
make("grant_awards", 1200, f"""
  concat('90', {pick("array('CA','CH','CF','YD','EP')",141,5)}, lpad(id, 6, '0')) AS award_id,
  {pick("array('Office of Head Start','Children''s Bureau','Office of Child Care','Office of Family Assistance','Office of Child Support Services')",142,5)} AS program_office,
  concat({pick("array('Community Action','Family Services','Youth Futures','Healthy Start')",143,4)}, ' of ', {pick("array('Springfield','Fairview','Riverside','Franklin')",144,4)}) AS recipient_org,
  {pick(st,145,51)} AS state_code, round(50000 + {u(146)} * 2450000, 2) AS award_amount, {d('2024-09-01', 700, 147)} AS award_date,
  {pick("array('93.600','93.556','93.575','93.558','93.563')",148,5)} AS assistance_listing_number, {d('2027-01-01', 900, 149)} AS project_period_end""",
  "ACF discretionary grant awards, one row per award.")

# COMMAND ----------

# MAGIC %md ## Tag identifiers (read later from system.information_schema.column_tags)

# COMMAND ----------

INDIRECT_COLS = {"county_fips", "address_zip", "zip_code", "latitude", "longitude", "street_address", "case_id", "recipient_id",
                 "child_record_id", "afcars_record_id", "enrollment_id", "report_id"}
n = 0
for t in TABLES:
    for c in cols(t):
        level = "direct" if c in pii(t) else "indirect" if c in INDIRECT_COLS else None
        if level:
            spark.sql(f"ALTER TABLE {S}.{t} ALTER COLUMN {c} SET TAGS ('acf_identifier' = '{level}')"); n += 1
    spark.sql(f"ALTER TABLE {S}.{t} SET TAGS ('acf_data_owner' = 'ACF', 'acf_synthetic' = 'true')")
print("tagged", n, "identifier columns")
missing = [(t, c) for t in TABLES for c in cols(t) if c not in spark.table(f"{S}.{t}").columns]
assert not missing, f"spec columns missing from tables: {missing}"