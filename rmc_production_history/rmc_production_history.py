import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data, None

def get_columns():
    return [
        {
            "label": _("RMC Entry"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "RMC Production Entry",
            "width": 130
        },
        {
            "label": _("Status"),
            "fieldname": "workflow_state",
            "fieldtype": "Data",
            "width": 90,
            "color": {
                "Produced": "blue",
                "In-Transit": "orange",
                "Delivered": "green"
            }
        },
        {
            "label": _("Production Date"),
            "fieldname": "production_date",
            "fieldtype": "Date",
            "width": 95
        },
        {
            "label": _("RMC Grade"),
            "fieldname": "rmc_grade",
            "fieldtype": "Link",
            "options": "Item",
            "width": 100
        },
        {
            "label": _("Quantity (m³)"),
            "fieldname": "quantity",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("Source"),
            "fieldname": "source_warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 120
        },
        {
            "label": _("Destination"),
            "fieldname": "destination_warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 120
        },
        {
            "label": _("Production Stock Entry"),
            "fieldname": "production_entry",
            "fieldtype": "Link",
            "options": "Stock Entry",
            "width": 130
        },
        {
            "label": _("Transit Stock Entry"),
            "fieldname": "transit_entry",
            "fieldtype": "Link",
            "options": "Stock Entry",
            "width": 130
        },
        {
            "label": _("Delivery Stock Entry"),
            "fieldname": "delivery_entry",
            "fieldtype": "Link",
            "options": "Stock Entry",
            "width": 130
        },
        {
            "label": _("Total Cost"),
            "fieldname": "total_cost",
            "fieldtype": "Currency",
            "width": 110
        },
        {
            "label": _("Cost per m³"),
            "fieldname": "per_unit_cost",
            "fieldtype": "Currency",
            "width": 110
        }
    ]

def get_data(filters):
    conditions = get_conditions(filters)
    
    entries = frappe.db.sql("""
        SELECT 
            rpe.name,
            rpe.workflow_state,
            rpe.production_date,
            rpe.rmc_grade,
            rpe.quantity,
            rpe.source_warehouse,
            rpe.destination_warehouse,
            rpe.total_cost,
            rpe.per_unit_cost
        FROM 
            `tabRMC Production Entry` rpe
        WHERE
            rpe.docstatus = 1
            {conditions}
        ORDER BY 
            rpe.production_date DESC, rpe.name
    """.format(conditions=conditions), filters, as_dict=1)

    # Get related stock entries
    for entry in entries:
        stock_entries = frappe.get_all("Stock Entry",
            filters={
                "rmc_production_entry": entry.name,
                "docstatus": 1
            },
            fields=["name", "stock_entry_type"]
        )
        
        for se in stock_entries:
            if se.stock_entry_type == "Material Receipt":
                entry.production_entry = se.name
            elif se.stock_entry_type == "Material Transfer":
                if "Transit" in frappe.db.get_value("Stock Entry", se.name, "to_warehouse"):
                    entry.transit_entry = se.name
                else:
                    entry.delivery_entry = se.name

    return entries

def get_conditions(filters):
    conditions = []

    if filters.get("from_date"):
        conditions.append("rpe.production_date >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("rpe.production_date <= %(to_date)s")
    if filters.get("status"):
        conditions.append("rpe.workflow_state = %(status)s")
    if filters.get("rmc_grade"):
        conditions.append("rpe.rmc_grade = %(rmc_grade)s")
    if filters.get("destination"):
        conditions.append("rpe.destination_warehouse = %(destination)s")

    return "AND {}".format(" AND ".join(conditions)) if conditions else ""
