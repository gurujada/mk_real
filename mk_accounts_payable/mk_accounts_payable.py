# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, scrub
from frappe.utils import getdate, nowdate, flt, cint, formatdate, cstr

class AccountsPayableReport:
    def __init__(self, filters=None):
        self.data = []
        self.columns = []
        self.filters = frappe._dict(filters or {})
        
        # Set required defaults for Payables
        self.filters.party_type = "Supplier"  # Hardcode party_type
        self.filters.account_type = "Payable"
        self.filters.naming_by = ["Buying Settings", "supp_master_name"]
        self.filters.report_date = getdate(self.filters.report_date or nowdate())
        
        # Initialize company first
        if not self.filters.get("company"):
            self.filters.company = frappe.db.get_default("Company")
            
        # Add default payable account
        if not self.filters.get("account"):
            self.filters.account = frappe.get_cached_value("Company", 
                self.filters.company,
                "default_payable_account")
        
        self.age_as_on = getdate(nowdate()) \
            if self.filters.report_date > getdate(nowdate()) \
            else self.filters.report_date

        # Initialize other required attributes
        self.company_currency = frappe.get_cached_value("Company", self.filters.company, "default_currency")
        self.currency_precision = frappe.db.get_default("currency_precision")
        self.party_details = {}
        self.invoices = []

    def run(self, args):
        self.filters.update(args)
        self.set_defaults()
        self.party_naming_by = frappe.db.get_value(
            self.filters.naming_by[0], None, self.filters.naming_by[1]
        )
        self.get_columns()
        self.get_data()
        return self.columns, self.data

    def set_defaults(self):
        if not self.filters.get("company"):
            self.filters.company = frappe.db.get_default("Company")
        self.company_currency = frappe.get_cached_value(
            "Company", self.filters.get("company"), "default_currency"
        )
        self.currency_precision = frappe.db.get_default("currency_precision")
        self.dr_or_cr = "credit"
        self.party_details = {}
        self.invoices = []
        self.data = []

    def get_columns(self):
        self.columns = [            
            {
                "label": _("Posting Date"),
                "fieldname": "posting_date",
                "fieldtype": "Date",
                "width": 90
            },
            {
                "label": _("Supplier"),
                "fieldname": "party",
                "fieldtype": "Link", 
                "options": "Supplier",
                "width": 120
            },
            {
                "label": _("Supplier Group"),
                "fieldname": "supplier_group", 
                "fieldtype": "Link",
                "options": "Supplier Group",
                "width": 120
            },
            {
                "label": _("Voucher Type"),
                "fieldname": "voucher_type",
                "fieldtype": "Data", 
                "width": 110
            },
            {
                "label": _("Bill No"),
                "fieldname": "voucher_no",
                "fieldtype": "Link",
                "options": "Purchase Invoice",
                "width": 120
            },
            {
                "label": _("Due Date"),
                "fieldname": "due_date",
                "fieldtype": "Date",
                "width": 90
            },
            {
                "label": _("Invoiced Amount"),
                "fieldname": "invoiced_amount",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 120
            },
            {
                "label": _("Outstanding Amount"),
                "fieldname": "outstanding_amount",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 120
            },
            {
                "label": _("Age (Days)"),
                "fieldname": "age",
                "fieldtype": "Int",
                "width": 80
            },
            {
                "label": _("0-30"),
                "fieldname": "range1",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 100
            },
            {
                "label": _("31-60"),
                "fieldname": "range2",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 100
            },
            {
                "label": _("61-90"),
                "fieldname": "range3",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 100
            },
            {
                "label": _("91-120"),
                "fieldname": "range4",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 100
            },
            {
                "label": _("120+"),
                "fieldname": "range5",
                "fieldtype": "Currency",
                "options": "currency",
                "width": 100
            }
        ]

    def get_data(self):
        self.entries = frappe.db.sql("""
            SELECT 
                ge.posting_date, 
                ge.due_date, 
                ge.party,
                s.supplier_group,
                ge.voucher_type, 
                ge.voucher_no,
                ge.account_currency as currency,
                SUM(ge.debit_in_account_currency) as invoice_amount,
                SUM(ge.credit_in_account_currency) as paid_amount
            FROM `tabGL Entry` ge
            LEFT JOIN `tabSupplier` s 
                ON ge.party = s.name
            WHERE 
                ge.company = %(company)s 
                AND ge.account = %(account)s
                AND ge.party_type = 'Supplier'
                AND ge.posting_date <= %(report_date)s
                AND ge.is_cancelled = 0
            GROUP BY 
                ge.voucher_type, 
                ge.voucher_no, 
                ge.party,
                ge.posting_date,
                ge.due_date
            ORDER BY 
                ge.posting_date, 
                ge.party
        """, self.filters, as_dict=1)

        self.build_data_from_entries()

    def build_data_from_entries(self):
        self.data = []
        for entry in self.entries:
            row = self.prepare_row(entry)
            self.data.append(row)

    def prepare_row(self, entry):
        return {
            "party": entry.party,
            "supplier_group": entry.supplier_group,
            "posting_date": entry.posting_date,
            "voucher_type": entry.voucher_type,
            "voucher_no": entry.voucher_no,
            "due_date": entry.due_date,
            "invoiced_amount": entry.invoice_amount,
            "outstanding_amount": entry.invoice_amount - entry.paid_amount,
            "age": (self.age_as_on - getdate(entry.posting_date)).days or 0,
            "range1": entry.get("range1", 0),
            "range2": entry.get("range2", 0),
            "range3": entry.get("range3", 0),
            "range4": entry.get("range4", 0),
            "range5": entry.get("range5", 0),
            "currency": entry.currency
        }

def execute(filters=None):
    args = {
        "account_type": "Payable",
        "naming_by": ["Buying Settings", "supp_master_name"],
    }
    return AccountsPayableReport(filters).run(args)
