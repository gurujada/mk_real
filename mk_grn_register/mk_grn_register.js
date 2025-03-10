// stock_consumption_report.js

frappe.query_reports["MK GRN Register"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_start(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_end(),
			"reqd": 1
		},
                {
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
                        "options": "Item Group",
			"reqd": 0
		},
                {
			"fieldname": "supplier",
			"label": __("Supplier"),
			"fieldtype": "Link",
                        "options": "Supplier",
			"reqd": 0
		},
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
                        "options": "Warehouse",
			"reqd": 0
		}
    ]
}
