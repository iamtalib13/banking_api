// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Database Integration", {
	refresh(frm) {
		frm.trigger("toggle_buttons");
	},

	sync_frequency(frm) {
		frm.trigger("toggle_buttons");
	},

	toggle_buttons(frm) {
		frm.remove_custom_button(__("Sync"));
		frm.remove_custom_button(__("Preview Source Data"));

		if (!frm.is_new()) {
			// Add Preview Source Data button to quickly test & inspect top 10 records in a dialog
			frm.add_custom_button(__("Preview Source Data"), function () {
				frm.call({
					doc: frm.doc,
					method: "preview_source_data",
					freeze: true,
					freeze_message: __("Testing Source DB & fetching preview data..."),
					callback: function (r) {
						if (r.message && r.message.length) {
							let rows = r.message;
							let columns = Object.keys(rows[0]);

							let table_html = `
								<div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
									<table class="table table-bordered table-striped text-left font-sm">
										<thead class="bg-light">
											<tr>
												<th style="width: 50px;">#</th>
												${columns.map((col) => `<th>${frappe.model.unscrub(col)}</th>`).join("")}
											</tr>
										</thead>
										<tbody>
											${rows
												.map(
													(row, idx) => `
												<tr>
													<td><strong>${idx + 1}</strong></td>
													${columns.map((col) => `<td>${row[col] !== null && row[col] !== undefined ? row[col] : "<em class='text-muted'>null</em>"}</td>`).join("")}
												</tr>
											`
												)
												.join("")}
										</tbody>
									</table>
								</div>
							`;

							let d = new frappe.ui.Dialog({
								title: __("Source Data Preview (First 10 Records)"),
								size: "large",
								fields: [
									{
										fieldtype: "HTML",
										fieldname: "preview_html",
										options: table_html,
									},
								],
							});
							d.show();
						} else {
							frappe.msgprint({
								title: __("No Data Returned"),
								indicator: "orange",
								message: __("Source Query executed successfully but returned 0 records."),
							});
						}
					},
				});
			});

			if (frm.doc.sync_frequency === "Manual") {
				frm.add_custom_button(__("Sync"), function () {
					frm.call({
						doc: frm.doc,
						method: "sync_data",
						freeze: true,
						freeze_message: __("Running DB to DB Data Pipeline Sync..."),
						callback: function (r) {
							if (!r.exc) {
								frappe.msgprint({
									title: __("Pipeline Sync Successful"),
									indicator: "green",
									message: r.message || __("Data sync completed successfully."),
								});
								frm.reload_doc();
							}
						},
					});
				}).addClass("btn-primary");
			}
		}
	},
});
