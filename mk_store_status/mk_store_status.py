from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	columns = [
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 300
		},
		{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 300
		},
		{
			"label": _("Qty Requested"),
			"fieldname": "qty_requested",
			"fieldtype": "Float",
			"width": 150
		},
		{
			"label": _("Qty Ordered"),
			"fieldname": "qty_ordered",
			"fieldtype": "Float",
			"width": 150
		},
		{
			"label": _("Qty Received"),
			"fieldname": "qty_received",
			"fieldtype": "Float",
			"width": 150
		},
		{
			"label": _("Qty Consumed"),
			"fieldname": "qty_consumed",
			"fieldtype": "Float",
			"width": 150
		}
	]
	return columns

def get_data(filters):
	conditions = get_conditions(filters)
	data = frappe.db.sql("""
		SELECT 
			i.item_group,
			sle.item_code,
			SUM(CASE WHEN sle.voucher_type = 'Material Request' THEN sle.actual_qty ELSE 0 END) AS qty_requested,
			SUM(CASE WHEN sle.voucher_type = 'Purchase Order' THEN sle.actual_qty ELSE 0 END) AS qty_ordered,
			SUM(CASE WHEN sle.voucher_type = 'Purchase Receipt' THEN sle.actual_qty ELSE 0 END) AS qty_received,
			SUM(CASE WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Material Issue' THEN sle.actual_qty ELSE 0 END) AS qty_consumed
		FROM `tabStock Ledger Entry` sle
		JOIN `tabItem` i ON i.name = sle.item_code
		LEFT JOIN `tabStock Entry` se ON se.name = sle.voucher_no
		WHERE sle.docstatus = 1 {conditions}
		GROUP BY sle.item_code, i.item_group
	""".format(conditions=conditions), filters, as_dict=1)

	return data


def get_conditions(filters):
	conditions = []
	if filters.get("item_group"):
		conditions.append("AND i.item_group = %(item_group)s")
	if filters.get("item_code"):
		conditions.append("AND sle.item_code = %(item_code)s")
	if filters.get("from_date"):
		conditions.append("AND sle.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("AND sle.posting_date <= %(to_date)s")
	
	return conditions 
