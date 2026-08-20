// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Database Integration", {
	refresh(frm) {
		frm.trigger("toggle_sync_button");
	},

	sync_frequency(frm) {
		frm.trigger("toggle_sync_button");
	},

	toggle_sync_button(frm) {
		frm.remove_custom_button(__("Sync"));

		if (!frm.is_new() && frm.doc.sync_frequency === "Manual") {
			frm.add_custom_button(__("Sync"), function () {
				frm.call({
					doc: frm.doc,
					method: "sync_data",
					freeze: true,
					freeze_message: __("Syncing data between databases..."),
					callback: function (r) {
						if (!r.exc) {
							frappe.msgprint({
								title: __("Sync Successful"),
								indicator: "green",
								message: r.message || __("Data sync completed successfully."),
							});
						}
					},
				});
			}).addClass("btn-primary");
		}
	},
});
