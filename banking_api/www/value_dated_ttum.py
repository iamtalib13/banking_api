import frappe
from frappe import _


def get_context(context):
    # Ensure user is logged in
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("You must be logged in to access this page."),
                     frappe.PermissionError)

    # Check role
    if "Value Dated TTUM User" not in frappe.get_roles(frappe.session.user):
        frappe.throw(
            _("You are not allowed to access Value Dated TTUM. Required role: {0}").format(
                frappe.bold("Value Dated TTUM User")
            ),
            frappe.PermissionError,
        )

    # Optional: customize context if needed
    context.no_cache = 1
