import frappe
from frappe.tests.utils import FrappeTestCase
from banking_api.banking_api.doctype.database_integration.database_integration import DatabaseIntegration


class TestDatabaseIntegration(FrappeTestCase):
	def test_render_query_dynamic_dates(self):
		doc = frappe.new_doc("Database Integration")
		doc.source_query = "SELECT * FROM tbl WHERE created_on >= '{{ days_ago(3) }}' AND created_on <= '{{ today }}'"
		
		rendered = doc.render_query(doc.source_query)
		expected_date_from = frappe.utils.add_days(frappe.utils.today(), -3)
		expected_date_to = frappe.utils.today()

		self.assertIn(expected_date_from, rendered)
		self.assertIn(expected_date_to, rendered)
		self.assertEqual(rendered, f"SELECT * FROM tbl WHERE created_on >= '{expected_date_from}' AND created_on <= '{expected_date_to}'")

	def test_render_query_helpers(self):
		doc = frappe.new_doc("Database Integration")
		query = "SELECT * FROM tbl WHERE d >= '{{ add_days(today, -5) }}'"
		rendered = doc.render_query(query)
		expected_date = frappe.utils.add_days(frappe.utils.today(), -5)
		self.assertEqual(rendered, f"SELECT * FROM tbl WHERE d >= '{expected_date}'")

	def test_render_query_without_templates(self):
		doc = frappe.new_doc("Database Integration")
		query = "SELECT cust_id, pan FROM accounts WHERE active = 1"
		rendered = doc.render_query(query)
		self.assertEqual(rendered, query)

