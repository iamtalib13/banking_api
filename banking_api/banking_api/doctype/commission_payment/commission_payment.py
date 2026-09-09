# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CommissionPayment(Document):
    def validate(self):
        self.validate_payment_reference()
        self.calculate_final_netpay()

    def validate_payment_reference(self):
        if self.payment_type not in ("Normal", "Deferred"):
            frappe.throw(
                _("Payment Type must be Normal or Deferred")
            )

        if not self.agent_code:
            frappe.throw(
                _("Agent Code is required")
            )

        if not self.payment_year or self.payment_year <= 0:
            frappe.throw(
                _("Payment Year must be greater than zero")
            )

        if not self.due_date:
            frappe.throw(
                _("Due Date is required")
            )

        # Deferred payment must point to one exact Commission record
        # and one exact source child schedule row.
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

        # Normal payment is consolidated agent-wise.
        # It may intentionally have no single Commission Link.
        elif self.payment_type == "Normal":
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
                        "Agent {0} and Due Date {1}"
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

        # Preserve the source value when it has been supplied.
        # Otherwise calculate it from Gross - TDS - Security Deposit.
        if self.netpay_amount in (None, ""):
            self.netpay_amount = calculated_netpay

        self.final_netpay = (
            flt(self.netpay_amount)
            - deduction_amount
        )

        if flt(self.final_netpay) < 0:
            frappe.throw(
                _("Final Net Pay cannot be negative")
            )
