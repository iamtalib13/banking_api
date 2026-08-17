import frappe


def _build_conditions(filters):
    """filters: list of [fieldname, operator, value]"""
    conditions = []
    values = {}
    for i, f in enumerate(filters or []):
        fieldname, operator, value = f[0], f[1], f[2]
        key = f"val{i}"
        if operator.lower() == "like":
            conditions.append(f"`{fieldname}` LIKE %({key})s")
            values[key] = f"%{value}%"
        else:
            conditions.append(f"`{fieldname}` = %({key})s")
            values[key] = value
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, values


@frappe.whitelist()
def get_commission_summary(filters=None):
    filters = frappe.parse_json(filters) if filters else []
    where_clause, values = _build_conditions(filters)

    row = frappe.db.sql(
        f"""
        SELECT
            COUNT(name) AS total_records,
            COALESCE(SUM(CAST(NULLIF(TRIM(eligible_amount), '') AS DECIMAL(18,2))), 0) AS total_eligible,
            COALESCE(SUM(CAST(NULLIF(TRIM(commission_amount), '') AS DECIMAL(18,2))), 0) AS total_commission,
            COALESCE(SUM(CAST(NULLIF(TRIM(netpay), '') AS DECIMAL(18,2))), 0) AS total_netpay,
            COALESCE(SUM(CAST(NULLIF(TRIM(security_deposit), '') AS DECIMAL(18,2))), 0) AS total_security_deposit
        FROM `tabCommission`
        WHERE {where_clause}
        """,
        values,
        as_dict=True,
    )

    result = row[0] if row else {}
    return {
        "total_records": result.get("total_records") or 0,
        "total_eligible": float(result.get("total_eligible") or 0),
        "total_commission": float(result.get("total_commission") or 0),
        "total_netpay": float(result.get("total_netpay") or 0),
        "total_security_deposit": float(result.get("total_security_deposit") or 0),
    }


@frappe.whitelist()
def get_commission_filter_options():
    sol = frappe.db.get_list(
        "Commission",
        fields=["sol_id", "sol_description"],
        group_by="sol_id",
        order_by="sol_id",
    )
    scheme = frappe.db.get_list(
        "Commission",
        fields=["scheme_code"],
        group_by="scheme_code",
        order_by="scheme_code",
        pluck="scheme_code",
    )
    agent = frappe.db.get_list(
        "Commission",
        fields=["agent_code"],
        group_by="agent_code",
        order_by="agent_code",
        pluck="agent_code",
    )

    return {
        "sol_list": [
            {
                "value": r.sol_id,
                "label": f"{r.sol_id} - {r.sol_description}" if r.sol_description else str(r.sol_id),
            }
            for r in sol
            if r.sol_id
        ],
        "scheme_list": [s for s in scheme if s],
        "agent_list": [a for a in agent if a],
    }
