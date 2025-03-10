from __future__ import unicode_literals
import frappe

def execute(filters=None):
    print("Executing report...")
    columns = get_columns()
    data = get_data(filters)
    print(f"Found {len(data)} rows")
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
            "width": 200,
            "indent": 1
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
            "fieldname": "paint_color_code",
            "label": "Color Code",
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
    paint_group = frappe.get_doc("Item Group", "Paints")
    
    # Debug print
    print(f"Paint group lft: {paint_group.lft}, rgt: {paint_group.rgt}")
    
    params = {
        "lft": paint_group.lft,
        "rgt": paint_group.rgt,
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date")
    }

    # First get all descendant item groups
    item_groups = frappe.db.sql("""
        SELECT name, lft, rgt, parent_item_group 
        FROM `tabItem Group`
        WHERE lft >= %(lft)s AND rgt <= %(rgt)s
        ORDER BY lft
    """, params, as_dict=1)

    # Debug print
    print("Found item groups:", [ig.name for ig in item_groups])

    # Build indent map
    indent_map = {}
    for ig in item_groups:
        level = 0
        parent = ig.parent_item_group
        while parent and parent != "All Item Groups":
            level += 1
            parent = frappe.db.get_value("Item Group", parent, "parent_item_group")
        indent_map[ig.name] = level
        
    # Debug print
    print("Indent map:", indent_map)

    # Get stock entries with modified query
    stock_entries = frappe.db.sql("""
        SELECT 
            se.posting_date,
            ig.name as item_group,
            se_item.item_code AS item,
            se_item.s_warehouse AS warehouse,
            se_item.cost_center,
            se_item.qty AS qty,
            se_item.stock_uom,  
            se_item.amount AS value,
            se_item.custom_paint_color_code AS paint_color_code
        FROM `tabStock Entry` AS se
        INNER JOIN `tabStock Entry Detail` AS se_item ON se.name = se_item.parent
        INNER JOIN `tabItem Group` ig ON se_item.item_group = ig.name
        WHERE se.docstatus = 1 
        AND se.purpose = 'Material Issue'
        AND ig.lft >= %(lft)s 
        AND ig.rgt <= %(rgt)s
        {conditions}
        ORDER BY ig.lft, se_item.item_code
    """.format(conditions=conditions), params, as_dict=1)

    # Debug print
    print("Found stock entries:", len(stock_entries))

    # Process data with indentation
    for row in stock_entries:
        # Debug print for each row
        print(f"Processing row: {row.item_group}")
        
        indent = indent_map.get(row.item_group, 0)
        # Debug indent level
        print(f"Indent level: {indent}")
        
        formatted_row = [
            row.posting_date,
            "\t" * indent + str(row.item_group),  # Changed spaces to tabs
            row.item,
            row.warehouse,
            row.cost_center,
            row.paint_color_code,
            row.qty,
            row.stock_uom,
            row.value
        ]
        # Debug formatted row
        print(f"Formatted row: {formatted_row}")
        
        data.append(formatted_row)

    # Final debug print
    print(f"Total rows processed: {len(data)}")
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
