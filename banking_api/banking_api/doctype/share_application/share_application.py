# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ShareApplication(Document):
    def validate(self):
        if self.docstatus == 1:
            if self.status != "Success":
                frappe.throw(
                    _("Only documents with Status = 'Success' can be submitted."))

            if not self.transaction_id:
                frappe.throw(
                    _("Transaction ID is mandatory before submission."))
