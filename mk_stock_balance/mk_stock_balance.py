# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


from operator import itemgetter
from typing import Any, TypedDict

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce
from frappe.utils import add_days, cint, date_diff, flt, getdate
from frappe.utils.nestedset import get_descendants_of

import erpnext
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.utils import add_additional_uom_columns


class StockBalanceFilter(TypedDict):
    company: str | None
    from_date: str
    to_date: str
    item_group: str | None
    item: str | None
    warehouse: str | None
    include_uom: str | None  # include extra info in converted UOM


SLEntry = dict[str, Any]


def execute(filters: StockBalanceFilter | None = None):
    return StockBalanceReport(filters).run()


class StockBalanceReport:
    def __init__(self, filters: StockBalanceFilter | None) -> None:
        self.filters = filters
        self.from_date = getdate(filters.get("from_date"))
        self.to_date = getdate(filters.get("to_date"))

        self.start_from = None
        self.data = []
        self.sorted_data = []  # Will hold hierarchically sorted data
        self.columns = []
        self.sle_entries: list[SLEntry] = []
        self.item_group_map = {}  # Will store parent-child relationships
        self.set_company_currency()

    def set_company_currency(self) -> None:
        if self.filters.get("company"):
            self.company_currency = erpnext.get_company_currency(self.filters.get("company"))
        else:
            self.company_currency = frappe.db.get_single_value("Global Defaults", "default_currency")

    def run(self):
        self.float_precision = cint(frappe.db.get_default("float_precision")) or 3

        self.inventory_dimensions = self.get_inventory_dimension_fields()
        self.get_item_group_hierarchy()
        self.prepare_opening_data_from_closing_balance()
        self.prepare_stock_ledger_entries() 
        self.prepare_new_data()

        if not self.columns:
            self.columns = self.get_columns()

        self.sort_data_hierarchically()
        
        return self.columns, self.sorted_data

    def prepare_opening_data_from_closing_balance(self) -> None:
        self.opening_data = frappe._dict({})

        closing_balance = self.get_closing_balance()
        if not closing_balance:
            return

        self.start_from = add_days(closing_balance[0].to_date, 1)
        res = frappe.get_doc("Closing Stock Balance", closing_balance[0].name).get_prepared_data()

        for entry in res.data:
            entry = frappe._dict(entry)

            group_by_key = self.get_group_by_key(entry)
            if (group_by_key) not in self.opening_data:
                self.opening_data.setdefault(group_by_key, entry)

    def prepare_new_data(self):
        self.item_warehouse_map = self.get_item_warehouse_map()

        del self.sle_entries

        sre_details = self.get_sre_reserved_qty_details()

        for _key, report_data in self.item_warehouse_map.items():
            report_data.update(
                {"reserved_stock": sre_details.get((report_data.item_code, report_data.warehouse), 0.0)}
            )

            if (
                not self.filters.get("include_zero_stock_items")
                and report_data
                and report_data.bal_qty == 0
                and report_data.bal_val == 0
            ):
                continue

            self.data.append(report_data)

    def get_item_warehouse_map(self):
        item_warehouse_map = {}
        self.opening_vouchers = self.get_opening_vouchers()

        # HACK: This is required to avoid causing db query in flt
        _system_settings = frappe.get_cached_doc("System Settings")
        with frappe.db.unbuffered_cursor():
            self.sle_entries = self.sle_query.run(as_dict=True, as_iterator=True)

            for entry in self.sle_entries:
                group_by_key = self.get_group_by_key(entry)
                if group_by_key not in item_warehouse_map:
                    self.initialize_data(item_warehouse_map, group_by_key, entry)

                self.prepare_item_warehouse_map(item_warehouse_map, entry, group_by_key)

                if self.opening_data.get(group_by_key):
                    del self.opening_data[group_by_key]

        for group_by_key, entry in self.opening_data.items():
            if group_by_key not in item_warehouse_map:
                self.initialize_data(item_warehouse_map, group_by_key, entry)

        item_warehouse_map = filter_items_with_no_transactions(
            item_warehouse_map, self.float_precision, self.inventory_dimensions
        )

        return item_warehouse_map

    def get_sre_reserved_qty_details(self) -> dict:
        from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
            get_sre_reserved_qty_for_items_and_warehouses as get_reserved_qty_details,
        )

        item_code_list, warehouse_list = [], []
        for d in self.item_warehouse_map:
            item_code_list.append(d[1])
            warehouse_list.append(d[2])

        return get_reserved_qty_details(item_code_list, warehouse_list)

    def prepare_item_warehouse_map(self, item_warehouse_map, entry, group_by_key):
        qty_dict = item_warehouse_map[group_by_key]
        for field in self.inventory_dimensions:
            qty_dict[field] = entry.get(field)

        if entry.voucher_type == "Stock Reconciliation" and (not entry.batch_no or entry.serial_no):
            qty_diff = flt(entry.qty_after_transaction) - flt(qty_dict.bal_qty)
        else:
            qty_diff = flt(entry.actual_qty)

        value_diff = flt(entry.stock_value_difference)

        if entry.posting_date < self.from_date or entry.voucher_no in self.opening_vouchers.get(
            entry.voucher_type, []
        ):
            qty_dict.opening_qty += qty_diff
            qty_dict.opening_val += value_diff

        elif entry.posting_date >= self.from_date and entry.posting_date <= self.to_date:
            if flt(qty_diff, self.float_precision) >= 0:
                qty_dict.in_qty += qty_diff
                qty_dict.in_val += value_diff
            else:
                qty_dict.out_qty += abs(qty_diff)
                qty_dict.out_val += abs(value_diff)

        qty_dict.val_rate = entry.valuation_rate
        qty_dict.bal_qty += qty_diff
        qty_dict.bal_val += value_diff

    def initialize_data(self, item_warehouse_map, group_by_key, entry):
        opening_data = self.opening_data.get(group_by_key, {})

        item_warehouse_map[group_by_key] = frappe._dict(
            {
                "item_code": entry.item_code,
                "warehouse": entry.warehouse,
                "item_group": entry.item_group,
                "company": entry.company,
                "currency": self.company_currency,
                "stock_uom": entry.stock_uom,
                "item_name": entry.item_name,
                "opening_qty": opening_data.get("bal_qty") or 0.0,
                "opening_val": opening_data.get("bal_val") or 0.0,
                "opening_fifo_queue": opening_data.get("fifo_queue") or [],
                "in_qty": 0.0,
                "in_val": 0.0,
                "out_qty": 0.0,
                "out_val": 0.0,
                "bal_qty": opening_data.get("bal_qty") or 0.0,
                "bal_val": opening_data.get("bal_val") or 0.0,
                "val_rate": 0.0,
            }
        )

    def get_group_by_key(self, row) -> tuple:
        group_by_key = [row.company, row.item_code, row.warehouse]

        for fieldname in self.inventory_dimensions:
            if not row.get(fieldname):
                continue

            if self.filters.get(fieldname):
                group_by_key.append(row.get(fieldname))

        return tuple(group_by_key)

    def get_closing_balance(self) -> list[dict[str, Any]]:
        if self.filters.get("ignore_closing_balance"):
            return []

        table = frappe.qb.DocType("Closing Stock Balance")

        query = (
            frappe.qb.from_(table)
            .select(table.name, table.to_date)
            .where(
                (table.docstatus == 1)
                & (table.company == self.filters.company)
                & (table.to_date <= self.from_date)
                & (table.status == "Completed")
            )
            .orderby(table.to_date, order=Order.desc)
            .limit(1)
        )

        for fieldname in ["warehouse", "item_code", "item_group"]:
            if self.filters.get(fieldname):
                query = query.where(table[fieldname] == self.filters.get(fieldname))

        return query.run(as_dict=True)

    def prepare_stock_ledger_entries(self):
        sle = frappe.qb.DocType("Stock Ledger Entry")
        item_table = frappe.qb.DocType("Item")

        query = (
            frappe.qb.from_(sle)
            .inner_join(item_table)
            .on(sle.item_code == item_table.name)
            .select(
                sle.item_code,
                sle.warehouse,
                sle.posting_date,
                sle.actual_qty,
                sle.valuation_rate,
                sle.company,
                sle.voucher_type,
                sle.qty_after_transaction,
                sle.stock_value_difference,
                sle.item_code.as_("name"),
                sle.voucher_no,
                sle.stock_value,
                sle.batch_no,
                sle.serial_no,
                sle.serial_and_batch_bundle,
                sle.has_serial_no,
                item_table.item_group,
                item_table.stock_uom,
                item_table.item_name,
            )
            .where((sle.docstatus < 2) & (sle.is_cancelled == 0))
            .orderby(sle.posting_datetime)
            .orderby(sle.creation)
        )

        query = self.apply_inventory_dimensions_filters(query, sle)
        query = self.apply_warehouse_filters(query, sle)
        query = self.apply_items_filters(query, item_table)
        query = self.apply_date_filters(query, sle)

        if self.filters.get("company"):
            query = query.where(sle.company == self.filters.get("company"))

        self.sle_query = query

    def apply_inventory_dimensions_filters(self, query, sle) -> str:
        inventory_dimension_fields = self.get_inventory_dimension_fields()
        if inventory_dimension_fields:
            for fieldname in inventory_dimension_fields:
                query = query.select(fieldname)
                if self.filters.get(fieldname):
                    query = query.where(sle[fieldname].isin(self.filters.get(fieldname)))

        return query

    def apply_warehouse_filters(self, query, sle) -> str:
        if self.filters.get("warehouse"):
            query = apply_warehouse_filter(query, sle, self.filters)

        return query

    def apply_items_filters(self, query, item_table) -> str:
        if item_group := self.filters.get("item_group"):
            children = get_descendants_of("Item Group", item_group, ignore_permissions=True)
            query = query.where(item_table.item_group.isin([*children, item_group]))

        for field in ["item_code", "brand"]:
            if not self.filters.get(field):
                continue
            elif field == "item_code":
                query = query.where(item_table.name == self.filters.get(field))
            else:
                query = query.where(item_table[field] == self.filters.get(field))

        return query

    def apply_date_filters(self, query, sle) -> str:
        if not self.filters.ignore_closing_balance and self.start_from:
            query = query.where(sle.posting_date >= self.start_from)

        if self.to_date:
            query = query.where(sle.posting_date <= self.to_date)

        return query

    def get_columns(self):
        columns = [
            {
                "label": _("Item Group"),
                "fieldname": "item_group",
                "fieldtype": "Link",
                "options": "Item Group",
                "width": 300,
                "indent": 1
            },
            {
                "label": _("Item Code"),
                "fieldname": "item_code",
                "fieldtype": "Link",
                "options": "Item",
                "width": 100,
            },
            {
                "label": _("Warehouse"),
                "fieldname": "warehouse",
                "fieldtype": "Link",
                "options": "Warehouse",
                "width": 100,
            },
            {
                "label": _("Stock UOM"),
                "fieldname": "stock_uom",
                "fieldtype": "Link",
                "options": "UOM",
                "width": 90,
            },
            {
                "label": _("Opening Qty"),
                "fieldname": "opening_qty",
                "fieldtype": "Float",
                "width": 80,
                "convertible": "qty",
            },
            {
                "label": _("Opening Value"),
                "fieldname": "opening_val",
                "fieldtype": "Float",
                "width": 80,
            },
            {
                "label": _("In Qty"),
                "fieldname": "in_qty",
                "fieldtype": "Float",
                "width": 80,
                "convertible": "qty",
            },
            {
                "label": _("In Value"),
                "fieldname": "in_val",
                "fieldtype": "Float",
                "width": 80,
            },
            {
                "label": _("Out Qty"),
                "fieldname": "out_qty",
                "fieldtype": "Float",
                "width": 80,
                "convertible": "qty",
            },
            {
                "label": _("Out Value"),
                "fieldname": "out_val",
                "fieldtype": "Float",
                "width": 80,
            },
            {
                "label": _("Balance Qty"),
                "fieldname": "bal_qty",
                "fieldtype": "Float",
                "width": 80,
                "convertible": "qty",
            },
            {
                "label": _("Balance Value"),
                "fieldname": "bal_val",
                "fieldtype": "Float",
                "width": 80,
            },
        ]

        return columns

    def add_additional_uom_columns(self):
        if not self.filters.get("include_uom"):
            return

        conversion_factors = self.get_itemwise_conversion_factor()
        add_additional_uom_columns(self.columns, self.data, self.filters.include_uom, conversion_factors)

    def get_itemwise_conversion_factor(self):
        items = []
        if self.filters.item_code or self.filters.item_group:
            items = [d.item_code for d in self.data]

        uom_table = frappe.qb.DocType("UOM Conversion Detail")
        item_table = frappe.qb.DocType("Item")
        
        query = (
            frappe.qb.from_(uom_table)
            .join(item_table)
            .on(uom_table.parent == item_table.name)
            .select(
                uom_table.conversion_factor,
                uom_table.parent,
            )
            .where(
                (uom_table.parenttype == "Item") & 
                (uom_table.uom == self.filters.include_uom)
            )
            .orderby(item_table.item_group)
            .orderby(item_table.item_name)
        )

        if items:
            query = query.where(uom_table.parent.isin(items))

        result = query.run(as_dict=1)
        if not result:
            return {}
        return result

    def get_opening_vouchers(self):
        opening_vouchers = {"Stock Entry": [], "Stock Reconciliation": []}

        se = frappe.qb.DocType("Stock Entry")
        sr = frappe.qb.DocType("Stock Reconciliation")

        vouchers_data = (
            frappe.qb.from_(
                (
                    frappe.qb.from_(se)
                    .select(se.name, Coalesce("Stock Entry").as_("voucher_type"))
                    .where((se.docstatus == 1) & (se.posting_date <= self.to_date) & (se.is_opening == "Yes"))
                )
                + (
                    frappe.qb.from_(sr)
                    .select(sr.name, Coalesce("Stock Reconciliation").as_("voucher_type"))
                    .where(
                        (sr.docstatus == 1)
                        & (sr.posting_date <= self.to_date)
                        & (sr.purpose == "Opening Stock")
                    )
                )
            ).select("voucher_type", "name")
        ).run(as_dict=True)

        if vouchers_data:
            for d in vouchers_data:
                opening_vouchers[d.voucher_type].append(d.name)

        return opening_vouchers

    @staticmethod
    def get_inventory_dimension_fields():
        return [dimension.fieldname for dimension in get_inventory_dimensions()]

    def get_item_group_hierarchy(self):
        # Get all item groups and their parents
        item_group = frappe.qb.DocType("Item Group")
        query = (
            frappe.qb.from_(item_group)
            .select(
                item_group.name,
                item_group.parent_item_group,
                item_group.lft,
                item_group.rgt
            )
            .orderby(item_group.lft)
        )
        self.item_group_map = {d.name: d for d in query.run(as_dict=True)}

    def sort_data_hierarchically(self):
        # Group data by item_group
        group_wise_data = {}
        for row in self.data:
            group = row.get("item_group")
            if group not in group_wise_data:
                group_wise_data[group] = []
            group_wise_data[group].append(row)

        # Calculate totals for each group including child groups
        def get_group_data(item_group, level=0):
            if not item_group:
                return []

            group_data = []
            current_group = self.item_group_map.get(item_group)
            if not current_group:
                return []

            # Add group's own data
            if item_group in group_wise_data:
                for row in group_wise_data[item_group]:
                    row_copy = row.copy()
                    row_copy["indent"] = level
                    group_data.append(row_copy)

            # Add child groups
            child_groups = [g.name for g in self.item_group_map.values() 
                           if g.parent_item_group == item_group]
            
            for child in sorted(child_groups):
                group_data.extend(get_group_data(child, level + 1))

            # Only return data if there are transactions
            return group_data if group_data else []

        # Process from root groups (those without parents)
        root_groups = [g.name for g in self.item_group_map.values() 
                      if not g.parent_item_group]
        
        self.sorted_data = []
        for root in sorted(root_groups):
            self.sorted_data.extend(get_group_data(root))


def filter_items_with_no_transactions(
    iwb_map, float_precision: float, inventory_dimensions: list | None = None
):
    pop_keys = []
    for group_by_key in iwb_map:
        qty_dict = iwb_map[group_by_key]

        no_transactions = True
        for key, val in qty_dict.items():
            if inventory_dimensions and key in inventory_dimensions:
                continue

            if key in [
                "item_code",
                "warehouse",
                "item_name",
                "item_group",
                "project",
                "stock_uom",
                "company",
                "opening_fifo_queue",
            ]:
                continue

            val = flt(val, float_precision)
            qty_dict[key] = val
            if key != "val_rate" and val:
                no_transactions = False

        if no_transactions:
            pop_keys.append(group_by_key)

    for key in pop_keys:
        iwb_map.pop(key)

    return iwb_map
