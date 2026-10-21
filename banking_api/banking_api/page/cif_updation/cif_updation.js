frappe.pages['cif-updation'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('CIF Assignment'),
		single_column: true
	});

	const form_html = `
		<div class="cif-assignment-wrapper" style="max-width: 520px; margin: 40px auto;">
			<div class="card p-4 shadow-sm" style="border-radius: 8px;">
				<h4 class="mb-4 text-center font-weight-bold">${__('CIF Assignment')}</h4>
				<div class="form-group mb-3">
					<label class="form-label font-weight-medium">${__('Auth ID')}</label>
					<input type="text" class="form-control" id="cif-auth-id" placeholder="${__('Enter Auth ID (e.g., SAH01549)')}" autocomplete="off">
				</div>
				<div class="form-group mb-4">
					<label class="form-label font-weight-medium">${__('CIF ID')}</label>
					<input type="text" class="form-control" id="cif-id" placeholder="${__('Enter CIF ID (e.g., 400357659)')}" autocomplete="off">
				</div>
				<button class="btn btn-primary w-100" id="btn-submit-cif">
					${__('Update Assignment')}
				</button>
			</div>
		</div>
	`;

	$(page.body).html(form_html);

	const $auth_input = $(page.body).find('#cif-auth-id');
	const $cif_input = $(page.body).find('#cif-id');
	const $submit_btn = $(page.body).find('#btn-submit-cif');

	function handleSubmit() {
		const auth_id = $auth_input.val().trim();
		const cif_id = $cif_input.val().trim();

		if (!auth_id || !cif_id) {
			frappe.msgprint({
				title: __('Validation Error'),
				message: __('Please enter both Auth ID and CIF ID.'),
				indicator: 'orange'
			});
			return;
		}

		frappe.call({
			method: 'banking_api.banking_api.page.cif_updation.cif_updation.update_cif_assignment',
			args: {
				auth_id: auth_id,
				cif_id: cif_id
			},
			freeze: true,
			freeze_message: __('Updating CIF Assignment...'),
			callback: function(response) {
				const res = response.message;
				if (!res) return;

				if (res.status === 'success') {
					frappe.msgprint({
						title: __('Assignment Updated'),
						message: `
							<div class="text-left" style="line-height: 1.8;">
								<p class="text-success font-weight-bold mb-2">${res.message}</p>
								<div><b>${__('CIF ID')}:</b> ${frappe.utils.escape_html(res.cif_id)}</div>
								<div><b>${__('Person ID')}:</b> ${frappe.utils.escape_html(res.person_id)}</div>
								<div><b>${__('Rows Affected')}:</b> ${res.rows_updated}</div>
							</div>
						`,
						indicator: 'green'
					});
					$cif_input.val('').focus();
				} else if (res.status === 'error') {
					frappe.msgprint({
						title: __('Error'),
						message: res.message,
						indicator: 'red'
					});
				}
			}
		});
	}

	$submit_btn.on('click', handleSubmit);

	$auth_input.add($cif_input).on('keypress', function(e) {
		if (e.which === 13) {
			handleSubmit();
		}
	});
};
