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
		if (!frm.doc.aadhar && !frm.doc.pan) {
			frm.clear_table("cif_details");
			frm.refresh_field("cif_details");
			frm.trigger("render_custom_table");
			return;
		}
		frappe.call({
			method: "banking_api.banking_api.doctype.cif_merge.cif_merge.get_cif_records",
			args: {
				aadhar: frm.doc.aadhar,
				pan: frm.doc.pan
			},
			callback: function(r) {
				frm.clear_table("cif_details");
				if (r.message && r.message.length > 0) {
					r.message.forEach(row => {
						let child = frm.add_child("cif_details");
						child.cif_id = row.cif_id;
						child.first_name = row.first_name;
						child.last_name = row.last_name;
						child.cif_creation = row.cif_creation;
						child.primary = row.primary || 0;
						child.merge = row.merge || 0;
						child.re_kyc = row.re_kyc || 0;
					});
				}
				frm.refresh_field("cif_details");
				frm.trigger("render_custom_table");
			}
		});
	},
	render_custom_table(frm) {
		if (!frm.fields_dict.merge_widget) return;
		let wrapper = $(frm.fields_dict.merge_widget.wrapper);
		wrapper.empty();

		let data = frm.doc.cif_details || [];
		
		let widget_html = `
		<div class="p-3 bg-white border rounded shadow-sm">
			<div class="d-flex justify-content-between align-items-center mb-3">
				<h6 class="m-0 font-weight-bold">CIF Deduplication & Table Control</h6>
				<input type="text" id="widget_search_input" class="form-control form-control-sm w-25" placeholder="Search token..." />
			</div>
			<div class="table-responsive">
				<table class="table table-bordered table-hover text-sm mb-0">
					<thead class="thead-light">
						<tr>
							<th>#</th>
							<th>CIF ID</th>
							<th>First Name</th>
							<th>Last Name</th>
							<th>Creation Date</th>
							<th class="text-center">Primary</th>
							<th class="text-center">Merge</th>
							<th class="text-center">Re-KYC</th>
						</tr>
					</thead>
					<tbody id="widget_table_body">
					</tbody>
				</table>
			</div>
		</div>`;

		wrapper.html(widget_html);

		function render_rows(filter_text) {
			let tbody = wrapper.find("#widget_table_body");
			tbody.empty();

			if (data.length === 0) {
				tbody.append(`<tr><td colspan="8" class="text-center text-muted">No CIF records found. Enter valid Aadhar or PAN to search.</td></tr>`);
				return;
			}

			data.forEach((row, idx) => {
				let fn = row.first_name || '';
				let ln = row.last_name || '';
				
				if (filter_text && !fn.toLowerCase().includes(filter_text) && !ln.toLowerCase().includes(filter_text) && !(row.cif_id||'').toLowerCase().includes(filter_text)) {
					return;
				}

				let tr = $(`
					<tr>
						<td>${idx + 1}</td>
						<td class="font-weight-bold">${row.cif_id || ''}</td>
						<td contenteditable="true" class="cell-fn">${fn}</td>
						<td contenteditable="true" class="cell-ln">${ln}</td>
						<td>${row.cif_creation || ''}</td>
						<td class="text-center"><input type="checkbox" class="chk-primary" ${row.primary ? 'checked' : ''} /></td>
						<td class="text-center"><input type="checkbox" class="chk-merge" ${row.merge ? 'checked' : ''} /></td>
						<td class="text-center"><input type="checkbox" class="chk-rekyc" ${row.rekyc ? 'checked' : ''} /></td>
					</tr>
				`);

				tr.find(".cell-fn").on("blur", function() {
					row.first_name = $(this).text().trim();
					frm.refresh_field("cif_details");
				});
				tr.find(".cell-ln").on("blur", function() {
					row.last_name = $(this).text().trim();
					frm.refresh_field("cif_details");
				});

				tr.find(".chk-primary").on("change", function() {
					let checked = $(this).is(":checked");
					data.forEach((r, i) => { r.primary = (i === idx && checked) ? 1 : 0; });
					if (checked) { row.merge = 0; row.rekyc = 0; }
					frm.refresh_field("cif_details");
					render_rows(filter_text);
				});

				tr.find(".chk-merge").on("change", function() {
					row.merge = $(this).is(":checked") ? 1 : 0;
					if (row.merge) { row.rekyc = 0; row.primary = 0; }
					frm.refresh_field("cif_details");
					render_rows(filter_text);
				});

				tr.find(".chk-rekyc").on("change", function() {
					row.rekyc = $(this).is(":checked") ? 1 : 0;
					if (row.rekyc) { row.merge = 0; row.primary = 0; }
					frm.refresh_field("cif_details");
					render_rows(filter_text);
				});

				tbody.append(tr);
			});
		}

		render_rows("");

		wrapper.find("#widget_search_input").on("input", function() {
			render_rows($(this).val().toLowerCase().trim());
		});
	}
});


