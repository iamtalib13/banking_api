// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Commission", {
    refresh(frm) {
        frm.add_custom_button("Fetch Commission Data", () => {
            frappe.call({
                method: "banking_api.banking_api.doctype.commission.commission.fetch_and_create_commission",
                freeze: true,
                freeze_message: "Fetching commission data and creating records...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "Commission Import Result",
                            message: `
								Query 1 Rows: ${r.message.query_1_count || 0}<br>
								Query 2 Rows: ${r.message.query_2_count || 0}<br>
								Inserted Docs: ${r.message.inserted_count || 0}<br>
								Errors: ${r.message.error_count || 0}
							`,
                            indicator: r.message.error_count ? "orange" : "green"
                        });
                    }
                }
            });
        });
    }
});
