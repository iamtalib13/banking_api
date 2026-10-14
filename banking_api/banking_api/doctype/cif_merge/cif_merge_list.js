frappe.listview_settings['CIF Merge'] = {
	onload: function(listview) {
		// Single Count Filter Button
		listview.page.add_inner_button(__('Count Filter'), function() {
			frappe.call({
				method: 'banking_api.banking_api.doctype.cif_merge.cif_merge.get_top_cif_counts',
				freeze: true,
				freeze_message: __('Top CIF counts load ho rahe hain...'),
				callback: function(r) {
					const data = r.message || [];
					if (!data.length) {
						frappe.msgprint(__('Koi CIF records nahi mile.'));
						return;
					}
					show_top_cif_dialog(listview, data);
				}
			});
		});

		// Status Capsules (Active / Inactive / All)
		frappe.call({
			method: 'banking_api.banking_api.doctype.cif_merge.cif_merge.get_status_summary',
			callback: function(r) {
				const summary = r.message || { Active: 0, Inactive: 0, Total: 0 };
				const fmt = (num) => Number(num || 0).toLocaleString('en-IN');

				const $container = $(`
					<div class="cif-status-capsules d-flex align-items-center ml-2" style="gap: 6px; display: inline-flex;">
						<button class="btn btn-xs btn-default text-success font-weight-bold" style="border-radius: 12px; border: 1px solid #86efac; background: #f0fdf4;" title="Filter Active CIFs">
							● Active <span class="badge badge-success ml-1">${fmt(summary.Active)}</span>
						</button>
						<button class="btn btn-xs btn-default text-danger font-weight-bold" style="border-radius: 12px; border: 1px solid #fca5a5; background: #fef2f2;" title="Filter Inactive CIFs">
							● Inactive <span class="badge badge-danger ml-1">${fmt(summary.Inactive)}</span>
						</button>
						<button class="btn btn-xs btn-default text-muted" style="border-radius: 12px; border: 1px solid #e2e8f0; background: #f8fafc;" title="Clear Status Filter">
							All <span class="badge badge-light border ml-1">${fmt(summary.Total)}</span>
						</button>
					</div>
				`);

				// Filter actions
				$container.find('.text-success').on('click', function() {
					listview.filter_area.clear();
					listview.filter_area.add([['CIF Merge', 'status', '=', 'Active']]);
				});

				$container.find('.text-danger').on('click', function() {
					listview.filter_area.clear();
					listview.filter_area.add([['CIF Merge', 'status', '=', 'Inactive']]);
				});

				$container.find('.text-muted').on('click', function() {
					listview.filter_area.clear();
				});

				listview.page.inner_toolbar ? listview.page.inner_toolbar.append($container) : listview.page.add_inner_button($container);
			}
		});
	}
};

function show_top_cif_dialog(listview, data) {
	let rowsHtml = data.map((item, index) => `
		<tr style="cursor: pointer;" class="top-cif-row" data-count="${item.total_cif_count}">
			<td class="text-center font-weight-bold">${index + 1}</td>
			<td><span class="badge badge-primary font-weight-bold" style="font-size: 13px;">${item.total_cif_count} CIFs</span></td>
			<td><b>${item.doc_count}</b> Aadhaars</td>
			<td class="text-right"><button class="btn btn-xs btn-primary apply-filter-btn" data-count="${item.total_cif_count}">Filter</button></td>
		</tr>
	`).join('');

	const d = new frappe.ui.Dialog({
		title: __('Top 10 CIF Count Filter'),
		fields: [
			{
				fieldname: 'html_table',
				fieldtype: 'HTML',
				options: `
					<div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
						<table class="table table-bordered table-hover mb-0">
							<thead class="thead-light">
								<tr>
									<th style="width: 50px;" class="text-center">#</th>
									<th>CIFs per Aadhaar</th>
									<th>Total Aadhaar Count</th>
									<th style="width: 80px;" class="text-right">Action</th>
								</tr>
							</thead>
							<tbody>
								${rowsHtml}
							</tbody>
						</table>
					</div>
				`
			}
		]
	});

	d.show();

	d.$wrapper.find('.apply-filter-btn, .top-cif-row').on('click', function(e) {
		const count = $(this).data('count');
		if (count !== undefined) {
			listview.filter_area.clear();
			listview.filter_area.add([['CIF Merge', 'total_cif_count', '=', parseInt(count)]]);
			d.hide();
		}
	});
}
