// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

const ALLOWED_GROUPS = [
    "Admin Expenses",
    "Labour Expenses",
    "Plant & Machinery Repair, Maintenance-Mk One"
];

frappe.query_reports["MK Tally Summary"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "supplier_group",
            "label": __("Supplier Group"),
            "fieldtype": "Link",
            "options": "Supplier Group",
            "get_query": () => ({
                filters: {
                    "name": ["in", ALLOWED_GROUPS]
                }
            })
        },
        {
            "fieldname": "period",
            "label": __("Period"),
            "fieldtype": "Select",
            "options": "Weekly\nMonthly\nQuarterly\nYearly",
            "default": "Monthly",
            "reqd": 1
        }
    ],
    
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (column.fieldtype == "Currency" && data && value !== "") {
            value = "<span style='float:right'>" + value + "</span>";
        }
        
        return value;
    },

    "initial_depth": 0,
    "tree": false,
    "is_tree": false,
    "presentation_currency": frappe.defaults.get_default("currency"),
    
    onload: function(report) {
        report.page.add_inner_button(__('Refresh'), function() {
            report.refresh();
        });
    }
};