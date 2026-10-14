import time
import frappe
from frappe.model.document import Document
from custom_report.db_connection import get_dr_connection
from psycopg2.extras import RealDictCursor


class CIFMerge(Document):
	def validate(self):
		if not self.aadhar:
			frappe.throw("Kripya Aadhar fill karein.")

		# Agar user ne child table me already data edit/add kiya hai, to use overwrite mat karo
		if not self.cif_details and self.aadhar:
			records = get_cif_records(aadhar=self.aadhar)
			if records:
				for r in records:
					self.append("cif_details", {
						"cif_id": r.get("cif_id"),
						"first_name": r.get("first_name"),
						"middle_name": r.get("middle_name"),
						"last_name": r.get("last_name"),
						"cif_creation": r.get("cif_creation"),
						"date_of_birth": r.get("date_of_birth"),
						"pan": r.get("pan"),
						"mobile": r.get("mobile"),
						"phone_local_code": r.get("phone_local_code"),
						"sol_id": r.get("sol_id"),
						"address_line_1": r.get("address_line_1"),
						"address_line_2": r.get("address_line_2"),
						"address_line_3": r.get("address_line_3"),
						"primary": r.get("primary", 0),
						"merge": r.get("merge", 0),
						"re_kyc": r.get("re_kyc", 0)
					})

		if self.cif_details:
			self.total_cif_count = len(self.cif_details)
		else:
			self.total_cif_count = 0


ACTIVE_CIF_QUERY = """
WITH aadhaar_cif_count AS (
    SELECT
        referencenumber AS aadhaar_no,
        COUNT(DISTINCT orgkey) AS total_cif_count
    FROM crmuser.entitydocument
    WHERE UPPER(docdescr) LIKE 'AADHAAR%'
      AND doccode = '2'
      AND referencenumber IS NOT NULL
      AND TRIM(referencenumber) != ''
    GROUP BY referencenumber
)
SELECT
    ed.referencenumber                      AS "AADHAAR NUMBER",
    ed.docdescr                             AS "DOC DESCRIPTION",
    ed.orgkey                               AS "CIF ID",
    pan.referencenumber                     AS "PAN NUMBER",
    pan.doccode                             AS "PAN DOC CODE",
    pan.docdescr                            AS "PAN DOC DESCRIPTION",
    a.cust_first_name                       AS "FIRST NAME",
    a.cust_middle_name                      AS "MIDDLE NAME",
    a.cust_last_name                        AS "LAST NAME",
    TRIM(
        CONCAT_WS(' ',
            NULLIF(TRIM(a.cust_first_name), ''),
            NULLIF(TRIM(a.cust_middle_name), ''),
            NULLIF(TRIM(a.cust_last_name), '')
        )
    )                                       AS "CUSTOMER NAME",
    a.primary_sol_id                        AS "SOL ID",
    a.relationshipopeningdate               AS "CIF OPENING DATE",
    TO_CHAR(a.cust_dob, 'YYYY-MM-DD')       AS "CUST DOB",
    COUNT(DISTINCT g.foracid)               AS "ACTIVE ACCOUNTS COUNT",
    STRING_AGG(DISTINCT g.foracid, ', ')   AS "ACTIVE ACCOUNT NUMBERS",
    'ACTIVE'                                AS "CIF STATUS",
    cp.phone_type                           AS "PHONE TYPE",   
    cp.phonenolocalcode                     AS "PHONE LOCAL CODE",
    cp.phoneno                              AS "PHONE NUMBER",
    ad.addresscategory                      AS "ADDRESS CATEGORY",
    ad.address_line1                        AS "ADDRESS LINE 1",
    ad.address_line2                        AS "ADDRESS LINE 2",
    ad.address_line3                        AS "ADDRESS LINE 3",
    ad.zip                                  AS "PIN CODE",       
    ac.total_cif_count                      AS "TOTAL CIF COUNT"
FROM crmuser.entitydocument ed
JOIN aadhaar_cif_count ac
    ON ed.referencenumber = ac.aadhaar_no
LEFT JOIN crmuser.entitydocument pan
    ON ed.orgkey = pan.orgkey
   AND pan.doccode = 'PAN'
   AND UPPER(pan.docdescr) LIKE 'PAN%'    
LEFT JOIN crmuser.accounts a
    ON ed.orgkey = a.orgkey
LEFT JOIN crmuser.address ad
    ON ed.orgkey = ad.orgkey
   AND UPPER(ad.addresscategory) = 'MAILING'
LEFT JOIN crmuser.cphone cp
    ON ed.orgkey = cp.phone_b2kid
   AND UPPER(cp.phone_type) = 'CELLPH'
JOIN tbaadm.gam g
    ON a.orgkey = g.cif_id
   AND g.acct_cls_flg = 'N'
   AND g.entity_cre_flg = 'Y'
   AND g.del_flg = 'N'                                       
WHERE UPPER(ed.docdescr) LIKE 'AADHAAR%'  
  AND ed.doccode = '2'
  AND LENGTH(TRIM(ed.referencenumber)) = 12
  AND {filter_clause}
GROUP BY
    ed.referencenumber,
    ed.docdescr,
    ed.orgkey,
    pan.referencenumber,
    pan.doccode,
    pan.docdescr,
    a.cust_first_name,
    a.cust_middle_name,
    a.cust_last_name,
    cp.phone_type,
    cp.phonenolocalcode,
    cp.phoneno,        
    ad.addresscategory,
    ad.address_line1,
    ad.address_line2,
    ad.address_line3,
    ad.zip,
    a.primary_sol_id,
    a.relationshipopeningdate,
    a.cust_dob,
    ac.total_cif_count
HAVING COUNT(DISTINCT g.foracid) > 0
ORDER BY
    ac.total_cif_count DESC,
    ed.referencenumber,
    ed.orgkey
"""

INACTIVE_CIF_QUERY = """
WITH aadhaar_cif_count AS (
    SELECT
        referencenumber AS aadhaar_no,
        COUNT(DISTINCT orgkey) AS total_cif_count
    FROM crmuser.entitydocument
    WHERE UPPER(docdescr) LIKE 'AADHAAR%'
      AND doccode = '2'
      AND referencenumber IS NOT NULL
      AND TRIM(referencenumber) != ''
    GROUP BY referencenumber
)
SELECT
    ed.referencenumber            AS "AADHAAR NUMBER",
    ed.docdescr                   AS "DOC DESCRIPTION",
    ed.orgkey                     AS "CIF ID",
    pan.referencenumber           AS "PAN NUMBER",
    pan.doccode                   AS "PAN DOC CODE",
    pan.docdescr                  AS "PAN DOC DESCRIPTION",
    a.cust_first_name             AS "FIRST NAME",
    a.cust_middle_name            AS "MIDDLE NAME",
    a.cust_last_name              AS "LAST NAME",
    TRIM(
        CONCAT_WS(' ',
            NULLIF(TRIM(a.cust_first_name), ''),
            NULLIF(TRIM(a.cust_middle_name), ''),
            NULLIF(TRIM(a.cust_last_name), '')
        )
    )                             AS "CUSTOMER NAME",
    a.primary_sol_id              AS "SOL ID",
    a.relationshipopeningdate     AS "CIF OPENING DATE",
    TO_CHAR(a.cust_dob, 'YYYY-MM-DD') AS "CUST DOB",
    COUNT(DISTINCT g.foracid)     AS "ACTIVE ACCOUNTS COUNT",
    COALESCE(STRING_AGG(DISTINCT g.foracid, ', '), 'NO ACTIVE ACCOUNT') AS "ACTIVE ACCOUNT NUMBERS",
    'INACTIVE'                    AS "CIF STATUS",
    cp.phone_type                 AS "PHONE TYPE",   
    cp.phonenolocalcode           AS "PHONE LOCAL CODE",
    cp.phoneno                    AS "PHONE NUMBER",
    ad.addresscategory            AS "ADDRESS CATEGORY",
    ad.address_line1              AS "ADDRESS LINE 1",
    ad.address_line2              AS "ADDRESS LINE 2",
    ad.address_line3              AS "ADDRESS LINE 3",
    ad.zip                        AS "PIN CODE",       
    ac.total_cif_count            AS "TOTAL CIF COUNT"
FROM crmuser.entitydocument ed
JOIN aadhaar_cif_count ac
    ON ed.referencenumber = ac.aadhaar_no
LEFT JOIN crmuser.entitydocument pan
    ON ed.orgkey = pan.orgkey
   AND pan.doccode = 'PAN'
   AND UPPER(pan.docdescr) LIKE 'PAN%'    
LEFT JOIN crmuser.accounts a
    ON ed.orgkey = a.orgkey
LEFT JOIN crmuser.address ad
    ON ed.orgkey = ad.orgkey
   AND UPPER(ad.addresscategory) = 'MAILING'
LEFT JOIN crmuser.cphone cp
    ON ed.orgkey = cp.phone_b2kid
   AND UPPER(cp.phone_type) = 'CELLPH'    
LEFT JOIN tbaadm.gam g
    ON a.orgkey = g.cif_id
   AND g.acct_cls_flg = 'N'
   AND g.entity_cre_flg = 'Y'
   AND g.del_flg = 'N'                                       
WHERE UPPER(ed.docdescr) LIKE 'AADHAAR%'
  AND ed.doccode = '2'
  AND LENGTH(TRIM(ed.referencenumber)) = 12
  AND {filter_clause}
GROUP BY
    ed.referencenumber,
    ed.docdescr,
    ed.orgkey,
    pan.referencenumber,
    pan.doccode,
    pan.docdescr,
    a.cust_first_name,
    a.cust_middle_name,
    a.cust_last_name,
    cp.phone_type,
    cp.phonenolocalcode,
    cp.phoneno,
    ad.addresscategory,
    ad.address_line1,
    ad.address_line2,
    ad.address_line3,
    ad.zip,     
    a.primary_sol_id,
    a.relationshipopeningdate,
    a.cust_dob,
    ac.total_cif_count
HAVING COUNT(DISTINCT g.foracid) = 0
ORDER BY
    ac.total_cif_count DESC,
    ed.referencenumber,
    ed.orgkey
"""


@frappe.whitelist()
def get_cif_records(aadhar=None, pan=None):
	if not aadhar and not pan:
		return []

	# Filter clause prepare
	params = {}
	if aadhar:
		filter_clause = "ed.referencenumber = %(search_val)s"
		params["search_val"] = str(aadhar).strip()
	else:
		filter_clause = "pan.referencenumber = %(search_val)s"
		params["search_val"] = str(pan).strip().upper()

	active_sql = ACTIVE_CIF_QUERY.format(filter_clause=filter_clause)
	inactive_sql = INACTIVE_CIF_QUERY.format(filter_clause=filter_clause)

	records = []
	conn = None
	try:
		conn = get_dr_connection()
		with conn.cursor(cursor_factory=RealDictCursor) as cur:
			# 1. Run Active query
			cur.execute(active_sql, params)
			active_rows = cur.fetchall() or []

			# 2. Run Inactive query
			cur.execute(inactive_sql, params)
			inactive_rows = cur.fetchall() or []

		raw_rows = active_rows + inactive_rows

		for r in raw_rows:
			records.append({
				"cif_id": r.get("CIF ID"),
				"first_name": r.get("FIRST NAME") or (r.get("CUSTOMER NAME", "").split(" ")[0] if r.get("CUSTOMER NAME") else ""),
				"middle_name": r.get("MIDDLE NAME") or "",
				"last_name": r.get("LAST NAME") or "",
				"cif_creation": str(r.get("CIF OPENING DATE")) if r.get("CIF OPENING DATE") else "",
				"date_of_birth": str(r.get("CUST DOB")) if r.get("CUST DOB") else "",
				"pan": r.get("PAN NUMBER") or "",
				"mobile": r.get("PHONE NUMBER") or "",
				"phone_local_code": r.get("PHONE LOCAL CODE") or "",
				"sol_id": r.get("SOL ID") or "",
				"address_line_1": r.get("ADDRESS LINE 1") or "",
				"address_line_2": r.get("ADDRESS LINE 2") or "",
				"address_line_3": r.get("ADDRESS LINE 3") or "",
				"cif_status": r.get("CIF STATUS") or "ACTIVE",
				"active_accounts_count": r.get("ACTIVE ACCOUNTS COUNT") or 0,
				"active_account_numbers": r.get("ACTIVE ACCOUNT NUMBERS") or "",
				"total_cif_count": r.get("TOTAL CIF COUNT") or len(raw_rows),
				"aadhar": r.get("AADHAAR NUMBER") or aadhar,
				"primary": 0,
				"merge": 0,
				"re_kyc": 0
			})

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="CIF Records Fetch Failed")
		frappe.throw(f"Error fetching CIF records from DB: {str(e)}")
	finally:
		if conn:
			try:
				conn.close()
			except Exception:
				pass

	return records


@frappe.whitelist()
def sync_all_cif_merge_records(batch_size=5000):
	"""
	Bulk synchronizes duplicate CIF records from Finacle DR DB into 'CIF Merge' doctype.
	Fetches active and inactive records in batches of 5000 rows to optimize memory and DB load.
	Command to execute:
		bench execute banking_api.banking_api.doctype.cif_merge.cif_merge.sync_all_cif_merge_records
	"""
	batch_size = int(batch_size)
	print(f"--- Starting Bulk CIF Merge Sync (Batch size: {batch_size}) ---")

	queries = [
		("ACTIVE", ACTIVE_CIF_QUERY.format(filter_clause="1=1")),
		("INACTIVE", INACTIVE_CIF_QUERY.format(filter_clause="1=1")),
	]

	total_processed = 0

	for label, sql in queries:
		print(f"\n[INFO] Processing {label} CIF Records...")
		batch_count = 0
		attempt = 0
		retry_count = 0
		while True:
			conn = None
			try:
				conn = get_dr_connection()
				with conn.cursor() as setup_cur:
					try:
						setup_cur.execute("SET statement_timeout = 0;")
						setup_cur.execute("SET idle_in_transaction_session_timeout = 0;")
					except Exception:
						pass

				cursor_name = f"cif_stream_{label.lower()}_{attempt}"
				with conn.cursor(name=cursor_name, cursor_factory=RealDictCursor) as cur:
					cur.itersize = batch_size
					cur.execute(sql)

					# Agar reconnect hua hai to already processed records ko fast-skip karein
					if batch_count > 0:
						print(f"[RECOVERY] Skipping {batch_count} already processed rows...")
						cur.scroll(batch_count, mode='absolute')

					while True:
						rows = cur.fetchmany(batch_size)
						if not rows:
							break

						# Group rows by Aadhaar number
						grouped = {}
						for r in rows:
							aadhaar = (r.get("AADHAAR NUMBER") or "").strip()
							if not aadhaar:
								continue
							if aadhaar not in grouped:
								grouped[aadhaar] = []
							grouped[aadhaar].append(r)

						for aadhaar, cif_list in grouped.items():
							_upsert_cif_merge(aadhaar, cif_list)

						frappe.db.commit()
						batch_count += len(rows)
						total_processed += len(rows)
						print(f"[PROGRESS] {label}: {batch_count} records processed so far...")
						# Har successful batch par retry delay reset karein
						retry_count = 0

				# Complete ho gaya without error to break outer loop
				break

			except Exception as e:
				frappe.db.rollback()
				attempt += 1
				retry_count += 1
				err_msg = str(e).strip()
				print(f"\n[WARNING] Disconnected at {batch_count} rows. Error: {err_msg}")
				wait_sec = min(retry_count * 5, 30)
				print(f"[RETRY attempt #{attempt}] Reconnecting in {wait_sec}s and resuming from row {batch_count}...")
				time.sleep(wait_sec)
			finally:
				if conn:
					try:
						conn.close()
					except Exception:
						pass

	print(f"\n--- Bulk CIF Merge Sync Completed! Total processed: {total_processed} ---")


def _upsert_cif_merge(aadhaar, cif_list):
	"""Helper to create or update CIF Merge document and its child CIF Details."""
	existing_name = frappe.db.get_value("CIF Merge", {"aadhar": aadhaar}, "name")

	if existing_name:
		doc = frappe.get_doc("CIF Merge", existing_name)
	else:
		doc = frappe.new_doc("CIF Merge")
		doc.aadhar = aadhaar

	existing_cif_ids = {row.cif_id for row in doc.cif_details}

	for r in cif_list:
		cif_id = r.get("CIF ID")
		if not cif_id or cif_id in existing_cif_ids:
			continue

		doc.append("cif_details", {
			"cif_id": cif_id,
			"first_name": r.get("FIRST NAME") or (r.get("CUSTOMER NAME", "").split(" ")[0] if r.get("CUSTOMER NAME") else ""),
			"middle_name": r.get("MIDDLE NAME") or "",
			"last_name": r.get("LAST NAME") or "",
			"cif_creation": str(r.get("CIF OPENING DATE")) if r.get("CIF OPENING DATE") else "",
			"date_of_birth": str(r.get("CUST DOB")) if r.get("CUST DOB") else "",
			"pan": r.get("PAN NUMBER") or "",
			"mobile": r.get("PHONE NUMBER") or "",
			"phone_local_code": r.get("PHONE LOCAL CODE") or "",
			"sol_id": r.get("SOL ID") or "",
			"address_line_1": r.get("ADDRESS LINE 1") or "",
			"address_line_2": r.get("ADDRESS LINE 2") or "",
			"address_line_3": r.get("ADDRESS LINE 3") or "",
			"primary": 0,
			"merge": 0,
			"re_kyc": 0
		})
		existing_cif_ids.add(cif_id)

	doc.total_cif_count = len(doc.cif_details)
	doc.flags.ignore_validate = True
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_permissions = True
	doc.save()
