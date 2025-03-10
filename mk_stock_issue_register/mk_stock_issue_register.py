from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    if not filters: filters = {}
    validate_filters(filters)
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def validate_filters(filters):
    if not (filters.get("from_date") and filters.get("to_date")):
        frappe.throw(_("From Date and To Date are mandatory"))

def get_columns():
    return [
        {
            "fieldname": "name",
            "label": _("Voucher No "),
            "fieldtype": "Link",
            "options": "Stock Entry",
            "width": 180
        },
        {
            "fieldname": "posting_date",
            "label": _("Posting Date"),
            "fieldtype": "Date",
            "width": 120
        },
        {
            "fieldname": "cost_center",
            "label": _("Cost Center"),
            "fieldtype": "Link",
            "options": "Cost Center",
            "width": 100
        },
        {
            "fieldname": "issue_serial_no",
            "label": _("Serial No"),
            "fieldtype": "data",
            "width": 100
        },
        {
            "fieldname": "item_group",
            "label": _("Item Group"),
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 120
        },
        {
            "fieldname": "item_code",
            "label": _("Item"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 200
        },
        {
            "fieldname": "qty",
            "label": _("Qty"),
            "fieldtype": "Float",
            "width": 80
        },
        {
            "fieldname": "stock_uom",
            "label": _("UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 40
        },
	{
            "fieldname": "valuation_rate",
            "label": _("Rate"),
            "fieldtype":  "Currency",
            "width": 80
        },
	{
            "fieldname": "amount",
            "label": _("Amount"),
            "fieldtype": "Currency",
            "width": 100
        }
    ]

def get_data(filters):
    conditions = get_conditions(filters)
    return frappe.db.sql("""
        select a.name, d.cost_center, a.posting_date, d.issue_serial_no, c.item_group, d.item_code, d.qty, c.stock_uom, d.valuation_rate,d.amount 
        from `tabStock Entry` as a 
	INNER JOIN `tabStock Entry Detail` as d
        INNER JOIN `tabItem` as c 
        on d.item_code=c.name  and a.name=d.parent 
        where a.docstatus=1 and a.stock_entry_type='Material Issue' {conditions}
        order by a.posting_date, a.name;
    """.format(conditions=conditions), filters, as_dict=1)

def get_conditions(filters):
    conditions = ""
    if filters.get("from_date"):
        conditions += " and a.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " and a.posting_date <= %(to_date)s"
    if filters.get("warehouse"):
        conditions += " and a.warehouse = %(warehouse)s"
    if filters.get("cost_center"):
        conditions += " and d.cost_center = %(cost_center)s"
    if filters.get("item_group"):
        conditions += """ and c.item_group in (select name from `tabItem Group` 
                        where lft >= (select lft from `tabItem Group` where name=%(item_group)s) 
                        and rgt <= (select rgt from `tabItem Group` where name=%(item_group)s))"""
    if filters.get("item"):
        conditions += """ and c.name in (select name from `tabItem` 
                        where lft >= (select lft from `tabItem` where name=%(item)s) 
                        and rgt <= (select rgt from `tabItem` where name=%(item)s))"""
    return conditions
