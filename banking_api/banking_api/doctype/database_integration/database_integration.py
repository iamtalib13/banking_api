# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import psycopg2
import frappe
from frappe import _
from frappe.model.document import Document


class DatabaseIntegration(Document):
	@frappe.whitelist()
	def sync_data(self):
		"""
		Executes manual data synchronization from source database to destination database.
		"""
		if not self.source_database:
			frappe.throw(_("Please select a Source Database."))

		if not self.destination_database:
			frappe.throw(_("Please select a Destination Database."))

		if not self.source_query:
			frappe.throw(_("Please specify a Source Query."))

		source_db_doc = frappe.get_doc("Database Configuration", self.source_database)
		dest_db_doc = frappe.get_doc("Database Configuration", self.destination_database)

		source_conn = None
		dest_conn = None

		try:
			# Connect to Source Database
			source_conn = source_db_doc.get_connection()
			with source_conn.cursor() as source_cursor:
				source_cursor.execute(self.source_query)
				rows = source_cursor.fetchall() if source_cursor.description else []

			# Connect to Destination Database
			dest_conn = dest_db_doc.get_connection()
			with dest_conn.cursor() as dest_cursor:
				if self.destination_query:
					if "%s" in self.destination_query and rows:
						dest_cursor.executemany(self.destination_query, rows)
					else:
						dest_cursor.execute(self.destination_query)
				dest_conn.commit()

			return _("Data synchronization completed successfully. Processed {0} records.").format(len(rows))

		except Exception as e:
			if dest_conn:
				dest_conn.rollback()
			frappe.throw(_("Database Sync failed: {0}").format(str(e)))

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
