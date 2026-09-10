# # Copyright (c) 2026, Talib Sheikh and contributors
# # For license information, please see license.txt

# import frappe
# from frappe import _
# from frappe.model.document import Document
# from frappe.utils import flt


# class CommissionPayment(Document):
#     def validate(self):
#         self.validate_payment_reference()
#         self.calculate_final_netpay()

#     def validate_payment_reference(self):
#         if self.payment_type not in ("Normal", "Deferred"):
#             frappe.throw(
#                 _("Payment Type must be Normal or Deferred")
#             )

#         if not self.agent_code:
#             frappe.throw(
#                 _("Agent Code is required")
#             )

#         if not self.agent_operative_account:
#             frappe.throw(
#                 _("Agent Operative Account is required")
#             )

#         if not self.payment_year or self.payment_year <= 0:
#             frappe.throw(
#                 _("Payment Year must be greater than zero")
#             )

#         if not self.due_date:
#             frappe.throw(
#                 _("Due Date is required")
#             )

#         # Deferred payment must point to one exact Commission record
#         # and one exact source child schedule row.
#         if self.payment_type == "Deferred":
#             if not self.commission:
#                 frappe.throw(
#                     _("Commission is required for Deferred payment")
#                 )

#             if not self.source_deferred_detail:
#                 frappe.throw(
#                     _("Source Deferred Detail is required for Deferred payment")
#                 )

#             existing_payment = frappe.db.exists(
#                 "Commission Payment",
#                 {
#                     "commission": self.commission,
#                     "payment_type": "Deferred",
#                     "payment_year": self.payment_year,
#                     "docstatus": ("<", 2),
#                 },
#             )

#             if existing_payment and existing_payment != self.name:
#                 frappe.throw(
#                     _(
#                         "Deferred Commission Payment already exists for "
#                         "Commission {0}, Payment Year {1}"
#                     ).format(
#                         self.commission,
#                         self.payment_year,
#                     )
#                 )

#         # Normal payment is consolidated agent-wise.
#         # It may intentionally have no single Commission Link.
#         elif self.payment_type == "Normal":
#             existing_payment = frappe.db.exists(
#                 "Commission Payment",
#                 {
#                     "agent_code": self.agent_code,
#                     "payment_type": "Normal",
#                     "due_date": self.due_date,
#                     "docstatus": ("<", 2),
#                 },
#             )

#             if existing_payment and existing_payment != self.name:
#                 frappe.throw(
#                     _(
#                         "Normal Commission Payment already exists for "
#                         "Agent {0} and Due Date {1}"
#                     ).format(
#                         self.agent_code,
#                         self.due_date,
#                     )
#                 )

#     def calculate_final_netpay(self):
#         gross_commission = flt(self.gross_commission)
#         tds_amount = flt(self.tds_amount)
#         security_deposit_amount = flt(self.security_deposit_amount)
#         deduction_amount = flt(self.deduction_amount)

#         calculated_netpay = (
#             gross_commission
#             - tds_amount
#             - security_deposit_amount
#         )

#         # Preserve the source value when it has been supplied.
#         # Otherwise calculate it from Gross - TDS - Security Deposit.
#         if self.netpay_amount in (None, ""):
#             self.netpay_amount = calculated_netpay

#         self.final_netpay = (
#             flt(self.netpay_amount)
#             - deduction_amount
#         )

#         if flt(self.final_netpay) < 0:
#             frappe.throw(
#                 _("Final Net Pay cannot be negative")
#             )

############################################################################################################################


# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt
import random
from datetime import datetime

import frappe
import requests
import xmltodict

from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now, now_datetime
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout, Timeout
from frappe.utils import cint, flt, now, now_datetime


class CommissionPayment(Document):
    def validate(self):
        self.validate_required_payment_fields()
        self.calculate_final_netpay()

    def validate_required_payment_fields(self):
        if self.payment_type not in ("Normal", "Deferred"):
            frappe.throw(
                _("Payment Type must be Normal or Deferred")
            )

        if not self.agent_code:
            frappe.throw(
                _("Agent Code is required")
            )

        if not self.agent_operative_account:
            frappe.throw(
                _("Agent Operative Account is required")
            )

        if not self.payment_year or self.payment_year <= 0:
            frappe.throw(
                _("Payment Year must be greater than zero")
            )

        if not self.due_date:
            frappe.throw(
                _("Due Date is required")
            )

        if self.payment_type == "Deferred":
            if not self.commission:
                frappe.throw(
                    _("Commission is required for Deferred payment")
                )

            if not self.source_deferred_detail:
                frappe.throw(
                    _("Source Deferred Detail is required for Deferred payment")
                )

            existing_payment = frappe.db.exists(
                "Commission Payment",
                {
                    "commission": self.commission,
                    "payment_type": "Deferred",
                    "payment_year": self.payment_year,
                    "docstatus": ("<", 2),
                },
            )

            if existing_payment and existing_payment != self.name:
                frappe.throw(
                    _(
                        "Deferred Commission Payment already exists for "
                        "Commission {0}, Payment Year {1}"
                    ).format(
                        self.commission,
                        self.payment_year,
                    )
                )

        if self.payment_type == "Normal":
            existing_payment = frappe.db.exists(
                "Commission Payment",
                {
                    "agent_code": self.agent_code,
                    "payment_type": "Normal",
                    "due_date": self.due_date,
                    "docstatus": ("<", 2),
                },
            )

            if existing_payment and existing_payment != self.name:
                frappe.throw(
                    _(
                        "Normal Commission Payment already exists for "
                        "Agent {0}, Due Date {1}"
                    ).format(
                        self.agent_code,
                        self.due_date,
                    )
                )

    def calculate_final_netpay(self):
        gross_commission = flt(self.gross_commission)
        tds_amount = flt(self.tds_amount)
        security_deposit_amount = flt(self.security_deposit_amount)
        deduction_amount = flt(self.deduction_amount)

        calculated_netpay = (
            gross_commission
            - tds_amount
            - security_deposit_amount
        )

        if self.netpay_amount in (None, ""):
            self.netpay_amount = calculated_netpay

        self.final_netpay = flt(self.netpay_amount) - deduction_amount

        if flt(self.final_netpay) < 0:
            frappe.throw(
                _("Final Net Pay cannot be negative")
            )


def _get_commission_settings():
    settings = frappe.get_single("Commission Settings")

    if not settings.enable_commission_payment:
        return settings, {
            "allowed": False,
            "message": "Commission payment is disabled in Commission Settings.",
        }

    if not settings.finacle_api_url:
        frappe.throw(
            _("Finacle API URL is mandatory in Commission Settings.")
        )

    if not settings.debit_account_number:
        frappe.throw(
            _("Debit Account Number is mandatory in Commission Settings.")
        )

    return settings, {
        "allowed": True,
        "message": "",
    }


def _update_commission_payment_failure(payment_doc, error_message):
    """
    Save failure details without submitting or cancelling the document.
    """
    payment_doc.payment_status = "Failed"
    payment_doc.failure_reason = error_message
    payment_doc.retry_count = int(payment_doc.retry_count or 0) + 1

    payment_doc.save(ignore_permissions=True)
    frappe.db.commit()


def _build_commission_transfer_xml(
    debit_account,
    credit_account,
    amount,
    settings,
    payment_doc,
):
    current_date = datetime.now().strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3]

    request_uuid = random.randint(1000000000, 9999999999)

    debit_particulars = (
        settings.debit_particulars
        or "Commission Payment Debited"
    )

    credit_particulars = (
        settings.credit_particulars
        or "Agent Commission Credited"
    )

    # transaction_type = settings.transaction_type or "T"
    # transaction_sub_type = settings.transaction_sub_type or "CI"
    # bank_id = settings.bank_id or "01"
    # channel_id = settings.channel_id or "COR"
    transaction_type = "T"
    transaction_sub_type = "CI"
    bank_id = "01"
    channel_id = "COR"

    payment_reference = (
        f"Commission Payment {payment_doc.name} "
        f"Agent {payment_doc.agent_code}"
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FIXML xsi:schemaLocation="http://www.finacle.com/fixml XferTrnAdd.xsd"
       xmlns="http://www.finacle.com/fixml"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Header>
        <RequestHeader>
            <MessageKey>
                <RequestUUID>{request_uuid}</RequestUUID>
                <ServiceRequestId>XferTrnAdd</ServiceRequestId>
                <ServiceRequestVersion>10.2</ServiceRequestVersion>
                <ChannelId>{channel_id}</ChannelId>
                <LanguageId></LanguageId>
            </MessageKey>
            <RequestMessageInfo>
                <BankId>{bank_id}</BankId>
                <TimeZone></TimeZone>
                <EntityId></EntityId>
                <EntityType></EntityType>
                <ArmCorrelationId>{payment_doc.name}</ArmCorrelationId>
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
                    <TrnType>{transaction_type}</TrnType>
                    <TrnSubType>{transaction_sub_type}</TrnSubType>
                </XferTrnHdr>
                <XferTrnDetail>

                    <PartTrnRec>
                        <AcctId>
                            <AcctId>{debit_account}</AcctId>
                        </AcctId>
                        <CreditDebitFlg>D</CreditDebitFlg>
                        <TrnAmt>
                            <amountValue>{amount:.2f}</amountValue>
                            <currencyCode>INR</currencyCode>
                        </TrnAmt>
                        <TrnParticulars>{debit_particulars}</TrnParticulars>
                        <PartTrnRmks>{payment_reference}</PartTrnRmks>
                        <ValueDt>{current_date}</ValueDt>
                    </PartTrnRec>

                    <PartTrnRec>
                        <AcctId>
                            <AcctId>{credit_account}</AcctId>
                        </AcctId>
                        <CreditDebitFlg>C</CreditDebitFlg>
                        <TrnAmt>
                            <amountValue>{amount:.2f}</amountValue>
                            <currencyCode>INR</currencyCode>
                        </TrnAmt>
                        <TrnParticulars>{credit_particulars}</TrnParticulars>
                        <PartTrnRmks>{payment_reference}</PartTrnRmks>
                        <ValueDt>{current_date}</ValueDt>
                    </PartTrnRec>

                </XferTrnDetail>
            </XferTrnAddRq>
        </XferTrnAddRequest>
    </Body>
</FIXML>"""


def _parse_finacle_transfer_response(response_text):
    """
    Return normalised Finacle response values.
    """
    try:
        response_dict = xmltodict.parse(response_text)
    except Exception as e:
        return {
            "success": False,
            "transaction_id": "",
            "status": "ERROR",
            "message": f"Unable to parse Finacle response: {str(e)}",
        }

    fixml = response_dict.get("FIXML", {}) or {}
    header = fixml.get("Header", {}) or {}
    response_header = header.get("ResponseHeader", {}) or {}
    host_transaction = response_header.get("HostTransaction", {}) or {}

    body = fixml.get("Body", {}) or {}
    transfer_response = body.get("XferTrnAddResponse", {}) or {}
    transfer_result = transfer_response.get("XferTrnAddRs", {}) or {}
    transaction_identifier = transfer_result.get("TrnIdentifier", {}) or {}

    status = str(host_transaction.get("Status") or "").strip().upper()
    transaction_id = str(
        transaction_identifier.get("TrnId") or ""
    ).strip()

    if status == "SUCCESS" and transaction_id:
        return {
            "success": True,
            "transaction_id": transaction_id,
            "status": status,
            "message": "Finacle transaction completed successfully.",
        }

    return {
        "success": False,
        "transaction_id": transaction_id,
        "status": status or "FAILED",
        "message": response_text or "Finacle API did not return a success status.",
    }


@frappe.whitelist()
def pay_now_commission_payment(payment_name):
    """
    Execute one Finacle transfer.

    Debit:
        Commission Settings.debit_account_number

    Credit:
        Commission Payment.agent_operative_account

    Amount:
        Commission Payment.final_netpay
    """
    if not payment_name:
        frappe.throw(
            _("Commission Payment document name is required.")
        )

    payment_doc = frappe.get_doc("Commission Payment", payment_name)
    lock_name = f"commission_payment_pay_now::{payment_doc.name}"

    if payment_doc.docstatus == 2:
        frappe.throw(
            _("Cancelled Commission Payment cannot be processed.")
        )

    # if payment_doc.payment_status == "Paid":
    #     return {
    #         "status": "warning",
    #         "message": _("This Commission Payment is already paid."),
    #         "transaction_id": payment_doc.transaction_id,
    #     }

    # if payment_doc.payment_status == "Processing":
    #     return {
    #         "status": "warning",
    #         "message": _("This Commission Payment is already processing."),
    #     }

    if payment_doc.payment_status == "Paid":
        return {
            "status": "warning",
            "message": _("This Commission Payment is already paid."),
            "transaction_id": payment_doc.transaction_id,
        }

    if payment_doc.payment_status == "Processing":
        return {
            "status": "warning",
            "message": _("This Commission Payment is already processing."),
        }

    if payment_doc.payment_status not in ("Pending", "Due", "Failed"):
        return {
            "status": "warning",
            "message": _(
                "Payment cannot be processed with status: {0}"
            ).format(payment_doc.payment_status),
        }

    if not payment_doc.agent_operative_account:
        frappe.throw(
            _("Agent Operative Account is required.")
        )

    payment_amount = flt(payment_doc.final_netpay)

    if payment_amount <= 0:
        frappe.throw(
            _("Final Net Pay must be greater than zero.")
        )

    settings, control = _get_commission_settings()

    if not control["allowed"]:
        return {
            "status": "skipped",
            "message": control["message"],
        }

    try:
        if frappe.cache().get_value(lock_name):
            frappe.throw(
                _("A payment is already in progress for this Commission Payment.")
            )

        frappe.cache().set_value(
            lock_name,
            frappe.session.user,
            expires_in_sec=180,
        )

    except frappe.ValidationError:
        raise
    except Exception:
        pass

    try:
        # Mark processing before calling external bank API.
        payment_doc.payment_status = "Processing"
        payment_doc.payment_initiated_on = now_datetime()
        payment_doc.failure_reason = ""
        payment_doc.save(ignore_permissions=True)
        frappe.db.commit()

        debit_account = str(
            settings.debit_account_number
        ).strip()

        credit_account = str(
            payment_doc.agent_operative_account
        ).strip()

        xml_data = _build_commission_transfer_xml(
            debit_account=debit_account,
            credit_account=credit_account,
            amount=payment_amount,
            settings=settings,
            payment_doc=payment_doc,
        )

        # connect_timeout = int(settings.connection_timeout or 10)
        # read_timeout = int(settings.read_timeout or 30)
        connect_timeout = cint(
            getattr(settings, "connection_timeout", None) or 10
        )

        read_timeout = cint(
            getattr(settings, "read_timeout", None) or 30
        )

        ssl_verify = cint(
            getattr(settings, "ssl_verify", 0)
        )

        try:
            response = requests.post(
                settings.finacle_api_url,
                data=xml_data.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
                # verify=bool(settings.ssl_verify),
                # timeout=(connect_timeout, read_timeout),
                verify=bool(ssl_verify),
                # verify=False,
                timeout=(10, 30),
            )

            response.raise_for_status()

        except (Timeout, ReadTimeout):
            error_message = (
                "Finacle API timeout occurred. Transaction status is unknown; "
                "verify in Finacle before retrying."
            )

            _update_commission_payment_failure(
                payment_doc,
                error_message,
            )

            return {
                "status": "error",
                "message": error_message,
            }

        except ConnectionError:
            error_message = (
                "Unable to connect to Finacle API. "
                "Check network/API availability before retrying."
            )

            _update_commission_payment_failure(
                payment_doc,
                error_message,
            )

            return {
                "status": "error",
                "message": error_message,
            }

        except HTTPError:
            error_message = (
                f"Finacle API returned HTTP "
                f"{getattr(response, 'status_code', 'error')}. "
                f"Response: {getattr(response, 'text', '')}"
            )

            _update_commission_payment_failure(
                payment_doc,
                error_message,
            )

            return {
                "status": "error",
                "message": "Finacle API returned an error response.",
            }

        response_text = response.text or ""

        parsed_response = _parse_finacle_transfer_response(
            response_text
        )

        if parsed_response["success"]:
            payment_doc = frappe.get_doc(
                "Commission Payment",
                payment_doc.name,
            )

            payment_doc.payment_status = "Paid"
            payment_doc.transaction_id = parsed_response["transaction_id"]
            payment_doc.payment_initiated_on = (
                payment_doc.payment_initiated_on or now_datetime()
            )
            payment_doc.paid_on = now_datetime()
            payment_doc.failure_reason = ""

            payment_doc.save(ignore_permissions=True)

            frappe.db.set_single_value(
                "Commission Settings",
                "last_payment_run",
                now(),
            )

            frappe.db.commit()

            return {
                "status": "success",
                "message": _(
                    "Commission payment completed successfully. "
                    "Transaction ID: {0}"
                ).format(
                    parsed_response["transaction_id"]
                ),
                "transaction_id": parsed_response["transaction_id"],
                "payment_name": payment_doc.name,
                "amount": payment_amount,
            }

        _update_commission_payment_failure(
            payment_doc,
            parsed_response["message"],
        )

        return {
            "status": "error",
            "message": _(
                "Commission payment failed. Error details are saved in the document."
            ),
            "transaction_id": parsed_response["transaction_id"],
        }

    except Exception:
        error_message = frappe.get_traceback()

        frappe.log_error(
            error_message,
            f"Commission Payment API Error - {payment_doc.name}",
        )

        try:
            _update_commission_payment_failure(
                payment_doc,
                error_message,
            )
        except Exception:
            frappe.db.rollback()

        return {
            "status": "error",
            "message": _(
                "Commission payment failed. Check Error Log and Failure Reason."
            ),
        }

    finally:
        try:
            frappe.cache().delete_value(lock_name)
        except Exception:
            pass


@frappe.whitelist()
def run_bulk_commission_payment(payment_names=None):
    """
    Execute Finacle payment one Commission Payment at a time.

    Only processes selected payment document names.
    Each payment calls pay_now_commission_payment(), so every record
    receives its own lock, API request, response status, and transaction ID.
    """
    frappe.only_for(("System Manager",))

    payment_names = (
        frappe.parse_json(payment_names)
        if isinstance(payment_names, str)
        else (payment_names or [])
    )

    if not payment_names:
        frappe.throw(
            _("Select at least one Commission Payment record.")
        )

    payment_names = list(dict.fromkeys(payment_names))

    processed_count = 0
    success_count = 0
    failed_count = 0
    skipped_count = 0
    results = []

    for payment_name in payment_names:
        processed_count += 1

        try:
            result = pay_now_commission_payment(payment_name)

            result_status = str(
                result.get("status") or "error"
            ).lower()

            if result_status == "success":
                success_count += 1
            elif result_status in ("warning", "skipped"):
                skipped_count += 1
            else:
                failed_count += 1

            results.append({
                "payment_name": payment_name,
                "status": result_status,
                "message": result.get("message", ""),
                "transaction_id": result.get("transaction_id", ""),
            })

        except Exception:
            failed_count += 1

            traceback = frappe.get_traceback()

            frappe.log_error(
                traceback,
                f"Bulk Commission Payment Failed - {payment_name}",
            )

            results.append({
                "payment_name": payment_name,
                "status": "error",
                "message": "Unhandled error. Check Error Log.",
                "transaction_id": "",
            })

    frappe.db.set_single_value(
        "Commission Settings",
        "last_payment_run",
        now(),
    )
    frappe.db.commit()

    return {
        "status": "success" if failed_count == 0 else "warning",
        "message": _(
            "Bulk commission payment completed. Processed: {0}, "
            "Success: {1}, Failed: {2}, Skipped: {3}."
        ).format(
            processed_count,
            success_count,
            failed_count,
            skipped_count,
        ),
        "processed_count": processed_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "results": results,
    }
