# Copyright 2026 Agrista
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Force res_brand_list_view standalone before the 18.0 module XML reloads.

In 17.0 this view inherited ``base.view_partner_tree`` (mode='primary'). In
18.0 that parent gained ``invoice_sending_method`` from the account module —
a field that does not exist on ``res.brand`` — which trips the upgrade
crawler's mock_view_list on the Brands menu with::

    ValueError: Invalid field 'invoice_sending_method' on model 'res.brand'

The 18.0 module XML already declares the view standalone (``inherit_id`` set
to False with an explicit ``<list>`` arch), but the in-place upgrade
pipeline does not always reset the existing DB record's ``inherit_id``
before the crawler runs. So we force the desired state in pre-migrate.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view
        SET inherit_id = NULL,
            mode = 'primary',
            arch_db = jsonb_build_object(
                'en_US', '<list string="Brands"><field name="name"/></list>'
            )
        WHERE id = (
            SELECT res_id FROM ir_model_data
            WHERE module = 'brand'
              AND name = 'res_brand_list_view'
              AND model = 'ir.ui.view'
        )
        """
    )
