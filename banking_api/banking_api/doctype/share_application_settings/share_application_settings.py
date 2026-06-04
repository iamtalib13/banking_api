# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
import psycopg2
import psycopg2.extras
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, now
import random
from datetime import datetime

import requests
import xmltodict
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout, Timeout


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
            now()
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


@frappe.whitelist()
def pay_now_share_application(entry_name):
    settings = frappe.get_single("Share Application Settings")
    lock_name = f"share_application_pay_now::{entry_name}"

    if not entry_name:
        frappe.throw(_("Share Application document name is required."))

    if not settings.enable_fund_transfer:
        return {
            "status": "skipped",
            "message": "Fund transfer is disabled in Share Application Settings."
        }

    if not settings.finacle_api_url:
        frappe.throw(
            _("Finacle API URL is mandatory in Share Application Settings."))

    share_amount = cint_safe(settings.share_account_credit_amount, 0)
    member_fee_amount = cint_safe(settings.member_fee_credit_amount, 0)
    total_debit_amount = share_amount + member_fee_amount

    if not settings.share_account_gl:
        frappe.throw(
            _("Share Account GL is mandatory in Share Application Settings."))

    if not settings.share_member_fee_gl:
        frappe.throw(
            _("Share Member Fee GL is mandatory in Share Application Settings."))

    if share_amount <= 0 and member_fee_amount <= 0:
        frappe.throw(
            _("At least one credit amount must be greater than zero."))

    if total_debit_amount <= 0:
        frappe.throw(_("Total debit amount must be greater than zero."))

    try:
        if frappe.cache().get_value(lock_name):
            frappe.throw(
                _("A fund transfer is already in progress for this Share Application."))
        frappe.cache().set_value(lock_name, frappe.session.user, expires_in_sec=120)
    except frappe.ValidationError:
        raise
    except Exception:
        pass

    try:
        doc = frappe.get_doc("Share Application", entry_name)

        if doc.docstatus != 0:
            return {
                "status": "warning",
                "message": "Only draft Share Application documents can be processed."
            }

        if doc.status == "Success":
            return {
                "status": "warning",
                "message": "This Share Application is already processed successfully."
            }

        debit_account = str(doc.account_number).strip(
        ) if doc.account_number else ""
        if not debit_account:
            _set_share_application_error(
                doc.name, "Account Number is missing on Share Application.")
            frappe.db.commit()
            return {
                "status": "error",
                "message": "Account Number is missing on Share Application."
            }

        conn = None
        cursor = None
        try:
            conn = db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            closed_account_query = """
                SELECT
                    foracid,
                    acct_name,
                    cust_id,
                    schm_code,
                    acct_opn_date,
                    acct_cls_flg,
                    acct_cls_date
                FROM tbaadm.gam
                WHERE foracid = %s
                  AND (
                        (acct_cls_flg = 'N' AND acct_cls_date IS NOT NULL)
                        OR
                        (acct_cls_flg = 'Y' AND acct_cls_date IS NOT NULL)
                      )
            """
            cursor.execute(closed_account_query, (debit_account,))
            closed_account_row = cursor.fetchone()

            if closed_account_row:
                error_message = f"Debit account number is closed: {debit_account}"
                _set_share_application_error(doc.name, error_message)
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": error_message
                }

            balance_query = """
                SELECT
                    g.foracid,
                    g.acct_name,
                    g.sol_id,
                    g.clr_bal_amt
                FROM tbaadm.gam g
                WHERE g.del_flg = 'N'
                  AND g.foracid = %s
            """
            cursor.execute(balance_query, (debit_account,))
            balance_row = cursor.fetchone()

            if not balance_row:
                error_message = f"Debit account not found or inactive: {debit_account}"
                _set_share_application_error(doc.name, error_message)
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": error_message
                }

            available_balance = float(balance_row.get("clr_bal_amt") or 0)

            if available_balance < float(total_debit_amount):
                error_message = (
                    f"Insufficient balance in debit account {debit_account}. "
                    f"Available balance is {available_balance}, required amount is {total_debit_amount}."
                )
                _set_share_application_error(doc.name, error_message)
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": error_message
                }

        except Exception as db_check_error:
            error_message = f"Debit account validation failed: {str(db_check_error)}"
            _set_share_application_error(doc.name, error_message)
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        guid = random.randint(1000000000, 9999999999)
        url = settings.finacle_api_url

        xml_parts = []
        xml_parts.append(
            f"""<PartTrnRec><AcctId><AcctId>{debit_account}</AcctId></AcctId><CreditDebitFlg>D</CreditDebitFlg><TrnAmt><amountValue>{total_debit_amount}</amountValue><currencyCode>INR</currencyCode></TrnAmt><TrnParticulars>Share Fund Debited</TrnParticulars><ValueDt>{current_date}</ValueDt></PartTrnRec>""")

        if share_amount > 0:
            xml_parts.append(
                f"""<PartTrnRec><AcctId><AcctId>{settings.share_account_gl}</AcctId></AcctId><CreditDebitFlg>C</CreditDebitFlg><TrnAmt><amountValue>{share_amount}</amountValue><currencyCode>INR</currencyCode></TrnAmt><TrnParticulars>SHARE ACCOUNT</TrnParticulars><ValueDt>{current_date}</ValueDt></PartTrnRec>""")

        if member_fee_amount > 0:
            xml_parts.append(
                f"""<PartTrnRec><AcctId><AcctId>{settings.share_member_fee_gl}</AcctId></AcctId><CreditDebitFlg>C</CreditDebitFlg><TrnAmt><amountValue>{member_fee_amount}</amountValue><currencyCode>INR</currencyCode></TrnAmt><TrnParticulars>SHARE MEMBER FEE</TrnParticulars><ValueDt>{current_date}</ValueDt></PartTrnRec>""")

        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<FIXML xsi:schemaLocation="http://www.finacle.com/fixml XferTrnAdd.xsd" xmlns="http://www.finacle.com/fixml" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Header>
        <RequestHeader>
            <MessageKey>
                <RequestUUID>{guid}</RequestUUID>
                <ServiceRequestId>XferTrnAdd</ServiceRequestId>
                <ServiceRequestVersion>10.2</ServiceRequestVersion>
                <ChannelId>COR</ChannelId>
            </MessageKey>
            <RequestMessageInfo>
                <BankId>01</BankId>
                <MessageDateTime>{current_date}</MessageDateTime>
            </RequestMessageInfo>
            <Security>
                <Token>
                    <PasswordToken>
                        <UserId></UserId>
                        <Password></Password>
                    </PasswordToken>
                </Token>
            </Security>
        </RequestHeader>
    </Header>
    <Body>
        <XferTrnAddRequest>
            <XferTrnAddRq>
                <XferTrnHdr>
                    <TrnType>T</TrnType>
                    <TrnSubType>CI</TrnSubType>
                </XferTrnHdr>
                <XferTrnDetail>
                    {''.join(xml_parts)}
                </XferTrnDetail>
            </XferTrnAddRq>
        </XferTrnAddRequest>
    </Body>
</FIXML>"""

        try:
            response = requests.post(
                url,
                data=xml_data.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
                verify=False,
                timeout=(10, 30)
            )
            response.raise_for_status()
        except (Timeout, ReadTimeout):
            error_message = "Finacle API timeout occurred while processing the transaction. Transaction status is unknown; verify before retrying."
            _set_share_application_error(doc.name, error_message)
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }
        except ConnectionError:
            error_message = "Unable to connect to Finacle API. Please verify network or server availability before retrying."
            _set_share_application_error(doc.name, error_message)
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }
        except HTTPError:
            error_message = f"Finacle API returned HTTP {getattr(response, 'status_code', 'error')}. Response: {getattr(response, 'text', '')}"
            _set_share_application_error(doc.name, error_message)
            frappe.db.commit()
            return {
                "status": "error",
                "message": "Finacle API returned an error response."
            }

        response_text = response.text or ""

        try:
            res_dict = xmltodict.parse(response_text)
        except Exception:
            error_message = f"Unable to parse Finacle API response. Raw response: {response_text}"
            _set_share_application_error(doc.name, error_message)
            frappe.db.commit()
            return {
                "status": "error",
                "message": "Unable to parse Finacle API response."
            }

        fixml_root = res_dict.get("FIXML", {}) if isinstance(
            res_dict, dict) else {}
        header = fixml_root.get("Header", {}) or {}
        response_header = header.get("ResponseHeader", {}) or {}
        host_transaction = response_header.get("HostTransaction", {}) or {}
        body = fixml_root.get("Body", {}) or {}
        xfer_response = body.get("XferTrnAddResponse", {}) or {}
        xfer_rs = xfer_response.get("XferTrnAddRs", {}) or {}
        trn_identifier = xfer_rs.get("TrnIdentifier", {}) or {}

        status = (host_transaction.get("Status") or "").strip().upper()
        transaction_id = (trn_identifier.get("TrnId") or "").strip()

        # if status == "SUCCESS" and transaction_id:
        #     frappe.db.set_value(
        #         "Share Application",
        #         doc.name,
        #         {
        #             "transaction_id": transaction_id,
        #             "fund_transfer_date": now_datetime(),
        #             "status": "Success",
        #             "error_log": ""
        #         },
        #         update_modified=True
        #     )
        #     frappe.db.set_single_value(
        #         "Share Application Settings", "last_transfer_run", now())
        #     frappe.db.set_single_value(
        #         "Share Application Settings", "total_debit_amount", total_debit_amount)
        #     frappe.db.commit()

        #     return {
        #         "status": "success",
        #         "message": f"Fund transfer completed successfully. Transaction ID: {transaction_id}",
        #         "transaction_id": transaction_id
        #     }

        if status == "SUCCESS" and transaction_id:
            frappe.db.set_value(
                "Share Application",
                doc.name,
                {
                    "transaction_id": transaction_id,
                    "fund_transfer_date": now_datetime(),
                    "status": "Success",
                    "error_log": ""
                },
                update_modified=True
            )

            frappe.db.set_single_value(
                "Share Application Settings", "last_transfer_run", now())
            frappe.db.set_single_value(
                "Share Application Settings", "total_debit_amount", total_debit_amount)

            submitted_doc = frappe.get_doc("Share Application", doc.name)
            if submitted_doc.docstatus == 0:
                submitted_doc.submit()

            frappe.db.commit()

            return {
                "status": "success",
                "message": f"Fund transfer completed successfully. Transaction ID: {transaction_id}",
                "transaction_id": transaction_id
            }

        error_message = response_text or "Finacle API did not return a success status."
        _set_share_application_error(doc.name, error_message)
        frappe.db.set_single_value(
            "Share Application Settings", "last_transfer_run", now())
        frappe.db.commit()
        return {
            "status": "error",
            "message": "Fund transfer failed. Error log updated in Share Application."
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(),
                         "Share Application Pay Now Failed")
        try:
            _set_share_application_error(entry_name, str(e))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        try:
            frappe.cache().delete_value(lock_name)
        except Exception:
            pass


def _set_share_application_error(docname, error_message):
    if not docname:
        return

    frappe.db.set_value(
        "Share Application",
        docname,
        {
            "error_log": (error_message or "")[:65535],
            "status": "Failed"
        },
        update_modified=True
    )


@frappe.whitelist()
def run_bulk_share_application_payment():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_fund_transfer:
        return {
            "status": "skipped",
            "message": "Fund transfer is disabled in Share Application Settings."
        }

    share_applications = frappe.get_all(
        "Share Application",
        filters={
            "status": ["!=", "Success"],
            "docstatus": 0
        },
        fields=["name", "status"]
    )

    if not share_applications:
        return {
            "status": "success",
            "message": "No pending Share Application records found for bulk payment.",
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0
        }

    processed_count = 0
    success_count = 0
    failed_count = 0
    skipped_count = 0
    result_lines = []

    for row in share_applications:
        docname = row.get("name")
        if not docname:
            skipped_count += 1
            continue

        processed_count += 1

        try:
            result = pay_now_share_application(docname)

            if isinstance(result, dict):
                result_status = (result.get("status") or "").lower()
                result_message = result.get("message") or ""

                if result_status == "success":
                    success_count += 1
                elif result_status in ("skipped", "warning"):
                    skipped_count += 1
                else:
                    failed_count += 1

                result_lines.append(f"{docname}: {result_message}")
            else:
                failed_count += 1
                result_lines.append(
                    f"{docname}: Unexpected response returned.")

        except Exception as e:
            failed_count += 1
            frappe.log_error(frappe.get_traceback(),
                             f"Bulk Share Payment Failed for {docname}")
            result_lines.append(f"{docname}: {str(e)}")

    return {
        "status": "success" if failed_count == 0 else "warning",
        "message": (
            f"Bulk payment completed. Processed: {processed_count}, "
            f"Success: {success_count}, Failed: {failed_count}, Skipped: {skipped_count}."
            + ("<br><br>" + "<br>".join(result_lines) if result_lines else "")
        ),
        "processed_count": processed_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count
    }
