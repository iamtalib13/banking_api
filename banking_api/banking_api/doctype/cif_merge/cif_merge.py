import frappe
from frappe.model.document import Document


class CIFMerge(Document):
	def validate(self):
		if not self.aadhar and not self.pan:
			frappe.throw("Kripya Aadhar ya PAN me se kam se kam ek field fill karein search karne ke liye.")

		if self.aadhar or self.pan:
			records = get_cif_records(self.aadhar, self.pan)
			if records:
				self.set("cif_details", [])
				for r in records:
					self.append("cif_details", {
						"cif_id": r.get("cif_id"),
						"first_name": r.get("first_name"),
						"last_name": r.get("last_name"),
						"cif_creation": r.get("cif_creation"),
						"primary": r.get("primary", 0),
						"merge": r.get("merge", 0),
						"re_kyc": r.get("re_kyc", 0)
					})


@frappe.whitelist()
def get_cif_records(aadhar=None, pan=None):
	filters = {}
	if aadhar:
		filters["aadhar"] = aadhar
	if pan:
		filters["pan"] = pan

	if not filters:
		return []

	# Share Application table me se matching CIF records fetch kar rahe hain
	return frappe.get_all(
		"Share Application",
		filters=filters,
		fields=["cif as cif_id", "first_name", "last_name", "creation as cif_creation"]
	)

