import frappe
from frappe import _, scrub
from frappe.utils import flt
from frappe.query_builder import DocType, Field
from frappe.query_builder.functions import Sum
from frappe.utils.nestedset import get_descendants_of

def execute(filters=None):
    if not filters:
        filters = {}
    return CostAnalytics(filters).run()

class CostAnalytics(object):
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.filters.parent_costcenter = self.filters.get("parent_costcenter") or "M K One Construction - MKB"
        self.descendant_costcenters = get_descendants_of("Cost Center", self.filters.parent_costcenter, ignore_permissions=True)
        
    def run(self):
        self.get_columns()
        self.get_data()
        skip_total_row = True  # Set to True to avoid totals row

        if self.filters.get("item_group"):
            item_group_data = frappe.db.get_value("Item Group", 
                self.filters.get("item_group"), ["lft", "rgt"], as_dict=1)
            if item_group_data:
                # Get all descendant item groups
                descendant_groups = frappe.db.sql("""
                    SELECT name FROM `tabItem Group` 
                    WHERE lft >= %s AND rgt <= %s
                """, (item_group_data.lft, item_group_data.rgt), as_dict=1)
                allowed_groups = [d.name for d in descendant_groups]
                self.filtered_data = [d for d in self.data if d.get("item_group") in allowed_groups]
            else:
                self.filtered_data = []
        else:
            self.filtered_data = self.data

        chart = self.get_chart_data()
        return self.columns, self.filtered_data, None, chart, None, skip_total_row

    def get_columns(self):
        self.columns = [
            {
                "label": _("Item Group"),
                "fieldname": "item_group",
                "fieldtype": "Link",
                "options": "Item Group",
                "width": 200
            }
        ]
        self.get_active_costcenters()
        for costcenter in self.costcenters:
            self.columns.append(
                {"label": _(costcenter.cost_center), "fieldname": costcenter.cost_center, "fieldtype": "Currency", "width": 120}
            )
        self.columns.append(
            {"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 120}
        )

    def get_data(self):
        self.get_issue_transactions_based_on_costcenter()
        self.get_rows_by_group()

    def get_active_costcenters(self):
        se = DocType("Stock Entry")
        sed = DocType("Stock Entry Detail")
        query = (
            frappe.qb.from_(sed)
            .join(se)
            .on(se.name == sed.parent)
            .select(sed.cost_center)
            .distinct()
            .where(
                (se.docstatus == 1)
                & (se.purpose == "Material Issue")
                & (sed.cost_center.isin(self.descendant_costcenters))
            )
            .orderby(sed.cost_center)
        )

        if self.filters.get("from_date"):
            query = query.where(se.posting_date >= self.filters.from_date)
        if self.filters.get("to_date"):
            query = query.where(se.posting_date <= self.filters.to_date)
        if self.filters.get("warehouse"):
            query = query.where(sed.s_warehouse == self.filters.warehouse)

        self.costcenters = query.run(as_dict=True)

    def get_issue_transactions_based_on_costcenter(self):
        sed = DocType("Stock Entry Detail")
        se = DocType("Stock Entry")
        item = DocType("Item")
        
        query = (
            frappe.qb.from_(sed)
            .inner_join(se)
            .on(sed.parent == se.name)
            .inner_join(item)
            .on(sed.item_code == item.name)
            .select(item.item_group, sed.cost_center, Sum(sed.amount).as_("amount"))
            .where(
                (se.docstatus == 1)
                & (se.purpose == "Material Issue")
                & (sed.cost_center.isin(self.descendant_costcenters))
            )
            .groupby(item.item_group, sed.cost_center)
        )

        if self.filters.get("company"):
            query = query.where(se.company == self.filters.company)
        if self.filters.get("from_date"):
            query = query.where(se.posting_date >= self.filters.from_date)
        if self.filters.get("to_date"):
            query = query.where(se.posting_date <= self.filters.to_date)
        if self.filters.get("warehouse"):
            query = query.where(sed.s_warehouse == self.filters.warehouse)

        self.entries = query.run(as_dict=True)
        self.get_groups()

    def get_rows_by_group(self):
        self.get_costcenter_data()
        out = []

        for d in reversed(self.group_entries):
            row = {"item_group": d.name, "indent": self.depth_map.get(d.name)}
            total = 0
            for costcenter in self.costcenters:
                amount = flt(self.costcenter_data.get(d.name, {}).get(costcenter.cost_center, 0.0))
                row[costcenter.cost_center] = amount
                if d.parent:
                    self.costcenter_data.setdefault(d.parent, frappe._dict()).setdefault(costcenter.cost_center, 0.0)
                    self.costcenter_data[d.parent][costcenter.cost_center] += amount
                total += amount
            row["total"] = total
            out = [row] + out

        self.data = out

    def get_costcenter_data(self):
        self.costcenter_data = frappe._dict()
        for d in self.entries:
            self.costcenter_data.setdefault(d.item_group, frappe._dict()).setdefault(d.cost_center, 0.0)
            self.costcenter_data[d.item_group][d.cost_center] += flt(d.amount)

    def get_groups(self):
        parent = "parent_item_group"
        grp = DocType("Item Group")
        self.depth_map = frappe._dict()
        query = (
            frappe.qb.from_(grp)
            .select(grp.name, grp.lft, grp.rgt, Field(parent).as_("parent"))
            .orderby(grp.lft)
        )

        self.group_entries = query.run(as_dict=True)

        for d in self.group_entries:
            if d.parent:
                self.depth_map.setdefault(d.name, self.depth_map.get(d.parent) + 1)
            else:
                self.depth_map.setdefault(d.name, 0)

    def get_chart_data(self):
        if not self.filtered_data:
            return None

        # Get cost center labels excluding first (Item Group) and last (Total) columns
        labels = [d.get("label") for d in self.columns[1:-1]]

        # Calculate total for each cost center
        period_totals = []
        for cost_center in labels:
            if self.filters.get("item_group"):
                # Get the maximum indent level in the filtered data to identify leaf nodes
                max_indent = max((row.get("indent", 0) for row in self.filtered_data), default=0)
                # Only sum leaf nodes (rows with max indent) to avoid double counting
                leaf_data = [row for row in self.filtered_data if row.get("indent", 0) == max_indent]
                total = sum(flt(row.get(cost_center, 0)) for row in leaf_data)
            else:
                # When no item_group filter, use root level rows as before
                root_level_data = [row for row in self.filtered_data if row.get("indent", 0) == 0]
                total = sum(flt(row.get(cost_center, 0)) for row in root_level_data)
            period_totals.append(total)

        datasets = [{
            "name": _("Total Consumption"),
            "values": period_totals
        }]

        return {
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "type": "bar",
            "fieldtype": "Currency"
        }
