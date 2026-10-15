frappe.listview_settings['CIF Merge'] = {
	get_indicator: function(doc) {
		if (doc.cif_status === "Completed") {
			return [__("Completed"), "green", "cif_status,=,Completed"];
		} else {
			return [__("Pending"), "orange", "cif_status,=,Pending"];
		}
	}
};
