import frappe
from frappe.model.document import Document


class CIFMerge(Document):
	def validate(self):
		if not self.aadhar and not self.pan:
			frappe.throw("Kripya Aadhar ya PAN me se kam se kam ek field fill karein search karne ke liye.")

		# Agar user ne child table me already data edit/add kiya hai, to use overwrite mat karo
		if not self.cif_details and (self.aadhar or self.pan):
			records = get_cif_records(self.aadhar, self.pan)
			if records:
				for r in records:
					self.append("cif_details", {
						"cif_id": r.get("cif_id"),
						"first_name": r.get("first_name"),
						"middle_name": r.get("middle_name"),
						"last_name": r.get("last_name"),
						"cif_creation": r.get("cif_creation"),
						"date_of_birth": r.get("date_of_birth"),
						"mobile": r.get("mobile"),
						"adress": r.get("adress"),
						"sol_id": r.get("sol_id"),
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
		{
			"cif_id": "CIF-100234",
			"first_name": "Rahul",
			"middle_name": "Kumar",
			"last_name": "Sharma",
			"cif_creation": "2024-01-15",
			"date_of_birth": "1992-05-12",
			"mobile": "9876543210",
			"adress": "123, Civil Lines, Jaipur",
			"sol_id": "SOL-001",
			"primary": 1,
			"merge": 0,
			"re_kyc": 0
		},
		{
			"cif_id": "CIF-100235",
			"first_name": "Rahul",
			"middle_name": "K",
			"last_name": "Verma",
			"cif_creation": "2024-02-20",
			"date_of_birth": "1992-05-12",
			"mobile": "9876543211",
			"adress": "45, MG Road, Indore",
			"sol_id": "SOL-002",
			"primary": 0,
			"merge": 1,
			"re_kyc": 0
		},
		{
			"cif_id": "CIF-100289",
			"first_name": "Aman",
			"middle_name": "",
			"last_name": "Sharma",
			"cif_creation": "2024-03-05",
			"date_of_birth": "1995-08-20",
			"mobile": "9812345678",
			"adress": "88, Ring Road, Delhi",
			"sol_id": "SOL-001",
			"primary": 0,
			"merge": 0,
			"re_kyc": 1
		},
		{
			"cif_id": "CIF-100312",
			"first_name": "Aman",
			"middle_name": "Singh",
			"last_name": "Singh",
			"cif_creation": "2024-04-12",
			"date_of_birth": "1990-11-15",
			"mobile": "9898989898",
			"adress": "12, Park Street, Kolkata",
			"sol_id": "SOL-003",
			"primary": 0,
			"merge": 1,
			"re_kyc": 0
		},
		{
			"cif_id": "CIF-100450",
			"first_name": "Priya",
			"middle_name": "",
			"last_name": "Patel",
			"cif_creation": "2024-05-18",
			"date_of_birth": "1998-01-25",
			"mobile": "9765432109",
			"adress": "502, Sky Tower, Ahmedabad",
			"sol_id": "SOL-004",
			"primary": 0,
			"merge": 0,
			"re_kyc": 0
		}
	]

	return test_data





