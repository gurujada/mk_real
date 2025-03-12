# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _, cint
from frappe.utils import flt, getdate, add_months, fmt_money

def execute(filters=None):
    if not filters:
        filters = {}
        
    # Set default dates if not provided
    filters["from_date"] = filters.get("from_date") or add_months(getdate(), -1)
    filters["to_date"] = filters.get("to_date") or getdate()

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {
            "label": _("RMC Grade"),
            "fieldname": "rmc_grade",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "label": _("Destination Warehouse"),
            "fieldname": "destination_warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 180
        },
        {
            "label": _("Total Quantity"),
            "fieldname": "total_quantity",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("Number of Batches"),
            "fieldname": "batch_count",
            "fieldtype": "Data",
            "width": 130
        },
        {
            "label": _("Average Batch Size"),
            "fieldname": "avg_batch_size",
            "fieldtype": "Data",
            "width": 130
        },
        {
            "label": _("Mixing Rate/m³"),
            "fieldname": "mixing_rate",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Total Mixing Cost"),
            "fieldname": "total_mixing_cost",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Total Cost"),
            "fieldname": "total_cost",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Average Cost/m³"),
            "fieldname": "avg_cost",
            "fieldtype": "Data",
            "width": 120
        }
    ]

def get_data(filters):
    conditions = "WHERE docstatus = 1"
    if filters.get("from_date"):
        conditions += f" AND production_date >= '{filters.get('from_date')}'"
    if filters.get("to_date"):
        conditions += f" AND production_date <= '{filters.get('to_date')}'"
    if filters.get("rmc_grade"):
        conditions += f" AND rmc_grade = '{filters.get('rmc_grade')}'"
    if filters.get("destination_warehouse"):
        conditions += f" AND destination_warehouse = '{filters.get('destination_warehouse')}'"
        
    # Get production data grouped by grade and warehouse
    data = frappe.db.sql(f"""
        SELECT 
            rmc_grade,
            destination_warehouse,
            COUNT(*) as batch_count,
            SUM(quantity) as total_quantity,
            AVG(mixing_rate) as mixing_rate,
            SUM(total_mixing_cost) as total_mixing_cost,
            ROUND(SUM(total_cost), 2) as total_cost,
            AVG(quantity) as avg_batch_size,
            ROUND(AVG(per_unit_cost), 2) as avg_cost
        FROM 
            `tabRMC Production Entry`
        {conditions}
        GROUP BY 
            rmc_grade, destination_warehouse
        ORDER BY 
            rmc_grade, destination_warehouse
    """, as_dict=1)
    
    # Return raw data without any transformations
    return data

def get_chart_data(data):
    if not data:
        return None

    # Create comparison chart for costs
    datasets = [
        {
            'name': 'Total Mixing Cost',
            'values': [d.total_mixing_cost for d in data]
        },
        {
            'name': 'Total Cost',
            'values': [d.total_cost for d in data]
        }
    ]

    chart = {
        'data': {
            'labels': [f"{d.rmc_grade} ({d.destination_warehouse})" for d in data],
            'datasets': datasets
        },
        'type': 'bar',
        'barOptions': {'stacked': False}
    }

    return chart
