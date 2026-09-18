frappe.ui.form.on("Commission Payment", {
    refresh(frm) {
        if (frm.is_new()) return;
        if (frm.doc.docstatus === 2) return;
        if (frm.doc.payment_status === "Paid") return;

        frm.add_custom_button(__("Pay Now"), () => {
            // if (!frm.doc.agent_operative_account) {
            //     frappe.msgprint(__("Agent Operative Account is required."));
            //     return;
            // }
            if (!frm.doc.agent_saving_account) {
                frappe.msgprint(__("Agent Saving Account is required."));
                return;
            }

            if (!frm.doc.final_netpay || flt(frm.doc.final_netpay) <= 0) {
                frappe.msgprint(__("Final Net Pay must be greater than zero."));
                return;
            }

            const amount = format_currency(frm.doc.final_netpay);
            // const account = frm.doc.agent_operative_account;
            const account = frm.doc.agent_saving_account;

            frappe.confirm(
                __(
                    // "Initiate commission payment of {0} to operative account {1}?",
                    "Initiate commission payment of {0} to saving account {1}?",
                    [amount, account]
                ),
                () => {
                    frappe.call({
                        method: "banking_api.banking_api.doctype.commission_payment.commission_payment.pay_now_commission_payment",
                        args: {
                            payment_name: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __("Initiating Finacle commission payment..."),
                        callback(r) {
                            const data = r.message || {};

                            frappe.msgprint({
                                title: __("Commission Payment Result"),
                                message: data.message || __("Process completed."),
                                indicator:
                                    data.status === "success"
                                        ? "green"
                                        : (
                                            data.status === "warning"
                                                ? "orange"
                                                : "red"
                                        )
                            });

                            frm.reload_doc();
                        }
                    });
                }
            );
        }).addClass("btn-primary");
    }
});