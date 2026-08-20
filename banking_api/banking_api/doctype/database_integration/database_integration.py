# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import json
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


class DatabaseIntegration(Document):
	@frappe.whitelist()
	def preview_source_data(self):
		"""
		Fetches up to 10 sample records from Source Database using source_query for testing.
		"""
		if not self.source_database:
			frappe.throw(_("Please select a Source Database."))

		if not self.source_query:
			frappe.throw(_("Please specify a Source Query."))

		source_db_doc = frappe.get_doc("Database Configuration", self.source_database)
		conn = None

		try:
			conn = source_db_doc.get_connection()
			with conn.cursor(cursor_factory=RealDictCursor) as cursor:
				cursor.execute(self.source_query)
				rows = cursor.fetchmany(10) if cursor.description else []
				return [dict(row) for row in rows]
		except Exception as e:
			frappe.throw(_("Source DB Preview failed: {0}").format(str(e)))
		finally:
			if conn:
				try:
					conn.close()
				except Exception:
					pass

	@frappe.whitelist()
	def sync_data(self):
		"""
		Executes DB-to-DB data pipeline synchronization and logs audit request in Database Request.
		"""
		if not self.source_database:
			frappe.throw(_("Please select a Source Database."))

		if not self.destination_database:
			frappe.throw(_("Please select a Destination Database."))

		if not self.source_query:
			frappe.throw(_("Please specify a Source Query."))

		if not self.destination_query:
			frappe.throw(_("Please specify a Destination Query."))

		source_db_doc = frappe.get_doc("Database Configuration", self.source_database)
		dest_db_doc = frappe.get_doc("Database Configuration", self.destination_database)

		source_conn = None
		dest_conn = None
		dict_rows = []
		records_count = 0
		execution_time = now_datetime()

		try:
			# 1. Fetch data from Source Database as dictionary records
			source_conn = source_db_doc.get_connection()
			with source_conn.cursor(cursor_factory=RealDictCursor) as source_cursor:
				source_cursor.execute(self.source_query)
				dict_rows = [dict(row) for row in source_cursor.fetchall()] if source_cursor.description else []
				records_count = len(dict_rows)

			# 2. Execute Destination Query in batch mode
			if dict_rows and self.destination_query:
				dest_conn = dest_db_doc.get_connection()
				with dest_conn.cursor() as dest_cursor:
					execute_batch(dest_cursor, self.destination_query, dict_rows, page_size=100)
					dest_conn.commit()

			log_message = _("Successfully processed {0} record(s).").format(records_count)

			# 3. Format payload with Sr. No. for audit logging
			formatted_payload = [
				{"sr_no": idx + 1, "values": row}
				for idx, row in enumerate(dict_rows)
			]

			# 4. Create Database Request Document as Audit Log
			db_request = frappe.get_doc({
				"doctype": "Database Request",
				"database_integration": self.name,
				"source_database": self.source_database,
				"destination_database": self.destination_database,
				"execution_datetime": execution_time,
				"records_count": records_count,
				"status": "Success",
				"synced_payload": json.dumps(formatted_payload, indent=2, default=str),
				"error_log": log_message
			})
			db_request.insert(ignore_permissions=True)

			# 5. Update execution metadata on Database Integration
			self.db_set("last_sync_on", execution_time)
			self.db_set("last_sync_status", "Success")
			self.db_set("records_processed", records_count)
			self.db_set("last_sync_log", log_message)

			return log_message

		except Exception as e:
			err_msg = str(e)
			if dest_conn:
				try:
					dest_conn.rollback()
				except Exception:
					pass

			formatted_payload = [
				{"sr_no": idx + 1, "values": row}
				for idx, row in enumerate(dict_rows)
			] if dict_rows else []

			# Log failure in Database Request Document
			try:
				db_request = frappe.get_doc({
					"doctype": "Database Request",
					"database_integration": self.name,
					"source_database": self.source_database,
					"destination_database": self.destination_database,
					"execution_datetime": execution_time,
					"records_count": records_count,
					"status": "Failed",
					"synced_payload": json.dumps(formatted_payload, indent=2, default=str),
					"error_log": err_msg
				})
				db_request.insert(ignore_permissions=True)
			except Exception:
				pass

			self.db_set("last_sync_on", execution_time)
			self.db_set("last_sync_status", "Failed")
			self.db_set("last_sync_log", err_msg)

			frappe.throw(_("Data Pipeline Sync failed: {0}").format(err_msg))

		finally:
			if source_conn:
				try:
					source_conn.close()
				except Exception:
					pass
			if dest_conn:
				try:
					dest_conn.close()
				except Exception:
					pass
