frappe.ui.form.on('MK Item List', {
    onload: function(frm) {
        // set default filter values
        frappe.query_report.set_filter_value('disabled', 0);
    },
    refresh: function(frm) {
        // refresh the report after changing filters
        frappe.query_report.refresh();
    },
    item_group: function(frm) {
        // update the sub_group filter based on the selected item_group
        let item_group = frappe.query_report.get_filter_value('item_group');
        if (item_group) {
            frappe.db.get_list('Item Group', {
                fields: ['name'],
                filters: {
                    parent_item_group: item_group
                }
            }).then(data => {
                let sub_groups = data.map(d => d.name);
                frappe.query_report.set_filter_options('sub_group', sub_groups);
                frappe.query_report.set_filter_value('sub_group', null);
            });
        } else {
            frappe.query_report.set_filter_options('sub_group', []);
            frappe.query_report.set_filter_value('sub_group', null);
        }
    }
});

frappe.query_reports['Item Group and Item Name Report'] = {
    filters: [
        {
            fieldname: 'disabled',
            label: __('Disabled'),
            fieldtype: 'Check'
        },
        {
            fieldname: 'item_group',
            label: __('Item Group'),
            fieldtype: 'Link',
            options: 'Item Group'
        },
        {
            fieldname: 'sub_group',
            label: __('Sub Group'),
            fieldtype: 'Link',
            options: 'Item Group',
            get_query: function() {
                let item_group = frappe.query_report.get_filter_value('item_group');
                return {
                    filters: {
                        parent_item_group: item_group
                    }
                };
            }
        }
    ]
};
