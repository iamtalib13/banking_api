# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

from tqdm import tqdm

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, getdate

import psycopg2
from psycopg2.extras import RealDictCursor

from decimal import (
    Decimal,
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_UP,
    ROUND_UP,
)


class Commission(Document):
    pass


def db_connection():
    """Connect to external PostgreSQL using Finacle DB Credentials."""
    try:
        creds = frappe.get_single("Finacle DB Credentials")

        port = int(creds.db_port) if creds.db_port else 5432

        return psycopg2.connect(
            host=creds.db_host,
            port=port,
            user=creds.db_user,
            password=creds.get_password("db_password"),
            database=creds.db_name,
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "PostgreSQL Connection Failed",
        )
        frappe.throw(_("Database Connection Error"))


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
        gsp.schm_desc,
        tam.deposit_period_days,
        tam.deposit_period_mths,
        tam.deposit_amount,
        /* ADDED - ACCOUNT NAME FROM GAM */
        g.acct_name
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
        AND g.schm_code IN ('2004','2005','2006','2010','2011','2012','2013','2014','2015')
    LEFT JOIN tbaadm.tam tam
        ON tam.acid = g.acid
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
        AND g.schm_code IN ('2004','2005','2006','2010','2011','2012','2013','2014','2015')
    INNER JOIN tbaadm.tdt tdt
        ON tdt.acid = g.acid
        AND tdt.flow_code = 'NI'
    WHERE
        tdt.flow_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
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
        AND g.schm_code IN ('2004','2005','2006','2010','2011','2012','2013','2014','2015')
    INNER JOIN tbaadm.dtt dtt
        ON dtt.acid = g.acid
        AND dtt.flow_code = 'NI'
    WHERE
        (
            (dtt.tran_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
             AND dtt.value_date > DATE '2026-07-31')
            OR
            (dtt.tran_date > DATE '2026-08-25'
             AND dtt.value_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31')
            OR
            (dtt.value_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
             AND dtt.tran_date > DATE '2026-08-31')
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
    ad.acct_opn_date,
    ad.cif_id_opening_date,
    ad.foracid,
    /* ADDED - ACCOUNT NAME */
    ad.acct_name,
    ad.deposit_amount,
    COALESCE(fd.total_flow_amount,0) AS total_flow_amount,
    /* CHANGED - SCHEME 2004 KA FLOW AMT SAME RAHEGA
       SCHEME 2005-2015 KA * 3 HOGA */
    CASE
        WHEN ad.scheme_code = '2004'
            THEN COALESCE(fd.total_flow_amount,0)
        WHEN ad.scheme_code IN ('2005','2006','2010','2011','2012','2013','2014','2015')
            THEN COALESCE(fd.total_flow_amount,0) * 3
        ELSE COALESCE(fd.total_flow_amount,0)
    END AS adjusted_flow_amount,
    COALESCE(td.total_tran_amt,0) AS total_tran_amt,
    LEAST(
        COALESCE(fd.total_flow_amount,0),
        COALESCE(td.total_tran_amt,0)
    ) AS commission_amount,
    CASE
        WHEN ad.acct_opn_date + INTERVAL '1 year' >= DATE '2026-08-31' THEN 'YES'
        ELSE 'NO'
    END AS one_year_completed,
    ad.deposit_period_days,
    ad.deposit_period_mths,
    COALESCE(rd.referencenumber,'N/A') AS referencenumber,
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
WHERE
    COALESCE(td.total_tran_amt,0) > 0
    -- ADDED: SIRF RDDSA AUR DDDSA PREFIX WALE RM_ID
AND (
    UPPER(ad.rm_id) LIKE 'RDDSA%'
    OR UPPER(ad.rm_id) LIKE 'DDDSA%'
)
ORDER BY
    ad.foracid,
    ad.rm_id,
    ad.scheme_code;
 
"""
QUERY_2 = """
--COMMITION QUERY 2 -- COUNT 6,563
 
WITH account_data AS (
SELECT
ds.rm_id,
g2.emp_name AS rm_name,
d2.operacc,
g.foracid,
g.acct_name,                    /* ADDED - ACCOUNT NAME FROM GAM */
g.acct_opn_date,
tam.deposit_amount,
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
AND g.acct_opn_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
AND g.acct_cls_flg = 'N'
LEFT JOIN tbaadm.tam AS tam
ON tam.acid = g.acid
LEFT JOIN tbaadm.dtt AS dtt
ON dtt.acid = g.acid
AND dtt.flow_code = 'PI'
AND dtt.tran_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
AND NOT (
dtt.value_date >= DATE '2026-07-01'
AND dtt.value_date < DATE '2026-08-01'
)
LEFT JOIN tbaadm.tdt AS tdt
ON tdt.acid = g.acid
AND tdt.flow_code = 'PI'
AND tdt.flow_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
LEFT JOIN custom.dsaauth AS d2
ON UPPER(ds.rm_id) = UPPER(d2.user_id)
LEFT JOIN tbaadm.get AS g2
ON d2.user_id = g2.emp_id
LEFT JOIN tbaadm.sol AS sol
ON g.sol_id = sol.sol_id
LEFT JOIN tbaadm.gsp AS gsp
ON gsp.schm_code = g.schm_code
GROUP BY
ds.rm_id,
g2.emp_name,
d2.operacc,
g.foracid,
g.acct_name,                    /* ADDED */
g.acct_opn_date,
tam.deposit_amount,
tam.deposit_period_mths,
tam.deposit_period_days,
g.sol_id,
sol.sol_desc,
g.schm_code,
gsp.schm_desc
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
ad.acct_name,                   /* ADDED - ACCOUNT NAME */
ad.acct_opn_date,
ad.deposit_amount,
ad.deposit_period_mths,
ad.deposit_period_days,
ad.sol_id,
ad.sol_desc,
ad.scheme_code,
ad.schm_desc,
SUM(ad.total_tran_amt_dtt)      AS total_tran_amt_dtt,
SUM(ad.total_flow_amt_tdt)      AS total_flow_amt_tdt,
SUM(ad.total_flow_amt_tdt)      AS adjusted_flow_amount,
LEAST(
COALESCE(SUM(ad.total_tran_amt_dtt),0),
COALESCE(SUM(ad.total_flow_amt_tdt),0)
) AS commission_amount,
CASE
WHEN ad.acct_opn_date + INTERVAL '1 year' <= DATE '2026-08-31' THEN 'YES'
ELSE 'NO'
END AS one_year_completed,
MAX(COALESCE(rd.referencenumber,'N/A')) AS referencenumber
FROM account_data AS ad
LEFT JOIN reference_data AS rd
ON UPPER(ad.rm_id) = UPPER(rd.rm_id)
WHERE ad.total_tran_amt_dtt > 0
-- ADDED: SIRF RDDSA AUR DDDSA PREFIX WALE RM_ID
AND (
    UPPER(ad.rm_id) LIKE 'RDDSA%'
    OR UPPER(ad.rm_id) LIKE 'DDDSA%'
)
GROUP BY
ad.rm_id,
ad.rm_name,
ad.operacc,
ad.foracid,
ad.acct_name,                   /* ADDED */
ad.acct_opn_date,
ad.deposit_amount,
ad.deposit_period_mths,
ad.deposit_period_days,
ad.sol_id,
ad.sol_desc,
ad.scheme_code,
ad.schm_desc
ORDER BY
ad.sol_id,
ad.rm_id,
ad.scheme_code,
ad.deposit_period_mths;


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


def _get_agent_details(agent_code):
    """
    Fetch agent-related fields from Agent DocType.

    Matching rule:
        Commission.agent_code == Agent.name

    Missing Agent or missing field values become "0".
    """
    default_details = {
        "cif": "0",
        "agent_operative_account": "0",
        "agent_saving_account": "0",
        "pan_status": "0",
        "agent_security_account": "0",
    }

    if not agent_code:
        return default_details

    agent_code = str(agent_code).strip()

    if not agent_code:
        return default_details

    agent_details = frappe.db.get_value(
        "Agent",
        agent_code,
        [
            "cif",
            "agent_operative_account",
            "agent_saving_account",
            "pan_status",
            "agent_security_account",
        ],
        as_dict=True,
    )

    if not agent_details:
        return default_details

    return {
        "cif": _safe_str(agent_details.get("cif")) or "0",
        "agent_operative_account": (
            _safe_str(
                agent_details.get("agent_operative_account")
            )
            or "0"
        ),
        "agent_saving_account": (
            _safe_str(
                agent_details.get("agent_saving_account")
            )
            or "0"
        ),
        "pan_status": (
            _safe_str(
                agent_details.get("pan_status")
            )
            or "0"
        ),
        "agent_security_account": (
            _safe_str(
                agent_details.get("agent_security_account")
            )
            or "0"
        ),
    }


# def _create_commission_from_query_1(row):
#     doc = frappe.get_doc({
#         "doctype": "Commission",

#         "agent_code": _safe_str(row.get("rm_id")),
#         "agent_name": _safe_str(row.get("rm_name")),
#         # "agent_operative_account": _safe_str(row.get("operacc")),
#         "customer_account_number": _safe_str(row.get("foracid")),
#         "customer_account_name": _safe_str(row.get("acct_name")),
#         "deposit_amount": _safe_int(row.get("deposit_amount")),

#         "tenure_months": _safe_int(row.get("deposit_period_mths")),
#         "tenure_days": _safe_int(row.get("deposit_period_days")),

#         # "demand": _safe_int(row.get("total_flow_amount")),
#         "demand": _safe_int(row.get("adjusted_flow_amount")),
#         "collection": _safe_int(row.get("total_tran_amt")),

#         # New fields
#         "eligible_amount": _safe_int(row.get("commission_amount")),
#         "account_opening_date": row.get("acct_opn_date"),
#         "remarks": _safe_str(row.get("one_year_completed")),

#         "pan_card": _safe_str(row.get("referencenumber")),
#         "scheme_code": _safe_str(row.get("scheme_code")),
#         "scheme_description": _safe_str(row.get("schm_desc")),
#         "sol_id": _safe_str(row.get("sol_id")),
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
#         # "agent_operative_account": _safe_str(row.get("operacc")),
#         "customer_account_number": _safe_str(row.get("foracid")),
#         "customer_account_name": _safe_str(row.get("acct_name")),
#         "deposit_amount": _safe_int(row.get("deposit_amount")),

#         "tenure_months": _safe_int(row.get("deposit_period_mths")),
#         "tenure_days": _safe_int(row.get("deposit_period_days")),

#         # "demand": _safe_int(row.get("total_flow_amt_tdt")),
#         "demand": _safe_int(row.get("adjusted_flow_amount")),
#         "collection": _safe_int(row.get("total_tran_amt_dtt")),

#         # New fields
#         "eligible_amount": _safe_int(row.get("commission_amount")),
#         "account_opening_date": row.get("acct_opn_date"),
#         "remarks": _safe_str(row.get("one_year_completed")),

#         "pan_card": _safe_str(row.get("referencenumber")),
#         "scheme_code": _safe_str(row.get("scheme_code")),
#         "scheme_description": _safe_str(row.get("schm_desc")),
#         "sol_id": _safe_str(row.get("sol_id")),
#         "sol_description": _safe_str(row.get("sol_desc")),
#     })

#     doc.insert(ignore_permissions=True)
#     frappe.db.commit()

#     return doc.name

def _create_commission_from_query_1(row):
    agent_code = _safe_str(row.get("rm_id")) or "0"
    agent_details = _get_agent_details(agent_code)

    doc = frappe.get_doc({
        "doctype": "Commission",

        "agent_code": agent_code,
        "agent_name": _safe_str(row.get("rm_name")) or "0",

        # Values come from Agent DocType, not QUERY_1.
        "cif": agent_details["cif"],
        "agent_operative_account": (
            agent_details["agent_operative_account"]
        ),
        "agent_saving_account": (
            agent_details["agent_saving_account"]
        ),
        "pan_status": agent_details["pan_status"],
        "agent_security_account": (
            agent_details["agent_security_account"]
        ),

        "customer_account_number": (
            _safe_str(row.get("foracid")) or "0"
        ),
        "customer_account_name": (
            _safe_str(row.get("acct_name")) or "0"
        ),
        "deposit_amount": _safe_int(
            row.get("deposit_amount")
        ),

        "tenure_months": _safe_int(
            row.get("deposit_period_mths")
        ),
        "tenure_days": _safe_int(
            row.get("deposit_period_days")
        ),

        "demand": _safe_int(
            row.get("adjusted_flow_amount")
        ),
        "collection": _safe_int(
            row.get("total_tran_amt")
        ),

        "eligible_amount": _safe_int(
            row.get("commission_amount")
        ),
        "account_opening_date": row.get(
            "acct_opn_date"
        ),
        "remarks": (
            _safe_str(row.get("one_year_completed"))
            or "0"
        ),

        "pan_card": (
            _safe_str(row.get("referencenumber"))
            or "0"
        ),
        "scheme_code": (
            _safe_str(row.get("scheme_code"))
            or "0"
        ),
        "scheme_description": (
            _safe_str(row.get("schm_desc"))
            or "0"
        ),
        "sol_id": (
            _safe_str(row.get("sol_id"))
            or "0"
        ),
        "sol_description": (
            _safe_str(row.get("sol_desc"))
            or "0"
        ),
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def _create_commission_from_query_2(row):
    agent_code = _safe_str(row.get("rm_id")) or "0"
    agent_details = _get_agent_details(agent_code)

    doc = frappe.get_doc({
        "doctype": "Commission",

        "agent_code": agent_code,
        "agent_name": _safe_str(row.get("rm_name")) or "0",

        # Values come from Agent DocType, not QUERY_2.
        "cif": agent_details["cif"],
        "agent_operative_account": (
            agent_details["agent_operative_account"]
        ),
        "agent_saving_account": (
            agent_details["agent_saving_account"]
        ),
        "pan_status": agent_details["pan_status"],
        "agent_security_account": (
            agent_details["agent_security_account"]
        ),

        "customer_account_number": (
            _safe_str(row.get("foracid")) or "0"
        ),
        "customer_account_name": (
            _safe_str(row.get("acct_name")) or "0"
        ),
        "deposit_amount": _safe_int(
            row.get("deposit_amount")
        ),

        "tenure_months": _safe_int(
            row.get("deposit_period_mths")
        ),
        "tenure_days": _safe_int(
            row.get("deposit_period_days")
        ),

        "demand": _safe_int(
            row.get("adjusted_flow_amount")
        ),
        "collection": _safe_int(
            row.get("total_tran_amt_dtt")
        ),

        "eligible_amount": _safe_int(
            row.get("commission_amount")
        ),
        "account_opening_date": row.get(
            "acct_opn_date"
        ),
        "remarks": (
            _safe_str(row.get("one_year_completed"))
            or "0"
        ),

        "pan_card": (
            _safe_str(row.get("referencenumber"))
            or "0"
        ),
        "scheme_code": (
            _safe_str(row.get("scheme_code"))
            or "0"
        ),
        "scheme_description": (
            _safe_str(row.get("schm_desc"))
            or "0"
        ),
        "sol_id": (
            _safe_str(row.get("sol_id"))
            or "0"
        ),
        "sol_description": (
            _safe_str(row.get("sol_desc"))
            or "0"
        ),
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
    Execute Query 2 first, then Query 1.
    Each document is inserted and committed individually.
    """
    frappe.only_for(("System Manager",))

    conn = None
    inserted_docs = []
    errors = []
    query_1_rows = []
    query_2_rows = []

    try:
        conn = db_connection()

        # Query 2 first, preserving current logic
        query_2_rows = _run_query(conn, QUERY_2)

        for row in query_2_rows:
            try:
                docname = _create_commission_from_query_2(row)
                inserted_docs.append(docname)

            except Exception:
                frappe.db.rollback()

                error_message = (
                    f"Query 2 row failed for foracid "
                    f"{row.get('foracid')}: {frappe.get_traceback()}"
                )

                frappe.log_error(
                    error_message,
                    "Commission Import Query 2 Row Error",
                )

                errors.append(error_message)

        # Query 1 second, preserving current logic
        query_1_rows = _run_query(conn, QUERY_1)

        for row in query_1_rows:
            try:
                docname = _create_commission_from_query_1(row)
                inserted_docs.append(docname)

            except Exception:
                frappe.db.rollback()

                error_message = (
                    f"Query 1 row failed for foracid "
                    f"{row.get('foracid')}: {frappe.get_traceback()}"
                )

                frappe.log_error(
                    error_message,
                    "Commission Import Query 1 Row Error",
                )

                errors.append(error_message)

        return {
            "status": "completed",
            "query_1_fetched": len(query_1_rows),
            "query_2_fetched": len(query_2_rows),
            "query_1_created": sum(
                1 for name in inserted_docs
                if name
            ),
            "query_2_created": len(inserted_docs),
            "inserted_count": len(inserted_docs),
            "error_count": len(errors),
            "errors": errors,
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Import Failed",
        )
        raise

    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def run_fetch_and_create_commission_with_progress(limit=None):
    """
    Execute Query 1 and Query 2 with terminal progress.
    Each document is inserted and committed individually.
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
        total_to_process = (
            min(limit, total_available)
            if limit
            else total_available
        )

        created_count = 0
        query_1_created = 0
        query_2_created = 0

        progress = tqdm(
            total=total_to_process,
            desc="Creating Commission Docs",
            unit="doc",
        )

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

                    error_message = (
                        f"Query 1 row failed for foracid "
                        f"{row.get('foracid')}: {frappe.get_traceback()}"
                    )

                    frappe.log_error(
                        error_message,
                        "Commission Import Query 1 Row Error",
                    )

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

                    error_message = (
                        f"Query 2 row failed for foracid "
                        f"{row.get('foracid')}: {frappe.get_traceback()}"
                    )

                    frappe.log_error(
                        error_message,
                        "Commission Import Query 2 Row Error",
                    )

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
            "query_1_fetched": len(query_1_rows),
            "query_2_fetched": len(query_2_rows),
            "query_1_created": query_1_created,
            "query_2_created": query_2_created,
            "inserted_count": len(inserted_docs),
            "error_count": len(errors),
            "errors": errors,
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Import Failed",
        )
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
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Debug Fetch Failed",
        )
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
            "sample_row": row,
        }

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Debug Create One Failed",
        )
        raise

    finally:
        if conn:
            conn.close()


def _get_deferred_product(product_name):
    """
    Load Product including its deferred child table.
    frappe.db.get_value does not provide the child rows,
    so Deferred needs the full Product document.
    """
    product_doc = frappe.get_doc("Product", product_name)

    if product_doc.commission_type != "Deferred":
        frappe.throw(
            _("Product {0} is not configured for Deferred commission").format(
                product_name
            )
        )

    if not product_doc.deferred_commission_schedule:
        frappe.throw(
            _("Deferred Commission Schedule is missing in Product: {0}").format(
                product_name
            )
        )

    return product_doc


def _get_valid_deferred_schedule_rows(product_doc):
    """
    Read, validate, and sort enabled Product deferred schedule rows.
    """
    schedule_rows = []
    used_years = set()

    for row in product_doc.deferred_commission_schedule:
        if not row.enabled:
            continue

        year_no = cint(row.year_no)
        rate = flt(row.commission_rate)

        if year_no <= 0:
            frappe.throw(
                _("Deferred Year No must be greater than 0 in Product: {0}").format(
                    product_doc.name
                )
            )

        if year_no in used_years:
            frappe.throw(
                _("Duplicate Deferred Year No {0} in Product: {1}").format(
                    year_no,
                    product_doc.name
                )
            )

        if rate < 0:
            frappe.throw(
                _("Deferred commission rate cannot be negative for Year {0}").format(
                    year_no
                )
            )

        used_years.add(year_no)

        schedule_rows.append({
            "year_no": year_no,
            "rate": rate,
            "remarks": _safe_str(row.remarks),
        })

    if not schedule_rows:
        frappe.throw(
            _("No enabled deferred commission rows found in Product: {0}").format(
                product_doc.name
            )
        )

    return sorted(schedule_rows, key=lambda item: item["year_no"])


def _create_deferred_commission_schedule(commission_doc, product_doc, eligible_amount):
    """
    Create deferred payout schedule rows in the current Commission document.

    Example:
    Commission document created on 2026-08-19:
    Year 1 due: 2026-09-01
    Year 2 due: 2027-09-01
    Year 3 due: 2028-09-01
    """
    commission_meta = frappe.get_meta("Commission")

    if not commission_meta.has_field("deferred_commission_details"):
        frappe.throw(
            _("Commission child table field 'deferred_commission_details' is missing")
        )

    if commission_doc.deferred_commission_details:
        frappe.throw(
            _("Deferred schedule already exists for Commission record: {0}").format(
                commission_doc.name
            )
        )

    schedule_rows = _get_valid_deferred_schedule_rows(product_doc)

    source_date = getdate(commission_doc.creation)

    # First day of the next calendar month.
    first_due_date = add_to_date(
        source_date.replace(day=1),
        months=1,
        as_string=True,
    )

    total_commission = 0
    total_rate = 0

    for schedule in schedule_rows:
        year_no = schedule["year_no"]
        rate = schedule["rate"]

        # gross_commission = (eligible_amount * rate) / 100
        # tds = gross_commission * 0.02
        # security_deposit = gross_commission * 0.10
        # netpay = gross_commission - (tds + security_deposit)

        gross_commission = (
            eligible_amount * rate
        ) / 100

        financial_values = (
            _calculate_commission_financial_values(
                commission_amount=gross_commission,
                eligible_amount=eligible_amount,
                pan_status=commission_doc.pan_status,
            )
        )

        gross_commission = flt(
            financial_values["commission_amount"]
        )

        tds = flt(
            financial_values["tds"]
        )

        security_deposit = flt(
            financial_values["security_deposit"]
        )

        netpay = flt(
            financial_values["netpay"]
        )

        due_date = add_to_date(
            first_due_date,
            years=year_no - 1,
            as_string=True,
        )

        commission_doc.append(
            "deferred_commission_details",
            {
                "year_no": year_no,
                "commission_rate": rate,
                "eligible_amount": eligible_amount,
                "gross_commission": gross_commission,
                "due_date": due_date,
                "status": "Pending",
                "tds": tds,
                "security_deposit": security_deposit,
                "netpay": netpay,
                "remarks": schedule["remarks"],
            },
        )

        total_commission += gross_commission
        total_rate += rate

    return {
        "total_commission": total_commission,
        "total_rate": total_rate,
        "first_due_date": first_due_date,
        "schedule_count": len(schedule_rows),
    }


# def _update_agent_deduction_and_final_net_pay(agent_code):
#     """
#     Update deduction and final_net_pay in all Commission records
#     belonging to the same agent.

#     Rule:
#     - agent_total_netpay = sum of all active Commission.netpay values
#     - if agent_total_netpay > 1000:
#         deduction = 150
#         final_net_pay = agent_total_netpay - 150
#     - otherwise:
#         deduction = 0
#         final_net_pay = agent_total_netpay
#     """

#     if not agent_code:
#         return {
#             "agent_code": None,
#             "agent_total_netpay": 0,
#             "deduction": 0,
#             "final_net_pay": 0,
#         }

#     agent_code = str(agent_code).strip()

#     result = frappe.db.sql(
#         """
#         SELECT
#             COALESCE(
#                 SUM(
#                     CAST(NULLIF(TRIM(netpay), '') AS DECIMAL(18, 2))
#                 ),
#                 0
#             ) AS agent_total_netpay
#         FROM `tabCommission`
#         WHERE agent_code = %s
#         AND docstatus < 2
#         """,
#         (agent_code,),
#         as_dict=True,
#     )

#     agent_total_netpay = (
#         flt(result[0].agent_total_netpay)
#         if result and result[0].agent_total_netpay is not None
#         else 0
#     )

#     deduction = 150 if agent_total_netpay > 1000 else 0
#     final_net_pay = agent_total_netpay - deduction

#     frappe.db.sql(
#         """
#         UPDATE `tabCommission`
#         SET
#             deduction = %s,
#             final_net_pay = %s
#         WHERE agent_code = %s
#         AND docstatus < 2
#         """,
#         (
#             deduction,
#             final_net_pay,
#             agent_code,
#         ),
#     )

#     return {
#         "agent_code": agent_code,
#         "agent_total_netpay": agent_total_netpay,
#         "deduction": deduction,
#         "final_net_pay": final_net_pay,
#     }


def _calculate_agent_deduction(
    agent_total_netpay,
    calculation_settings,
):
    """
    Calculate agent deduction from Commission Settings.

    Supported types:
        Amount Above Limit
        Percentage Above Limit
        Fixed Amount
        Percentage Of Total
    """
    if not calculation_settings[
        "enable_agent_deduction"
    ]:
        return Decimal("0"), _decimal_amount(
            agent_total_netpay
        )

    total_netpay = _decimal_amount(
        agent_total_netpay
    )

    deduction_type = calculation_settings[
        "agent_deduction_type"
    ]

    deduction_limit = _decimal_amount(
        calculation_settings[
            "agent_deduction_limit"
        ]
    )

    deduction_amount = _decimal_amount(
        calculation_settings[
            "agent_deduction_amount"
        ]
    )

    deduction_percentage = _decimal_amount(
        calculation_settings[
            "agent_deduction_percentage"
        ]
    )

    if deduction_type == "Fixed Amount":
        deduction = deduction_amount

    elif deduction_type == "Percentage Of Total":
        deduction = (
            total_netpay
            * deduction_percentage
            / Decimal("100")
        )

    elif deduction_type == "Percentage Above Limit":
        excess = max(
            total_netpay - deduction_limit,
            Decimal("0"),
        )

        deduction = (
            excess
            * deduction_percentage
            / Decimal("100")
        )

    else:
        # Amount Above Limit
        deduction = (
            deduction_amount
            if total_netpay > deduction_limit
            else Decimal("0")
        )

    maximum_deduction = calculation_settings[
        "agent_deduction_maximum"
    ]

    if maximum_deduction is not None:
        deduction = min(
            deduction,
            _decimal_amount(maximum_deduction),
        )

    deduction = _round_calculation_amount(
        deduction,
        calculation_settings,
    )

    if calculation_settings[
        "agent_deduction_operation"
    ] == "Add":
        final_netpay = (
            total_netpay + deduction
        )
    else:
        final_netpay = (
            total_netpay - deduction
        )

    final_netpay = _round_calculation_amount(
        final_netpay,
        calculation_settings,
    )

    return deduction, final_netpay


def _update_agent_deduction_and_final_net_pay(
    agent_code,
):
    """
    Update deduction and final_net_pay on all active Commission
    documents belonging to the same agent.

    The calculation remains agent-level and is not changed.
    Only the hardcoded calculation values are now read from
    Commission Settings.
    """
    if not agent_code:
        return {
            "agent_code": None,
            "agent_total_netpay": 0,
            "deduction": 0,
            "final_net_pay": 0,
        }

    agent_code = str(agent_code).strip()

    result = frappe.db.sql(
        """
        SELECT
            COALESCE(
                SUM(
                    CAST(
                        NULLIF(TRIM(netpay), '')
                        AS DECIMAL(18, 2)
                    )
                ),
                0
            ) AS agent_total_netpay
        FROM `tabCommission`
        WHERE agent_code = %s
        AND docstatus < 2
        """,
        (agent_code,),
        as_dict=True,
    )

    agent_total_netpay = (
        flt(result[0].agent_total_netpay)
        if result
        and result[0].agent_total_netpay is not None
        else 0
    )

    calculation_settings = (
        _get_commission_calculation_settings()
    )

    deduction, final_net_pay = (
        _calculate_agent_deduction(
            agent_total_netpay=agent_total_netpay,
            calculation_settings=calculation_settings,
        )
    )

    frappe.db.sql(
        """
        UPDATE `tabCommission`
        SET
            deduction = %s,
            final_net_pay = %s
        WHERE agent_code = %s
        AND docstatus < 2
        """,
        (
            flt(deduction),
            flt(final_net_pay),
            agent_code,
        ),
    )

    return {
        "agent_code": agent_code,
        "agent_total_netpay": agent_total_netpay,
        "deduction": flt(deduction),
        "final_net_pay": flt(final_net_pay),
    }


def _get_product_commission_type(scheme_code):
    """
    Return Commission Type configured in Product.

    Product name equals Product.product_code because Product uses:
    autoname = field:product_code
    """
    if not scheme_code:
        frappe.throw(_("Scheme Code is required to create Commission Payment"))

    product_name = str(scheme_code).strip()

    commission_type = frappe.db.get_value(
        "Product",
        product_name,
        "commission_type",
    )

    if not commission_type:
        frappe.throw(
            _("Commission Type is not configured in Product: {0}").format(
                product_name
            )
        )

    return commission_type


def _commission_payment_exists(commission_name, payment_type, payment_year):
    """
    Check whether a Commission Payment already exists.

    Duplicate key:
    Commission + Payment Type + Payment Year.
    """
    return frappe.db.exists(
        "Commission Payment",
        {
            "commission": commission_name,
            "payment_type": payment_type,
            "payment_year": payment_year,
            "docstatus": ("<", 2),
        },
    )


def _create_commission_payment_if_missing(payment_data):
    """
    Insert a Commission Payment only if the same schedule/payment
    record does not already exist.
    """
    existing_payment = _commission_payment_exists(
        payment_data.get("commission"),
        payment_data.get("payment_type"),
        payment_data.get("payment_year"),
    )

    if existing_payment:
        return {
            "created": False,
            "name": existing_payment,
        }

    payment_doc = frappe.get_doc({
        "doctype": "Commission Payment",
        **payment_data,
    })

    payment_doc.insert(ignore_permissions=True)

    return {
        "created": True,
        "name": payment_doc.name,
    }


def create_commission_payment_records(commission_doc):
    """
    Create payment records after Commission calculation.

    Normal type:
    - One consolidated payment record for the agent.

    Deferred type:
    - One payment record per yearly deferred schedule row.
    """
    commission_type = frappe.db.get_value(
        "Product",
        str(commission_doc.scheme_code).strip(),
        "commission_type",
    )

    if not commission_type:
        frappe.throw(
            _("Commission Type is missing for Scheme Code: {0}").format(
                commission_doc.scheme_code
            )
        )

    if commission_type == "Deferred":
        return {
            "commission_type": "Deferred",
            "deferred_result": _create_deferred_payment_records(
                commission_doc
            ),
        }

    return {
        "commission_type": commission_type,
        "normal_result": _create_normal_agent_payment_if_missing(
            commission_doc.agent_code
        ),
    }


def _get_deferred_product_codes():
    """
    Return Product document names configured with Deferred commission type.

    Product.name equals Product.product_code because Product uses:
    autoname = field:product_code
    """
    return frappe.get_all(
        "Product",
        filters={"commission_type": "Deferred"},
        pluck="name",
    )


def _create_normal_agent_payment_if_missing(agent_code, due_date=None):
    """
    Create one consolidated Commission Payment record for one agent.

    Includes only Commission records whose Product commission type
    is NOT Deferred.
    """
    if not agent_code:
        frappe.throw(_("Agent Code is required"))

    agent_code = str(agent_code).strip()
    due_date = due_date or frappe.utils.today()

    deferred_product_codes = _get_deferred_product_codes()

    deferred_condition = ""
    values = {"agent_code": agent_code}

    if deferred_product_codes:
        placeholders = ", ".join(
            [f"%(deferred_scheme_{i})s" for i in range(
                len(deferred_product_codes))]
        )

        deferred_condition = f"""
            AND c.scheme_code NOT IN ({placeholders})
        """

        for i, scheme_code in enumerate(deferred_product_codes):
            values[f"deferred_scheme_{i}"] = scheme_code

    # totals = frappe.db.sql(
    #     f"""
    #     SELECT
    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS gross_commission,

    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS tds_amount,

    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS security_deposit_amount,

    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.netpay), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS netpay_amount,

    #         MAX(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2))) AS deduction_amount,

    #         MAX(CAST(NULLIF(TRIM(c.final_net_pay), '') AS DECIMAL(18,2))) AS final_netpay

    #     FROM `tabCommission` c
    #     WHERE c.agent_code = %(agent_code)s
    #     AND c.docstatus < 2
    #     {deferred_condition}
    #     """,
    #     values,
    #     as_dict=True,
    # )
#################################################################################################
    # totals = frappe.db.sql(
    #     f"""
    # SELECT
    #     MAX(NULLIF(TRIM(c.agent_operative_account), '')) AS agent_operative_account,
    #     MAX(NULLIF(TRIM(c.agent_saving_account), '')) AS agent_saving_account,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS gross_commission,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS tds_amount,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS security_deposit_amount,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.netpay), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS netpay_amount,

    #     MAX(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2))) AS deduction_amount,

    #     MAX(CAST(NULLIF(TRIM(c.final_net_pay), '') AS DECIMAL(18,2))) AS finalnetpay

    # FROM `tabCommission` c
    # WHERE c.agent_code = %(agent_code)s
    # AND c.docstatus < 2
    # {deferred_condition}
    # """,
    #     values,
    #     as_dict=True,
    # )

    totals = frappe.db.sql(
        f"""
    SELECT
        MAX(NULLIF(TRIM(c.agent_operative_account), ''))
            AS agent_operative_account,

        MAX(NULLIF(TRIM(c.agent_saving_account), ''))
            AS agent_saving_account,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.commission_amount), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS gross_commission,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.tds), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS tds_amount,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.security_deposit), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS security_deposit_amount,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.netpay), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS netpay_amount,

        MAX(
            CAST(
                NULLIF(TRIM(c.deduction), '')
                AS DECIMAL(18,2)
            )
        ) AS deduction_amount,

        MAX(
            CAST(
                NULLIF(TRIM(c.final_net_pay), '')
                AS DECIMAL(18,2)
            )
        ) AS finalnetpay

    FROM `tabCommission` c
    WHERE c.agent_code = %(agent_code)s
    AND c.docstatus < 2
    {deferred_condition}
    """,
        values,
        as_dict=True,
    )
    totals = totals[0] if totals else {}
    # agent_operative_account = _safe_str(
    #     totals.get("agent_operative_account")
    # )
    # agent_saving_account = _safe_str(
    #     totals.get("agent_saving_account")
    # )

    agent_operative_account = (
        _safe_str(
            totals.get("agent_operative_account")
        )
        or "0"
    )

    agent_saving_account = (
        _safe_str(
            totals.get("agent_saving_account")
        )
        or "0"
    )

    if not agent_operative_account:
        frappe.throw(
            _("Agent Operative Account not found for Agent: {0}").format(
                agent_code
            )
        )
    if not agent_saving_account:
        frappe.throw(
            _("Agent Saving Account not found for Agent: {0}").format(
                agent_code
            )
        )

    gross_commission = flt(totals.get("gross_commission"))
    tds_amount = flt(totals.get("tds_amount"))
    security_deposit_amount = flt(totals.get("security_deposit_amount"))
    netpay_amount = flt(totals.get("netpay_amount"))
    deduction_amount = flt(totals.get("deduction_amount"))
    final_netpay = flt(totals.get("final_netpay"))

    if gross_commission <= 0 and netpay_amount <= 0:
        return {
            "created": False,
            "reason": "No normal Commission amount available for this agent",
            "name": None,
        }

    existing_payment = frappe.db.exists(
        "Commission Payment",
        {
            "agent_code": agent_code,
            "payment_type": "Normal",
            "due_date": due_date,
            "docstatus": ("<", 2),
        },
    )

    if existing_payment:
        payment_doc = frappe.get_doc("Commission Payment", existing_payment)

        # Do not alter a payment that is currently processing or already paid.
        if payment_doc.payment_status in ("Processing", "Paid"):
            return {
                "created": False,
                "updated": False,
                "name": payment_doc.name,
                "reason": "Payment is already Processing or Paid",
            }

        # payment_doc.agent_operative_account = agent_operative_account
        # payment_doc.agent_saving_account = agent_saving_account
        payment_doc.agent_operative_account = (
            agent_operative_account
        )

        payment_doc.agent_saving_account = (
            agent_saving_account
        )
        payment_doc.gross_commission = gross_commission
        payment_doc.tds_amount = tds_amount
        payment_doc.security_deposit_amount = security_deposit_amount
        payment_doc.netpay_amount = netpay_amount
        payment_doc.deduction_amount = deduction_amount
        payment_doc.final_netpay = final_netpay
        payment_doc.payment_status = "Pending"
        payment_doc.save(ignore_permissions=True)

        return {
            "created": False,
            "updated": True,
            "name": payment_doc.name,
        }

    payment_doc = frappe.get_doc({
        "doctype": "Commission Payment",
        "agent_code": agent_code,
        # "agent_operative_account": agent_operative_account,
        # "agent_saving_account": agent_saving_account,
        "agent_operative_account": (
            agent_operative_account
        ),

        "agent_saving_account": (
            agent_saving_account
        ),
        "payment_type": "Normal",
        "payment_year": 1,
        "due_date": due_date,
        "gross_commission": gross_commission,
        "tds_amount": tds_amount,
        "security_deposit_amount": security_deposit_amount,
        "netpay_amount": netpay_amount,
        "deduction_amount": deduction_amount,
        "final_netpay": final_netpay,
        "payment_status": "Pending",
    })

    payment_doc.insert(ignore_permissions=True)

    return {
        "created": True,
        "updated": False,
        "name": payment_doc.name,
    }


def _get_commission_calculation_settings():
    """
    Load all calculation settings from Commission Settings.

    Defaults preserve the original calculation:
        TDS = 2% of Commission Amount
        Security Deposit = 10% of Commission Amount
        Net Pay = Commission Amount - TDS - Security Deposit
        Agent deduction = 150 when total net pay > 1000
        No rounding
    """
    settings = frappe.get_single(
        "Commission Settings"
    )

    decimal_places = cint(
        getattr(
            settings,
            "calculation_decimal_places",
            2,
        )
        or 2
    )

    if decimal_places < 0:
        decimal_places = 0

    return {
        "round_calculated_amounts": cint(
            getattr(
                settings,
                "round_calculated_amounts",
                0,
            )
        ),

        "calculation_decimal_places": decimal_places,

        "calculation_rounding_method": (
            getattr(
                settings,
                "calculation_rounding_method",
                None,
            )
            or "Half Up"
        ),

        "enable_tds": cint(
            getattr(
                settings,
                "enable_tds",
                1,
            )
        ),

        "tds_operation": (
            getattr(
                settings,
                "tds_operation",
                None,
            )
            or "Percentage"
        ),

        "tds_percentage": flt(
            getattr(
                settings,
                "tds_percentage",
                2,
            )
            if getattr(
                settings,
                "tds_percentage",
                None,
            )
            not in (None, "")
            else 2
        ),

        "tds_percentage_without_valid_pan": flt(
            getattr(
                settings,
                "tds_percentage_without_valid_pan",
                20,
            )
            if getattr(
                settings,
                "tds_percentage_without_valid_pan",
                None,
            )
            not in (None, "")
            else 20
        ),

        "tds_fixed_amount": flt(
            getattr(
                settings,
                "tds_fixed_amount",
                0,
            )
            or 0
        ),

        "tds_base": (
            getattr(
                settings,
                "tds_base",
                None,
            )
            or "Commission Amount"
        ),

        "tds_maximum_amount": (
            flt(settings.tds_maximum_amount)
            if getattr(
                settings,
                "tds_maximum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "enable_security_deposit": cint(
            getattr(
                settings,
                "enable_security_deposit",
                1,
            )
        ),

        "security_deposit_operation": (
            getattr(
                settings,
                "security_deposit_operation",
                None,
            )
            or "Percentage"
        ),

        "security_deposit_percentage": flt(
            getattr(
                settings,
                "security_deposit_percentage",
                10,
            )
            if getattr(
                settings,
                "security_deposit_percentage",
                None,
            )
            not in (None, "")
            else 10
        ),

        "security_deposit_fixed_amount": flt(
            getattr(
                settings,
                "security_deposit_fixed_amount",
                0,
            )
            or 0
        ),

        "security_deposit_base": (
            getattr(
                settings,
                "security_deposit_base",
                None,
            )
            or "Commission Amount"
        ),

        "security_deposit_maximum_amount": (
            flt(settings.security_deposit_maximum_amount)
            if getattr(
                settings,
                "security_deposit_maximum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "net_pay_operation": (
            getattr(
                settings,
                "net_pay_operation",
                None,
            )
            or "Commission Amount - TDS - Security Deposit"
        ),

        "net_pay_fixed_adjustment": flt(
            getattr(
                settings,
                "net_pay_fixed_adjustment",
                0,
            )
            or 0
        ),

        "net_pay_minimum_amount": (
            flt(settings.net_pay_minimum_amount)
            if getattr(
                settings,
                "net_pay_minimum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "net_pay_maximum_amount": (
            flt(settings.net_pay_maximum_amount)
            if getattr(
                settings,
                "net_pay_maximum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "enable_agent_deduction": cint(
            getattr(
                settings,
                "enable_agent_deduction",
                1,
            )
        ),

        "agent_deduction_type": (
            getattr(
                settings,
                "agent_deduction_type",
                None,
            )
            or "Amount Above Limit"
        ),

        "agent_deduction_limit": flt(
            getattr(
                settings,
                "agent_deduction_limit",
                1000,
            )
            or 1000
        ),

        "agent_deduction_amount": flt(
            getattr(
                settings,
                "agent_deduction_amount",
                150,
            )
            or 150
        ),

        "agent_deduction_percentage": flt(
            getattr(
                settings,
                "agent_deduction_percentage",
                0,
            )
            or 0
        ),

        "agent_deduction_maximum": (
            flt(settings.agent_deduction_maximum)
            if getattr(
                settings,
                "agent_deduction_maximum",
                None,
            )
            not in (None, "")
            else None
        ),

        "agent_deduction_operation": (
            getattr(
                settings,
                "agent_deduction_operation",
                None,
            )
            or "Subtract"
        ),
    }


def _decimal_amount(value):
    return Decimal(
        str(
            0
            if value in (None, "")
            else value
        )
    )


def _round_calculation_amount(
    value,
    calculation_settings,
):
    """
    Round only when Round Calculated Amounts is enabled.
    """
    amount = _decimal_amount(value)

    if not calculation_settings[
        "round_calculated_amounts"
    ]:
        return amount

    rounding_map = {
        "Half Up": ROUND_HALF_UP,
        "Half Down": ROUND_HALF_DOWN,
        "Down": ROUND_DOWN,
        "Up": ROUND_UP,
        "Ceiling": ROUND_CEILING,
        "Floor": ROUND_FLOOR,
    }

    rounding_mode = rounding_map.get(
        calculation_settings[
            "calculation_rounding_method"
        ],
        ROUND_HALF_UP,
    )

    decimal_places = calculation_settings[
        "calculation_decimal_places"
    ]

    quantizer = Decimal("1").scaleb(
        -decimal_places
    )

    return amount.quantize(
        quantizer,
        rounding=rounding_mode,
    )


def _apply_amount_limit(
    amount,
    maximum_amount,
):
    amount = _decimal_amount(amount)

    if maximum_amount is None:
        return amount

    return min(
        amount,
        _decimal_amount(maximum_amount),
    )


def _get_calculation_base(
    base_name,
    commission_amount,
    eligible_amount,
    tds=Decimal("0"),
    security_deposit=Decimal("0"),
):
    """
    Return the configured base amount.

    Supported bases are the values in Commission Settings.
    """
    if base_name == "Eligible Amount":
        return _decimal_amount(
            eligible_amount
        )

    if base_name == "Net Pay Before TDS":
        return (
            _decimal_amount(commission_amount)
            - _decimal_amount(security_deposit)
        )

    if base_name == "Net Pay Before Security Deposit":
        return (
            _decimal_amount(commission_amount)
            - _decimal_amount(tds)
        )

    return _decimal_amount(
        commission_amount
    )


def _calculate_base_percentage(
    base_amount,
    percentage,
):
    return (
        _decimal_amount(base_amount)
        * _decimal_amount(percentage)
        / Decimal("100")
    )


def _has_valid_pan_status(pan_status):
    """
    Return True only for valid/active PAN status values.
    """
    normalized_status = str(
        pan_status or ""
    ).strip().casefold()

    return normalized_status in {
        "valid and operative".casefold(),
        "active".casefold(),
    }


# def _calculate_tds(
#     commission_amount,
#     eligible_amount,
#     calculation_settings,
#     security_deposit=Decimal("0"),
#     pan_status=None,
# ):
#     """
#     Calculate TDS dynamically.

#     Supported operations:
#         Percentage
#         Fixed Amount
#         Percentage Plus Security Deposit
#         Percentage Minus Security Deposit
#     """
#     if not calculation_settings["enable_tds"]:
#         return Decimal("0")

#     base_amount = _get_calculation_base(
#         base_name=calculation_settings["tds_base"],
#         commission_amount=commission_amount,
#         eligible_amount=eligible_amount,
#         security_deposit=security_deposit,
#     )

#     operation = calculation_settings[
#         "tds_operation"
#     ]

#     # percentage_amount = _calculate_base_percentage(
#     #     base_amount,
#     #     calculation_settings["tds_percentage"],
#     # )

#     if _has_valid_pan_status(pan_status):
#         applicable_tds_percentage = (
#             calculation_settings["tds_percentage"]
#         )
#     else:
#         applicable_tds_percentage = (
#             calculation_settings[
#                 "tds_percentage_without_valid_pan"
#             ]
#         )

#     percentage_amount = _calculate_base_percentage(
#         base_amount,
#         applicable_tds_percentage,
#     )

#     if operation == "Fixed Amount":
#         tds = _decimal_amount(
#             calculation_settings["tds_fixed_amount"]
#         )

#     elif operation == "Percentage Plus Security Deposit":
#         tds = (
#             percentage_amount
#             + _decimal_amount(security_deposit)
#         )

#     elif operation == "Percentage Minus Security Deposit":
#         tds = (
#             percentage_amount
#             - _decimal_amount(security_deposit)
#         )

#     else:
#         tds = percentage_amount

#     if tds < 0:
#         tds = Decimal("0")

#     tds = _apply_amount_limit(
#         tds,
#         calculation_settings[
#             "tds_maximum_amount"
#         ],
#     )

#     return _round_calculation_amount(
#         tds,
#         calculation_settings,
#     )


def _calculate_tds(
    commission_amount,
    eligible_amount,
    calculation_settings,
    security_deposit=Decimal("0"),
    pan_status=None,
):
    """
    Calculate TDS dynamically.

    Valid PAN status:
        Uses tds_percentage.

    Missing/invalid PAN status:
        Uses tds_percentage_without_valid_pan.

    The selected tds_operation logic remains unchanged.
    """
    if not calculation_settings["enable_tds"]:
        return Decimal("0")

    base_amount = _get_calculation_base(
        base_name=calculation_settings["tds_base"],
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        security_deposit=security_deposit,
    )

    if _has_valid_pan_status(pan_status):
        applicable_tds_percentage = (
            calculation_settings["tds_percentage"]
        )
    else:
        applicable_tds_percentage = (
            calculation_settings[
                "tds_percentage_without_valid_pan"
            ]
        )

    percentage_amount = _calculate_base_percentage(
        base_amount,
        applicable_tds_percentage,
    )

    operation = calculation_settings[
        "tds_operation"
    ]

    if operation == "Fixed Amount":
        tds = _decimal_amount(
            calculation_settings["tds_fixed_amount"]
        )

    elif operation == "Percentage Plus Security Deposit":
        tds = (
            percentage_amount
            + _decimal_amount(security_deposit)
        )

    elif operation == "Percentage Minus Security Deposit":
        tds = (
            percentage_amount
            - _decimal_amount(security_deposit)
        )

    else:
        tds = percentage_amount

    if tds < 0:
        tds = Decimal("0")

    tds = _apply_amount_limit(
        tds,
        calculation_settings["tds_maximum_amount"],
    )

    return _round_calculation_amount(
        tds,
        calculation_settings,
    )


def _calculate_security_deposit(
    commission_amount,
    eligible_amount,
    tds,
    calculation_settings,
):
    """
    Calculate Security Deposit dynamically.

    Supported operations:
        Percentage
        Fixed Amount
        Percentage Plus TDS
        Percentage Minus TDS
    """
    if not calculation_settings[
        "enable_security_deposit"
    ]:
        return Decimal("0")

    base_amount = _get_calculation_base(
        base_name=calculation_settings[
            "security_deposit_base"
        ],
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        tds=tds,
    )

    operation = calculation_settings[
        "security_deposit_operation"
    ]

    percentage_amount = _calculate_base_percentage(
        base_amount,
        calculation_settings[
            "security_deposit_percentage"
        ],
    )

    if operation == "Fixed Amount":
        security_deposit = _decimal_amount(
            calculation_settings[
                "security_deposit_fixed_amount"
            ]
        )

    elif operation == "Percentage Plus TDS":
        security_deposit = (
            percentage_amount
            + _decimal_amount(tds)
        )

    elif operation == "Percentage Minus TDS":
        security_deposit = (
            percentage_amount
            - _decimal_amount(tds)
        )

    else:
        security_deposit = percentage_amount

    if security_deposit < 0:
        security_deposit = Decimal("0")

    security_deposit = _apply_amount_limit(
        security_deposit,
        calculation_settings[
            "security_deposit_maximum_amount"
        ],
    )

    return _round_calculation_amount(
        security_deposit,
        calculation_settings,
    )


def _calculate_netpay(
    commission_amount,
    tds,
    security_deposit,
    calculation_settings,
):
    """
    Calculate Net Pay dynamically from Net Pay Operation.
    """
    commission_amount = _decimal_amount(
        commission_amount
    )
    tds = _decimal_amount(tds)
    security_deposit = _decimal_amount(
        security_deposit
    )

    operation = calculation_settings[
        "net_pay_operation"
    ]

    if operation == "Commission Amount - TDS":
        netpay = commission_amount - tds

    elif operation == "Commission Amount - Security Deposit":
        netpay = (
            commission_amount
            - security_deposit
        )

    elif operation == (
        "Commission Amount + TDS - Security Deposit"
    ):
        netpay = (
            commission_amount
            + tds
            - security_deposit
        )

    elif operation == (
        "Commission Amount - TDS + Security Deposit"
    ):
        netpay = (
            commission_amount
            - tds
            + security_deposit
        )

    elif operation == (
        "Commission Amount + TDS + Security Deposit"
    ):
        netpay = (
            commission_amount
            + tds
            + security_deposit
        )

    elif operation == "Commission Amount + Security Deposit":
        netpay = (
            commission_amount
            + security_deposit
        )

    elif operation == "Commission Amount":
        netpay = commission_amount

    elif operation == "Custom Fixed Adjustment":
        netpay = (
            commission_amount
            + _decimal_amount(
                calculation_settings[
                    "net_pay_fixed_adjustment"
                ]
            )
        )

    else:
        netpay = (
            commission_amount
            - tds
            - security_deposit
        )

    minimum_amount = calculation_settings[
        "net_pay_minimum_amount"
    ]

    maximum_amount = calculation_settings[
        "net_pay_maximum_amount"
    ]

    if minimum_amount is not None:
        netpay = max(
            netpay,
            _decimal_amount(minimum_amount),
        )

    if maximum_amount is not None:
        netpay = min(
            netpay,
            _decimal_amount(maximum_amount),
        )

    return _round_calculation_amount(
        netpay,
        calculation_settings,
    )


# def _calculate_commission_financial_values(
#     commission_amount,
#     eligible_amount,
#     pan_status=None,
# ):
#     """
#     Central financial calculation engine.

#     The TDS/Security Deposit dependency is resolved in this order:
#         1. Calculate preliminary TDS.
#         2. Calculate Security Deposit.
#         3. Recalculate TDS if it depends on Security Deposit.
#         4. Calculate Net Pay.
#     """
#     calculation_settings = (
#         _get_commission_calculation_settings()
#     )

#     commission_amount = _round_calculation_amount(
#         commission_amount,
#         calculation_settings,
#     )

#     tds_operation = calculation_settings[
#         "tds_operation"
#     ]

#     # First pass: calculate TDS without security deposit.
#     preliminary_tds = _calculate_tds(
#         commission_amount=commission_amount,
#         eligible_amount=eligible_amount,
#         calculation_settings=calculation_settings,
#         security_deposit=Decimal("0"),
#         pan_status=pan_status,
#     )

#     security_deposit = _calculate_security_deposit(
#         commission_amount=commission_amount,
#         eligible_amount=eligible_amount,
#         tds=preliminary_tds,
#         calculation_settings=calculation_settings,
#     )

#     # Second pass: TDS operations involving Security Deposit.
#     if tds_operation in (
#         "Percentage Plus Security Deposit",
#         "Percentage Minus Security Deposit",
#     ):
#         tds = _calculate_tds(
#             commission_amount=commission_amount,
#             eligible_amount=eligible_amount,
#             calculation_settings=calculation_settings,
#             security_deposit=security_deposit,
#             pan_status=pan_status,
#         )
#     else:
#         tds = preliminary_tds

#     netpay = _calculate_netpay(
#         commission_amount=commission_amount,
#         tds=tds,
#         security_deposit=security_deposit,
#         calculation_settings=calculation_settings,
#     )

#     return {
#         "commission_amount": commission_amount,
#         "tds": tds,
#         "security_deposit": security_deposit,
#         "netpay": netpay,
#         "calculation_settings": calculation_settings,
#     }

def _calculate_commission_financial_values(
    commission_amount,
    eligible_amount,
    pan_status=None,
):
    """
    Central financial calculation engine.

    TDS percentage is selected using Commission.pan_status:

    Valid and Operative / Active:
        Commission Settings.tds_percentage

    Missing or other PAN status:
        Commission Settings.tds_percentage_without_valid_pan
    """
    calculation_settings = (
        _get_commission_calculation_settings()
    )

    commission_amount = _round_calculation_amount(
        commission_amount,
        calculation_settings,
    )

    tds_operation = calculation_settings[
        "tds_operation"
    ]

    preliminary_tds = _calculate_tds(
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        calculation_settings=calculation_settings,
        security_deposit=Decimal("0"),
        pan_status=pan_status,
    )

    security_deposit = _calculate_security_deposit(
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        tds=preliminary_tds,
        calculation_settings=calculation_settings,
    )

    if tds_operation in (
        "Percentage Plus Security Deposit",
        "Percentage Minus Security Deposit",
    ):
        tds = _calculate_tds(
            commission_amount=commission_amount,
            eligible_amount=eligible_amount,
            calculation_settings=calculation_settings,
            security_deposit=security_deposit,
            pan_status=pan_status,
        )
    else:
        tds = preliminary_tds

    netpay = _calculate_netpay(
        commission_amount=commission_amount,
        tds=tds,
        security_deposit=security_deposit,
        calculation_settings=calculation_settings,
    )

    return {
        "commission_amount": commission_amount,
        "tds": tds,
        "security_deposit": security_deposit,
        "netpay": netpay,
        "calculation_settings": calculation_settings,
        "pan_status": pan_status,
        "tds_percentage_used": (
            calculation_settings["tds_percentage"]
            if _has_valid_pan_status(pan_status)
            else calculation_settings[
                "tds_percentage_without_valid_pan"
            ]
        ),
    }


def _get_eligible_amount_scheme_groups():
    """
    Read scheme groups from Commission Settings.

    Format:
        2014
        2015,2016,2017,2018
        2019,2020

    Returns:
        {
            "2014": ("2014",),
            "2015": ("2015", "2016", "2017", "2018"),
            "2016": ("2015", "2016", "2017", "2018"),
            ...
        }
    """
    settings = frappe.get_single(
        "Commission Settings"
    )

    raw_groups = (
        getattr(
            settings,
            "eligible_amount_scheme_groups",
            None,
        )
        or ""
    )

    scheme_groups = {}
    used_schemes = set()

    for raw_line in str(raw_groups).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        scheme_codes = [
            scheme.strip()
            for scheme in line.split(",")
            if scheme.strip()
        ]

        if not scheme_codes:
            continue

        # Remove duplicates within a group while
        # preserving the entered order.
        group = tuple(
            dict.fromkeys(scheme_codes)
        )

        for scheme_code in group:
            if scheme_code in scheme_groups:
                frappe.throw(
                    _(
                        "Scheme Code {0} is configured in "
                        "more than one Eligible Amount Scheme Group."
                    ).format(scheme_code)
                )

            scheme_groups[scheme_code] = group
            used_schemes.add(scheme_code)

    return scheme_groups


def _get_eligible_amount_scheme_group(
    scheme_code,
):
    """
    Return the configured group for one scheme.

    If the scheme is not configured in a group, it becomes
    its own group.
    """
    scheme_code = str(
        scheme_code or ""
    ).strip()

    if not scheme_code:
        frappe.throw(
            _("Scheme Code is required.")
        )

    scheme_groups = (
        _get_eligible_amount_scheme_groups()
    )

    return scheme_groups.get(
        scheme_code,
        (scheme_code,),
    )


@frappe.whitelist()
def calculate_commission_amount(docname):
    """
    Calculate Commission.commission_amount based on Product commission type.

    Supported Product commission types:
    1. Fixed Rate
    2. Age Based
    3. Eligible Amount Based
    4. Deferred

    After each calculation:
    - TDS = 2% of commission amount.
    - Security Deposit = 10% of commission amount.
    - Net Pay = commission amount - TDS - Security Deposit.
    - Agent-level deduction/final_net_pay is updated for every record
      with the same agent_code.
    """

    if not docname:
        frappe.throw(_("Commission document name is required"))

    commission_doc = frappe.get_doc("Commission", docname)

    if not commission_doc.scheme_code:
        frappe.throw(_("Scheme Code is required in Commission document"))

    if commission_doc.eligible_amount in (None, ""):
        frappe.throw(_("Eligible Amount is required in Commission document"))

    if not commission_doc.agent_code:
        frappe.throw(_("Agent Code is required in Commission document"))

    product_name = str(commission_doc.scheme_code).strip()

    product = frappe.db.get_value(
        "Product",
        product_name,
        [
            "commission_type",
            "commission_rate",
            "commission_rate_upto_one_year",
            "commission_rate_above_one_year",
            "slab_1_limit",
            "slab_1_rate",
            "slab_2_limit",
            "slab_2_rate",
            "slab_3_rate",
        ],
        as_dict=True,
    )

    if not product:
        frappe.throw(
            _("No Product found with Product Code: {0}").format(
                product_name
            )
        )

    if not product.commission_type:
        frappe.throw(
            _("Commission Type is not configured in Product: {0}").format(
                product_name
            )
        )

    commission_type = product.commission_type
    eligible_amount = flt(commission_doc.eligible_amount)

    if eligible_amount < 0:
        frappe.throw(_("Eligible Amount cannot be negative"))

    rate = None
    is_deferred = False
    deferred_result = None

    # ==========================================================
    # PRODUCT TYPE 1: FIXED RATE
    # ==========================================================
    if commission_type == "Fixed Rate":
        if product.commission_rate in (None, ""):
            frappe.throw(
                _("Commission Rate is required for Product: {0}").format(
                    product_name
                )
            )

        rate = flt(product.commission_rate)

    # ==========================================================
    # PRODUCT TYPE 2: AGE BASED
    # ==========================================================
    elif commission_type == "Age Based":
        remarks = _safe_str(commission_doc.remarks).upper()

        if remarks == "YES":
            if product.commission_rate_upto_one_year in (None, ""):
                frappe.throw(
                    _(
                        "Commission Rate Upto One Year is required "
                        "for Product: {0}"
                    ).format(product_name)
                )

            rate = flt(product.commission_rate_upto_one_year)

        elif remarks == "NO":
            if product.commission_rate_above_one_year in (None, ""):
                frappe.throw(
                    _(
                        "Commission Rate Above One Year is required "
                        "for Product: {0}"
                    ).format(product_name)
                )

            rate = flt(product.commission_rate_above_one_year)

        else:
            frappe.throw(
                _(
                    "Remarks must be YES or NO for Age Based Product: {0}"
                ).format(product_name)
            )

    # ==========================================================
    # PRODUCT TYPE 3: ELIGIBLE AMOUNT BASED
    # ==========================================================
    elif commission_type == "Eligible Amount Based":
        required_fields = {
            "Slab 1 Limit": product.slab_1_limit,
            "Slab 1 Rate": product.slab_1_rate,
            "Slab 2 Limit": product.slab_2_limit,
            "Slab 2 Rate": product.slab_2_rate,
            "Slab 3 Rate": product.slab_3_rate,
        }

        for field_label, field_value in required_fields.items():
            if field_value in (None, ""):
                frappe.throw(
                    _("{0} is required for Product: {1}").format(
                        field_label,
                        product_name,
                    )
                )

        slab_1_limit = flt(product.slab_1_limit)
        slab_2_limit = flt(product.slab_2_limit)

        if slab_1_limit < 0:
            frappe.throw(_("Slab 1 Limit cannot be negative"))

        if slab_2_limit <= slab_1_limit:
            frappe.throw(
                _(
                    "Slab 2 Limit must be greater than "
                    "Slab 1 Limit for Product: {0}"
                ).format(product_name)
            )

        # agent_code = str(commission_doc.agent_code).strip()

        # eligible_products = frappe.get_all(
        #     "Product",
        #     filters={"commission_type": "Eligible Amount Based"},
        #     pluck="name",
        # )

        # if not eligible_products:
        #     frappe.throw(
        #         _(
        #             "No Product found with commission_type = "
        #             "'Eligible Amount Based'"
        #         )
        #     )

        # in_clause = ", ".join(["%s"] * len(eligible_products))
        # in_params = tuple(eligible_products)

        # result = frappe.db.sql(
        #     """
        #     SELECT
        #         COALESCE(SUM(c.eligible_amount), 0) AS total
        #     FROM `tabCommission` c
        #     WHERE c.agent_code = %s
        #     AND c.docstatus < 2
        #     AND c.scheme_code IN ({0})
        #     """.format(in_clause),
        #     tuple([agent_code] + list(in_params)),
        #     as_dict=True,
        # )

        # agent_total = (
        #     flt(result[0].total)
        #     if result and result[0].total is not None
        #     else 0
        # )

        # if agent_total <= 0:
        #     frappe.throw(
        #         _(
        #             "Total eligible amount for Agent {0} "
        #             "(Eligible Amount Based products) is zero or invalid"
        #         ).format(agent_code)
        #     )

        # frappe.db.sql(
        #     """
        #     UPDATE `tabCommission`
        #     SET agent_total_eligible_collection = %s
        #     WHERE agent_code = %s
        #     AND docstatus < 2
        #     AND scheme_code IN ({0})
        #     """.format(in_clause),
        #     tuple([agent_total, agent_code] + list(in_params)),
        # )

        # commission_doc.agent_total_eligible_collection = agent_total

        agent_code = str(
            commission_doc.agent_code
        ).strip()

        current_scheme_code = str(
            commission_doc.scheme_code
        ).strip()

        eligible_scheme_group = (
            _get_eligible_amount_scheme_group(
                current_scheme_code
            )
        )

        group_placeholders = ", ".join(
            ["%s"] * len(eligible_scheme_group)
        )

        group_values = (
            [agent_code]
            + list(eligible_scheme_group)
        )

        result = frappe.db.sql(
            f"""
            SELECT
                COALESCE(
                    SUM(c.eligible_amount),
                    0
                ) AS total
            FROM `tabCommission` c
            INNER JOIN `tabProduct` p
                ON p.name = c.scheme_code
            WHERE c.agent_code = %s
            AND c.docstatus < 2
            AND p.commission_type = 'Eligible Amount Based'
            AND c.scheme_code IN ({group_placeholders})
            """,
            tuple(group_values),
            as_dict=True,
        )

        agent_total = (
            flt(result[0].total)
            if result
            and result[0].total is not None
            else 0
        )

        if agent_total <= 0:
            frappe.throw(
                _(
                    "Total eligible amount for Agent {0} "
                    "and Scheme Group {1} is zero or invalid."
                ).format(
                    agent_code,
                    ", ".join(eligible_scheme_group),
                )
            )

        frappe.db.sql(
            f"""
            UPDATE `tabCommission` c
            INNER JOIN `tabProduct` p
                ON p.name = c.scheme_code
            SET c.agent_total_eligible_collection = %s
            WHERE c.agent_code = %s
            AND c.docstatus < 2
            AND p.commission_type = 'Eligible Amount Based'
            AND c.scheme_code IN ({group_placeholders})
            """,
            tuple(
                [agent_total, agent_code]
                + list(eligible_scheme_group)
            ),
        )

        commission_doc.agent_total_eligible_collection = (
            agent_total
        )

        if agent_total <= slab_1_limit:
            rate = flt(product.slab_1_rate)
        elif agent_total <= slab_2_limit:
            rate = flt(product.slab_2_rate)
        else:
            rate = flt(product.slab_3_rate)

    # ==========================================================
    # PRODUCT TYPE 4: DEFERRED
    # ==========================================================
    elif commission_type == "Deferred":
        is_deferred = True

        product_doc = _get_deferred_product(product_name)

        deferred_result = _create_deferred_commission_schedule(
            commission_doc=commission_doc,
            product_doc=product_doc,
            eligible_amount=eligible_amount,
        )

        # Parent values are the total of all deferred schedule years.
        commission_amount = flt(deferred_result["total_commission"])
        rate = flt(deferred_result["total_rate"])

    # ==========================================================
    # INVALID COMMISSION TYPE
    # ==========================================================
    else:
        frappe.throw(
            _(
                "Invalid Commission Type '{0}' in Product: {1}. "
                "Allowed values are Fixed Rate, Age Based, "
                "Eligible Amount Based, and Deferred."
            ).format(
                commission_type,
                product_name,
            )
        )

    if rate is None:
        frappe.throw(
            _("Unable to determine commission rate for Product: {0}").format(
                product_name
            )
        )

    if rate < 0:
        frappe.throw(_("Commission rate cannot be negative"))

    # ==========================================================
    # COMMON FINANCIAL CALCULATION
    # ==========================================================
    if not is_deferred:
        commission_amount = (eligible_amount * rate) / 100

    # tds = commission_amount * 0.02
    # security_deposit = commission_amount * 0.10
    # netpay = commission_amount - (tds + security_deposit)

    financial_values = (
        _calculate_commission_financial_values(
            commission_amount=commission_amount,
            eligible_amount=eligible_amount,
            pan_status=commission_doc.pan_status,
        )
    )

    commission_amount = flt(
        financial_values["commission_amount"]
    )

    tds = flt(
        financial_values["tds"]
    )

    security_deposit = flt(
        financial_values["security_deposit"]
    )

    netpay = flt(
        financial_values["netpay"]
    )

    commission_doc.commission_amount = commission_amount
    commission_doc.tds = tds
    commission_doc.security_deposit = security_deposit
    commission_doc.netpay = netpay

    if frappe.get_meta("Commission").has_field("applied_commission_rate"):
        commission_doc.applied_commission_rate = rate

    if frappe.get_meta("Commission").has_field("commission_type_applied"):
        commission_doc.commission_type_applied = commission_type

    commission_doc.save(ignore_permissions=True)

    # ==========================================================
    # AGENT-WISE DEDUCTION / FINAL NET PAY
    # ==========================================================
    agent_summary = _update_agent_deduction_and_final_net_pay(
        commission_doc.agent_code
    )

    commission_doc.reload()

    payment_result = create_commission_payment_records(
        commission_doc
    )

    frappe.db.commit()

    response = {
        "status": "success",
        "docname": commission_doc.name,
        "product_code": product_name,
        "commission_type": commission_type,
        "remarks": commission_doc.remarks,
        "eligible_amount": eligible_amount,
        "agent_total_eligible_collection": (
            flt(commission_doc.agent_total_eligible_collection)
            if commission_type == "Eligible Amount Based"
            else None
        ),
        "agent_total_netpay": agent_summary["agent_total_netpay"],
        "deduction": agent_summary["deduction"],
        "final_net_pay": agent_summary["final_net_pay"],
        "applied_rate": rate,
        "commission_amount": commission_amount,
        "tds": tds,
        "security_deposit": security_deposit,
        "netpay": netpay,
        "commission_payment": payment_result,
    }

    if is_deferred:
        response.update({
            "deferred_schedule_count": deferred_result["schedule_count"],
            "first_deferred_due_date": deferred_result["first_due_date"],
            "message": _("Deferred commission schedule created successfully"),
        })

    return response


def _create_deferred_payment_records(commission_doc):
    """
    Create one Commission Payment document for each row in
    Commission.deferred_commission_details.

    Each Deferred payment remains linked to its individual Commission record,
    because every annual installment has its own source record, year, and due date.
    """
    if not commission_doc.deferred_commission_details:
        return {
            "created_count": 0,
            "existing_count": 0,
            "payments": [],
        }

    payment_results = []

    for deferred_row in commission_doc.deferred_commission_details:
        payment_year = int(deferred_row.year_no or 0)

        if payment_year <= 0:
            frappe.throw(
                _("Invalid Deferred Year No in Commission: {0}").format(
                    commission_doc.name
                )
            )

        if not deferred_row.due_date:
            frappe.throw(
                _("Due Date is required for Deferred Year {0}").format(
                    payment_year
                )
            )

        existing_payment = frappe.db.exists(
            "Commission Payment",
            {
                "commission": commission_doc.name,
                "payment_type": "Deferred",
                "payment_year": payment_year,
                "docstatus": ("<", 2),
            },
        )

        if existing_payment:
            payment_results.append({
                "created": False,
                "name": existing_payment,
            })
            continue

        payment_doc = frappe.get_doc({
            "doctype": "Commission Payment",
            "commission": commission_doc.name,
            "agent_code": commission_doc.agent_code,
            "agent_operative_account": commission_doc.agent_operative_account,
            "agent_saving_account": commission_doc.agent_saving_account,
            "payment_type": "Deferred",
            "payment_year": payment_year,
            "due_date": deferred_row.due_date,
            "source_deferred_detail": deferred_row.name,
            "gross_commission": flt(deferred_row.gross_commission),
            "tds_amount": flt(deferred_row.tds),
            "security_deposit_amount": flt(
                deferred_row.security_deposit
            ),
            "netpay_amount": flt(deferred_row.netpay),
            "deduction_amount": 0,
            "final_netpay": flt(deferred_row.netpay),
            "payment_status": (
                "Due"
                if deferred_row.status == "Due"
                else "Pending"
            ),
        })

        payment_doc.insert(ignore_permissions=True)

        payment_results.append({
            "created": True,
            "name": payment_doc.name,
        })

    return {
        "created_count": sum(
            1 for payment in payment_results if payment["created"]
        ),
        "existing_count": sum(
            1 for payment in payment_results if not payment["created"]
        ),
        "payments": payment_results,
    }


def _get_product_with_deferred_schedule(product_name):
    """
    Load complete Product document because deferred schedule is a child table.
    """
    product_doc = frappe.get_doc("Product", product_name)

    if product_doc.commission_type != "Deferred":
        frappe.throw(
            _("Product {0} is not configured as Deferred").format(
                product_name
            )
        )

    if not product_doc.deferred_commission_schedule:
        frappe.throw(
            _("Deferred Commission Schedule is missing in Product: {0}").format(
                product_name
            )
        )

    return product_doc


def _validate_deferred_schedule(product_doc):
    """
    Validate enabled Product deferred commission schedule rows.
    Returns schedule rows sorted by year_no.
    """
    enabled_rows = []
    used_years = set()

    for row in product_doc.deferred_commission_schedule:
        if not row.enabled:
            continue

        year_no = cint(row.year_no)
        commission_rate = flt(row.commission_rate)

        if year_no <= 0:
            frappe.throw(
                _("Deferred Year No must be greater than zero in Product: {0}").format(
                    product_doc.name
                )
            )

        if year_no in used_years:
            frappe.throw(
                _("Duplicate Deferred Year No {0} in Product: {1}").format(
                    year_no,
                    product_doc.name
                )
            )

        if commission_rate < 0:
            frappe.throw(
                _("Deferred Commission Rate cannot be negative for Year {0}").format(
                    year_no
                )
            )

        used_years.add(year_no)
        enabled_rows.append({
            "year_no": year_no,
            "commission_rate": commission_rate,
            "remarks": _safe_str(row.remarks),
        })

    if not enabled_rows:
        frappe.throw(
            _("No enabled Deferred Commission Schedule rows found in Product: {0}").format(
                product_doc.name
            )
        )

    return sorted(enabled_rows, key=lambda row: row["year_no"])


def _generate_deferred_commission_schedule(commission_doc, product_doc, eligible_amount):
    """
    Generate the full annual deferred payout schedule in the Commission child table.

    Due-date rule:
    - Year 1: first day of next calendar month after Commission record creation.
    - Year 2: one year after Year 1 due date.
    - Year N: Year 1 due date plus N-1 years.

    Example:
    Commission created on 2026-08-19:
    - Year 1 due: 2026-09-01
    - Year 2 due: 2027-09-01
    """
    commission_meta = frappe.get_meta("Commission")

    if not commission_meta.has_field("deferred_commission_details"):
        frappe.throw(
            _("Commission field 'deferred_commission_details' does not exist")
        )

    if commission_doc.deferred_commission_details:
        frappe.throw(
            _("Deferred commission schedule already exists for Commission: {0}").format(
                commission_doc.name
            )
        )

    schedule_rows = _validate_deferred_schedule(product_doc)

    # Commission document creation date controls the deferred due cycle.
    source_date = getdate(commission_doc.creation)

    # First day of next month.
    first_due_date = add_to_date(
        source_date.replace(day=1),
        months=1,
        as_string=True,
    )

    total_deferred_amount = 0
    total_deferred_rate = 0

    for schedule in schedule_rows:
        year_no = schedule["year_no"]
        rate = schedule["commission_rate"]

        gross_commission = (eligible_amount * rate) / 100
        tds = gross_commission * 0.02
        security_deposit = gross_commission * 0.10
        netpay = gross_commission - (tds + security_deposit)

        due_date = add_to_date(
            first_due_date,
            years=year_no - 1,
            as_string=True,
        )

        commission_doc.append(
            "deferred_commission_details",
            {
                "year_no": year_no,
                "commission_rate": rate,
                "eligible_amount": eligible_amount,
                "gross_commission": gross_commission,
                "due_date": due_date,
                "status": "Pending",
                "tds": tds,
                "security_deposit": security_deposit,
                "netpay": netpay,
                "remarks": schedule["remarks"],
            },
        )

        total_deferred_amount += gross_commission
        total_deferred_rate += rate

    return {
        "total_deferred_amount": total_deferred_amount,
        "total_deferred_rate": total_deferred_rate,
        "first_due_date": first_due_date,
        "schedule_count": len(schedule_rows),
    }


@frappe.whitelist()
def calculate_commission_for_all():
    """
    Calculate commission on ALL Commission documents.
    Calls calculate_commission_amount(docname) for each document.
    """
    frappe.only_for(("System Manager",))

    # Get all Commission names
    commission_names = frappe.get_all(
        "Commission",
        filters={"docstatus": ("<", 2)},  # ignore cancelled if any
        pluck="name",
    )

    if not commission_names:
        return {
            "status": "completed",
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "errors": [],
        }

    success_count = 0
    error_count = 0
    errors = []

    for docname in commission_names:
        try:
            # Call existing method
            calculate_commission_amount(docname)
            success_count += 1
        except Exception:
            error_count += 1
            errors.append(
                f"{docname}: {frappe.get_traceback()}"
            )
            # Optionally log
            frappe.log_error(
                frappe.get_traceback(),
                f"Commission Calculation Error - {docname}",
            )

    return {
        "status": "completed",
        "total_processed": len(commission_names),
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }


@frappe.whitelist()
def mark_due_deferred_commissions(payment_date=None):
    """
    Mark deferred schedule rows as Due when their due_date has arrived.
    Actual payment remains a manual action.
    """
    frappe.only_for(("System Manager",))

    payment_date = getdate(payment_date) if payment_date else getdate()

    result = frappe.db.sql(
        """
        UPDATE `tabDeferred Commission Detail`
        SET status = 'Due'
        WHERE parenttype = 'Commission'
        AND parentfield = 'deferred_commission_details'
        AND status = 'Pending'
        AND due_date <= %s
        """,
        payment_date,
    )

    frappe.db.commit()

    return {
        "status": "success",
        "payment_date": payment_date,
        "message": _("Deferred commission rows marked as Due"),
    }


@frappe.whitelist()
def get_due_deferred_commissions(payment_date=None):
    """
    Return Deferred Commission Detail rows that are due and not yet paid.
    """
    frappe.only_for(("System Manager",))

    payment_date = getdate(payment_date) if payment_date else getdate()

    return frappe.db.sql(
        """
        SELECT
            c.name AS commission_name,
            c.agent_code,
            c.agent_name,
            c.scheme_code,
            c.customer_account_number,
            c.customer_account_name,
            d.name AS deferred_detail_name,
            d.year_no,
            d.commission_rate,
            d.eligible_amount,
            d.gross_commission,
            d.tds,
            d.security_deposit,
            d.netpay,
            d.due_date,
            d.status
        FROM `tabDeferred Commission Detail` d
        INNER JOIN `tabCommission` c
            ON c.name = d.parent
        WHERE d.parenttype = 'Commission'
        AND d.parentfield = 'deferred_commission_details'
        AND d.status IN ('Pending', 'Due')
        AND d.due_date <= %s
        AND c.docstatus < 2
        ORDER BY d.due_date, c.agent_code, c.name
        """,
        payment_date,
        as_dict=True,
    )


@frappe.whitelist()
def mark_deferred_commission_paid(
    commission_name,
    deferred_detail_name,
    payment_reference=None,
    paid_on=None,
):
    """
    Mark exactly one deferred annual installment as paid.
    Stops duplicate payment of the same year.
    """
    frappe.only_for(("System Manager",))

    paid_on = getdate(paid_on) if paid_on else getdate()

    commission_doc = frappe.get_doc("Commission", commission_name)

    deferred_row = next(
        (
            row for row in commission_doc.deferred_commission_details
            if row.name == deferred_detail_name
        ),
        None,
    )

    if not deferred_row:
        frappe.throw(_("Deferred Commission Detail row not found"))

    if deferred_row.status == "Paid":
        frappe.throw(
            _("Deferred commission for Year {0} is already paid").format(
                deferred_row.year_no
            )
        )

    if getdate(deferred_row.due_date) > paid_on:
        frappe.throw(
            _("This deferred commission is not due until {0}").format(
                deferred_row.due_date
            )
        )

    deferred_row.status = "Paid"
    deferred_row.paid_on = paid_on
    deferred_row.payment_reference = payment_reference

    commission_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "commission_name": commission_doc.name,
        "year_no": deferred_row.year_no,
        "gross_commission": deferred_row.gross_commission,
        "tds": deferred_row.tds,
        "security_deposit": deferred_row.security_deposit,
        "netpay": deferred_row.netpay,
        "paid_on": paid_on,
        "payment_reference": payment_reference,
        "message": _("Deferred commission installment marked as paid"),
    }
