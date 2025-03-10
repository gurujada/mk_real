import frappe
from frappe import _
from frappe.utils import getdate, add_months, add_days, add_to_date, get_first_day, get_last_day, format_date

# Define allowed supplier groups at module level
ALLOWED_GROUPS = ["Admin Expenses", "Labour Expenses", "Plant & Machinery Repair, Maintenance-Mk One"]

def execute(filters=None):
    if not filters:
        filters = {}
    
    validate_filters(filters)
    columns = get_columns(filters)
    data = get_data(filters)

    chart_data = get_chart_data(columns, data)
    return columns, data, None, chart_data

def validate_filters(filters):
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("From Date and To Date are required"))

    if filters.get("from_date") > filters.get("to_date"):
        frappe.throw(_("From Date cannot be greater than To Date"))

    if not filters.get("period"):
        filters["period"] = "Monthly"  # Default to monthly if not specified

    if filters.get("period") not in ["Weekly", "Monthly", "Quarterly", "Yearly"]:
        frappe.throw(_("Invalid period. Please select Weekly, Monthly, Quarterly, or Yearly"))

    if filters.get("supplier_group") and filters.get("supplier_group") not in ALLOWED_GROUPS:
        frappe.throw(_("Selected Supplier Group must be one of the allowed groups"))

def get_period_date_ranges(filters):
    ranges = []
    period_start_date = getdate(filters.from_date)
    end_date = getdate(filters.to_date)

    while period_start_date <= end_date:
        if filters.period == "Weekly":
            period_end_date = add_days(period_start_date, 6)
        elif filters.period == "Monthly":
            period_end_date = get_last_day(period_start_date)
        elif filters.period == "Quarterly":
            period_end_date = get_last_day(add_months(period_start_date, 2))
        else:  # Yearly
            period_end_date = get_last_day(add_months(period_start_date, 11))

        if period_end_date > end_date:
            period_end_date = end_date

        ranges.append({
            "start_date": period_start_date,
            "end_date": period_end_date,
            "label": get_period_label(period_start_date, period_end_date, filters.period)
        })

        if filters.period == "Weekly":
            period_start_date = add_days(period_end_date, 1)
        elif filters.period == "Monthly":
            period_start_date = add_months(period_start_date, 1)
        elif filters.period == "Quarterly":
            period_start_date = add_months(period_start_date, 3)
        else:  # Yearly
            period_start_date = add_months(period_start_date, 12)

    return ranges

def get_period_label(start_date, end_date, period):
    if period == "Weekly":
        return f"{format_date(start_date)} - {format_date(end_date)}"
    elif period == "Monthly":
        return format_date(start_date, "MMM YYYY")
    elif period == "Quarterly":
        return f"Q{(start_date.month-1)//3 + 1} {start_date.year}"
    else:  # Yearly
        return str(start_date.year)

def get_columns(filters):
    columns = [
        {
            "fieldname": "supplier_name",
            "label": _("Supplier Name"),
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 200
        }
    ]

    # Add columns for each period
    periods = get_period_date_ranges(filters)
    for period in periods:
        columns.append({
            "fieldname": f"period_{period['start_date'].strftime('%Y%m%d')}",
            "label": period["label"],
            "fieldtype": "Currency",
            "width": 130
        })

    # Add total column
    columns.append({
        "fieldname": "total",
        "label": _("Total"),
        "fieldtype": "Currency",
        "width": 130
    })

    return columns

def get_data(filters):
    # Get target supplier groups based on filters
    target_groups = []
    if filters.get("supplier_group"):
        # If supplier_group is selected, use only that group and its descendants
        target_groups = [filters.get("supplier_group")] + get_descendant_supplier_groups(filters.get("supplier_group"))
    else:
        # If no supplier_group selected, use all allowed groups and their descendants
        for group in ALLOWED_GROUPS:
            target_groups.extend([group] + get_descendant_supplier_groups(group))
        target_groups = list(set(target_groups))  # Remove duplicates

    # Get periods for column generation
    periods = get_period_date_ranges(filters)

    # Get suppliers from target groups
    suppliers = frappe.get_all(
        "Supplier",
        fields=["name", "supplier_name", "supplier_group"],
        filters={"supplier_group": ["in", target_groups]}
    )

    data = []
    for supplier in suppliers:
        row = {"supplier_name": supplier.supplier_name}
        total = 0

        for period in periods:
            # Get payment entries for this period
            period_total = frappe.db.sql("""
                SELECT 
                    COALESCE(SUM(
                        CASE 
                            WHEN pe.payment_type = 'Pay' THEN pe.paid_amount
                            ELSE 0
                        END
                    ), 0) as paid_amount
                FROM `tabPayment Entry` pe
                WHERE pe.party_type = 'Supplier'
                    AND pe.party = %s
                    AND pe.docstatus = 1
                    AND pe.posting_date BETWEEN %s AND %s
            """, (supplier.name, period["start_date"], period["end_date"]), as_dict=1)

            amount = period_total[0].paid_amount if period_total else 0
            fieldname = f"period_{period['start_date'].strftime('%Y%m%d')}"
            row[fieldname] = amount
            total += amount

        row["total"] = total
        data.append(row)

    return sorted(data, key=lambda x: x["total"], reverse=True)

def get_descendant_supplier_groups(group_name):
    """Get all descendant supplier groups for a given supplier group"""
    lft, rgt = frappe.db.get_value('Supplier Group', group_name, ['lft', 'rgt'])
    if not (lft and rgt):
        return []

    descendants = frappe.db.sql("""
        SELECT name
        FROM `tabSupplier Group`
        WHERE lft > %s AND rgt < %s
    """, (lft, rgt), as_dict=1)

    return [d.name for d in descendants]

def get_chart_data(columns, data):
    if not data:
        return None

    period_columns = columns[1:-1]  # Exclude supplier_name and total columns
    labels = [col['label'] for col in period_columns]
    
    # Calculate period totals
    period_totals = []
    for col in period_columns:
        total = sum(row.get(col['fieldname'], 0) for row in data)
        period_totals.append(total)

    chart = {
        "data": {
            "labels": labels,
            "datasets": [{
                "name": _("Payment Total"),
                "values": period_totals
            }]
        },
        "type": "bar",
        "fieldtype": "Currency",
        "colors": ["#5e64ff"],
        "barOptions": {
            "spaceRatio": 0.2
        }
    }

    return chart