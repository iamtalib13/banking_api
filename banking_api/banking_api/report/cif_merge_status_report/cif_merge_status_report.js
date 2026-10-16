// Copyright (c) 2026, Antigravity and contributors
// For license information, please see license.txt

frappe.query_reports["CIF Merge Status Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "cif_status",
			"label": __("CIF Status"),
			"fieldtype": "Select",
			"options": "\nApproved\nRejected\nNo Action Needed"
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "cif_status") {
			if (data.cif_status === "Approved") {
				value = `<span class="indicator-pill green font-weight-bold">${__("Approved")}</span>`;
			} else if (data.cif_status === "Rejected") {
				value = `<span class="indicator-pill red font-weight-bold">${__("Rejected")}</span>`;
			} else if (data.cif_status === "No Action Needed") {
				value = `<span class="indicator-pill blue font-weight-bold">${__("No Action Needed")}</span>`;
			}
		}
		return value;
	}
};
