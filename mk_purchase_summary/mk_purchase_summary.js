frappe.query_reports["MK Purchase Summary"] = {
    "filters": [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
            reqd: 1
        },
        {
            fieldname:"to_date",
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
            label: __("Item Group"),
            fieldname: "item_group",
            fieldtype: "Link",
            options: "Item Group"
        }
    ],

    "tree": true,
    "name_field": "name",
    "parent_field": "parent",
    "initial_depth": 1,

    formatter: function(value, row, column, data, default_formatter) {
        if (column.fieldtype == "Currency") {
            value = default_formatter(value, row, column, data);
            if (data && !data.parent) {
                return `<b>${value}</b>`;
            }
            return value;
        }
        return default_formatter(value, row, column, data);
    }
};