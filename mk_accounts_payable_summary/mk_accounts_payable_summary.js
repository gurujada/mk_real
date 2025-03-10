frappe.query_reports["MK Accounts Payable Summary"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1
        },
        {
            fieldname: "report_date",
            label: __("Posting Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: "supplier_group",
            label: __("Supplier Group"),
            fieldtype: "Link",
            options: "Supplier Group"
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier",
            get_query: function() {
                var supplier_group = frappe.query_report.get_filter_value('supplier_group');
                return {
                    filters: {
                        'supplier_group': supplier_group
                    }
                };
            }
        }
    ]
};