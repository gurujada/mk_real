frappe.query_reports["MK Expense Summary"] = {
    "filters": [
        {
            fieldname: "payment_type",
            label: __("Payment Type"),
            fieldtype: "Select",
            options: ["Pay", "Receive"],
            default: "Pay",
            reqd: 1
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
            reqd: 1
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1
        },
        {
            fieldname: "range",
            label: __("Range"),
            fieldtype: "Select",
            options: [
                { "value": "Weekly", "label": __("Weekly") },
                { "value": "Monthly", "label": __("Monthly") },
                { "value": "Quarterly", "label": __("Quarterly") },
                { "value": "Yearly", "label": __("Yearly") }
            ],
            default: "Monthly",
            reqd: 1
        },
        {
            label: "Supplier Group",
            fieldname: "supplier_group",
            fieldtype: "Link",
            options: "Supplier Group",
            width: 100,
        },
    ]
};