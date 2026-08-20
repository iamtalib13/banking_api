# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


class DatabaseIntegration(Document):
	@frappe.whitelist()
	def sync_data(self):
		"""
		Executes DB-to-DB data pipeline synchronization.
		Source Query returns rows (e.g. SELECT cif_id, pan_number AS pan FROM netwin_customers)
		Destination Query maps placeholders (e.g. UPDATE finprd_customers SET pan = %(pan)s WHERE cif_id = %(cif_id)s)
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
		records_count = 0

		try:
			# 1. Fetch data from Source Database as dictionary records
			source_conn = source_db_doc.get_connection()
			with source_conn.cursor(cursor_factory=RealDictCursor) as source_cursor:
				source_cursor.execute(self.source_query)
				dict_rows = [dict(row) for row in source_cursor.fetchall()] if source_cursor.description else []
				records_count = len(dict_rows)

			# 2. Execute Destination Query in batch mode using named placeholders %(fieldname)s
			if dict_rows and self.destination_query:
				dest_conn = dest_db_doc.get_connection()
				with dest_conn.cursor() as dest_cursor:
					execute_batch(dest_cursor, self.destination_query, dict_rows, page_size=100)
					dest_conn.commit()

			log_message = _("Successfully processed {0} record(s).").format(records_count)

			# 3. Update execution metadata
			self.db_set("last_sync_on", now_datetime())
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

			self.db_set("last_sync_on", now_datetime())
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
