# Databricks notebook source
# MAGIC %md
# MAGIC # Agreement spec (shared definitions)
# MAGIC Single source of truth for the source tables, the synthetic agreements and the shares, including the mismatch each share is built to show (ground truth).

# COMMAND ----------

"""Single source of truth for the ACF Delta Share monitoring demo.
Drives (1) the synthetic agreement PDFs, (2) the ACF source tables, (3) the Delta Shares and recipients,
and (4) the ground-truth table that says which mismatch each share was built to show. All content is synthetic."""

ACF_SYSTEM = {"name": "ACF Enterprise Data Platform (EDP)", "acronym": "ACF-EDP",
              "function": "Agency analytics lakehouse; publishes approved datasets to partner agencies through Delta Sharing",
              "location": "AWS us-east-1, Databricks workspace operated by ACF OCIO"}

# ACF source tables (schema acf_deltashare_demo). Columns marked * are direct identifiers (PII).
TABLES = {
 "foster_care_afcars": ["afcars_record_id", "state_code", "county_fips", "child_name*", "child_dob*", "age_at_removal", "sex", "race_ethnicity",
                        "removal_date", "removal_reason", "placement_setting", "num_placements", "discharge_date", "discharge_reason",
                        "length_of_stay_days", "caseworker_id"],
 "child_maltreatment_reports": ["report_id", "state_code", "report_date", "report_source", "maltreatment_type", "disposition", "child_age",
                                "child_sex", "victim_flag", "perpetrator_relationship", "child_name*", "address_zip"],
 "head_start_enrollment": ["enrollment_id", "program_id", "grantee_name", "center_id", "state_code", "child_name*", "child_dob*", "child_age_months",
                           "enrollment_date", "program_option", "disability_services_flag", "health_insurance_status", "immunizations_up_to_date",
                           "dental_exam_completed", "family_income_pct_fpl", "parent_phone*"],
 "head_start_centers": ["center_id", "program_id", "center_name", "street_address", "city", "state_code", "zip_code", "latitude", "longitude",
                        "funded_slots_infant_toddler", "funded_slots_preschool", "licensing_status", "director_email*"],
 "tanf_recipients": ["recipient_id", "case_id", "state_code", "benefit_month", "recipient_ssn*", "recipient_ssn_hash", "date_of_birth*",
                     "household_size", "benefit_amount", "work_participation_status", "sanction_flag"],
 "tanf_caseload_monthly": ["state_code", "benefit_month", "total_families", "total_recipients", "adult_recipients", "child_recipients",
                           "total_expenditures", "work_participation_rate"],
 "ccdf_children_served": ["child_record_id", "state_code", "county_fips", "child_dob*", "child_age_band", "provider_type", "care_setting",
                          "monthly_subsidy_amount", "family_income_band", "chip_medicaid_enrolled_flag", "parent_name*", "parent_email*"],
 "child_support_collections": ["case_id", "state_code", "fiscal_year", "quarter", "order_type", "current_support_due", "current_support_collected",
                               "arrears_collected", "noncustodial_parent_ssn*", "custodial_parent_name*", "interstate_flag"],
 "grant_awards": ["award_id", "program_office", "recipient_org", "state_code", "award_amount", "award_date", "assistance_listing_number",
                  "project_period_end"],
}
def cols(t): return [c.rstrip("*") for c in TABLES[t]]
def pii(t): return [c.rstrip("*") for c in TABLES[t] if c.endswith("*")]

# Agreements. "allowed" = columns the signed document permits. "shared" = what the Delta Share actually exposes.
# "scenario" = the mismatch the share was built to show (ground truth for the compliance check).
AGREEMENTS = [
 dict(doc_id="ACF-NIH-2025-014", kind="MOU", style="typed", partner="NIH", office="Eunice Kennedy Shriver National Institute of Child Health and Human Development (NICHD)",
      system_b="NICHD Child Outcomes Research Enclave", purpose="De-identified foster care outcomes research on placement stability",
      share="acf_nih_nichd_afcars", recipient="nih_nichd", effective="2025-03-01", expires="2028-02-29", signed=True,
      tables={"foster_care_afcars": ["afcars_record_id", "state_code", "age_at_removal", "sex", "race_ethnicity", "removal_reason",
                                     "placement_setting", "num_placements", "discharge_reason", "length_of_stay_days"]},
      shared={"foster_care_afcars": ["afcars_record_id", "state_code", "county_fips", "age_at_removal", "child_dob", "sex", "race_ethnicity",
                                     "removal_reason", "placement_setting", "num_placements", "discharge_reason", "length_of_stay_days"]},
      scenario="OVER_SHARING", note="child_dob (PII) and county_fips shared but not in the agreement"),
 dict(doc_id="ACF-NIH-2025-031", kind="MOU", style="handwritten", partner="NIH", office="National Institute of Environmental Health Sciences (NIEHS)",
      system_b="NIEHS Early Childhood Exposure Study Platform", purpose="Early childhood health indicators for an environmental exposure cohort study",
      share="acf_nih_niehs_headstart", recipient="nih_niehs", effective="2025-06-15", expires="2027-06-14", signed=True,
      tables={"head_start_enrollment": ["program_id", "state_code", "child_age_months", "health_insurance_status", "immunizations_up_to_date",
                                        "dental_exam_completed", "disability_services_flag"]},
      shared={"head_start_enrollment": ["program_id", "state_code", "child_age_months", "health_insurance_status", "immunizations_up_to_date",
                                        "dental_exam_completed", "disability_services_flag", "family_income_pct_fpl"]},
      scenario="COMPLIANT_WITH_AMENDMENT", note="family_income_pct_fpl added by Amendment No. 1"),
 dict(doc_id="ACF-NIH-2025-031-A1", kind="AMENDMENT", style="typed", partner="NIH", office="National Institute of Environmental Health Sciences (NIEHS)",
      system_b="NIEHS Early Childhood Exposure Study Platform", purpose="Adds family income as a percent of the federal poverty level to Appendix C",
      share="acf_nih_niehs_headstart", recipient="nih_niehs", effective="2026-04-01", expires="2027-06-14", signed=True, amends="ACF-NIH-2025-031",
      tables={"head_start_enrollment": ["family_income_pct_fpl"]}, shared=None, scenario="AMENDMENT", note="adds one column"),
 dict(doc_id="ACF-CDC-2025-008", kind="ISA", style="typed", partner="CDC", office="National Center for Injury Prevention and Control (NCIPC)",
      system_b="NCIPC Violence Prevention Data Platform", purpose="Child maltreatment surveillance for injury and violence prevention",
      share="acf_cdc_ncipc_maltreatment", recipient="cdc_ncipc", effective="2025-01-10", expires="2028-01-09", signed=True,
      tables={"child_maltreatment_reports": ["report_id", "state_code", "report_date", "maltreatment_type", "disposition", "child_age",
                                             "child_sex", "victim_flag", "perpetrator_relationship"]},
      shared={"child_maltreatment_reports": ["report_id", "state_code", "report_date", "maltreatment_type", "disposition", "child_age",
                                             "child_sex", "victim_flag", "perpetrator_relationship"]},
      scenario="COMPLIANT", note=""),
 dict(doc_id="ACF-CDC-2026-002", kind="MOU", style="handwritten", partner="CDC", office="National Center for Immunization and Respiratory Diseases (NCIRD)",
      system_b="NCIRD Immunization Coverage Analytics", purpose="Immunization coverage among children enrolled in Head Start",
      share="acf_cdc_ncird_immunization", recipient="cdc_ncird", effective="2026-02-01", expires="2029-01-31", signed=True,
      tables={"head_start_enrollment": ["program_id", "center_id", "state_code", "child_age_months", "immunizations_up_to_date"]},
      shared={"head_start_enrollment": ["program_id", "state_code", "child_age_months", "immunizations_up_to_date"]},
      scenario="UNDER_SHARING", note="center_id is in the agreement but not shared"),
 dict(doc_id="ACF-CDC-2026-011", kind="MOU", style="typed", partner="CDC", office="National Center for Health Statistics (NCHS)",
      system_b="NCHS Research Data Center", purpose="TANF caseload trends linked to national health survey estimates",
      share="acf_cdc_nchs_tanf", recipient="cdc_nchs", effective="2026-08-01", expires="2029-07-31", signed=True,
      tables={"tanf_caseload_monthly": ["state_code", "benefit_month", "total_families", "total_recipients", "child_recipients"]},
      shared=None, scenario="NOT_IMPLEMENTED", note="agreement signed, share never created"),
 dict(doc_id="ACF-FDA-2025-004", kind="MOU", style="typed", partner="FDA", office="Human Foods Program (HFP)",
      system_b="HFP Recall Outreach Analytics", purpose="Locate Head Start centers serving infants and toddlers for infant formula recall outreach",
      share="acf_fda_hfp_centers", recipient="fda_hfp", effective="2025-09-01", expires="2027-08-31", signed=True,
      tables={"head_start_centers": ["center_id", "center_name", "street_address", "city", "state_code", "zip_code", "funded_slots_infant_toddler"]},
      shared={"head_start_centers": ["center_id", "center_name", "street_address", "city", "state_code", "zip_code", "funded_slots_infant_toddler",
                                     "director_email"]},
      scenario="OVER_SHARING", note="director_email (contact PII) shared but not in the agreement"),
 dict(doc_id="ACF-CMS-2024-019", kind="ISA", style="typed", partner="CMS", office="Center for Medicaid and CHIP Services (CMCS)",
      system_b="CMCS Eligibility Analytics Environment", purpose="Link TANF recipients to Medicaid enrollment for eligibility alignment",
      share="acf_cms_cmcs_tanf_medicaid", recipient="cms_cmcs", effective="2024-10-01", expires="2026-09-30", signed=True,
      tables={"tanf_recipients": ["recipient_id", "state_code", "benefit_month", "recipient_ssn_hash", "date_of_birth", "household_size"]},
      shared={"tanf_recipients": ["recipient_id", "state_code", "benefit_month", "recipient_ssn_hash", "date_of_birth", "household_size"]},
      scenario="EXPIRED_AGREEMENT", note="agreement expired 2026-09-30; share still active"),
 dict(doc_id="ACF-CMS-2026-006", kind="MOU", style="handwritten", partner="CMS", office="Center for Medicaid and CHIP Services (CMCS)",
      system_b="CMCS CHIP Outreach Workbench", purpose="CHIP outreach to families of children receiving child care subsidies",
      share="acf_cms_ccdf_chip", recipient="cms_cmcs", shared_recipient="cms_ccsq", effective="2026-03-15", expires="2028-03-14", signed=True,
      tables={"ccdf_children_served": ["child_record_id", "state_code", "county_fips", "child_age_band", "chip_medicaid_enrolled_flag", "family_income_band"]},
      shared={"ccdf_children_served": ["child_record_id", "state_code", "county_fips", "child_age_band", "chip_medicaid_enrolled_flag", "family_income_band"]},
      scenario="RECIPIENT_MISMATCH", note="agreement names CMCS; share granted to CCSQ (Center for Clinical Standards and Quality)"),
 dict(doc_id="ACF-OS-2025-022", kind="MOU", style="typed", partner="OS", office="Office of the Assistant Secretary for Planning and Evaluation (ASPE)",
      system_b="ASPE Policy Analytics Workbench", purpose="TANF caseload and expenditure analysis for policy evaluation",
      share="acf_os_aspe_tanf", recipient="os_aspe", effective="2025-05-01", expires="2028-04-30", signed=True,
      tables={"tanf_caseload_monthly": cols("tanf_caseload_monthly")}, shared={"tanf_caseload_monthly": cols("tanf_caseload_monthly")},
      scenario="COMPLIANT", note=""),
 dict(doc_id="ACF-OS-2026-009", kind="ISA", style="handwritten", partner="OS", office="Office of the Assistant Secretary for Planning and Evaluation (ASPE)",
      system_b="ASPE Policy Analytics Workbench", purpose="Child support collection performance by state for program evaluation",
      share="acf_os_aspe_child_support", recipient="os_aspe", effective="2026-01-05", expires="2029-01-04", signed=True,
      tables={"child_support_collections": ["state_code", "fiscal_year", "quarter", "order_type", "current_support_due", "current_support_collected",
                                            "arrears_collected", "interstate_flag"]},
      shared={"child_support_collections": cols("child_support_collections")},
      scenario="OVER_SHARING", note="whole table shared: case_id, noncustodial_parent_ssn and custodial_parent_name are not in the agreement"),
]

# A share with no agreement behind it at all.
UNDOCUMENTED_SHARES = [dict(share="acf_os_ocio_grants_adhoc", recipient="os_ocio", tables={"grant_awards": cols("grant_awards")},
                            scenario="NO_AGREEMENT", note="ad hoc share to HHS OCIO with no MOU or ISA on file")]

PEOPLE = {  # fictional signatories and contacts
 "ACF": [("Dana R. Whitfield", "Chief Information Officer, ACF OCIO"), ("Marcus Ellery", "Director, Division of Data Governance, ACF")],
 "NIH": [("Priya Raman, PhD", "Director, Office of Data Science, NICHD"), ("Thomas Okafor", "Associate Director for Data, NIEHS")],
 "CDC": [("Elena Vasquez, MPH", "Director, Data Science Branch, NCIPC"), ("Robert Lindqvist", "Branch Chief, NCIRD"), ("Grace Nakamura", "Director, NCHS RDC")],
 "FDA": [("Kevin Abernathy", "Director, Office of Analytics, HFP")],
 "CMS": [("Sandra Okonkwo", "Director, Data and Systems Group, CMCS")],
 "OS":  [("Jonathan Pierce", "Deputy Assistant Secretary, ASPE")],
}
