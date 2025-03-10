import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 120},
        {"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": _("MR Qty"), "fieldname": "mr_qty", "fieldtype": "Float", "width": 100},
        {"label": _("PO Qty"), "fieldname": "po_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 130},
        {"label": _("Pending Qty"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 130},
        {"label": _("UOM"), "fieldname": "uom", "width": 50},
        {"label": _("MR No"), "fieldname": "mr_name", "fieldtype": "Link", "options": "Material Request", "width": 130},
        {"label": _("PO No"), "fieldname": "po_name", "fieldtype": "Link", "options": "Purchase Order", "width": 130},
        {"label": _("MR Date"), "fieldname": "mr_date", "fieldtype": "Date", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120}
    ]

    conditions = []
    values = []
 
    if filters.get("from_date"):
        conditions.append("mr.transaction_date >= %s")
        values.append(filters["from_date"])

    if filters.get("to_date"):
        conditions.append("mr.transaction_date <= %s")
        values.append(filters["to_date"])

    if filters.get("item_group"):
        conditions.append("mri.item_group = %s")
        values.append(filters["item_group"])

    if filters.get("status"):
        conditions.append("mr.status = %s")
        values.append(filters["status"])
    
    conditions_str = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT 
            mri.item_group,
            mri.item_code,
            mri.qty as mr_qty,
            COALESCE(poi.qty, 0) as po_qty,
            COALESCE(poi.received_qty, 0) as received_qty,
            CASE 
                WHEN poi.qty IS NULL THEN mri.qty
                ELSE mri.qty - COALESCE(poi.received_qty, 0)
            END as pending_qty,
            mri.uom,
            mr.name as mr_name,
            po.name as po_name,
            mr.transaction_date as mr_date,
            CASE 
                WHEN po.name IS NULL THEN 'Pending'
                WHEN COALESCE(poi.received_qty, 0) = 0 THEN 'Ordered'
                WHEN COALESCE(poi.received_qty, 0) < mri.qty THEN 'Partially Received'
                WHEN COALESCE(poi.received_qty, 0) >= mri.qty THEN 'Completed'
            END as status
        FROM 
            `tabMaterial Request` mr
        JOIN 
            `tabMaterial Request Item` mri ON mr.name = mri.parent
        LEFT JOIN 
            `tabPurchase Order Item` poi ON mri.name = poi.material_request_item
        LEFT JOIN 
            `tabPurchase Order` po ON poi.parent = po.name AND po.docstatus = 1
        WHERE 
            mr.docstatus = 1 AND {conditions_str}
        ORDER BY mr.transaction_date
    """

    data = frappe.db.sql(query, tuple(values), as_dict=1)

    return columns, data
