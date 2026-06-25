import frappe

def execute():
    # JavaScript code to replace the primary action button on the list view
    js_code = """
frappe.listview_settings['Finacle EDR Sync Log'] = {
    primary_action: function() {
        frappe.confirm(
            __('Are you sure you want to sync new employees to Finacle?'),
            function() {
                frappe.call({
                    method: "banking_api.finacle_sync.sync_employees_to_finacle",
                    freeze: true,
                    freeze_message: __('Syncing new employees to Finacle...'),
                    callback: function(r) {
                        frappe.msgprint(__('Sync process completed.'));
                        cur_list.refresh();
                    }
                });
            }
        );
    },
    refresh: function(listview) {
        setTimeout(() => {
            if (listview.page.btn_primary) {
                listview.page.btn_primary.html('<span class="hidden-xs">Sync Employees to Finacle</span>');
            }
        }, 10);
    }
};
    """

    # Check if a Client Script already exists for this Doctype
    script_name = frappe.db.get_value("Client Script", {"dt": "Finacle EDR Sync Log", "view": "List"})
    
    if script_name:
        # Update existing
        doc = frappe.get_doc("Client Script", script_name)
        doc.script = js_code
        doc.save(ignore_permissions=True)
        print("Updated existing Client Script.")
    else:
        # Create new
        doc = frappe.get_doc({
            "doctype": "Client Script",
            "name": "Finacle EDR Sync Log - List",
            "dt": "Finacle EDR Sync Log",
            "view": "List",
            "script": js_code,
            "module": "Banking API",
            "enabled": 1
        })
        doc.insert(ignore_permissions=True)
        print("Created new Client Script.")
    
    frappe.db.commit()
