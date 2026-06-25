frappe.listview_settings['Finacle EDR Sync Log'] = {
    refresh: function(listview) {
        listview.page.add_inner_button(__('Sync Employees to Finacle'), function() {
            frappe.confirm(
                __('Are you sure you want to sync new employees to Finacle?'),
                function() {
                    frappe.call({
                        method: "banking_api.finacle_sync.sync_employees_to_finacle",
                        freeze: true,
                        freeze_message: __('Syncing new employees to Finacle...'),
                        callback: function(r) {
                            frappe.msgprint(__('Sync process completed.'));
                            listview.refresh();
                        }
                    });
                }
            );
        });
    }
};
