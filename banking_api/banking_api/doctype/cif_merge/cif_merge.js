frappe.ui.form.on("CIF Merge", {
	refresh(frm) {
		frm.trigger("render_custom_table");
	},
	cif_details_on_form_rendered(frm) {
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
		
		// 1. Compute token counts across First & Last names
		let token_counts = {};
		data.forEach(r => {
			let fn = (r.first_name || '').trim().toLowerCase();
			let ln = (r.last_name || '').trim().toLowerCase();
			if (fn.length >= 2) token_counts[fn] = (token_counts[fn] || 0) + 1;
			if (ln.length >= 2) token_counts[ln] = (token_counts[ln] || 0) + 1;
		});

		let dup_tokens = Object.keys(token_counts).filter(t => token_counts[t] >= 2);
		let primary_count = data.filter(r => r.primary).length;
		let merge_count = data.filter(r => r.merge).length;
		let rekyc_count = data.filter(r => r.re_kyc).length;

		let badge_colors = ['primary', 'info', 'warning', 'danger', 'secondary', 'dark'];
		let token_badges_html = dup_tokens.length > 0
			? dup_tokens.map((t, i) => `<span class="badge badge-${badge_colors[i % badge_colors.length]} mr-1 px-2 py-1">${t} (${token_counts[t]})</span>`).join('')
			: `<span class="text-muted font-italic">No duplicate name tokens detected</span>`;

		let widget_html = `
		<div class="p-3 bg-white border rounded shadow-sm mb-3">
			<div class="d-flex justify-content-between align-items-center mb-2">
				<h6 class="m-0 font-weight-bold text-primary">CIF Search Summary & Duplicate Tokens</h6>
				<div>
					<span class="badge badge-success px-2 py-1">Primary: ${primary_count}</span>
					<span class="badge badge-purple px-2 py-1 style="background-color: #6f42c1; color: white;">Merge: ${merge_count}</span>
					<span class="badge badge-warning px-2 py-1">Re-KYC: ${rekyc_count}</span>
				</div>
			</div>
			<div class="d-flex align-items-center flex-wrap gap-2 mb-2">
				<strong class="text-secondary mr-2">Duplicate Substrings:</strong>
				${token_badges_html}
			</div>
		</div>`;

		wrapper.html(widget_html);
	}
});

// Color-coding child table rows based on selection
frappe.ui.form.on("CIF Details", {
	form_render(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let grid_row = frm.fields_dict.cif_details.grid.get_row(cdn);
		if (!grid_row) return;

		$(grid_row.wrapper).removeClass("table-success table-purple table-warning");
		if (row.primary) {
			$(grid_row.wrapper).addClass("table-success");
		} else if (row.merge) {
			$(grid_row.wrapper).css("background-color", "#f3e8ff");
		} else if (row.re_kyc) {
			$(grid_row.wrapper).addClass("table-warning");
		}
	}
});



