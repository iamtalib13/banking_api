frappe.ui.form.on("Share Application", {
	refresh(frm) {
		if (frm.is_new()) return;

		const can_pay = frm.doc.docstatus === 0 && frm.doc.payment_status !== "Success";
		if (!can_pay) return;

		frm.add_custom_button(__("Pay Now"), function () {
			frappe.confirm(
				__("Are you sure you want to initiate the fund transfer for this Share Application?"),
				function () {
					frappe.call({
						method: "banking_api.banking_api.doctype.share_application_settings.share_application_settings.pay_now_share_application",
						args: {
							entry_name: frm.doc.name
						},
						freeze: true,
						freeze_message: __("Initiating fund transfer..."),
						callback: function (r) {
							if (r.message) {
								frappe.msgprint({
									title: __("Fund Transfer Result"),
									message: r.message.message || __("Process completed."),
									indicator: r.message.status === "success" ? "green" : (r.message.status === "warning" ? "orange" : "red")
								});
							}
							frm.reload_doc();
						}
					});
				}
			);
		});

		frm.change_custom_button_type(__("Pay Now"), null, "primary");
	}
});