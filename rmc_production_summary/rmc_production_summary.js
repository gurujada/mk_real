// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["RMC Production Summary"] = {
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
            "fieldname": "rmc_grade",
            "label": __("RMC Grade"),
            "fieldtype": "Link",
            "options": "Item",
            "get_query": function() {
                return {
                    filters: {
                        'item_group': 'RMC'
                    }
                };
            }
        },
        {
            "fieldname": "destination_warehouse",
            "label": __("Destination Warehouse"),
            "fieldtype": "Link",
            "options": "Warehouse"
        }
    ],
    
    "formatter": function(value, row, column, data, default_formatter) {
        if (!data) return value;

        value = default_formatter(value, row, column, data);
        
        if (column.fieldtype == "Float") {
            value = frappe.format(value, {fieldtype: 'Float', precision: 3});
        }

        if (column.fieldtype == "Currency") {
            value = frappe.format(value, {fieldtype: 'Currency'});
        }
        
        if (column.fieldname == "total_cost" || column.fieldname == "total_mixing_cost") {
            const is_total_row = data.rmc_grade === "Total";
            if (is_total_row) {
                value = `<b>${value}</b>`;
            }
        }
        
        return value;
    },

    "initial_depth": 0,
    
    onload: function(report) {
        report.page.add_inner_button(__("Export Summary"), function() {
            frappe.query_reports[report.name].export_report(report);
        });
    },

    export_report: function(report) {
        let filters = report.get_values();

        frappe.call({
            method: 'frappe.desk.query_report.run',
            args: {
                report_name: report.name,
                filters: filters,
                ignore_prepared_report: true,
                is_tree: false,
                export: true
            },
            callback: function(r) {
                if (r.message) {
                    window.open("/api/method/frappe.desk.query_report.download?" + 
                        $.param({
                            report_name: report.name,
                            filters: JSON.stringify(filters),
                            file_format_type: "Excel"
                        })
                    );
                }
            }
        });
    }
};
