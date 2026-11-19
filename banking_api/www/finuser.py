import re
import datetime
import frappe
from frappe import _


EXACT_SQL_QUERY = """SELECT DISTINCT
    u.user_id,
    g.emp_name,
    g.sol_id,
    u.role_id,
    upr.user_work_class,
    c.disabled_from_date,
    c.disabled_upto_date,
    p.del_flg
FROM finfadm.urm_user_role_tbl u
LEFT JOIN tbaadm."get" g
    ON u.user_id = g.emp_id
LEFT JOIN finfadm.user_creds_tbl c
    ON u.user_id = c.user_id
LEFT JOIN finfadm.user_profile_tbl p
    ON u.user_id = p.user_id
LEFT JOIN finfadm.upr_coreserver upr
    ON u.user_id = upr.user_id
WHERE p.del_flg = 'N'
  AND (
      c.disabled_from_date IS NULL
      OR c.disabled_upto_date IS NULL
      OR CURRENT_DATE NOT BETWEEN
          c.disabled_from_date::date
          AND c.disabled_upto_date::date
  )
ORDER BY
    u.user_id,
    u.role_id;"""


ALLOWED_ROLES = {
    "Operations Support Executive",
    "CBS Support Executive",
    "System Manager",
    "Administrator",
    "Branch Manager",
    "Branch Operations Manager",
    "FinUser Maker",
    "FinUser Checker"
}

ALL_BRANCH_ROLES = {
    "Operations Support Executive",
    "CBS Support Executive",
    "System Manager",
    "Administrator"
}

MAKER_ROLES = {
    "Branch Manager",
    "FinUser Maker",
    "System Manager",
    "Administrator"
}

CHECKER_ROLES = {
    "Branch Operations Manager",
    "FinUser Checker",
    "System Manager",
    "Administrator"
}

RESIGNED_ACCESS_ROLES = {"CBS Support Executive", "System Manager", "Administrator"}
ROLE_UPDATE_ACCESS_ROLES = {"CBS Support Executive", "System Manager", "Administrator"}


def check_access():
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Access Denied: Please login to access this page."), frappe.PermissionError)

    user_roles = set(frappe.get_roles(frappe.session.user))
    if frappe.session.user != "Administrator" and not (user_roles & ALLOWED_ROLES):
        frappe.throw(_("Access Denied: You do not have permission to access Finacle User Management."), frappe.PermissionError)


def can_approve_requests():
    """Checks if current logged in user has Checker permissions."""
    if frappe.session.user == "Administrator":
        return True
    user_roles = set(frappe.get_roles(frappe.session.user))
    return bool(user_roles & CHECKER_ROLES)


def can_create_deputation():
    """Checks if current logged in user has Maker permissions."""
    if frappe.session.user == "Administrator":
        return True
    user_roles = set(frappe.get_roles(frappe.session.user))
    return bool(user_roles & MAKER_ROLES)


def get_user_allowed_sol_ids():
    """
    Returns list of SOL IDs allowed for the logged in user.
    Admin and Head Office roles get None (meaning ALL branches allowed).
    Branch Managers and local users get only their mapped SOL ID(s).
    """
    if frappe.session.user == "Administrator":
        return None

    user_roles = set(frappe.get_roles(frappe.session.user))
    if user_roles & ALL_BRANCH_ROLES:
        return None

    # Fetch SOL ID mapped to user from Employee master
    emp = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        ["name", "sol_id", "branch", "sahayog_branch"],
        as_dict=True
    )

    allowed_sols = set()
    if emp:
        if emp.sol_id:
            allowed_sols.add(str(emp.sol_id).strip())
        if emp.branch:
            # Check if branch name matches sol_id or code
            sol = frappe.db.get_value("Sahayog Branch", {"name": emp.branch}, "sol_id") or frappe.db.get_value("Sahayog Branch", {"branch": emp.branch}, "sol_id")
            if sol:
                allowed_sols.add(str(sol).strip())
        if emp.sahayog_branch:
            sol = frappe.db.get_value("Sahayog Branch", {"name": emp.sahayog_branch}, "sol_id")
            if sol:
                allowed_sols.add(str(sol).strip())

    return list(allowed_sols) if allowed_sols else []


def check_role_update_access():
    check_access()
    user_roles = set(frappe.get_roles(frappe.session.user))
    if frappe.session.user != "Administrator" and not (user_roles & ROLE_UPDATE_ACCESS_ROLES):
        frappe.throw(_("Access Denied: Only CBS Support Executive can update roles."), frappe.PermissionError)


def can_update_role():
    return False


def check_resigned_access():
    check_access()
    user_roles = set(frappe.get_roles(frappe.session.user))
    if frappe.session.user != "Administrator" and not (user_roles & RESIGNED_ACCESS_ROLES):
        frappe.throw(_("Access Denied: Only CBS Support Executive or Admin can access resigned employee management."), frappe.PermissionError)


def can_manage_resigned():
    if frappe.session.user == "Administrator":
        return True
    user_roles = set(frappe.get_roles(frappe.session.user))
    return bool(user_roles & RESIGNED_ACCESS_ROLES)


def can_disable_user():
    return False


def get_finacle_dr_connection():
    from banking_api.banking_api.doctype.database_configuration.database_configuration import (
        get_db_connection,
    )
    return get_db_connection(database="Finacle Production DR", timeout=15)


def get_context(context):
    context.no_cache = 1

    check_access()
    context.can_manage_resigned = can_manage_resigned()
    context.can_update_role = can_update_role()
    context.can_disable_user = can_disable_user()
    context.can_create_deputation = can_create_deputation()
    context.can_approve_requests = can_approve_requests()

    context.is_guest = False

    # Get allowed SOL IDs for logged in user (BM gets only their branch, Admin gets None = all)
    allowed_sol_ids = get_user_allowed_sol_ids()

    # 1. Fetch Sahayog Branches from MariaDB (filtered by user's authorized branch if restricted)
    branch_query = """
        SELECT 
            sol_id AS code,
            branch AS name,
            IFNULL(zone, 'Other') AS zone,
            IFNULL(region, '') AS region,
            IFNULL(district, '') AS district
        FROM `tabSahayog Branch`
        WHERE IFNULL(sol_id, '') != ''
    """
    if allowed_sol_ids is not None:
        if not allowed_sol_ids:
            # BM has no mapped branch
            branch_query += " AND 1=0 "
            branches = frappe.db.sql(branch_query, as_dict=True)
        else:
            branch_query += " AND sol_id IN %(sols)s ORDER BY CAST(sol_id AS UNSIGNED) ASC, sol_id ASC "
            branches = frappe.db.sql(branch_query, {"sols": tuple(allowed_sol_ids)}, as_dict=True)
    else:
        branch_query += " ORDER BY CAST(sol_id AS UNSIGNED) ASC, sol_id ASC "
        branches = frappe.db.sql(branch_query, as_dict=True)

    # 2. Execute query on Finacle DR including NULL date users as active
    fin_counts = {}
    total_query_records = 0
    all_rows = []
    try:
        conn = get_finacle_dr_connection()
        cur = conn.cursor()
        cur.execute(EXACT_SQL_QUERY)
        all_rows = cur.fetchall()
        total_query_records = len(all_rows)

        for r in all_rows:
            uid = str(r[0] or "").strip()
            if uid.upper().startswith("P"):
                continue
            sol = str(r[2] or "").strip()
            if sol:
                fin_counts[sol] = fin_counts.get(sol, 0) + 1
        conn.close()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Finacle DR Exact Query Execution Failed")

    for b in branches:
        sol = str(b["code"]).strip()
        b["active_total"] = fin_counts.get(sol, 0)

    context.branches = branches
    context.total_query_records = total_query_records

    # Pass all active users for instant User View search & listing
    all_users_list = []
    branch_map = {str(b["code"]): b["name"] for b in branches}
    zone_map = {str(b["code"]): b.get("zone", "Other") for b in branches}

    for r in all_rows:
        u_id = str(r[0] or "").strip()
        if u_id.upper().startswith("P"):
            continue
        u_name = str(r[1] or "").strip() or u_id
        u_sol = str(r[2] or "").strip()
        u_role = str(r[3] or "").strip()
        u_work_class = str(r[4] or "").strip()
        all_users_list.append({
            "user_id": u_id,
            "name": u_name,
            "sol_id": u_sol,
            "branch_name": branch_map.get(u_sol, "N/A"),
            "zone": zone_map.get(u_sol, "Other"),
            "role_id": u_role,
            "work_class": u_work_class,
        })
    # Enrich with ERPNext employee ID and designation (strictly numeric emp id only, strictly exclude prefix)
    erp_emps = frappe.db.sql(
        "SELECT name, IFNULL(designation, '') AS designation FROM `tabEmployee` WHERE name REGEXP '^[0-9]+$'",
        as_dict=True,
    )
    emp_meta = {}
    for emp in erp_emps:
        raw_name = str(emp.name or "").strip()
        if raw_name.isdigit():
            emp_code = raw_name.lstrip("0")
            if emp_code:
                emp_meta[emp_code] = {"emp_id": raw_name, "designation": str(emp.designation or "")}

    for u in all_users_list:
        digits = re.sub(r"^[^\d]*0*", "", u["user_id"])
        info = emp_meta.get(digits, {})
        u["emp_id"] = info.get("emp_id", "")
        u["designation"] = info.get("designation", "")

    context.all_users = all_users_list

    return context


@frappe.whitelist()
def get_branch_users(sol_id):
    check_access()
    """
    Returns users matching sol_id directly from the exact query execution.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)

    if not sol_id:
        return {"users": [], "roles": [], "counts": {"ALL": 0}, "total": 0}

    sol_id = str(sol_id).strip()

    rows = []
    try:
        conn = get_finacle_dr_connection()
        cur = conn.cursor()
        cur.execute(EXACT_SQL_QUERY)
        all_rows = cur.fetchall()
        rows = [r for r in all_rows if str(r[2] or "").strip() == sol_id]
        conn.close()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Finacle DR Query Failed for SOL {sol_id}")
        return {"users": [], "roles": [], "counts": {"ALL": 0}, "total": 0, "error": str(e)}

    users_list = []
    roles_set = set()
    role_counts = {}

    for r in rows:
        user_id = str(r[0] or "").strip()
        if user_id.upper().startswith("P"):
            continue
        emp_name = str(r[1] or "").strip() or user_id
        solid = str(r[2] or "").strip()
        role_id = str(r[3] or "").strip()
        work_class = str(r[4] or "").strip()
        dis_from = str(r[5]) if r[5] else ""
        dis_upto = str(r[6]) if r[6] else ""
        del_flg = str(r[7] or "").strip()

        if role_id:
            roles_set.add(role_id)
            role_counts[role_id] = role_counts.get(role_id, 0) + 1

        users_list.append({
            "user_id": user_id,
            "name": emp_name,
            "sol_id": solid,
            "role_id": role_id,
            "work_class": work_class,
            "disabled_from_date": dis_from,
            "disabled_upto_date": dis_upto,
            "del_flg": del_flg,
        })

    counts = {"ALL": len(users_list)}
    counts.update(role_counts)
    sorted_roles = sorted(roles_set, key=lambda x: role_counts.get(x, 0), reverse=True)

    # Enrich with ERPNext employee designation (strictly numeric emp id only, strictly exclude prefix)
    if users_list:
        erp_emps = frappe.db.sql(
            "SELECT name, IFNULL(designation, '') AS designation FROM `tabEmployee` WHERE name REGEXP '^[0-9]+$'",
            as_dict=True,
        )
        emp_meta = {}
        for emp in erp_emps:
            raw_name = str(emp.name or "").strip()
            if raw_name.isdigit():
                emp_code = raw_name.lstrip("0")
                if emp_code:
                    emp_meta[emp_code] = str(emp.designation or "")

        for u in users_list:
            digits = re.sub(r"^[^\d]*0*", "", u["user_id"])
            u["designation"] = emp_meta.get(digits, "")

    return {
        "users": users_list,
        "roles": sorted_roles,
        "counts": counts,
        "total": len(users_list),
    }

# resign employee: Fetches all resigned employees from ERPNext and matches with Finacle Production DR users to identify those still active in Finacle.
@frappe.whitelist()
def get_resigned_employees():
    check_resigned_access()
    """
    Fetch ALL Left employees from ERPNext and match with Finacle Production DR users.
    u.user_id format e.g. SAH001754 -> non-zero digits matched with Employee name e.g. 1754.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)

    # 1. Fetch all Left employees from ERPNext
    left_emps = frappe.db.sql(
        """
        SELECT 
            name, 
            employee_name, 
            IFNULL(designation, '') AS designation, 
            IFNULL(sol_id, '') AS sol_id, 
            relieving_date, 
            IFNULL(cell_number, '') AS cell_number
        FROM `tabEmployee`
        WHERE status = 'Left'
        ORDER BY relieving_date DESC, name DESC;
        """,
        as_dict=True,
    )

    # 2. Query all Finacle Production DR users
    fin_map = {}
    today = datetime.date.today()

    try:
        conn = get_finacle_dr_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT 
                u.user_id, 
                g.emp_name, 
                g.sol_id, 
                u.role_id, 
                c.disabled_from_date, 
                c.disabled_upto_date
            FROM finfadm.urm_user_role_tbl u
            LEFT JOIN tbaadm."get" g ON u.user_id = g.emp_id
            LEFT JOIN finfadm.user_creds_tbl c ON u.user_id = c.user_id
            LEFT JOIN finfadm.user_profile_tbl p ON u.user_id = p.user_id
            WHERE p.del_flg = 'N';
            """
        )
        all_fin = cur.fetchall()
        conn.close()

        for r in all_fin:
            uid = str(r[0] or "").strip()
            # Non-zero numeric matching: e.g. SAH001754 -> 1754
            digits = re.sub(r"^[^\d]*0*", "", uid)
            if digits:
                dis_from = r[4].date() if r[4] else None
                dis_upto = r[5].date() if r[5] else None
                is_disabled = bool(dis_from and dis_upto and (dis_from <= today <= dis_upto))
                is_active = not is_disabled

                if digits not in fin_map:
                    fin_map[digits] = []
                fin_map[digits].append({
                    "user_id": uid,
                    "emp_name": r[1] or "",
                    "sol_id": r[2] or "",
                    "role_id": r[3] or "",
                    "is_active": is_active,
                })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed fetching Finacle users for Resigned Employees")

    # 3. Fetch branch names map from Sahayog Branch
    branch_rows = frappe.db.sql("SELECT sol_id, branch FROM `tabSahayog Branch` WHERE IFNULL(sol_id, '') != ''", as_dict=True)
    branch_map = {str(b.sol_id).strip(): b.branch for b in branch_rows}

    # 4. Match ONLY Left employees who are STILL ACTIVE in Finacle (Action Required)
    resigned_list = []

    for emp in left_emps:
        emp_code = str(emp.name or "").strip().lstrip("0")
        fin_users = fin_map.get(emp_code)

        if not fin_users:
            continue

        active_fin_users = [f for f in fin_users if f["is_active"]]
        if not active_fin_users:
            continue

        fin_roles = ", ".join(sorted(set(f["role_id"] for f in active_fin_users if f.get("role_id"))))
        fin_uids = ", ".join(sorted(set(f["user_id"] for f in active_fin_users)))

        sol_code = str(emp.sol_id or (active_fin_users[0].get("sol_id") if active_fin_users else "")).strip()
        branch_title = branch_map.get(sol_code, "N/A")

        resigned_list.append({
            "emp_id": emp.name,
            "name": emp.employee_name,
            "designation": emp.designation,
            "sol_id": sol_code,
            "branch_name": branch_title,
            "relieving_date": str(emp.relieving_date or ""),
            "is_finacle_active": True,
            "finacle_user_id": fin_uids,
            "finacle_roles": fin_roles,
        })

    # Sort by relieving date descending (most recent first)
    resigned_list.sort(key=lambda x: x["relieving_date"] or "0000-00-00", reverse=True)

    return {
        "employees": resigned_list,
        "total": len(resigned_list),
        "active_in_finacle_count": len(resigned_list),
    }

# get_missing_in_finacle_employees: Fetches all Active employees from ERPNext and identifies those missing in Finacle DR "get" table.
@frappe.whitelist()
def get_missing_in_finacle_employees():
    check_resigned_access()
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)

    # 1. Fetch Active employees from ERPNext (ZingHR / MySahayog)
    active_emps = frappe.db.sql(
        """
        SELECT 
            name, 
            employee_name, 
            IFNULL(designation, '') AS designation, 
            IFNULL(sol_id, '') AS sol_id, 
            date_of_joining,
            IFNULL(cell_number, '') AS cell_number
        FROM `tabEmployee`
        WHERE status = 'Active'
          AND IFNULL(department, '') NOT IN ('Teaching', 'Non - Teaching', 'Housekeeping', 'Establishment')
          AND IFNULL(branch, '') != 'Janhit'
          AND IFNULL(sol_id, '') != 'Janhit'
          AND IFNULL(sol_id, '') != ''
          AND name != 'Admin'
          AND name REGEXP '^[0-9]+$'
          AND IFNULL(custom_exclude_from_hefm, 0) = 0
        ORDER BY date_of_joining DESC, name DESC;
        """,
        as_dict=True,
    )

    # 2. Query Finacle DR tbaadm."get" table
    finacle_emp_ids = set()
    try:
        conn = get_finacle_dr_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT emp_id, entity_cre_flg, del_flg, sol_id, emp_name, emp_short_name
            FROM tbaadm."get"
            WHERE emp_id LIKE '%SAH%'
              AND del_flg = 'N';
            """
        )
        rows = cur.fetchall()
        conn.close()

        for r in rows:
            uid = str(r[0] or "").strip()
            # extract numeric part for matching: SAH00483 -> 483
            digits = re.sub(r"^[^\d]*0*", "", uid)
            if digits:
                finacle_emp_ids.add(digits)
            finacle_emp_ids.add(uid)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed fetching Finacle get table for Missing Employees")

    # 3. Fetch branch names map
    branch_rows = frappe.db.sql("SELECT sol_id, branch FROM `tabSahayog Branch` WHERE IFNULL(sol_id, '') != ''", as_dict=True)
    branch_map = {str(b.sol_id).strip(): b.branch for b in branch_rows}

    # 4. Filter employees missing in Finacle
    missing_list = []
    for emp in active_emps:
        raw_id = str(emp.name or "").strip()
        digits = re.sub(r"^[^\d]*0*", "", raw_id)
        # Expected finacle id with SAH0
        expected_fin_id = f"SAH0{digits.zfill(4)}" if digits else f"SAH0{raw_id}"

        # Match check by normalized digits or raw_id
        if digits not in finacle_emp_ids and raw_id not in finacle_emp_ids and expected_fin_id not in finacle_emp_ids:
            sol_code = str(emp.sol_id or "").strip()
            branch_title = branch_map.get(sol_code, "")
            missing_list.append({
                "emp_id": raw_id,
                "expected_fin_id": expected_fin_id,
                "emp_name": emp.employee_name,
                "designation": emp.designation,
                "sol_id": sol_code,
                "branch_name": branch_title,
                "date_of_joining": str(emp.date_of_joining or ""),
                "cell_number": emp.cell_number,
            })

    return {
        "employees": missing_list,
        "total": len(missing_list),
    }



# update_user_role: Updates user role in Finacle database table finfadm.urm_user_role_tbl.
@frappe.whitelist()
def update_user_role(user_id, old_role, new_role):
    check_role_update_access()

    if not user_id or not new_role:
        frappe.throw(_("User ID and new role are required."))

    user_id = str(user_id).strip()
    new_role = str(new_role).strip()
    old_role = str(old_role or "").strip()

    from banking_api.banking_api.doctype.database_configuration.database_configuration import (
        get_db_connection,
    )

    conn = None
    try:
        if frappe.db.exists("Database Configuration", {"database": "Finacle Production"}):
            conn = get_db_connection(database="Finacle Production", timeout=15)
        elif frappe.db.exists("Database Configuration", {"name": "Finacle Production"}):
            conn = get_db_connection(name="Finacle Production", timeout=15)
        else:
            conn = get_finacle_dr_connection()

        cur = conn.cursor()
        if old_role:
            # role id updation query with old_role in WHERE clause to ensure correct update
            cur.execute(
                "UPDATE finfadm.urm_user_role_tbl SET role_id = %s WHERE user_id = %s AND role_id = %s",
                (new_role, user_id, old_role),
            )
        else:
            # role id updation query without old_role in WHERE clause (for cases where old_role is unknown)
            cur.execute(
                "UPDATE finfadm.urm_user_role_tbl SET role_id = %s WHERE user_id = %s",
                (new_role, user_id),
            )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": _("Role updated to {0} for user {1}.").format(new_role, user_id),
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Update Finacle Role Failed for {user_id}")
        return {
            "status": "error",
            "message": _("Failed to update role: {0}").format(str(e)),
        }


# disable_finacle_user: Disables user login in Finacle database table finfadm.user_creds_tbl.
@frappe.whitelist()
def disable_finacle_user(user_id, emp_id=None):
    """
    Disable user in Finacle Production database by setting:
    disabled_from_date = CURRENT_TIMESTAMP, disabled_upto_date = TIMESTAMP '2099-11-09 00:00:00.000'
    Uses Database Configuration: 'Finacle Production' (or falls back to DR if not configured)
    """
    check_resigned_access()

    if not user_id:
        frappe.throw(_("Finacle User ID is required."))

    user_id = str(user_id).strip()

    from banking_api.banking_api.doctype.database_configuration.database_configuration import (
        get_db_connection,
    )

    conn = None
    try:
        # Check if writable 'Finacle Production' configuration exists, else use available Finacle config
        if frappe.db.exists("Database Configuration", {"database": "Finacle Production"}):
            conn = get_db_connection(database="Finacle Production", timeout=15)
        elif frappe.db.exists("Database Configuration", {"name": "Finacle Production"}):
            conn = get_db_connection(name="Finacle Production", timeout=15)
        else:
            conn = get_finacle_dr_connection()

        cur = conn.cursor()
        # deactivation query: disables user in Finacle
        query = """
            UPDATE finfadm.user_creds_tbl
            SET
                disabled_from_date = CURRENT_TIMESTAMP,
                disabled_upto_date = TIMESTAMP '2099-11-09 00:00:00.000'
            WHERE user_id = %s;
        """
        cur.execute(query, (user_id,))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": _("User {0} successfully disabled in Finacle.").format(user_id)
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Disable Finacle User Failed for {user_id}")
        return {
            "status": "error",
            "message": _("Failed to update Finacle database: {0}").format(str(e))
        }


# create_deputation_request: BM creates temporary deputation request in Employee finuser_items child table.
@frappe.whitelist()
def create_deputation_request(user_id, current_sol_id, depute_sol_id, from_date, to_date, remarks=None):
    """
    Creates a new Deputation item under Employee.finuser_items child table.
    """
    check_access()

    if not can_create_deputation():
        frappe.throw(_("Permission Denied: Only Branch Manager or authorized FinUser Maker can initiate deputation."), frappe.PermissionError)

    allowed_sols = get_user_allowed_sol_ids()
    if allowed_sols is not None and str(current_sol_id).strip() not in allowed_sols:
        frappe.throw(_("Permission Denied: You can only depute users from your authorized branch ({0}).").format(", ".join(allowed_sols)), frappe.PermissionError)

    if not user_id or not current_sol_id or not depute_sol_id or not from_date or not to_date:
        frappe.throw(_("Please provide all required fields: User ID, Current SOL, Depute SOL, From Date, and To Date."))

    if current_sol_id == depute_sol_id:
        frappe.throw(_("Depute SOL ID cannot be identical to Current SOL ID."))

    if str(to_date) < str(from_date):
        frappe.throw(_("To Date cannot be before From Date."))

    emp_name = _get_employee_by_user_id(user_id)
    if not emp_name:
        frappe.throw(_("No active Employee record found linked to Finacle User {0}.").format(user_id))

    emp_doc = frappe.get_doc("Employee", emp_name)
    emp_doc.append("finuser_items", {
        "action_type": "Deputation",
        "status": "Pending Checker Approval",
        "current_sol_id": current_sol_id,
        "depute_sol_id": depute_sol_id,
        "from_date": from_date,
        "to_date": to_date,
        "remarks": remarks,
        "maker_id": frappe.session.user,
        "maker_datetime": frappe.utils.now_datetime(),
    })
    emp_doc.save(ignore_permissions=True)

    return {
        "status": "success",
        "employee": emp_doc.name,
        "message": _("Deputation request for {0} submitted to Checker for approval.").format(emp_doc.employee_name or user_id)
    }


# approve_finuser_item: BOM approves pending deputation, validates maker!=checker, and updates SOL in Finacle.
@frappe.whitelist()
def approve_finuser_item(employee, row_name, remarks=None):
    """
    Approves a pending FinUser item row in Employee child table.
    """
    check_access()

    if not can_approve_requests():
        frappe.throw(_("Permission Denied: Only Branch Operations Manager (BOM) or authorized FinUser Checker can approve requests."), frappe.PermissionError)

    emp_doc = frappe.get_doc("Employee", employee)
    row = next((r for r in emp_doc.finuser_items if r.name == row_name), None)
    if not row:
        frappe.throw(_("FinUser item row not found."))

    if row.status != "Pending Checker Approval":
        frappe.throw(_("Only pending items can be approved."))

    if frappe.session.user == row.maker_id:
        frappe.throw(_("Maker and Checker cannot be the same user."))

    row.checker_id = frappe.session.user
    row.checker_datetime = frappe.utils.now_datetime()
    row.checker_remarks = remarks
    row.status = "Active" if row.action_type == "Deputation" else "Approved"

    if row.action_type == "Deputation":
        finacle_user_id = emp_doc.user_id or emp_doc.name
        _update_finacle_sol(
            user_id=finacle_user_id,
            target_sol=row.depute_sol_id,
            current_sol=row.current_sol_id,
            action="Deputation"
        )

    emp_doc.save(ignore_permissions=True)
    return {"status": "success", "message": _("Request approved successfully.")}


# reject_finuser_item: BOM rejects pending deputation with mandatory remarks, ensuring maker!=checker.
@frappe.whitelist()
def reject_finuser_item(employee, row_name, remarks):
    """
    Rejects a pending FinUser item row in Employee child table.
    """
    check_access()

    if not can_approve_requests():
        frappe.throw(_("Permission Denied: Only Branch Operations Manager (BOM) or authorized FinUser Checker can reject requests."), frappe.PermissionError)

    if not remarks:
        frappe.throw(_("Remarks are required to reject."))

    emp_doc = frappe.get_doc("Employee", employee)
    row = next((r for r in emp_doc.finuser_items if r.name == row_name), None)
    if not row:
        frappe.throw(_("FinUser item row not found."))

    if row.status != "Pending Checker Approval":
        frappe.throw(_("Only pending items can be rejected."))

    if frappe.session.user == row.maker_id:
        frappe.throw(_("Maker and Checker cannot be the same user."))

    row.checker_id = frappe.session.user
    row.checker_datetime = frappe.utils.now_datetime()
    row.checker_remarks = remarks
    row.status = "Rejected"

    emp_doc.save(ignore_permissions=True)
    return {"status": "success", "message": _("Request rejected.")}


# reverse_deputation_item: Manually reverts active deputation early and restores base SOL ID in Finacle.
@frappe.whitelist()
def reverse_deputation_item(employee, row_name, remarks=None):
    """
    Manually reverses an active deputation and restores base SOL ID.
    """
    check_access()

    emp_doc = frappe.get_doc("Employee", employee)
    row = next((r for r in emp_doc.finuser_items if r.name == row_name), None)
    if not row or row.action_type != "Deputation" or row.status != "Active":
        frappe.throw(_("Only active deputations can be reversed."))

    row.is_reversed = 1
    row.reversal_date = frappe.utils.now_datetime()
    row.status = "Reversed"
    if remarks:
        row.remarks = (row.remarks or "") + f"\nReversal Remark: {remarks}"

    finacle_user_id = emp_doc.user_id or emp_doc.name
    _update_finacle_sol(
        user_id=finacle_user_id,
        target_sol=row.current_sol_id,
        current_sol=row.depute_sol_id,
        action="Reversal"
    )

    emp_doc.save(ignore_permissions=True)
    return {"status": "success", "message": _("Deputation reversed and base SOL restored.")}


# _get_employee_by_user_id: Helper to find Employee document name from Finacle user ID.
def _get_employee_by_user_id(user_id):
    """Finds Frappe Employee doc name mapped to user_id."""
    emp = frappe.db.get_value("Employee", {"user_id": user_id}, "name")
    if emp:
        return emp
    emp = frappe.db.get_value("Employee", {"name": user_id}, "name")
    if emp:
        return emp
    return frappe.db.get_value("Employee", {"status": "Active"}, "name")


# _update_finacle_sol: Executes DBA query UPDATE tbaadm.upr SET sol_id = %s WHERE user_id = %s AND sol_id = %s in Finacle.
def _update_finacle_sol(user_id, target_sol, current_sol=None, action="Update"):
    """
    Executes SOL update query in Finacle DB as per DBA recommendation:
    UPDATE tbaadm.upr SET sol_id = %s WHERE user_id = %s AND sol_id = %s;
    """
    if not user_id or not target_sol:
        return

    from banking_api.banking_api.doctype.database_configuration.database_configuration import get_db_connection
    # dabase_name = "Finacle Production"
    db_config = frappe.db.get_value(
        "Database Configuration",
        {"database_name": ["in", ["Finacle", "postgres", "finfadm"]]},
        "name"
    ) or frappe.db.get_value("Database Configuration", {}, "name")

    if not db_config:
        frappe.log_error(f"No Database Configuration found. Skipped {action} for {user_id}", f"Finacle {action} DB Config Missing")
        return

    conn = None
    try:
        conn = get_db_connection(name=db_config, timeout=15)
        cur = conn.cursor()
        # If current_sol is provided, use it in WHERE clause; else update based on user_id only
        # deputation / SOL update query (DBA approved): updates user sol_id in Finacle (tbaadm.upr)
        if current_sol:
            query = "UPDATE tbaadm.upr SET sol_id = %s WHERE user_id = %s AND sol_id = %s;"
            cur.execute(query, (str(target_sol).strip(), str(user_id).strip(), str(current_sol).strip()))
        else:
            query = "UPDATE tbaadm.upr SET sol_id = %s WHERE user_id = %s;"
            cur.execute(query, (str(target_sol).strip(), str(user_id).strip()))

        conn.commit()
        conn.close()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        frappe.log_error(frappe.get_traceback(), f"Finacle {action} failed for {user_id}")
        frappe.throw(_("Failed to update SOL in Finacle: {0}").format(str(e)))


# process_deputation_daily_scheduler: Daily cron to send 3-day advance alerts and auto-revert expired deputations back to base SOL.
def process_deputation_daily_scheduler():
    """
    Daily Cron Scheduler:
    1. 3-day advance alert for expiring deputations in FinUser Items
    2. Auto-expire and auto-revert deputations whose to_date has passed
    """
    from frappe.utils import add_days, getdate, today

    current_date = getdate(today())
    reminder_date = add_days(current_date, 3)

    # 1. 3-day advance reminder, fetch all active deputations expiring in 3 days and notify maker/checker via real-time message
    expiring_items = frappe.db.sql("""
        SELECT item.name as row_name, item.parent as employee, emp.employee_name, emp.user_id,
               item.depute_sol_id, item.current_sol_id, item.to_date, item.maker_id, item.checker_id
        FROM `tabFinUser Items` item
        JOIN `tabEmployee` emp ON item.parent = emp.name
        WHERE item.action_type = 'Deputation'
          AND item.status = 'Active'
          AND item.to_date = %s
          AND item.is_reversed = 0
    """, (reminder_date,), as_dict=True)

    for req in expiring_items:
        msg = f"Deputation for {req.employee_name or req.user_id} at SOL {req.depute_sol_id} will expire in 3 days ({req.to_date})."
        recipients = list(filter(None, [req.maker_id, req.checker_id]))
        for u in recipients:
            frappe.publish_realtime("msgprint", msg, user=u)

    # 2. Auto-expiry & auto-revert, reversal of expired deputations back to base SOL
    expired_items = frappe.db.sql("""
        SELECT item.name as row_name, item.parent as employee, emp.user_id, item.current_sol_id, item.depute_sol_id
        FROM `tabFinUser Items` item
        JOIN `tabEmployee` emp ON item.parent = emp.name
        WHERE item.action_type = 'Deputation'
          AND item.status = 'Active'
          AND item.to_date < %s
          AND item.is_reversed = 0
    """, (current_date,), as_dict=True)

    for exp in expired_items:
        try:
            emp_doc = frappe.get_doc("Employee", exp.employee)
            row = next((r for r in emp_doc.finuser_items if r.name == exp.row_name), None)
            if row:
                row.status = "Expired"
                row.is_reversed = 1
                row.reversal_date = frappe.utils.now_datetime()
                row.remarks = (row.remarks or "") + "\nAuto-expired and reverted by scheduler."
                _update_finacle_sol(
                    user_id=exp.user_id or exp.employee,
                    target_sol=exp.current_sol_id,
                    current_sol=exp.depute_sol_id,
                    action="Auto-Reversal"
                )
                emp_doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Auto-revert failed for employee {exp.employee}")


# get_pending_approvals: Fetches pending deputation requests for Checker review on same page
@frappe.whitelist()
def get_pending_approvals():
    check_access()
    if not can_approve_requests():
        return {"requests": [], "total": 0}

    allowed_sols = get_user_allowed_sol_ids()

    query = """
        SELECT 
            item.name as row_name,
            item.parent as employee,
            emp.employee_name,
            emp.user_id,
            item.current_sol_id,
            item.depute_sol_id,
            item.from_date,
            item.to_date,
            item.remarks,
            item.maker_id,
            item.maker_datetime,
            item.creation
        FROM `tabFinUser Items` item
        JOIN `tabEmployee` emp ON item.parent = emp.name
        WHERE item.action_type = 'Deputation'
          AND item.status = 'Pending Checker Approval'
    """
    if allowed_sols is not None:
        if not allowed_sols:
            return {"requests": [], "total": 0}
        query += " AND (item.current_sol_id IN %(sols)s OR item.depute_sol_id IN %(sols)s) "
        query += " ORDER BY item.creation DESC "
        rows = frappe.db.sql(query, {"sols": tuple(allowed_sols)}, as_dict=True)
    else:
        query += " ORDER BY item.creation DESC "
        rows = frappe.db.sql(query, as_dict=True)

    return {
        "requests": rows,
        "total": len(rows)
    }




