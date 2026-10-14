frappe.listview_settings['CIF Merge'] = {
	get_indicator: function(doc) {
		if (doc.status === "Active") {
			return [__("Active"), "green", "status,=,Active"];
		} else {
			return [__("Inactive"), "red", "status,=,Inactive"];
		}
	},
	formatters: {
		status: function(val) {
			if (val === "Active") {
				return `<span class="indicator-pill green">${__("Active")}</span>`;
			} else {
				return `<span class="indicator-pill red">${__("Inactive")}</span>`;
			}
		},
		cif_status: function(val) {
			if (val === "Completed") {
				return `<span class="indicator-pill green font-weight-bold">${__("Completed")}</span>`;
			} else {
				return `<span class="indicator-pill orange font-weight-bold">${__("Pending")}</span>`;
			}
		}
	}
};
