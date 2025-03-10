import frappe
from frappe import _, scrub
from frappe.utils import add_days, add_to_date, flt, getdate, fmt_money
from frappe.query_builder import DocType
from pypika.functions import Sum

from erpnext.accounts.utils import get_fiscal_year
from frappe.utils.nestedset import get_descendants_of

def execute(filters=None):
    return PurchaseAnalytics(filters).run()

class PurchaseAnalytics(object):
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.date_field = "posting_date"
        self.months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ]
        self.get_period_date_ranges()

    def run(self):
        self.get_columns()
        self.get_data()

        # Handle item group filter
        if self.filters.get("item_group"):
            self.apply_item_group_filter_to_entries()
            
        self.process_data_into_tree()
        chart = self.get_chart_data()
        return self.columns, self.data, None, chart, None, 1

    def get_columns(self):
        self.columns = [{
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 200
        }]

        for end_date in self.periodic_daterange:
            period = self.get_period(end_date)
            self.columns.append({
                "label": _(period),
                "fieldname": scrub(period),
                "fieldtype": "Currency",
                "options": "Company:company:default_currency",
                "width": 120
            })

        self.columns.append({
            "label": _("Total"),
            "fieldname": "total",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120
        })

    def get_data(self):
        self.get_purchase_transactions()
        
    def get_purchase_transactions(self):
        self.get_item_groups()

        tran = DocType("Purchase Receipt")
        detail = DocType("Purchase Receipt Item")
        item = DocType("Item")

        query = (
            frappe.qb.from_(tran)
            .inner_join(detail)
            .on(tran.name == detail.parent)
            .inner_join(item)
            .on(detail.item_code == item.name)
            .select(
                item.item_group.as_("item_group"),
                Sum(detail.base_net_amount).as_("value_field"),
                Sum(detail.item_tax_amount).as_("tax_field"),
                tran.posting_date.as_("posting_date")
            )
            .where(
                (tran.docstatus == 1) & 
                (tran.company == self.filters.company) &
                (tran.posting_date.between(self.filters.from_date, self.filters.to_date))
            )
            .groupby(item.item_group, tran.posting_date)
        )

        self.entries = query.run(as_dict=True)

    def get_item_groups(self):
        item_groups = frappe.get_all(
            "Item Group",
            fields=["name", "parent_item_group", "is_group", "lft", "rgt"],
            filters={"docstatus": 0},
            order_by="lft"
        )

        self.item_group_hierarchy = {}
        for ig in item_groups:
            self.item_group_hierarchy[ig.name] = {
                "parent": ig.parent_item_group,
                "is_group": ig.is_group,
                "lft": ig.lft,
                "rgt": ig.rgt
            }

    def calculate_indent_level(self, item_group):
        """Calculate the level of nesting for an item group"""
        level = 0
        current = item_group
        while current:
            parent = self.item_group_hierarchy.get(current, {}).get("parent")
            if parent:
                level += 1
            current = parent
        return level

    def process_data_into_tree(self):
        period_data = {}
        
        # First pass: Calculate amounts for each item group
        for entry in self.entries:
            item_group = entry.item_group
            if not item_group:
                continue
                
            posting_date = getdate(entry.posting_date)
            period = self.get_period(posting_date)
            amount = flt(entry.value_field) + flt(entry.tax_field)
            
            # Initialize dictionaries
            if item_group not in period_data:
                period_data[item_group] = {}
            if period not in period_data[item_group]:
                period_data[item_group][period] = 0
                
            period_data[item_group][period] += amount
            
            # Roll up to parent groups
            parent = self.item_group_hierarchy.get(item_group, {}).get("parent")
            while parent:
                if parent not in period_data:
                    period_data[parent] = {}
                if period not in period_data[parent]:
                    period_data[parent][period] = 0
                    
                period_data[parent][period] += amount
                parent = self.item_group_hierarchy.get(parent, {}).get("parent")

        # Second pass: Create data rows with proper structure
        self.data = []
        for item_group, periods in period_data.items():
            indent = self.calculate_indent_level(item_group)
            row = frappe._dict({
                "name": item_group,
                "parent": self.item_group_hierarchy.get(item_group, {}).get("parent") or "",
                "item_group": item_group,
                "indent": indent
            })
            
            total = 0
            for period in self.period_list:
                amount = periods.get(period, 0)
                row[scrub(period)] = amount
                total += amount
            
            if total > 0:  # Only include rows with data
                row["total"] = total
                self.data.append(row)

        # Sort by lft value to maintain hierarchy
        self.data.sort(key=lambda x: self.item_group_hierarchy.get(x.item_group, {}).get("lft", 0))

    def apply_item_group_filter_to_entries(self):
        """Apply item group filter to raw entries"""
        selected_group = self.filters.item_group
        is_group = self.item_group_hierarchy.get(selected_group, {}).get("is_group", 0)
        
        if is_group:
            # If it's a group, include children
            children = get_descendants_of("Item Group", selected_group, ignore_permissions=True)
            allowed_groups = [selected_group] + children
        else:
            # If it's a leaf node, just include itself
            allowed_groups = [selected_group]
            
        self.entries = [e for e in self.entries if e.get("item_group") in allowed_groups]

    def get_chart_data(self):
        """Create chart data for total purchase amounts by period"""
        labels = []
        values = []
        tooltips = []
        currency = frappe.get_cached_value('Company', self.filters.company, 'default_currency')

        for end_date in self.periodic_daterange:
            period = self.get_period(end_date)
            period_name = scrub(period)
            
            # Get all entries for this period
            period_total = sum(
                flt(entry.value_field) + flt(entry.tax_field)
                for entry in self.entries
                if self.get_period(entry.posting_date) == period
            )
            
            labels.append(period)
            values.append(period_total)
            tooltips.append(fmt_money(period_total, 2, currency))

        return {
            "data": {
                "labels": labels,
                "datasets": [{
                    "name": _("Total Purchase Amount"),
                    "values": values,
                    "tooltipContent": tooltips
                }]
            },
            "type": "bar",
            "fieldtype": "Currency",
            "colors": ["#5e64ff"]
        } if values else None

    def get_period(self, posting_date):
        if isinstance(posting_date, str):
            posting_date = getdate(posting_date)

        try:
            if self.filters.range == "Weekly":
                period = "Week {0} {1}".format(
                    str(posting_date.isocalendar()[1]), str(posting_date.year)
                )
            elif self.filters.range == "Monthly":
                period = str(self.months[posting_date.month - 1]) + " " + str(posting_date.year)
            elif self.filters.range == "Quarterly":
                period = "Quarter {} {}".format(
                    str(((posting_date.month - 1) // 3) + 1), str(posting_date.year)
                )
            else:
                year = get_fiscal_year(posting_date, company=self.filters.company)
                period = str(year[0])
            return period
        except Exception:
            return None

    def get_period_date_ranges(self):
        from dateutil.relativedelta import MO, relativedelta
        
        from_date = getdate(self.filters.from_date)
        to_date = getdate(self.filters.to_date)

        increment = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(
            self.filters.range, 1
        )

        if self.filters.range in ["Monthly", "Quarterly"]:
            from_date = from_date.replace(day=1)
        elif self.filters.range == "Yearly":
            from_date = get_fiscal_year(from_date)[1]
        else:
            from_date = from_date + relativedelta(from_date, weekday=MO(-1))

        self.periodic_daterange = []
        for dummy in range(1, 53):
            if self.filters.range == "Weekly":
                period_end_date = add_days(from_date, 6)
            else:
                period_end_date = add_to_date(from_date, months=increment, days=-1)

            if period_end_date > to_date:
                period_end_date = to_date

            self.periodic_daterange.append(period_end_date)

            from_date = add_days(period_end_date, 1)
            if period_end_date == to_date:
                break
                
        self.period_list = [self.get_period(end_date) for end_date in self.periodic_daterange]