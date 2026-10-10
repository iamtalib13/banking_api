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
	if not aadhar and not pan:
		return []

	# Mock testing data: only return data for valid sample test values
	valid_aadhar_samples = ["123456789012", "787654321098", "1234"]
	valid_pan_samples = ["ABCDE1234F", "XYZPS9876Q", "ABCDE"]

	a_match = aadhar and any(s in aadhar for s in valid_aadhar_samples)
	p_match = pan and any(s in pan for s in valid_pan_samples)

	if not (a_match or p_match):
		return []

	test_data = [
		{"cif_id": "CIF-100234", "first_name": "Rahul", "last_name": "Sharma", "cif_creation": "2024-01-15", "primary": 1, "merge": 0, "re_kyc": 0},
		{"cif_id": "CIF-100235", "first_name": "Rahul", "last_name": "Verma",  "cif_creation": "2024-02-20", "primary": 0, "merge": 1, "re_kyc": 0},
		{"cif_id": "CIF-100289", "first_name": "Aman",  "last_name": "Sharma", "cif_creation": "2024-03-05", "primary": 0, "merge": 0, "re_kyc": 1},
		{"cif_id": "CIF-100312", "first_name": "Aman",  "last_name": "Singh",  "cif_creation": "2024-04-12", "primary": 0, "merge": 1, "re_kyc": 0},
		{"cif_id": "CIF-100450", "first_name": "Priya", "last_name": "Patel",  "cif_creation": "2024-05-18", "primary": 0, "merge": 0, "re_kyc": 0}
	]

	return test_data




