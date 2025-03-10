import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

class MKAccountsPayableSummary:
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.filters.report_date = getdate(self.filters.report_date or nowdate())
        self.age_as_on = getdate(nowdate()) \
            if self.filters.report_date > getdate(nowdate()) \
            else self.filters.report_date
        self.receivables = []  # Changed from dict to list
        self.supplier_map = {}  # Track suppliers with index

    def run(self):
        self.get_columns()
        self.get_supplier_details()
        self.get_invoices()
        self.get_payments()
        self.get_advances()
        self.get_debit_notes()
        data = self.process_data()
        return self.columns, data

    def get_columns(self):
        self.columns = [
            {
                "label": _("Supplier Group"),
                "fieldname": "supplier_group",
                "fieldtype": "Link",
                "options": "Supplier Group",
                "width": 150
            },
            {
                "label": _("Supplier"),
                "fieldname": "supplier",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 180
            },
            {
                "label": _("Advance Amount"),
                "fieldname": "advance_amount",
                "fieldtype": "Currency",
                "width": 120
            },
            {
                "label": _("Invoiced Amount"),
                "fieldname": "invoiced_amount",
                "fieldtype": "Currency",
                "width": 120
            },
            {
                "label": _("Paid Amount"),
                "fieldname": "paid_amount",
                "fieldtype": "Currency",
                "width": 120
            },
            {
                "label": _("Debit Note"),
                "fieldname": "debit_note",
                "fieldtype": "Currency",
                "width": 120
            },
            {
                "label": _("Outstanding Amount"),
                "fieldname": "outstanding_amount",
                "fieldtype": "Currency",
                "width": 120
            },
            {
                "label": _("Overdue Amount"),
                "fieldname": "overdue_amount",
                "fieldtype": "Currency",
                "width": 120
            }
        ]

    def get_supplier_details(self):
        conditions = ""
        if self.filters.get("supplier_group"):
            conditions += " AND supplier_group = %(supplier_group)s"
        if self.filters.get("supplier"):
            conditions += " AND name = %(supplier)s"

        suppliers = frappe.db.sql("""
            SELECT name, supplier_group 
            FROM `tabSupplier`
            WHERE disabled = 0 {0}
        """.format(conditions), self.filters, as_dict=1)

        for d in suppliers:
            self.supplier_map[d.name] = len(self.receivables)
            self.receivables.append(frappe._dict({
                "party": d.name,
                "supplier_group": d.supplier_group,
                "invoiced_amount": 0,
                "paid_amount": 0,
                "outstanding_amount": 0,
                "overdue_amount": 0,
                "advance_amount": 0,
                "debit_note": 0
            }))

    def get_invoices(self):
        conditions = ""
        if self.filters.get("supplier"):
            conditions += " AND supplier = %(supplier)s"

        invoices = frappe.db.sql("""
            SELECT supplier, grand_total, outstanding_amount, due_date
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 
            AND company = %(company)s
            AND posting_date <= %(report_date)s
            AND outstanding_amount != 0
            {0}
        """.format(conditions), self.filters, as_dict=1)

        for d in invoices:
            self.append_invoice_to_receivables(d)

    def get_payments(self):
        conditions = ""
        if self.filters.get("supplier"):
            conditions += " AND party = %(supplier)s"

        payments = frappe.db.sql("""
            SELECT party as supplier, paid_amount
            FROM `tabPayment Entry`
            WHERE docstatus = 1 
            AND payment_type = 'Pay'
            AND party_type = 'Supplier'
            AND company = %(company)s
            AND posting_date <= %(report_date)s
            {0}
        """.format(conditions), self.filters, as_dict=1)

        for d in payments:
            self.append_payment_to_receivables(d)

    def get_advances(self):
        conditions = ""
        if self.filters.get("supplier"):
            conditions += " AND t1.party = %(supplier)s"

        advances = frappe.db.sql("""
            SELECT 
                t1.party,
                IFNULL(t1.paid_amount, 0) as advance_amount
            FROM `tabPayment Entry` t1
            WHERE
                t1.docstatus = 1 
                AND t1.payment_type = 'Pay'
                AND t1.party_type = 'Supplier'
                AND t1.company = %(company)s
                AND t1.posting_date <= %(report_date)s
                {0}
        """.format(conditions), self.filters, as_dict=1)

        for advance in advances:
            self.append_advance_to_receivables(advance)

    def get_debit_notes(self):
        conditions = ""
        if self.filters.get("supplier"):
            conditions += " AND supplier = %(supplier)s"

        debit_notes = frappe.db.sql("""
            SELECT supplier, grand_total
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 
            AND is_return = 1
            AND company = %(company)s
            AND posting_date <= %(report_date)s
            {0}
        """.format(conditions), self.filters, as_dict=1)

        for d in debit_notes:
            self.append_note_to_receivables(d)

    def append_invoice_to_receivables(self, invoice):
        if invoice.party not in self.supplier_map:
            idx = len(self.receivables)
            self.supplier_map[invoice.party] = idx
            self.receivables.append(frappe._dict({
                "party": invoice.party,
                "invoiced_amount": 0.0,
                "paid_amount": 0.0,
                "credit_note_amount": 0.0,
                "advance_amount": 0.0,
                "outstanding_amount": 0.0,
                "overdue_amount": 0.0
            }))
        
        idx = self.supplier_map[invoice.party]
        entry = self.receivables[idx]
        entry.invoiced_amount += flt(invoice.invoice_amount or 0.0)
        entry.outstanding_amount += flt(invoice.outstanding_amount or 0.0)
        if getdate(invoice.due_date) < self.age_as_on:
            entry.overdue_amount += flt(invoice.outstanding_amount or 0.0)

    def append_note_to_receivables(self, note):
        if note.supplier not in self.supplier_map:
            idx = len(self.receivables)
            self.supplier_map[note.supplier] = idx
            self.receivables.append(frappe._dict({
                "party": note.supplier,
                "invoiced_amount": 0,
                "paid_amount": 0, 
                "credit_note_amount": 0,
                "advance_amount": 0,
                "outstanding_amount": 0,
                "overdue_amount": 0
            }))
        
        idx = self.supplier_map[note.supplier]
        self.receivables[idx].credit_note_amount += flt(note.grand_total)

    def append_advance_to_receivables(self, advance):
        if advance.party not in self.supplier_map:
            idx = len(self.receivables)
            self.supplier_map[advance.party] = idx
            self.receivables.append(frappe._dict({
                "party": advance.party,
                "invoiced_amount": 0.0,
                "paid_amount": 0.0,
                "credit_note_amount": 0.0, 
                "advance_amount": 0.0,
                "outstanding_amount": 0.0,
                "overdue_amount": 0.0
            }))
        
        idx = self.supplier_map[advance.party]
        self.receivables[idx].advance_amount += flt(advance.advance_amount or 0.0)

    def append_payment_to_receivables(self, payment):
        if payment.party not in self.supplier_map:
            idx = len(self.receivables)
            self.supplier_map[payment.party] = idx
            self.receivables.append(frappe._dict({
                "party": payment.party,
                "invoiced_amount": 0.0,
                "paid_amount": 0.0,
                "credit_note_amount": 0.0,
                "advance_amount": 0.0,
                "outstanding_amount": 0.0,
                "overdue_amount": 0.0
            }))
        
        idx = self.supplier_map[payment.party]
        self.receivables[idx].paid_amount += flt(payment.paid_amount or 0.0)

    def process_data(self):
        data = []
        for receivable in self.receivables:
            row = {
                "supplier_group": frappe.get_value("Supplier", receivable.party, "supplier_group"),
                "supplier": receivable.party,
                "advance_amount": receivable.advance_amount,  # Ensure this matches the field name
                "invoiced_amount": receivable.invoiced_amount,
                "paid_amount": receivable.paid_amount,
                "debit_note": receivable.credit_note_amount,
                "outstanding_amount": receivable.outstanding_amount,
                "overdue_amount": receivable.overdue_amount
            }
            data.append(row)
        return data

def execute(filters=None):
    return MKAccountsPayableSummary(filters).run()