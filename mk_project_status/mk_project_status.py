import frappe
from frappe import _, scrub
from frappe.utils import add_days, add_to_date, flt, getdate
from frappe.query_builder import DocType, Case
from pypika.terms import ValueWrapper

from erpnext.accounts.utils import get_fiscal_year
from frappe.utils.nestedset import get_descendants_of

def execute(filters=None):
    report = ProjectAnalytics(filters)
    return report.run()


class ProjectAnalytics(object):
    def __init__(self, filters=None):
        self.chart_labels = []
        self.filters = frappe._dict(filters or {})
        
        # Validate range
        valid_ranges = ["Weekly", "Monthly", "Quarterly", "Half-Yearly", "Yearly"]
        if self.filters.range and self.filters.range not in valid_ranges:
            frappe.throw(_("Invalid range. Please select from {0}").format(", ".join(valid_ranges)))
            
        self.months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        self.get_period_date_ranges()

    def run(self):
        self.get_columns()
        self.get_groups()
        self.get_orders_data()
        self.get_receipts_data()
        self.get_consumption_data()
        self.get_rows_by_group()
        skip_total_row = 1

        if self.filters.get("item_group"):
            # filter data based on item group and children
            children = get_descendants_of("Item Group", self.filters.item_group, ignore_permissions=True)
            self.filtered_data = [d for d in self.data if d.get("item_group") in [self.filters.item_group] + children]
        else:
            self.filtered_data = self.data
            
        if self.filtered_data:
            self.get_chart_data()
        else:
            self.chart = None
            
        return self.columns, self.filtered_data, None, self.chart, None, skip_total_row

    def get_columns(self):
        self.columns = [
            {
                "label": _("Item Group"),
                "fieldname": "item_group",
                "fieldtype": "Link",
                "options": "Item Group",
                "width": 200,
            }
        ]

        for end_date in self.periodic_daterange:
            period = self.get_period(end_date)
            self.chart_labels.append(period)
            self.columns.append(
                {"label": "Orders " + period, "fieldname": "orders" + scrub(period), "fieldtype": "Currency"})
            self.columns.append(
                {"label": "Receipts " + period, "fieldname": "receipts" + scrub(period), "fieldtype": "Currency"})
            self.columns.append(
                {"label": "Consumption " + period, "fieldname": "consumption" + scrub(period), "fieldtype": "Currency"})
        
        # Add total columns after the period columns
        self.columns.append(
            {"label": "Total Orders", "fieldname": "orders_total", "fieldtype": "Currency", "width": 120})
        self.columns.append(
            {"label": "Total Receipts", "fieldname": "receipts_total", "fieldtype": "Currency", "width": 120})
        self.columns.append(
            {"label": "Total Consumption", "fieldname": "consumption_total", "fieldtype": "Currency", "width": 120})

    def get_orders_data(self):
        self.get_purchase_transactions_based_on_item_group()

    def get_receipts_data(self):
        self.get_receipt_transactions_based_on_item_group()

    def get_consumption_data(self):
        self.get_consumption_transactions_based_on_item_group()

    def get_purchase_transactions_based_on_item_group(self):
        tran = DocType("Purchase Order")
        detail = DocType("Purchase Order Item")
        item = DocType("Item")
        query = (
            frappe.qb.from_(tran)
            .inner_join(detail)
            .on(tran.name == detail.parent)
            .inner_join(item)
            .on(detail.item_code == item.name)
            .select(
                item.item_group,
                item.item_code,
                tran.transaction_date,
                tran.name.as_("voucher_no"),
                tran.supplier,
                detail.qty,
                detail.rate,
                detail.amount,
                detail.base_amount,
                tran.company,
                tran.status
            )
            .where((detail.docstatus == 1) & (tran.docstatus == 1))
        )

        if self.filters.get("company"):
            query = query.where(tran.company == self.filters.company)
        if self.filters.get("from_date"):
            query = query.where(tran.transaction_date >= self.filters.from_date)
        if self.filters.get("to_date"):
            query = query.where(tran.transaction_date <= self.filters.to_date)
        if self.filters.get("cost_center"):
            query = query.where(tran.cost_center == self.filters.cost_center)
            
        self.order_entries = query.run(as_dict=1)
        

    def get_receipt_transactions_based_on_item_group(self):
        # Get receipts from Purchase Receipt
        pr = DocType("Purchase Receipt")
        pr_item = DocType("Purchase Receipt Item")
        item = DocType("Item")
        pr_query = (
            frappe.qb.from_(pr)
            .inner_join(pr_item)
            .on(pr.name == pr_item.parent)
            .inner_join(item)
            .on(pr_item.item_code == item.name)
            .select(
                item.item_group,
                item.item_code,
                pr.posting_date,
                pr.name.as_("voucher_no"),
                pr_item.warehouse,
                Case()
                .when(pr.is_return == 1, -pr_item.amount)
                .else_(pr_item.amount)
                .as_("amount"),
                ValueWrapper("Purchase Receipt").as_("voucher_type")
            )
            .where(
                (pr_item.docstatus == 1) &
                (pr.docstatus == 1)
            )
        )

        # Get receipts from Stock Entry
        se = DocType("Stock Entry")
        se_detail = DocType("Stock Entry Detail")
        se_query = (
            frappe.qb.from_(se)
            .inner_join(se_detail)
            .on(se.name == se_detail.parent)
            .inner_join(item)
            .on(se_detail.item_code == item.name)
            .select(
                item.item_group,
                item.item_code,
                se.posting_date,
                se.name.as_("voucher_no"),
                se_detail.t_warehouse.as_("warehouse"),
                se_detail.amount,
                ValueWrapper("Stock Entry").as_("voucher_type")
            )
            .where(
                (se_detail.docstatus == 1) &
                (se.docstatus == 1) &
                (se.purpose == "Material Receipt")
            )
        )

        # Apply filters before union
        if self.filters.get("company"):
            pr_query = pr_query.where(pr.company == self.filters.company)
            se_query = se_query.where(se.company == self.filters.company)
        if self.filters.get("from_date"):
            pr_query = pr_query.where(pr.posting_date >= self.filters.from_date)
            se_query = se_query.where(se.posting_date >= self.filters.from_date)
        if self.filters.get("to_date"):
            pr_query = pr_query.where(pr.posting_date <= self.filters.to_date)
            se_query = se_query.where(se.posting_date <= self.filters.to_date)
        if self.filters.get("cost_center"):
            pr_query = pr_query.where(pr.cost_center == self.filters.cost_center)
            se_query = se_query.where(se.cost_center == self.filters.cost_center)

        # Combine queries after applying filters
        query = pr_query.union_all(se_query)
            
        self.receipt_entries = query.run(as_dict=1)
        
        

    def get_consumption_transactions_based_on_item_group(self):
        conditions = ""
        if self.filters.get("company"):
            conditions += " AND se.company = %(company)s"
        if self.filters.get("from_date"):
            conditions += " AND se.posting_date >= %(from_date)s"
        if self.filters.get("to_date"):
            conditions += " AND se.posting_date <= %(to_date)s"
        if self.filters.get("cost_center"):
            conditions += " AND se.cost_center = %(cost_center)s"

        def get_ste_data():
            query = f"""
                SELECT
                    itm.item_group,
                    se.posting_date,
                    sed.amount,
                    se.name as voucher_no,
                    sed.item_code,
                    'Stock Entry' as voucher_type,
                    CONCAT('Material Issue [Source:',
                        COALESCE(sed.s_warehouse, 'NULL'),
                        ' Target:', COALESCE(sed.t_warehouse, 'NULL'),
                        ']') as entry_type
                FROM `tabStock Entry` se
                INNER JOIN `tabStock Entry Detail` sed ON se.name = sed.parent
                INNER JOIN `tabItem` itm ON sed.item_code = itm.name
                WHERE se.docstatus = 1
                AND (
                    -- Include entries that are genuine Material Issues:
                    -- 1. Must be Material Issue purpose
                    se.purpose = 'Material Issue'
                    -- 2. Must have MI- prefix in name (Material Issue)
                    AND se.name LIKE 'MI-%%'
                    -- 3. Must not be a transfer (check for specific pattern)
                    AND se.name NOT LIKE 'MAT-%%'
                    -- 4. Must have source warehouse
                    AND sed.s_warehouse IS NOT NULL
                    -- 5. Must be a consumption, not internal movement
                    AND NOT EXISTS (
                        SELECT 1 FROM `tabStock Entry Detail` sed2
                        WHERE sed2.parent = se.name
                        AND sed2.t_warehouse IS NOT NULL
                    )
                )
                {conditions}
            """
            return frappe.db.sql(query, self.filters, as_dict=1)
            
        def get_dn_data():
            query = f"""
                SELECT
                    itm.item_group,
                    dn.posting_date,
                    CASE WHEN dn.is_return = 1 THEN -1 * dni.amount ELSE dni.amount END as amount,
                    dn.name as voucher_no,
                    dni.item_code,
                    'Delivery Note' as voucher_type,
                    CASE WHEN dn.is_return = 1 THEN 'Sales Return' ELSE 'Delivery' END as entry_type
                FROM `tabDelivery Note` dn
                INNER JOIN `tabDelivery Note Item` dni ON dn.name = dni.parent
                INNER JOIN `tabItem` itm ON dni.item_code = itm.name
                WHERE dn.docstatus = 1
                AND dni.docstatus = 1
                {conditions.replace('se.', 'dn.')}
            """
            return frappe.db.sql(query, self.filters, as_dict=1)
            
        def get_si_data():
            query = f"""
                SELECT
                    itm.item_group,
                    si.posting_date,
                    CASE WHEN si.is_return = 1 THEN -1 * sii.amount ELSE sii.amount END as amount,
                    si.name as voucher_no,
                    sii.item_code,
                    'Sales Invoice' as voucher_type,
                    CASE WHEN si.is_return = 1 THEN 'Sales Return' ELSE 'Direct Invoice' END as entry_type
                FROM `tabSales Invoice` si
                INNER JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
                INNER JOIN `tabItem` itm ON sii.item_code = itm.name
                WHERE si.docstatus = 1
                AND sii.docstatus = 1
                AND si.update_stock = 1
                {conditions.replace('se.', 'si.')}
            """
            return frappe.db.sql(query, self.filters, as_dict=1)

        # Get and validate each type of consumption entry
        ste_entries = get_ste_data()
        print("\nDEBUG: Analyzing Stock Entry Consumption:")
        ste_total = 0
        ste_by_pattern = {'MI-': 0, 'MAT-': 0, 'Other': 0}
        
        for entry in ste_entries:
            amount = entry.amount or 0
            ste_total += amount
            
            # Categorize by naming pattern
            if entry.voucher_no.startswith('MI-'):
                ste_by_pattern['MI-'] += amount
            elif entry.voucher_no.startswith('MAT-'):
                ste_by_pattern['MAT-'] += amount
            else:
                ste_by_pattern['Other'] += amount
            
            # Print detailed entry info
            if amount != 0:  # Only show non-zero entries
                print(f"Entry: {entry.voucher_no}")
                print(f"  Amount: {amount:,.2f}")
                print(f"  Type: {entry.entry_type}")
                print(f"  Group: {entry.item_group}")
                print("  -----------")
                
        print("\nStock Entry Totals by Pattern:")
        for pattern, total in ste_by_pattern.items():
            print(f"{pattern}: {total:,.2f}")
        print(f"Total: {ste_total:,.2f}")

        dn_entries = get_dn_data()
        print("\nDEBUG: Delivery Note Consumption Details:")
        for entry in dn_entries:
            print(f"Delivery {entry.voucher_no}: {entry.amount:,.2f} | {entry.entry_type}")
        print(f"Total Delivery Consumption: {sum(e.amount for e in dn_entries):,.2f}")

        si_entries = get_si_data()
        print("\nDEBUG: Sales Invoice Consumption Details:")
        for entry in si_entries:
            print(f"Invoice {entry.voucher_no}: {entry.amount:,.2f} | {entry.entry_type}")
        print(f"Total Direct Invoice Consumption: {sum(e.amount for e in si_entries):,.2f}")

        # Combine all entries
        self.consumption_entries = ste_entries + dn_entries + si_entries
        print(f"\nDEBUG: Total Combined Consumption: {sum(e.amount for e in self.consumption_entries):,.2f}")

        # Summarize and print debug information
        type_totals = {}
        for entry in self.consumption_entries:
            entry_type = entry.get('entry_type', '').split('[')[0].strip()  # Get clean type without warehouse info
            type_totals[entry_type] = type_totals.get(entry_type, 0) + entry.amount

        print("\nDEBUG: Consumption by Type:")
        for entry_type, total in sorted(type_totals.items()):
            print(f"{entry_type}: {total:,.2f}")
            
        print("\nDEBUG: Sample Entries:")
        for entry in self.consumption_entries[:5]:  # Show first 5 entries
            print(f"Entry: {entry.voucher_no} | Type: {entry.entry_type} | Amount: {entry.amount} | Group: {entry.item_group}")
        
    def get_rows_by_group(self):
        self.get_orders_periodic_data()
        self.get_receipts_periodic_data()
        self.get_consumption_periodic_data()
        out = []

        for d in reversed(self.group_entries):
            row = {"item_group": d.name, "indent": self.depth_map.get(d.name)}
            ototal = rtotal = ctotal = 0
            for end_date in self.periodic_daterange:
                period = self.get_period(end_date)
                oamount = flt(self.orders_periodic_data.get(d.name, {}).get(period, 0.0))
                ramount = flt(self.receipts_periodic_data.get(d.name, {}).get(period, 0.0))
                camount = flt(self.consumption_periodic_data.get(d.name, {}).get(period, 0.0))
                row["orders" + scrub(period)] = oamount
                row["receipts" + scrub(period)] = ramount
                row["consumption" + scrub(period)] = camount
                if d.parent:
                    self.orders_periodic_data.setdefault(d.parent, frappe._dict()).setdefault(period, 0.0)
                    self.receipts_periodic_data.setdefault(d.parent, frappe._dict()).setdefault(period, 0.0)
                    self.consumption_periodic_data.setdefault(d.parent, frappe._dict()).setdefault(period, 0.0)
                    self.orders_periodic_data[d.parent][period] += oamount
                    self.receipts_periodic_data[d.parent][period] += ramount
                    self.consumption_periodic_data[d.parent][period] += camount
                ototal += oamount
                rtotal += ramount
                ctotal += camount

            row["orders_total"] = ototal
            row["receipts_total"] = rtotal
            row["consumption_total"] = ctotal
            out = [row] + out

        self.data = out

    def get_orders_periodic_data(self):
        self.orders_periodic_data = frappe._dict()
        cement_total = 0.0
        
        # First pass: Collect direct amounts for each item group
        for d in self.order_entries:
            period = self.get_period(d.get("transaction_date"))
            amount = flt(d.amount)
            
                

            
            self.orders_periodic_data.setdefault(d.item_group, frappe._dict()).setdefault(period, 0.0)
            self.orders_periodic_data[d.item_group][period] += amount
        
        
            
        # Second pass: Roll up amounts to parent groups
        for d in reversed(self.group_entries):
            if not d.parent:
                continue
                
            for period in self.periodic_daterange:
                period_key = self.get_period(period)
                child_amount = self.orders_periodic_data.get(d.name, {}).get(period_key, 0.0)
                
                if child_amount:
                    self.orders_periodic_data.setdefault(d.parent, frappe._dict()).setdefault(period_key, 0.0)
                    self.orders_periodic_data[d.parent][period_key] += child_amount

    def get_receipts_periodic_data(self):
        self.receipts_periodic_data = frappe._dict()
        
        
        # First pass: Collect direct amounts for each item group
        receipts_data = {"total": 0}
        for d in self.receipt_entries:
            period = self.get_period(d.get("posting_date"))
            amount = flt(d.amount)
            
            if d.item_group == "CEMENTS":
                receipts_data["total"] += amount
            
            self.receipts_periodic_data.setdefault(d.item_group, frappe._dict()).setdefault(period, 0.0)
            self.receipts_periodic_data[d.item_group][period] += amount
            
        if receipts_data["total"] > 0:
            print(f"Total Receipts: {receipts_data['total']:,.2f}")
        
        
            
        # Second pass: Roll up amounts to parent groups
        for d in reversed(self.group_entries):
            if not d.parent:
                continue
                
            for period in self.periodic_daterange:
                period_key = self.get_period(period)
                child_amount = self.receipts_periodic_data.get(d.name, {}).get(period_key, 0.0)
                
                if child_amount:
                    self.receipts_periodic_data.setdefault(d.parent, frappe._dict()).setdefault(period_key, 0.0)
                    self.receipts_periodic_data[d.parent][period_key] += child_amount

    def get_consumption_periodic_data(self):
        self.consumption_periodic_data = frappe._dict()
        
        # First pass: Collect direct amounts for each item group
        consumption_data = {"total": 0}
        for d in self.consumption_entries:
            period = self.get_period(d.get("posting_date"))
            amount = flt(d.amount)
            
            if d.item_group == "CEMENTS":
                consumption_data["total"] += amount
            
            self.consumption_periodic_data.setdefault(d.item_group, frappe._dict()).setdefault(period, 0.0)
            self.consumption_periodic_data[d.item_group][period] += amount
            
        if consumption_data["total"] > 0:
            print("\n=== CEMENTS SUMMARY ===")
            print(f"Total Consumption: {consumption_data['total']:,.2f}")
            print("===\n")
        

        
        # Second pass: Roll up amounts to parent groups
        for d in reversed(self.group_entries):
            if not d.parent:
                continue
                
            frappe.msgprint(f"DEBUG: Processing parent rollup for {d.name} -> {d.parent}")
            period_totals = frappe._dict()
                
            for period in self.periodic_daterange:
                period_key = self.get_period(period)
                child_amount = self.consumption_periodic_data.get(d.name, {}).get(period_key, 0.0)
                
                if child_amount:
                    self.consumption_periodic_data.setdefault(d.parent, frappe._dict()).setdefault(period_key, 0.0)
                    self.consumption_periodic_data[d.parent][period_key] += child_amount
                    period_totals[period_key] = self.consumption_periodic_data[d.parent][period_key]
            

    def get_period(self, posting_date):
        if self.filters.range == "Weekly":
            period = _("Week {0} {1}").format(str(posting_date.isocalendar()[1]), str(posting_date.year))
        elif self.filters.range == "Monthly":
            period = _(str(self.months[posting_date.month - 1])) + " " + str(posting_date.year)
        elif self.filters.range == "Quarterly":
            period = _("Quarter {0} {1}").format(
                str(((posting_date.month - 1) // 3) + 1), str(posting_date.year)
            )
        elif self.filters.range == "Half-Yearly":
            period = _("Half Year {0} {1}").format(
                "1" if posting_date.month <= 6 else "2", str(posting_date.year)
            )
        else:
            year = get_fiscal_year(posting_date, company=self.filters.company)
            period = str(year[0])
        return period

    def get_period_date_ranges(self):
        from dateutil.relativedelta import MO, relativedelta

        from_date, to_date = getdate(self.filters.from_date), getdate(self.filters.to_date)

        increment = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(
            self.filters.range, 1
        )

        if self.filters.range in ["Monthly", "Quarterly"]:
            from_date = from_date.replace(day=1)
        elif self.filters.range == "Yearly":
            from_date = get_fiscal_year(from_date, company=self.filters.company)[1]
            to_date = get_fiscal_year(to_date, company=self.filters.company)[2]
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

    def get_groups(self):
        parent = "parent_item_group"
        grp = DocType("Item Group")
        self.depth_map = frappe._dict()

        query = (
            frappe.qb.from_(grp)
            .select(grp.name, grp.lft, grp.rgt, grp.parent_item_group.as_("parent"))
            .orderby(grp.lft)
        )

        self.group_entries = query.run(as_dict=1)

        for d in self.group_entries:
            if d.parent:
                self.depth_map.setdefault(d.name, self.depth_map.get(d.parent) + 1)
            else:
                self.depth_map.setdefault(d.name, 0)

    def get_chart_data(self):
        if not self.filtered_data:
            return

        labels = self.chart_labels
        orders = [self.filtered_data[0]["orders" + scrub(period)] for period in labels]
        receipts = [self.filtered_data[0]["receipts" + scrub(period)] for period in labels]
        consumptions = [self.filtered_data[0]["consumption" + scrub(period)] for period in labels]
        
        currency = frappe.get_cached_value('Global Defaults', None, 'default_currency')
        self.chart = {
            "data": {
                "labels": labels,
                "datasets": [
                    {"name": "Orders", "values": orders, "chartType": "bar"},
                    {"name": "Receipts", "values": receipts, "chartType": "bar"},
                    {"name": "Consumption", "values": consumptions, "chartType": "bar"}
                ]
            },
            "type": "bar",
            "fieldtype": "Currency",
            "axisOptions": {"xIsSeries": True}
            
        }
