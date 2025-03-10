import frappe

def execute(filters=None):
    return ItemList(filters).run()
class ItemList(object):
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.columns = []
        self.data = []
        self.depth_map={}

    def run(self):
        self.get_columns()
        self.get_data()
        return self.columns, self.data
    def get_columns(self):
        self.columns = [
            {
            "fieldname": "item_group",
            "label": "Item Group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 300
            },
            {
            "fieldname": "item_name",
            "label": "Item Name",
            "align": "left",
            "fieldtype": "Link",
            "options": "Item",
            "width": 300
            } ]
    def get_data(self):
        qry = """
                (
                select ig.name as item_group, i.name as item_name, ig.parent_item_group from `tabItem Group` 
                ig LEFT JOIN `tabItem` i ON ig.name=i.item_group order by lft                
                )
             """
        self.group_entries = frappe.db.sql(qry, as_dict=1)           
        for d in self.group_entries:
            if d.parent_item_group:
                self.depth_map.setdefault(d.item_group, self.depth_map.get(d.parent_item_group) + 1)
            else:
                self.depth_map.setdefault(d.item_group, 0)
        for d in self.group_entries:
            self.data.append({
                "item_group": d.item_group,
                "indent": self.depth_map.get(d.item_group,0),
                "item_name": d.item_name})
