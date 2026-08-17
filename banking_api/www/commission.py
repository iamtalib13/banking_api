import frappe
from frappe import _


@frappe.whitelist()
def get_commission_summary(filters=None):
    filters = frappe.parse_json(filters) if filters else []
    result = frappe.db.get_list(
        "Commission",
        filters=filters,
        fields=[
            "count(name) as total_records",
            "sum(eligible_amount) as total_eligible",
            "sum(commission_amount) as total_commission",
            "sum(net_pay) as total_net_pay",
            "sum(final_net_pay) as total_final_net_pay",
        ],
    )
    row = result[0] if result else {}
    return {
        "total_records": row.get("total_records") or 0,
        "total_eligible": row.get("total_eligible") or 0,
        "total_commission": row.get("total_commission") or 0,
        "total_net_pay": row.get("total_net_pay") or 0,
        "total_final_net_pay": row.get("total_final_net_pay") or 0,
    }


@frappe.whitelist()
def get_commission_filter_options():
    sol = frappe.db.get_list("Commission", fields=[
                             "sol_id", "sol_name"], group_by="sol_id", order_by="sol_id")
    scheme = frappe.db.get_list("Commission", fields=[
                                "scheme_code"], group_by="scheme_code", order_by="scheme_code", pluck="scheme_code")
    agent = frappe.db.get_list("Commission", fields=[
                               "agent_code"], group_by="agent_code", order_by="agent_code", pluck="agent_code")

    return {
        "sol_list": [{"value": r.sol_id, "label": f"{r.sol_id} - {r.sol_name}" if r.sol_name else r.sol_id} for r in sol],
        "scheme_list": scheme,
        "agent_list": agent,
    }
