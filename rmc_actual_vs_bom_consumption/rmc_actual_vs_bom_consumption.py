# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_months

def execute(filters=None):
    if not filters:
        filters = {}

    # Set default dates if not provided
    if not filters.get("from_date"):
        filters["from_date"] = add_months(getdate(), -1)
    if not filters.get("to_date"):
        filters["to_date"] = getdate()

    columns = get_columns()
    data = get_data(filters)
    chart = get_chart_data(data)

    return columns, data, None, chart

def get_columns():
    return [
        {
            "fieldname": "rmc_grade",
            "label": _("RMC Grade"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 120
        },
        {
            "fieldname": "ticket_number",
            "label": _("Ticket Number"),
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "production_date",
            "label": _("Production Date"),
            "fieldtype": "Date",
            "width": 95
        },
        {
            "fieldname": "item_code",
            "label": _("Raw Material"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "fieldname": "estimated_qty",
            "label": _("BOM Qty"),
            "fieldtype": "Float",
            "width": 100,
            "precision": 3
        },
        {
            "fieldname": "actual_qty",
            "label": _("Actual Qty"),
            "fieldtype": "Float",
            "width": 100,
            "precision": 3
        },
        {
            "fieldname": "variance",
            "label": _("Variance"),
            "fieldtype": "Float",
            "width": 100,
            "precision": 3
        },
        {
            "fieldname": "variance_percent",
            "label": _("Variance %"),
            "fieldtype": "Percent",
            "width": 100,
            "precision": 2
        }
    ]

def get_data(filters):
    conditions = "WHERE pe.docstatus = 1"
    if filters.get("from_date"):
        conditions += f" AND pe.production_date >= '{filters.get('from_date')}'"
    if filters.get("to_date"):
        conditions += f" AND pe.production_date <= '{filters.get('to_date')}'"
    if filters.get("rmc_grade"):
        conditions += f" AND pe.rmc_grade = '{filters.get('rmc_grade')}'"
        
    data = frappe.db.sql(f"""
        SELECT 
            pe.rmc_grade,
            pe.production_date,
            pe.ticket_number,
            rm.item_code,
            rm.estimated_qty,
            rm.qty as actual_qty,
            rm.variance,
            rm.variance_percent
        FROM 
            `tabRMC Production Entry` pe
            INNER JOIN `tabRMC Raw Materials` rm ON rm.parent = pe.name
        {conditions}
        ORDER BY 
            pe.production_date DESC,
            pe.rmc_grade,
            rm.idx
    """, as_dict=1)
    
    # Round numbers for better display
    for row in data:
        row.estimated_qty = flt(row.estimated_qty, 3)
        row.actual_qty = flt(row.actual_qty, 3)
        row.variance = flt(row.variance, 3)
        row.variance_percent = flt(row.variance_percent, 2)
    
    return data

def get_chart_data(data):
    if not data:
        return None

    # Group data by RMC Grade and Raw Material
    summary = {}
    for d in data:
        key = (d.rmc_grade, d.item_code)
        if key not in summary:
            summary[key] = {
                'estimated': 0,
                'actual': 0
            }
        summary[key]['estimated'] += d.estimated_qty
        summary[key]['actual'] += d.actual_qty

    # Get unique materials and grades
    materials = sorted(list(set(d.item_code for d in data)))
    grades = sorted(list(set(d.rmc_grade for d in data)))

    datasets = []
    colors = ['#2490ef', '#19a979']  # Blue for BOM, Green for Actual
    
    for grade in grades:
        datasets.extend([
            {
                'name': f'{grade} - BOM',
                'values': [summary.get((grade, m), {}).get('estimated', 0) for m in materials],
                'chartType': 'bar'
            },
            {
                'name': f'{grade} - Actual',
                'values': [summary.get((grade, m), {}).get('actual', 0) for m in materials],
                'chartType': 'bar'
            }
        ])

    chart = {
        'data': {
            'labels': materials,
            'datasets': datasets
        },
        'type': 'bar',
        'height': 300,
        'colors': colors
    }

    return chart
