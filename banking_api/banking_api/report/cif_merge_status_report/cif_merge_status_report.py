# Copyright (c) 2026, Antigravity and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data)
	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{
			"label": _("Date"),
			"fieldname": "action_date",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Aadhaar Number"),
			"fieldname": "aadhar",
			"fieldtype": "Link",
			"options": "CIF Merge",
			"width": 150
		},
		{
			"label": _("CIF Status"),
			"fieldname": "cif_status",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("Total CIFs"),
			"fieldname": "total_cif_count",
			"fieldtype": "Int",
			"width": 90
		},
		{
			"label": _("Primary CIF"),
			"fieldname": "primary_cif",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("Merged CIFs"),
			"fieldname": "merged_cifs",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": _("Re-KYC CIFs"),
			"fieldname": "rekyc_cifs",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Action Taken By"),
			"fieldname": "modified_by",
			"fieldtype": "Data",
			"width": 180
		}
	]


def get_data(filters):
	conditions = ["m.cif_status IN ('Approved', 'Rejected', 'No Action Needed')"]
	values = {}

	if filters.get("from_date"):
		conditions.append("DATE(m.modified) >= %(from_date)s")
		values["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("DATE(m.modified) <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	if filters.get("cif_status"):
		conditions.append("m.cif_status = %(cif_status)s")
		values["cif_status"] = filters.get("cif_status")

	where_clause = " AND ".join(conditions)

	sql = f"""
		SELECT
			DATE(m.modified) as action_date,
			m.aadhar,
			m.cif_status,
			m.total_cif_count,
			m.modified_by,
			MAX(CASE WHEN d.primary = 1 THEN d.cif_id END) as primary_cif,
			GROUP_CONCAT(DISTINCT CASE WHEN d.merge = 1 THEN d.cif_id END ORDER BY d.cif_id SEPARATOR ', ') as merged_cifs,
			GROUP_CONCAT(DISTINCT CASE WHEN d.re_kyc = 1 THEN d.cif_id END ORDER BY d.cif_id SEPARATOR ', ') as rekyc_cifs
		FROM `tabCIF Merge` m
		LEFT JOIN `tabCIF Details` d ON d.parent = m.name
		WHERE {where_clause}
		GROUP BY m.name, DATE(m.modified), m.aadhar, m.cif_status, m.total_cif_count, m.modified_by
		ORDER BY DATE(m.modified) DESC, m.modified DESC
	"""

	return frappe.db.sql(sql, values, as_dict=True)


def get_report_summary(data):
	approved = sum(1 for r in data if r.get("cif_status") == "Approved")
	rejected = sum(1 for r in data if r.get("cif_status") == "Rejected")
	no_action = sum(1 for r in data if r.get("cif_status") == "No Action Needed")

	return [
		{
			"value": approved,
			"label": _("Approved"),
			"datatype": "Int",
			"indicator": "Green"
		},
		{
			"value": rejected,
			"label": _("Rejected"),
			"datatype": "Int",
			"indicator": "Red"
		},
		{
			"value": no_action,
			"label": _("No Action Needed"),
			"datatype": "Int",
			"indicator": "Blue"
		},
		{
			"value": len(data),
			"label": _("Total Processed"),
			"datatype": "Int",
			"indicator": "Gray"
		}
	]


def get_chart(data):
	if not data:
		return None

	date_status_map = {}
	for r in data:
		d_str = str(r.get("action_date"))
		st = r.get("cif_status")
		if d_str not in date_status_map:
			date_status_map[d_str] = {"Approved": 0, "Rejected": 0, "No Action Needed": 0}
		if st in date_status_map[d_str]:
			date_status_map[d_str][st] += 1

	labels = sorted(list(date_status_map.keys()))[-10:]  # last 10 dates
	approved_data = [date_status_map[d]["Approved"] for d in labels]
	rejected_data = [date_status_map[d]["Rejected"] for d in labels]
	no_action_data = [date_status_map[d]["No Action Needed"] for d in labels]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Approved"), "values": approved_data},
				{"name": _("Rejected"), "values": rejected_data},
				{"name": _("No Action Needed"), "values": no_action_data}
			]
		},
		"type": "bar",
		"colors": ["#16a34a", "#dc2626", "#2563eb"]
	}
