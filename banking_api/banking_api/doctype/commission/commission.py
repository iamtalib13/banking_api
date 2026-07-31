# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

from tqdm import tqdm
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

import psycopg2
from psycopg2.extras import RealDictCursor


class Commission(Document):
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


QUERY_1 = """
WITH account_data AS (
    SELECT
        d.rm_id,
        g2.emp_name AS rm_name,
        d2.operacc,
        g.cif_id,
        g.acct_opn_date,
        a2.relationshipopeningdate AS cif_id_opening_date,
        g.foracid,
        g.sol_id,
        sol.sol_desc,
        g.schm_code AS scheme_code,
        gsp.schm_desc
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
       AND g.schm_code IN (
            '2004','2005','2006','2010','2011','2012','2013','2014','2015'
       )
    LEFT JOIN crmuser.accounts a2
        ON g.cif_id = a2.orgkey
    LEFT JOIN tbaadm.sol sol
        ON g.sol_id = sol.sol_id
    LEFT JOIN tbaadm.gsp gsp
        ON g.schm_code = gsp.schm_code
    LEFT JOIN custom.dsaauth d2
        ON d.rm_id = d2.user_id
    LEFT JOIN tbaadm.get g2
        ON d2.user_id = g2.emp_id
),
flow_data AS (
    SELECT
        d.rm_id,
        g.foracid,
        g.schm_code,
        SUM(tdt.flow_amt) AS total_flow_amount
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
       AND g.schm_code IN (
            '2004','2005','2006','2010','2011','2012','2013','2014','2015'
       )
    INNER JOIN tbaadm.tdt tdt
        ON tdt.acid = g.acid
       AND tdt.flow_code = 'NI'
    WHERE tdt.flow_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
    GROUP BY d.rm_id, g.foracid, g.schm_code
    HAVING SUM(tdt.flow_amt) > 0
),
tran_data AS (
    SELECT
        d.rm_id,
        g.foracid,
        g.schm_code,
        SUM(dtt.tran_amt) AS total_tran_amt
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
       AND g.schm_code IN (
            '2004','2005','2006','2010','2011','2012','2013','2014','2015'
       )
    INNER JOIN tbaadm.dtt dtt
        ON dtt.acid = g.acid
       AND dtt.flow_code = 'NI'
    WHERE (
        (
            dtt.tran_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
            AND dtt.value_date > DATE '2026-05-31'
        )
        OR
        (
            dtt.tran_date > DATE '2026-06-30'
            AND dtt.value_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
        )
        OR
        (
            dtt.value_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
            AND dtt.tran_date > DATE '2026-06-30'
        )
    )
    GROUP BY d.rm_id, g.foracid, g.schm_code
    HAVING SUM(dtt.tran_amt) > 0
),
reference_data AS (
    SELECT
        ed.referencenumber,
        da.user_id AS rm_id
    FROM crmuser.entitydocument ed
    INNER JOIN tbaadm.gam g
        ON ed.orgkey = g.cif_id
    INNER JOIN custom.dsaauth da
        ON g.foracid = da.operacc
    WHERE ed.doccode = 'PAN'
)
SELECT
    ad.rm_id,
    ad.rm_name,
    ad.operacc,
    ad.cif_id,
    ad.acct_opn_date,
    ad.cif_id_opening_date,
    ad.foracid,
    COALESCE(fd.total_flow_amount, 0) AS total_flow_amount,
    COALESCE(td.total_tran_amt, 0) AS total_tran_amt,
    COALESCE(rd.referencenumber, 'N/A') AS referencenumber,
    ad.scheme_code,
    ad.schm_desc,
    ad.sol_id,
    ad.sol_desc
FROM account_data ad
LEFT JOIN flow_data fd
    ON ad.rm_id = fd.rm_id
   AND ad.foracid = fd.foracid
   AND ad.scheme_code = fd.schm_code
LEFT JOIN tran_data td
    ON ad.rm_id = td.rm_id
   AND ad.foracid = td.foracid
   AND ad.scheme_code = td.schm_code
LEFT JOIN reference_data rd
    ON ad.rm_id = rd.rm_id
WHERE COALESCE(td.total_tran_amt, 0) > 0
ORDER BY ad.foracid, ad.rm_id, ad.scheme_code
"""

QUERY_2 = """
WITH account_data AS (
    SELECT
        ds.rm_id,
        g2.emp_name AS rm_name,
        d2.operacc,
        g.foracid,
        tam.deposit_period_mths,
        tam.deposit_period_days,
        COUNT(DISTINCT g.acid) AS count_acid_gam,
        SUM(dtt.tran_amt) AS total_tran_amt_dtt,
        SUM(tdt.flow_amt) AS total_flow_amt_tdt,
        g.sol_id,
        sol.sol_desc,
        g.schm_code AS scheme_code,
        gsp.schm_desc
    FROM custom.dsamap AS ds
    LEFT JOIN tbaadm.gam AS g
        ON g.foracid = ds.account_number
       AND g.schm_code IN (
            '2001','2002','2003',
            '2018','2019','2020','2021','2022','2023','2024','2025','2026','2027','2028','2029','2030','2031','2032','2033','2034','2035',
            '2101','2102','2103','2104','2105','2106',
            '2201','2202','2203',
            '9001','9002'
       )
       AND g.acct_opn_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
       AND g.acct_cls_flg = 'N'
    LEFT JOIN tbaadm.tam AS tam
        ON tam.acid = g.acid
    LEFT JOIN tbaadm.dtt AS dtt
        ON dtt.acid = g.acid
       AND dtt.flow_code = 'PI'
       AND dtt.tran_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
       AND NOT (
            dtt.value_date >= DATE '2026-05-01'
            AND dtt.value_date < DATE '2026-06-01'
       )
    LEFT JOIN tbaadm.tdt AS tdt
        ON tdt.acid = g.acid
       AND tdt.flow_code = 'PI'
       AND tdt.flow_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
    LEFT JOIN custom.dsaauth AS d2
        ON UPPER(ds.rm_id) = UPPER(d2.user_id)
    LEFT JOIN tbaadm.get AS g2
        ON d2.user_id = g2.emp_id
    LEFT JOIN tbaadm.sol AS sol
        ON g.sol_id = sol.sol_id
    LEFT JOIN tbaadm.gsp AS gsp
        ON gsp.schm_code = g.schm_code
    GROUP BY
        ds.rm_id, g2.emp_name, d2.operacc, g.foracid,
        tam.deposit_period_mths, tam.deposit_period_days,
        g.sol_id, sol.sol_desc, g.schm_code, gsp.schm_desc
),
reference_data AS (
    SELECT
        ed.referencenumber,
        da.user_id AS rm_id
    FROM crmuser.entitydocument AS ed
    JOIN tbaadm.gam AS g
        ON ed.orgkey = g.cif_id
    JOIN custom.dsaauth AS da
        ON g.foracid = da.operacc
    WHERE ed.doccode = 'PAN'
)
SELECT
    ad.rm_id,
    ad.rm_name,
    ad.operacc,
    ad.foracid,
    ad.deposit_period_mths,
    ad.deposit_period_days,
    ad.sol_id,
    ad.sol_desc,
    ad.scheme_code,
    ad.schm_desc,
    SUM(ad.total_tran_amt_dtt) AS total_tran_amt_dtt,
    SUM(ad.total_flow_amt_tdt) AS total_flow_amt_tdt,
    MAX(COALESCE(rd.referencenumber, 'N/A')) AS referencenumber
FROM account_data AS ad
LEFT JOIN reference_data AS rd
    ON UPPER(ad.rm_id) = UPPER(rd.rm_id)
WHERE ad.total_tran_amt_dtt > 0
GROUP BY
    ad.rm_id, ad.rm_name, ad.operacc, ad.foracid,
    ad.deposit_period_mths, ad.deposit_period_days,
    ad.sol_id, ad.sol_desc, ad.scheme_code, ad.schm_desc
ORDER BY
    ad.sol_id, ad.rm_id, ad.scheme_code, ad.deposit_period_mths
"""


def _safe_int(value):
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _safe_str(value):
    if value is None:
        return None
    return str(value).strip()


# def _create_commission_from_query_1(row):
#     doc = frappe.get_doc({
#         "doctype": "Commission",
#         "agent_code": _safe_str(row.get("rm_id")),
#         "agent_name": _safe_str(row.get("rm_name")),
#         "agent_operative_account": _safe_int(row.get("operacc")),
#         "customer_account_number": _safe_int(row.get("foracid")),
#         "demand": _safe_int(row.get("total_flow_amount")),
#         "collection": _safe_int(row.get("total_tran_amt")),
#         "pan_card": _safe_str(row.get("referencenumber")),
#         "scheme_code": _safe_int(row.get("scheme_code")),
#         "scheme_description": _safe_str(row.get("schm_desc")),
#         "sol_id": _safe_int(row.get("sol_id")),
#         "sol_description": _safe_str(row.get("sol_desc")),
#     })
#     doc.insert(ignore_permissions=True)
#     frappe.db.commit()
#     return doc.name


# def _create_commission_from_query_2(row):
#     doc = frappe.get_doc({
#         "doctype": "Commission",
#         "agent_code": _safe_str(row.get("rm_id")),
#         "agent_name": _safe_str(row.get("rm_name")),
#         "agent_operative_account": _safe_int(row.get("operacc")),
#         "customer_account_number": _safe_int(row.get("foracid")),
#         "tenure_months": _safe_int(row.get("deposit_period_mths")),
#         "tenure_days": _safe_int(row.get("deposit_period_days")),
#         "sol_id": _safe_int(row.get("sol_id")),
#         "sol_description": _safe_str(row.get("sol_desc")),
#         "scheme_code": _safe_int(row.get("scheme_code")),
#         "scheme_description": _safe_str(row.get("schm_desc")),
#         "collection": _safe_int(row.get("total_tran_amt_dtt")),
#         "demand": _safe_int(row.get("total_flow_amt_tdt")),
#         "pan_card": _safe_str(row.get("referencenumber")),
#     })
#     doc.insert(ignore_permissions=True)
#     frappe.db.commit()
#     return doc.name


def _create_commission_from_query_1(row):
    doc = frappe.get_doc({
        "doctype": "Commission",
        "agent_code": _safe_str(row.get("rm_id")),
        "agent_name": _safe_str(row.get("rm_name")),
        "agent_operative_account": _safe_str(row.get("operacc")),
        "customer_account_number": _safe_str(row.get("foracid")),
        "demand": _safe_int(row.get("total_flow_amount")),
        "collection": _safe_int(row.get("total_tran_amt")),
        "pan_card": _safe_str(row.get("referencenumber")),
        "scheme_code": _safe_str(row.get("scheme_code")),
        "scheme_description": _safe_str(row.get("schm_desc")),
        "sol_id": _safe_str(row.get("sol_id")),
        "sol_description": _safe_str(row.get("sol_desc")),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _create_commission_from_query_2(row):
    doc = frappe.get_doc({
        "doctype": "Commission",
        "agent_code": _safe_str(row.get("rm_id")),
        "agent_name": _safe_str(row.get("rm_name")),
        "agent_operative_account": _safe_str(row.get("operacc")),
        "customer_account_number": _safe_str(row.get("foracid")),
        "tenure_months": _safe_int(row.get("deposit_period_mths")),
        "tenure_days": _safe_int(row.get("deposit_period_days")),
        "sol_id": _safe_str(row.get("sol_id")),
        "sol_description": _safe_str(row.get("sol_desc")),
        "scheme_code": _safe_str(row.get("scheme_code")),
        "scheme_description": _safe_str(row.get("schm_desc")),
        "collection": _safe_int(row.get("total_tran_amt_dtt")),
        "demand": _safe_int(row.get("total_flow_amt_tdt")),
        "pan_card": _safe_str(row.get("referencenumber")),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _run_query(connection, query):
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query)
        return cursor.fetchall()


@frappe.whitelist()
def fetch_and_create_commission():
    """
    Run both external PostgreSQL queries one by one,
    create Commission documents row by row,
    and commit after each document.
    """
    frappe.only_for(("System Manager",))

    conn = None
    inserted_docs = []
    errors = []

    try:
        conn = db_connection()

        # query_1_rows = _run_query(conn, QUERY_1)
        # for row in query_1_rows:
        #     try:
        #         docname = _create_commission_from_query_1(row)
        #         inserted_docs.append(docname)
        #     except Exception:
        #         frappe.db.rollback()
        #         error_message = f"Query 1 row failed for foracid {row.get('foracid')}: {frappe.get_traceback()}"
        #         frappe.log_error(
        #             error_message, "Commission Import Query 1 Row Error")
        #         errors.append(error_message)

        query_2_rows = _run_query(conn, QUERY_2)
        for row in query_2_rows:
            try:
                docname = _create_commission_from_query_2(row)
                inserted_docs.append(docname)
            except Exception:
                frappe.db.rollback()
                error_message = f"Query 2 row failed for foracid {row.get('foracid')}: {frappe.get_traceback()}"
                frappe.log_error(
                    error_message, "Commission Import Query 2 Row Error")
                errors.append(error_message)

        query_1_rows = _run_query(conn, QUERY_1)
        for row in query_1_rows:
            try:
                docname = _create_commission_from_query_1(row)
                inserted_docs.append(docname)
            except Exception:
                frappe.db.rollback()
                error_message = f"Query 1 row failed for foracid {row.get('foracid')}: {frappe.get_traceback()}"
                frappe.log_error(
                    error_message, "Commission Import Query 1 Row Error")
                errors.append(error_message)

        return {
            "status": "completed",
            "query_1_count": len(query_1_rows),
            "query_2_count": len(query_2_rows),
            "inserted_count": len(inserted_docs),
            "inserted_docs": inserted_docs,
            "error_count": len(errors),
            "errors": errors,
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Commission Import Failed")
        raise
    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def run_fetch_and_create_commission_with_progress(limit=None):
    """
    Run both queries and create Commission documents with terminal progress bar.
    Queries remain unchanged.
    Each record is inserted and committed one by one.
    """
    frappe.only_for(("System Manager",))

    conn = None
    inserted_docs = []
    errors = []

    try:
        if limit is not None and str(limit).strip():
            limit = int(limit)
            if limit <= 0:
                frappe.throw(_("Limit must be greater than 0"))
        else:
            limit = None

        conn = db_connection()

        query_1_rows = _run_query(conn, QUERY_1)
        query_2_rows = _run_query(conn, QUERY_2)

        total_available = len(query_1_rows) + len(query_2_rows)
        total_to_process = min(
            limit, total_available) if limit else total_available

        created_count = 0
        query_1_created = 0
        query_2_created = 0

        progress = tqdm(total=total_to_process,
                        desc="Creating Commission Docs", unit="doc")

        try:
            for row in query_1_rows:
                if limit and created_count >= limit:
                    break

                try:
                    docname = _create_commission_from_query_1(row)
                    inserted_docs.append(docname)
                    created_count += 1
                    query_1_created += 1
                    progress.update(1)
                except Exception:
                    frappe.db.rollback()
                    error_message = f"Query 1 row failed for foracid {row.get('foracid')}: {frappe.get_traceback()}"
                    frappe.log_error(
                        error_message, "Commission Import Query 1 Row Error")
                    errors.append(error_message)

            for row in query_2_rows:
                if limit and created_count >= limit:
                    break

                try:
                    docname = _create_commission_from_query_2(row)
                    inserted_docs.append(docname)
                    created_count += 1
                    query_2_created += 1
                    progress.update(1)
                except Exception:
                    frappe.db.rollback()
                    error_message = f"Query 2 row failed for foracid {row.get('foracid')}: {frappe.get_traceback()}"
                    frappe.log_error(
                        error_message, "Commission Import Query 2 Row Error")
                    errors.append(error_message)
        finally:
            progress.close()

        print("\nCommission Fetch Completed")
        print(f"Query 1 Rows Fetched: {len(query_1_rows)}")
        print(f"Query 2 Rows Fetched: {len(query_2_rows)}")
        print(f"Query 1 Docs Created: {query_1_created}")
        print(f"Query 2 Docs Created: {query_2_created}")
        print(f"Total Docs Created: {len(inserted_docs)}")
        print(f"Total Errors: {len(errors)}")

        return {
            "status": "completed",
            "limit": limit,
            "query_1_count": len(query_1_rows),
            "query_2_count": len(query_2_rows),
            "query_1_created": query_1_created,
            "query_2_created": query_2_created,
            "inserted_count": len(inserted_docs),
            "inserted_docs": inserted_docs,
            "error_count": len(errors),
            "errors": errors,
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Commission Import Failed")
        raise
    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def debug_fetch_commission_data():
    frappe.only_for(("System Manager",))

    conn = None
    try:
        conn = db_connection()

        query_1_rows = _run_query(conn, QUERY_1)
        query_2_rows = _run_query(conn, QUERY_2)

        print("\n===== COMMISSION DEBUG FETCH =====")
        print(f"QUERY 1 ROW COUNT: {len(query_1_rows)}")
        print(f"QUERY 2 ROW COUNT: {len(query_2_rows)}")

        if query_1_rows:
            print("QUERY 1 FIRST ROW:")
            print(query_1_rows[0])
        else:
            print("QUERY 1 returned no rows")

        if query_2_rows:
            print("QUERY 2 FIRST ROW:")
            print(query_2_rows[0])
        else:
            print("QUERY 2 returned no rows")

        return {
            "query_1_count": len(query_1_rows),
            "query_2_count": len(query_2_rows),
            "query_1_first_row": query_1_rows[0] if query_1_rows else None,
            "query_2_first_row": query_2_rows[0] if query_2_rows else None,
        }

    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         "Commission Debug Fetch Failed")
        raise
    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def debug_create_one_commission():
    frappe.only_for(("System Manager",))

    conn = None
    try:
        conn = db_connection()
        query_1_rows = _run_query(conn, QUERY_1)

        if not query_1_rows:
            return {"status": "no_data"}

        row = query_1_rows[0]
        docname = _create_commission_from_query_1(row)

        return {
            "status": "success",
            "docname": docname,
            "sample_row": row
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         "Commission Debug Create One Failed")
        raise
    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def calculate_commission_amount(docname):
    if not docname:
        frappe.throw(_("Commission document name is required"))

    commission_doc = frappe.get_doc("Commission", docname)

    if not commission_doc.scheme_code:
        frappe.throw(_("Scheme Code is required in Commission document"))

    if commission_doc.collection in (None, ""):
        frappe.throw(_("Collection value is required in Commission document"))

    product_name = str(commission_doc.scheme_code).strip()

    if not frappe.db.exists("Product", product_name):
        frappe.throw(
            _("No Product record found with ID / Name: {0}").format(product_name))

    commission_rate = frappe.db.get_value(
        "Product", product_name, "commission_rate")

    if commission_rate in (None, ""):
        frappe.throw(
            _("Commission Rate is empty in Product: {0}").format(product_name))

    collection_amount = flt(commission_doc.collection)
    commission_rate = flt(commission_rate)

    commission_amount = (collection_amount * commission_rate) / 100

    commission_doc.commission_amount = commission_amount
    commission_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "docname": commission_doc.name,
        "scheme_code": commission_doc.scheme_code,
        "product_name": product_name,
        "collection": collection_amount,
        "commission_rate": commission_rate,
        "commission_amount": commission_amount,
    }
