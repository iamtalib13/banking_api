# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
import psycopg2
import psycopg2.extras
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class ShareApplicationSettings(Document):
    pass


def db_connection():
    """Connect to external PostgreSQL (Finacle) using Finacle DB Credentials."""
    try:
        creds = frappe.get_single("Finacle DB Credentials")

        port = int(creds.db_port) if creds.db_port else 5432

        conn = psycopg2.connect(
            host=creds.db_host,
            port=port,
            user=creds.db_user,
            password=creds.get_password("db_password"),
            database=creds.db_name
        )
        return conn
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),
                         "PostgreSQL Connection Failed")
        frappe.throw(_("Database Connection Error: {0}").format(str(e)))


def cint_safe(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def get_share_application_query(sync_days):
    return f"""
		WITH AccountPriority AS (
			SELECT
				a.orgkey AS customer_id,
				a.bodatecreated AS cif_creation_dt,
				g.foracid AS acct_num,
				g.acct_opn_date AS account_opening_date,
				ROW_NUMBER() OVER (
					PARTITION BY a.orgkey
					ORDER BY
						CASE
							WHEN g.schm_code = '1001' THEN 1
							WHEN g.schm_code = '1002' THEN 2
							WHEN g.schm_code = '1003' THEN 3
							WHEN g.schm_code = '1004' THEN 4
							WHEN g.schm_code = '1005' THEN 5
							WHEN g.schm_code = '1006' THEN 6
							WHEN g.schm_code = '1008' THEN 7
							WHEN g.schm_code = '1009' THEN 8
							WHEN g.schm_code = '1010' THEN 9
							WHEN g.schm_code = '1011' THEN 10
							WHEN g.schm_code = '1012' THEN 11
							WHEN g.schm_code = '1013' THEN 12
							WHEN g.schm_code = '1101' THEN 13
							WHEN g.schm_code = '1102' THEN 14
							WHEN g.schm_code = '1103' THEN 15
							WHEN g.schm_code = '1104' THEN 16
							ELSE 17
						END
				) AS rank
			FROM tbaadm.gam g
			JOIN crmuser.accounts a ON g.cif_id = a.orgkey
			JOIN tbaadm.gsp g2 ON g.schm_code = g2.schm_code
			JOIN crmuser.entitydocument d ON a.orgkey = d.orgkey
			JOIN crmuser.address c ON a.orgkey = c.orgkey
			JOIN crmuser.phoneemail b ON a.orgkey = b.orgkey
			JOIN tbaadm.sol s ON g.sol_id = s.sol_id
			LEFT JOIN tbaadm.ant f ON g.acid = f.acid
			WHERE g.schm_type IN ('SBA', 'CAA')
			  AND g.schm_code IN (
				  '1001','1002','1003','1004','1005','1006','1008',
				  '1009','1010','1011','1012','1013','1101','1102','1103','1104'
			  )
		)
		SELECT
			customer_id,
			cif_creation_dt,
			acct_num,
			account_opening_date
		FROM AccountPriority
		WHERE rank = 1
		  AND account_opening_date BETWEEN CURRENT_DATE - INTERVAL '{int(sync_days)} day' AND CURRENT_DATE
		  AND cif_creation_dt > DATE '2024-12-09'
	"""


def run_share_application_sync():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_sync:
        return {
            "status": "skipped",
            "message": "Share Application Sync is disabled."
        }

    sync_days = cint_safe(settings.sync_back_days, default=1)

    conn = None
    cursor = None
    created_count = 0
    skipped_count = 0
    total_rows = 0

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = get_share_application_query(sync_days)
        cursor.execute(query)
        rows = cursor.fetchall() or []
        total_rows = len(rows)

        if rows:
            fetched_cifs = list({
                str(row.get("customer_id")).strip()
                for row in rows
                if row.get("customer_id") is not None
            })

            existing_cifs = set()
            if fetched_cifs:
                existing = frappe.get_all(
                    "Share Application",
                    filters={"cif": ["in", fetched_cifs]},
                    pluck="cif"
                )
                existing_cifs = {str(cif).strip()
                                 for cif in existing if cif is not None}

            for row in rows:
                customer_id = row.get("customer_id")
                acct_num = row.get("acct_num")
                cif_creation_dt = row.get("cif_creation_dt")
                account_opening_date = row.get("account_opening_date")

                if customer_id is None:
                    skipped_count += 1
                    continue

                customer_id_str = str(customer_id).strip()
                if customer_id_str in existing_cifs:
                    skipped_count += 1
                    continue

                doc = frappe.new_doc("Share Application")
                doc.cif = customer_id
                doc.account_number = acct_num
                doc.cif_creation_date = cif_creation_dt
                doc.account_opening_date = account_opening_date
                doc.status = "Pending"
                doc.insert(ignore_permissions=True)

                existing_cifs.add(customer_id_str)
                created_count += 1

        frappe.db.set_single_value(
            "Share Application Settings",
            "last_sync_run",
            now_datetime()
        )
        frappe.db.commit()

        return {
            "status": "success",
            "total_rows": total_rows,
            "created_count": created_count,
            "skipped_count": skipped_count,
            "message": (
                f"Sync completed. Total fetched: {total_rows}, "
                f"created: {created_count}, skipped existing: {skipped_count}."
            )
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(),
                         "Share Application Sync Failed")
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@frappe.whitelist()
def run_share_application_sync_manual():
    return run_share_application_sync()


def hourly_share_application_sync():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_sync:
        return

    if (settings.sync_timing or "").strip() != "Hourly":
        return

    run_share_application_sync()


def daily_share_application_sync():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_sync:
        return

    if (settings.sync_timing or "").strip() != "Daily":
        return

    run_share_application_sync()
