// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["MK Accounts Payable"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "report_date",
            label: __("Posting Date"),
            fieldtype: "Date", 
            default: frappe.datetime.get_today(),
        },
        {
            fieldname: "finance_book",
            label: __("Finance Book"),
            fieldtype: "Link",
            options: "Finance Book"
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "Link", 
            options: "Cost Center",
            get_query: () => {
                var company = frappe.query_report.get_filter_value("company");
                return {
                    filters: {
                        company: company
                    }
                };
            }
        },
        {
            fieldname: "party_account",
            label: __("Payable Account"),
            fieldtype: "Link",
            options: "Account",
            get_query: () => {
                var company = frappe.query_report.get_filter_value("company");
                return {
                    filters: {
                        company: company,
                        account_type: "Payable",
                        is_group: 0
                    }
                };
            }
        },
        {
            fieldname: "ageing_based_on",
            label: __("Ageing Based On"),
            fieldtype: "Select",
            options: "Posting Date\nDue Date\nSupplier Invoice Date",
            default: "Due Date"
        },
        {
            fieldname: "range",
            label: __("Ageing Range"), 
            fieldtype: "Data",
            default: "30, 60, 90, 120"
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options('Supplier', txt);
            }
        },
        {
            fieldname: "supplier_group",
            label: __("Supplier Group"),
            fieldtype: "Link",
            options: "Supplier Group"
        },
        {
            fieldname: "group_by_party",
            label: __("Group By Supplier"),
            fieldtype: "Check"
        },
        {
            fieldname: "based_on_payment_terms",
            label: __("Based On Payment Terms"),
            fieldtype: "Check",
        },
        {
            fieldname: "show_remarks",
            label: __("Show Remarks"),
            fieldtype: "Check"
        },
        {
            fieldname: "show_future_payments",
            label: __("Show Future Payments"), 
            fieldtype: "Check"
        },
        {
            fieldname: "in_party_currency",
            label: __("In Party Currency"),
            fieldtype: "Check"
        }
    ],

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && data.bold) {
            value = value.bold();
        }
        return value;
    },

    onload: function(report) {
        report.page.add_inner_button(__("Accounts Payable Summary"), function() {
            var filters = report.get_values();
            frappe.set_route("query-report", "Accounts Payable Summary", {
                company: filters.company
            });
        });
    }
};

erpnext.utils.add_dimensions("Accounts Payable", 9);
