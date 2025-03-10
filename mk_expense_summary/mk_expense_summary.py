import frappe
from frappe import _, scrub
from frappe.utils import add_days, add_to_date, flt, getdate
from frappe.query_builder import DocType, Field
from erpnext.accounts.utils import get_fiscal_year
from frappe.utils.nestedset import get_descendants_of
from dateutil.relativedelta import relativedelta, MO

def execute(filters=None):
    report = PaymentAnalytics(filters)
    report.validate_filters()
    report.get_period_date_ranges()
    report.get_columns()
    report.get_data()
    
    # Filter data based on supplier group
    if report.filters.get("supplier_group"):
        report.filtered_data = [d for d in report.data if d.get("supplier_group") == report.filters.supplier_group]
    else:
        report.filtered_data = report.data
    
    report.get_chart_data()
    return report.columns, report.filtered_data, None, report.chart, None, 0

class PaymentAnalytics:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.date_field = "posting_date"
        self.months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        self.data = []
        self.columns = []
        self.filtered_data = [] 
        self.chart = {}
        self.supplier_groups = []
        self.entries = []
        self.payment_periodic_data = frappe._dict()
        self.periodic_daterange = []

    def validate_filters(self):
        if not self.filters.get("company"):
            frappe.throw(_("Please select a Company"))
        if not self.filters.get("from_date") or not self.filters.get("to_date"):
            frappe.throw(_("Please select From Date and To Date"))
        if not self.filters.get("payment_type"):
            frappe.throw(_("Please select Payment Type"))
        if self.filters.from_date > self.filters.to_date:
            frappe.throw(_("From Date must be before To Date"))
        if self.filters.get("range") not in ["Weekly", "Monthly", "Quarterly", "Yearly"]:
            self.filters.range = "Monthly"

    def get_period_date_ranges(self):
        from_date, to_date = getdate(self.filters.from_date), getdate(self.filters.to_date)

        if self.filters.range == "Weekly":
            from_date = from_date + relativedelta(weekday=MO(-1))
            self.periodic_daterange = []
            while from_date <= to_date:
                self.periodic_daterange.append(min(add_days(from_date, 6), to_date))
                from_date = add_days(from_date, 7)
        else:
            # Monthly, Quarterly, or Yearly
            increment = {
                "Monthly": 1,
                "Quarterly": 3,
                "Yearly": 12
            }.get(self.filters.range, 1)

            if self.filters.range in ["Monthly", "Quarterly"]:
                from_date = from_date.replace(day=1)
            elif self.filters.range == "Yearly":
                from_date = get_fiscal_year(from_date, company=self.filters.company)[1]

            self.periodic_daterange = []
            while from_date <= to_date:
                period_end = add_to_date(from_date, months=increment, days=-1)
                if period_end > to_date:
                    period_end = to_date
                self.periodic_daterange.append(period_end)
                from_date = add_days(period_end, 1)

    def get_columns(self):
        self.columns = [{
            "label": _("Supplier Group"),
            "fieldname": "supplier_group",
            "fieldtype": "Link",
            "options": "Supplier Group",
            "width": 200
        }]

        for end_date in self.periodic_daterange:
            period = self.get_period(end_date)
            self.columns.append({
                "label": _(period),
                "fieldname": scrub(period),
                "fieldtype": "Float",
                "width": 120
            })

        self.columns.append({
            "label": _("Total"),
            "fieldname": "total",
            "fieldtype": "Float",
            "width": 120
        })

    def get_data(self):
        self.get_payment_entries()
        self.get_rows_by_supplier_group()

    def get_payment_entries(self):
        pe = DocType("Payment Entry")
        supplier = DocType("Supplier")

        query = (
            frappe.qb.from_(pe)
            .join(supplier)
            .on(pe.party == supplier.name)
            .select(
                supplier.supplier_group.as_("supplier_group"),
                pe.base_paid_amount.as_("amount"),
                pe.posting_date
            )
            .where(pe.docstatus == 1)
            .where(pe.payment_type == self.filters.payment_type)
            .where(pe.party_type == "Supplier")
            .where(pe.company == self.filters.company)
            .where(pe.posting_date >= self.filters.from_date)
            .where(pe.posting_date <= self.filters.to_date)
        )

        if self.filters.get("mode_of_payment"):
            query = query.where(pe.mode_of_payment == self.filters.mode_of_payment)
        if self.filters.get("supplier_group"):
            query = query.where(supplier.supplier_group == self.filters.supplier_group)

        self.entries = query.run(as_dict=1)
        self.get_supplier_groups()

    def get_rows_by_supplier_group(self):
        self.get_periodic_data()
        out = []

        for group in sorted(self.supplier_groups):
            row = {"supplier_group": group}
            total = 0
            for end_date in self.periodic_daterange:
                period = self.get_period(end_date)
                amount = flt(self.payment_periodic_data.get(group, {}).get(period, 0.0))
                row[scrub(period)] = amount
                total += amount
            row["total"] = total
            if total != 0:  # Only include rows with non-zero totals
                out.append(row)

        self.data = sorted(out, key=lambda x: x["total"], reverse=True)

    def get_periodic_data(self):
        self.payment_periodic_data = frappe._dict()
        for d in self.entries:
            if not d.posting_date:
                continue
            period = self.get_period(d.posting_date)
            self.payment_periodic_data.setdefault(d.supplier_group, frappe._dict())
            self.payment_periodic_data[d.supplier_group][period] = \
                self.payment_periodic_data[d.supplier_group].get(period, 0.0) + flt(d.amount)

    def get_period(self, posting_date):
        if isinstance(posting_date, str):
            posting_date = getdate(posting_date)

        if self.filters.range == "Weekly":
            period = _("Week {0} {1}").format(posting_date.isocalendar()[1], posting_date.year)
        elif self.filters.range == "Monthly":
            period = _(self.months[posting_date.month - 1]) + " " + str(posting_date.year)
        elif self.filters.range == "Quarterly":
            quarter = ((posting_date.month - 1) // 3) + 1
            period = _("Quarter {0} {1}").format(quarter, posting_date.year)
        else:
            period = str(get_fiscal_year(posting_date, company=self.filters.company)[0])
        return period

    def get_supplier_groups(self):
        if not self.entries:
            return
        self.supplier_groups = list(set(d.supplier_group for d in self.entries if d.supplier_group))

    def get_chart_data(self):
        if not self.filtered_data:
            return

        labels = [d.get("label") for d in self.columns[1:-1]]  # Exclude first and last columns
        datasets = []

        # Calculate period totals
        period_totals = []
        for period in labels:
            period_field = scrub(period)
            total = sum(row.get(period_field, 0) for row in self.filtered_data)
            period_totals.append(total)

        datasets.append({
            "name": _("Total Expenses"),
            "values": period_totals
        })

        self.chart = {
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "type": "bar",
            "fieldtype": "Currency"
        }