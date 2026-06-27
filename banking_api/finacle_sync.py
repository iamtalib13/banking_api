import frappe
from frappe import _

@frappe.whitelist()
def sync_employees_to_finacle():
    """
    Cron Job function to sync new Employee records to Finacle via direct SQL INSERT.
    Only syncs records where custom_finacle_synced = 0.
    """
    try:
        import psycopg2
    except ImportError:
        frappe.logger().error("psycopg2 is not installed. Cannot sync to Finacle.")
        return

    # Fetch only new employees
    employees = frappe.get_all(
        "Employee",
        filters={"custom_finacle_synced": 0},
        fields=["name", "employee_name", "first_name", "last_name", "user_id", "company_email", "personal_email"]
    )
    
    if not employees:
        frappe.logger().info("Finacle Sync: No new employees found to sync.")
        return

    # Fetch Database Credentials
    settings = frappe.get_single("Finacle DB Credentials")
    host = (settings.db_host or "").strip()
    port = settings.db_port
    user = (settings.db_user or "").strip()
    password = settings.get_password("db_password")
    db_name = (settings.db_name or "").strip()

    if not all([host, port, user, password, db_name]):
        frappe.logger().error("Finacle DB Credentials are incomplete.")
        return

    connection = None
    cursor = None

    try:
        # Establish DB Connection
        connection = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db_name,
        )
        cursor = connection.cursor()

        for emp in employees:
            finacle_emp_id = f"SAH0{emp.name}"
            
            # Map values according to the required query
            emp_name = emp.employee_name[:50] if emp.employee_name else ""
            emp_short_name = emp.first_name[:15] if emp.first_name else emp_name[:15]
            email = emp.company_email or emp.personal_email or None

            # Prepare the INSERT query
            insert_query = """
            INSERT INTO tbaadm."get"
            (emp_id, entity_cre_flg, del_flg, emp_intls, sol_id, emp_name, emp_short_name, 
             emp_sign_power_num, emp_sign_power_amt, emp_desig, emp_stat, tot_mod_times, 
             lchg_user_id, lchg_time, rcre_user_id, rcre_time, is_head_teller, ts_cnt, 
             emp_email_id, alt1_emp_name, alt1_emp_short_name)
            VALUES
            (%s, 'Y', 'N', NULL, '1042', %s, %s, 
             0, 0.0000, NULL, NULL, 0, 
             'SYSTEM', NOW(), 'SYSTEM', NOW(), 'N', 1, 
             %s, NULL, NULL)
            """

            # Values tuple for psycopg2
            query_values = (
                finacle_emp_id,       # emp_id
                emp_name,             # emp_name
                emp_short_name,       # emp_short_name
                email                 # emp_email_id
            )

            try:
                # Execute the query
                cursor.execute(insert_query, query_values)
                
                # Update status in Frappe
                frappe.db.set_value("Employee", emp.name, "custom_finacle_synced", 1)
                frappe.db.commit() # Commit Frappe changes for this employee
                
                log_sync_attempt(emp.name, finacle_emp_id, query_values, {"status": "success", "message": "Record inserted to DB"}, "Success")

            except Exception as e:
                connection.rollback() # Rollback Finacle DB transaction for this failed insert
                error_msg = str(e)
                log_sync_attempt(emp.name, finacle_emp_id, query_values, {"error": error_msg}, "Failed")

        # Commit all successful inserts to Finacle DB
        connection.commit()

    except psycopg2.Error as exc:
        frappe.logger().error(f"Finacle DB connection failed: {str(exc)}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def log_sync_attempt(employee, finacle_emp_id, request_data, response_data, status):
    """
    Creates an entry in 'Finacle EDR Sync Log' tracking table
    """
    doc = frappe.get_doc({
        "doctype": "Finacle EDR Sync Log",
        "employee": employee,
        "finacle_employee_id": finacle_emp_id,
        "request_data": frappe.as_json(request_data),
        "response_data": frappe.as_json(response_data),
        "status": status,
        "sync_time": frappe.utils.now()
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
