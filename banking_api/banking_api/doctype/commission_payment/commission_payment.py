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
        if not self.commission:
            frappe.throw(_("Commission is required"))

        if self.payment_type not in ("Normal", "Deferred"):
            frappe.throw(
                _("Payment Type must be Normal or Deferred")
            )

        if not self.payment_year or self.payment_year <= 0:
            frappe.throw(
                _("Payment Year must be greater than zero")
            )

        if not self.due_date:
            frappe.throw(
                _("Due Date is required")
            )

        if self.payment_type == "Deferred" and not self.source_deferred_detail:
            frappe.throw(
                _("Source Deferred Detail is required for Deferred payment")
            )

        duplicate_filters = {
            "commission": self.commission,
            "payment_type": self.payment_type,
            "payment_year": self.payment_year,
            "docstatus": ("<", 2),
        }

        existing_payment = frappe.db.exists(
            "Commission Payment",
            duplicate_filters,
        )

        if existing_payment and existing_payment != self.name:
            frappe.throw(
                _(
                    "Commission Payment already exists for Commission {0}, "
                    "Payment Type {1}, Payment Year {2}"
                ).format(
                    self.commission,
                    self.payment_type,
                    self.payment_year,
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

        if not self.netpay_amount:
            self.netpay_amount = calculated_netpay

        self.final_netpay = (
            flt(self.netpay_amount)
            - deduction_amount
        )

        if flt(self.final_netpay) < 0:
            frappe.throw(
                _("Final Net Pay cannot be negative")
            )
