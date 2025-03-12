// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["RMC Actual vs BOM Consumption"] = {
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
        }
    ],
    
    "formatter": function(value, row, column, data, default_formatter) {
        if (!data) return value;

        value = default_formatter(value, row, column, data);
        
        if (column.fieldname == "variance_percent" && data.variance_percent !== undefined) {
            const variance = flt(data.variance_percent, 2);
            if (variance > 0) {
                value = `<span style='color: var(--red-500)'>${value}</span>`;
            } else if (variance < 0) {
                value = `<span style='color: var(--green-500)'>${value}</span>`;
            }
        }

        if (column.fieldname == "mixing_cost" || column.fieldname == "mixing_rate") {
            value = frappe.format(value, column);
        }
        
        return value;
    },

    "initial_depth": 0,
    
    onload: function(report) {
        report.page.add_inner_button(__("Export Details"), function() {
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
