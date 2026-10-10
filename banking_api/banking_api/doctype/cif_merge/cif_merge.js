frappe.ui.form.on("CIF Merge", {
	refresh(frm) {
		frm.trigger("render_custom_table");
	},
	aadhar(frm) {
		frm.trigger("fetch_cifs");
	},
	pan(frm) {
		frm.trigger("fetch_cifs");
	},
	fetch_cifs(frm) {
		if (!frm.doc.aadhar && !frm.doc.pan) return;
		frappe.call({
			method: "banking_api.banking_api.doctype.cif_merge.cif_merge.get_cif_records",
			args: {
				aadhar: frm.doc.aadhar,
				pan: frm.doc.pan
			},
			callback: function(r) {
				if (r.message) {
					frm.clear_table("cif_details");
					r.message.forEach(row => {
						let child = frm.add_child("cif_details");
						child.cif_id = row.cif_id;
						child.first_name = row.first_name;
						child.last_name = row.last_name;
						child.cif_creation = row.cif_creation;
					});
					frm.refresh_field("cif_details");
					frm.trigger("render_custom_table");
				}
			}
		});
	},
	render_custom_table(frm) {
		if (!frm.fields_dict.merge_widget) return;
		let wrapper = $(frm.fields_dict.merge_widget.wrapper);
		wrapper.empty();

		// Custom HTML layout rendering from doc.cif_details
		let data = frm.doc.cif_details || [];
		let html = `<div class="p-2 border rounded bg-light">
			<h5>CIF Deduplication & Table Control</h5>
			<table class="table table-bordered table-sm bg-white">
				<thead>
					<tr>
						<th>CIF ID</th>
						<th>First Name</th>
						<th>Last Name</th>
						<th>Creation Date</th>
						<th>Primary</th>
						<th>Merge</th>
						<th>Re-KYC</th>
					</tr>
				</thead>
				<tbody>`;

		if (data.length === 0) {
			html += `<tr><td colspan="7" class="text-center text-muted">No CIF records found. Fill Aadhar or PAN to search.</td></tr>`;
		} else {
			data.forEach((row, idx) => {
				html += `<tr>
					<td>${row.cif_id || ''}</td>
					<td>${row.first_name || ''}</td>
					<td>${row.last_name || ''}</td>
					<td>${row.cif_creation || ''}</td>
					<td><input type="checkbox" ${row.primary ? 'checked' : ''} disabled /></td>
					<td><input type="checkbox" ${row.merge ? 'checked' : ''} disabled /></td>
					<td><input type="checkbox" ${row.re_kyc ? 'checked' : ''} disabled /></td>
				</tr>`;
			});
		}

		html += `</tbody></table></div>`;
		wrapper.html(html);
	}
});

