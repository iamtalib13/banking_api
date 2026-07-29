frappe.listview_settings["Commission"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Fetch Commission Data"), () => {
            frappe.confirm(
                __("This will fetch commission records and create Commission documents. Do you want to continue?"),
                () => {
                    frappe.call({
                        method: "banking_api.banking_api.doctype.commission.commission.fetch_and_create_commission",
                        freeze: true,
                        freeze_message: __("Fetching commission data..."),
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __("Commission Fetch Result"),
                                    indicator: r.message.error_count ? "orange" : "green",
                                    message: `
										<div>
											<p><b>Status:</b> ${r.message.status || "Completed"}</p>
											<p><b>Query 1 Rows:</b> ${r.message.query_1_count || 0}</p>
											<p><b>Query 2 Rows:</b> ${r.message.query_2_count || 0}</p>
											<p><b>Inserted Docs:</b> ${r.message.inserted_count || 0}</p>
											<p><b>Errors:</b> ${r.message.error_count || 0}</p>
										</div>
									`
                                });
                                listview.refresh();
                            }
                        }
                    });
                }
            );
        });
    }
};