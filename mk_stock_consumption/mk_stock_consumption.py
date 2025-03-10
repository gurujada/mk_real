import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    
    if not data:
        frappe.msgprint(_("No records found"))
        
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "item_group",
            "label": _("Item Group"),
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 250,
            "indent": 1
        },
        {
            "fieldname": "item_code",
            "label": _("Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 300,
            "align": "left"
        },
        {
            "fieldname": "warehouse",
            "label": _("Warehouse"),
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160
        },
        {
            "fieldname": "cost_center",
            "label": _("Cost Center"),
            "fieldtype": "Link",
            "options": "Cost Center",
            "width": 160
        },
        {
            "fieldname": "qty",
            "label": _("Consumed Qty"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "uom",
            "label": _("UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 80
        },
        {
            "fieldname": "value",
            "label": _("Consumed Value"),
            "fieldtype": "Float",
            "width": 150
        }
    ]

def get_item_group_hierarchy():
    return frappe.db.sql("""
        SELECT name, parent_item_group, lft, rgt
        FROM `tabItem Group`
        ORDER BY lft
    """, as_dict=1)

def build_tree_data(consumption_data, item_groups):
    # Initialize group totals and transaction map
    group_totals = {}
    transactions_by_group = {}
    
    # Setup parent-child relationships and level mapping
    parent_map = {ig['name']: ig['parent_item_group'] for ig in item_groups}
    level_map = {}
    for ig in item_groups:
        level = 0
        parent = parent_map.get(ig['name'])
        while parent:
            level += 1
            parent = parent_map.get(parent)
        level_map[ig['name']] = level
        
        # Initialize group totals
        group_totals[ig['name']] = {
            'item_group': ig['name'],
            'item_code': '',
            'warehouse': '',
            'cost_center': '',
            'qty': 0,
            'uom': '',
            'value': 0,
            'indent': level,
            'is_group': True
        }
        transactions_by_group[ig['name']] = []
    
    # First, organize transactions by their immediate group
    for row in consumption_data:
        group_name = row['item_group']
        if group_name in transactions_by_group:
            transactions_by_group[group_name].append({
                'item_group': group_name,
                'item_code': row['item_code'],
                'warehouse': row['warehouse'],
                'cost_center': row['cost_center'],
                'qty': flt(row['qty']),
                'uom': row['uom'],
                'value': flt(row['value']),
                'indent': level_map.get(group_name, 0) + 1,
                'is_group': False
            })
    
    # Calculate group totals from bottom up
    processed_groups = set()
    final_data = []
    
    def process_group(group_name):
        if group_name in processed_groups:
            return
        
        # Process children first
        children = [name for name, parent in parent_map.items() if parent == group_name]
        for child in children:
            process_group(child)
        
        # Add direct transactions to group total
        group_transactions = transactions_by_group.get(group_name, [])
        group_total = group_totals[group_name]
        for trans in group_transactions:
            group_total['qty'] += trans['qty']
            group_total['value'] += trans['value']
        
        # Add children totals to group total
        for child in children:
            child_total = group_totals[child]
            group_total['qty'] += child_total['qty']
            group_total['value'] += child_total['value']
        
        processed_groups.add(group_name)
    
    # Process all root groups (those without parents)
    for ig in sorted(item_groups, key=lambda x: x['lft']):
        if not parent_map.get(ig['name']):
            process_group(ig['name'])
    
    # Build final data in correct order
    for ig in sorted(item_groups, key=lambda x: x['lft']):
        if group_totals[ig['name']]['qty'] > 0:  # Only include groups with transactions
            final_data.append(group_totals[ig['name']])
            final_data.extend(transactions_by_group[ig['name']])
    
    return final_data

def get_data(filters):
    return get_consumption_data(filters)

def get_consumption_data(filters):
    consumption_query = """
        SELECT 
            i.item_group,
            sle.item_code,
            sle.warehouse,
            COALESCE(sed.cost_center, '') as cost_center,
            ABS(SUM(sle.actual_qty)) AS qty,
            i.stock_uom AS uom,
            SUM(ABS(COALESCE(sle.actual_qty, 0)) * COALESCE(sle.valuation_rate, 0)) AS value
        FROM 
            `tabStock Ledger Entry` sle
        INNER JOIN 
            `tabItem` i ON sle.item_code = i.name
        INNER JOIN 
            `tabStock Entry` se ON sle.voucher_no = se.name 
            AND sle.voucher_type = 'Stock Entry'
            AND se.stock_entry_type = 'Material Issue'
            AND se.docstatus = 1
        LEFT JOIN (
            SELECT 
                parent,
                item_code,
                s_warehouse,
                cost_center,
                SUM(qty) as total_qty
            FROM 
                `tabStock Entry Detail`
            GROUP BY 
                parent, item_code, s_warehouse, cost_center
        ) sed ON se.name = sed.parent
            AND sle.item_code = sed.item_code
            AND sle.warehouse = sed.s_warehouse
        WHERE
            sle.docstatus = 1
            AND sle.actual_qty < 0
            AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
            {conditions}
        GROUP BY
            i.item_group, sle.item_code, sle.warehouse, COALESCE(sed.cost_center, '')
        HAVING
            qty > 0
        ORDER BY
            i.item_group, sle.item_code
    """
    
    conditions = get_conditions(filters)
    where_conditions = f"AND {conditions}" if conditions else ""
    
    data = frappe.db.sql(
        consumption_query.format(conditions=where_conditions), 
        filters, 
        as_dict=1
    )
    
    for row in data:
        row.qty = flt(row.qty)
        row.value = flt(row.value)
    
    return data

def get_conditions(filters):
    conditions = []
    
    if filters.get("warehouse") and filters.get("warehouse") != "All":
        conditions.append("sle.warehouse = %(warehouse)s")
    
    if filters.get("cost_center") and filters.get("cost_center") != "All":
        conditions.append("sed.cost_center = %(cost_center)s")
        
    if filters.get("item_group"):
        item_group_data = frappe.db.get_value("Item Group", 
            filters.get("item_group"), ["lft", "rgt"], as_dict=1)
        if item_group_data:
            conditions.append("""EXISTS (
                SELECT name FROM `tabItem Group` ig
                WHERE ig.lft >= {lft} AND ig.rgt <= {rgt}
                AND i.item_group = ig.name)""".format(
                    lft=item_group_data.lft,
                    rgt=item_group_data.rgt
                ))
                
    if filters.get("item_code"):
        conditions.append("sle.item_code = %(item_code)s")
        
    return " AND ".join(conditions) if conditions else ""
