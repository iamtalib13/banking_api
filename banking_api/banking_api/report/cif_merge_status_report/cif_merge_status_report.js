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
		} else if (column.fieldname === "cif_type") {
			if (data.cif_type === "Primary") {
				value = `<span class="badge badge-success px-2 py-0.5">${__("PRIMARY")}</span>`;
			} else if (data.cif_type === "Merge") {
				value = `<span class="badge px-2 py-0.5" style="background-color: #9333ea; color: white;">${__("MERGE")}</span>`;
			} else if (data.cif_type === "Re-KYC") {
				value = `<span class="badge badge-warning px-2 py-0.5">${__("RE-KYC")}</span>`;
			}
		} else if (column.fieldname === "pan") {
			if (data.pan) {
				value = `<span class="badge badge-light border text-monospace font-weight-bold">${data.pan}</span>`;
			}
		} else if (column.fieldname === "pin_code") {
			if (data.pin_code) {
				value = `<span class="badge badge-light border font-weight-bold">${data.pin_code}</span>`;
			}
		}
		return value;
	},
	"onload": function(report) {
		// Hide Frappe standard Actions dropdown button
		let hide_actions_interval = setInterval(() => {
			let $actions = report.page.wrapper.find('.actions-btn-group, [data-label="Actions"]');
			if ($actions.length) {
				$actions.attr('style', 'display: none !important');
			}
		}, 50);
		setTimeout(() => clearInterval(hide_actions_interval), 2000);
	}
		
};
