# -*- coding: utf-8 -*-
{
    'name': "Documento Soporte electrónico Gastos Colombia",
    'summary': 'Law compliant electronic invoicing for Colombia.',
    'sequence': 10,
    'description': """ 
        Add-on for electronic invoicing generation that meets the 
        requirements of the resolution issued by DIAN.
    """,

    'author': "Pragmatic S.A.S.",
    'category': 'Invoicing & Payments',
    'website': "https://www.pragmatic.com.co",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'version': '14.1.0.0.0',
    'license': 'OPL-1',
    'support': 'soporte.fe@pragmatic.com.co',
    'price': '99',
    'currency': 'EUR',
    'images': ['static/description/splasher.jpg'],

    # any module necessary for this one to work correctly
    'depends': ['base', 'account', 'l10n_co', 'contacts', 'mail','base_setup','l10n_co_cei','l10n_co_esd','hr_expense'],

    # always loaded
    'data': [
        'views/hr_expense.xml',
        'views/hr_expense_sheet.xml',
    ],

    'application': True,
}

