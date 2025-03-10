from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
    columns = [
        {
            "fieldname": "date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100
        },
        {
            "fieldname": "purchase_receipt_no",
            "label": _("Purchase Receipt No"),
            "fieldtype": "Link",
            "options": "Purchase Receipt",
            "width": 150
        },
        {
            "fieldname": "purchase_order_no",
            "label": _("Purchase Order No"),
            "fieldtype": "Link",
            "options": "Purchase Order",
            "width": 150
        },
        {
            "fieldname": "supplier_name",
            "label": _("Supplier Name"),
            "fieldtype": "Data",
            "width": 200
        },
        {
            "fieldname": "warehouse",
            "label": _("Warehouse"),
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 150
        },
        {
            "fieldname": "bill_no",
            "label": _("Bill No"),
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "item_name",
            "label": _("Item Name"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 200
        },
        {
            "fieldname": "uom",
            "label": _("UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 100
        },
        {
            "fieldname": "qty",
            "label": _("Qty"),
            "fieldtype": "Float",
            "width": 100
        },
        {
            "fieldname": "rate",
            "label": _("Rate"),
            "fieldtype": "Currency",
            "width": 100
        },
        {
            "fieldname": "amount",
            "label": _("Amount"),
            "fieldtype": "Currency",
            "width": 100
        },
        {
            "fieldname": "tax_amount",
            "label": _("Tax Amount"),
            "fieldtype": "Currency",
            "width": 100
        },
        {
            "fieldname": "charges",
            "label": _("Charges"),
            "fieldtype": "Currency",
            "width": 100
        },
        {
            "fieldname": "gross_amount",
            "label": _("Gross Amount"),
            "fieldtype": "Currency",
            "width": 100
        }
    ]

    if not filters:
        filters = {}

    conditions = []
    if filters.get("warehouse"):
        conditions.append("pri.warehouse = %(warehouse)s")
    if filters.get("from_date"):
        conditions.append("pr.posting_date >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("pr.posting_date <= %(to_date)s")

    conditions = " AND ".join(conditions)
    if conditions:
        conditions = "AND " + conditions

    sql = """
        SELECT 
            pr.posting_date as date,
            pri.parent as purchase_receipt_no,
            pri.purchase_order as purchase_order_no,
            pr.supplier_name,
            pri.warehouse,
            pr.supplier_delivery_note as bill_no,
            pri.item_name,
            pri.uom,
            pri.qty,
            pri.rate,
            pri.amount,
            COALESCE(
                (SELECT SUM(tax_amount) 
                FROM `tabPurchase Taxes and Charges` 
                WHERE parent = pri.parent 
                AND charge_type IN ('On Net Total', 'On Previous Row Total')),
                0
            ) as tax_amount,
            COALESCE(
                (SELECT SUM(tax_amount) 
                FROM `tabPurchase Taxes and Charges` 
                WHERE parent = pri.parent 
                AND charge_type = 'Actual'),
                0
            ) as charges,
            pri.amount + 
            COALESCE((SELECT SUM(tax_amount) 
                    FROM `tabPurchase Taxes and Charges` 
                    WHERE parent = pri.parent), 0
            ) as gross_amount
        FROM 
            `tabPurchase Receipt Item` pri
            INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE 
            pri.docstatus = 1 
            {conditions}
    """

    data = frappe.db.sql(sql.format(conditions=conditions), filters, as_dict=1)

    return columns, data
