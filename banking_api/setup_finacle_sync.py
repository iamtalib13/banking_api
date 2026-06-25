import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    # 1. Create Custom Field 'custom_finacle_synced' in Employee DocType
    custom_fields = {
        "Employee": [
            {
                "fieldname": "custom_finacle_synced",
                "label": "Finacle Synced",
                "fieldtype": "Check",
                "insert_after": "status",
                "default": "0",
                "read_only": 1
            }
        ]
    }
    create_custom_fields(custom_fields)
    print("Custom field 'custom_finacle_synced' created in Employee.")

    # 2. Update existing employees to have custom_finacle_synced = 1
    frappe.db.sql("UPDATE `tabEmployee` SET custom_finacle_synced = 1 WHERE IFNULL(custom_finacle_synced, 0) = 0")
    frappe.db.commit()
    print("Existing Employees updated: custom_finacle_synced = 1.")

    # 3. Create 'Finacle EDR Sync Log' DocType if it doesn't exist
    if not frappe.db.exists("DocType", "Finacle EDR Sync Log"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Finacle EDR Sync Log",
            "module": "Banking API",
            "custom": 1,
            "istable": 0,
            "naming_rule": "Expression",
            "autoname": "format:FIN-SYNC-{YYYY}-{MM}-{####}",
            "fields": [
                {
                    "fieldname": "employee",
                    "label": "Employee",
                    "fieldtype": "Link",
                    "options": "Employee",
                    "in_list_view": 1,
                    "reqd": 1
                },
                {
                    "fieldname": "finacle_employee_id",
                    "label": "Finacle Employee ID",
                    "fieldtype": "Data",
                    "in_list_view": 1
                },
                {
                    "fieldname": "status",
                    "label": "Status",
                    "fieldtype": "Select",
                    "options": "Success\nFailed",
                    "in_list_view": 1,
                    "reqd": 1
                },
                {
                    "fieldname": "sync_time",
                    "label": "Sync Time",
                    "fieldtype": "Datetime",
                    "in_list_view": 1
                },
                {
                    "fieldname": "request_data",
                    "label": "Request Data",
                    "fieldtype": "Code"
                },
                {
                    "fieldname": "response_data",
                    "label": "Response Data",
                    "fieldtype": "Code"
                }
            ],
            "permissions": [
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1
                }
            ]
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("DocType 'Finacle EDR Sync Log' created successfully.")
    else:
        print("DocType 'Finacle EDR Sync Log' already exists.")
