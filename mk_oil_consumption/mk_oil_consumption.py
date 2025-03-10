# stock_consumption_report.py

from __future__ import unicode_literals
import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "posting_date",
            "label": "Date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "fieldname": "item_group",
            "label": "Item Group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 200
        },
        {
            "fieldname": "item",
            "label": "Item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 200
        },
        {
            "fieldname": "warehouse",
            "label": "Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 200
        },        
        {
            "fieldname": "cost_center",
            "label": "Cost Center",
            "fieldtype": "Link",
            "options": "Cost Center",
            "width": 200
        },
        {
            "fieldname": "vehicle_no",
            "label": "Vehicle No",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "reading",
            "label": "Reading",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "qty",
            "label": "Quantity",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "fieldname": "stock_uom",
            "label": "UOM",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 100
        },
        {
            "fieldname": "value",
            "label": "Value",
            "fieldtype": "Currency",
            "width": 100
        }
    ]

def get_data(filters):
    data = []
    conditions = get_conditions(filters)
    stock_entries = frappe.db.sql("""
        SELECT
            se.posting_date,
            se_item.item_group,
            se_item.item_code AS item,
            se_item.s_warehouse AS warehouse,
            se_item.cost_center,
            se_item.qty AS qty,
            se_item.stock_uom,  
            se_item.amount AS value,
            se_item.vehicle_no AS vehicle_no,
            se_item.reading AS reading
        FROM `tabStock Entry` AS se
        INNER JOIN `tabStock Entry Detail` AS se_item ON se.name = se_item.parent
        WHERE se.docstatus = 1 AND se.purpose = 'Material Issue' AND se_item.item_group='OILS AND LUBRICANTS'
        {conditions}
        ORDER BY se_item.item_group, se_item.item_code, se_item.s_warehouse, se_item.stock_uom, se_item.cost_center
    """.format(conditions=conditions), filters, as_dict=1)

    for row in stock_entries:
        data.append([
            row.posting_date,
            row.item_group,
            row.item,
            row.warehouse,
            row.cost_center,
            row.vehicle_no,
            row.reading,
            row.qty,
            row.stock_uom,
            row.value
        ])

    return data

def get_conditions(filters):
    conditions = ""
    if filters.get("from_date"):
        conditions += " AND se.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND se.posting_date <= %(to_date)s"
    if filters.get("item_group"):
        conditions += " AND se_item.item_group = %(item_group)s"
    if filters.get("warehouse"):
        conditions += " AND se_item.s_warehouse = %(warehouse)s"
    if filters.get("cost_center"):
        conditions += " AND se_item.cost_center = %(cost_center)s"
    return conditions
