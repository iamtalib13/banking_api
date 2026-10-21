import frappe
from frappe import _
from banking_api.banking_api.doctype.database_configuration.database_configuration import get_db_connection


@frappe.whitelist()
def update_cif_assignment(auth_id: str, cif_id: str) -> dict:
	"""
	Fetch personid for the given auth_id and assign it to the CIF in crmuser.accounts_mod.
	"""
	if not auth_id or not cif_id:
		frappe.throw(_("Both Auth ID and CIF ID are required."))

	auth_id = str(auth_id).strip()
	cif_id = str(cif_id).strip()

	conn = None
	cursor = None

	try:
		conn = get_db_connection(database="Finacle Production")
		cursor = conn.cursor()

		# Step 1: Retrieve person ID
		fetch_query = "SELECT personid FROM crmuser.users WHERE loginid = %s"
		cursor.execute(fetch_query, (auth_id,))
		row = cursor.fetchone()

		if not row or not row[0]:
			return {
				"status": "error",
				"message": _("No Person ID found for Auth ID: {0}").format(auth_id)
			}

		person_id = str(row[0]).strip()

		# Step 2: Update assignment in crmuser.accounts_mod
		update_query = "UPDATE crmuser.accounts_mod SET assignedto = %s WHERE orgkey = %s"
		cursor.execute(update_query, (person_id, cif_id))
		rows_updated = cursor.rowcount
		conn.commit()

		return {
			"status": "success",
			"person_id": person_id,
			"cif_id": cif_id,
			"rows_updated": rows_updated,
			"message": _("CIF {0} has been successfully assigned to Person ID {1}.").format(cif_id, person_id)
		}

	except Exception as exc:
		if conn:
			conn.rollback()
		frappe.log_error(title="CIF Assignment Error", message=frappe.get_traceback())
		frappe.throw(_("Database operation failed: {0}").format(str(exc)))

	finally:
		if cursor:
			cursor.close()
		if conn:
			conn.close()


