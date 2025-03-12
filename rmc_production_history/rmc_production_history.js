frappe.query_reports["RMC Production History"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "width": "80"
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "width": "80"
        },
        {
            "fieldname": "status",
            "label": __("Status"),
            "fieldtype": "Select",
            "options": "\nProduced\nIn-Transit\nDelivered",
            "width": "100"
        },
        {
            "fieldname": "rmc_grade",
            "label": __("RMC Grade"),
            "fieldtype": "Link",
            "options": "Item",
            "get_query": () => {
                return {
                    filters: { 'item_group': 'RMC' }
                };
            },
            "width": "100"
        },
        {
            "fieldname": "destination",
            "label": __("Destination"),
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": "100"
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname == "workflow_state") {
            var color = "";
            if (data.workflow_state === "Produced") color = "blue";
            else if (data.workflow_state === "In-Transit") color = "orange";
            else if (data.workflow_state === "Delivered") color = "green";
            
            if (color) {
                value = `<span style='color: var(--${color}-600); font-weight: bold;'>${value}</span>`;
            }
        }

        // Add icons for stock entries
        if (column.fieldname === "production_entry" && value) {
            value = `<i class='fa fa-industry text-muted' style='margin-right: 3px'></i>${value}`;
        }
        if (column.fieldname === "transit_entry" && value) {
            value = `<i class='fa fa-truck text-muted' style='margin-right: 3px'></i>${value}`;
        }
        if (column.fieldname === "delivery_entry" && value) {
            value = `<i class='fa fa-check-circle text-muted' style='margin-right: 3px'></i>${value}`;
        }

        return value;
    },

    "initial_depth": 0,
    "tree": false,
    "is_tree": false,
    "name_field": "name",
    
    onload: function(report) {
        report.page.add_inner_button(__("Create Production Entry"), function() {
            frappe.new_doc("RMC Production Entry");
        });
    }
};
