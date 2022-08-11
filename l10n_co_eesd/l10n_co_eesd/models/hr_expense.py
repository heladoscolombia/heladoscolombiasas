# -*- coding:utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import ValidationError
from datetime import date
import datetime


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    partner_id = fields.Many2one('res.partner', string='Tercero',required=True)

    def _create_sheet_from_expenses(self):
        if len(self.partner_id) != 1:
            raise ValidationError ('No es posible crear la hoja gastos de diferentes terceros')
        sheet = super(HrExpense, self)._create_sheet_from_expenses()
        sheet.partner_id = self.partner_id
        sheet.journal_id = sheet._select_journal_id()
        sheet.validate_dates_expenses()
        return sheet

    def _prepare_move_values(self):
        move_values = super(HrExpense,self)._prepare_move_values()
        move_values.update({'invoice_date': date.today(),'invoice_date_due': date.today()})
        if self.partner_id:
            move_values.update({'partner_id': self.partner_id})
            if self.partner_id.sd_enable:
                payment_term = self.env['account.payment.term'].search([('active','=',True)], limit=1)
                move_values.update({'is_support_document': True, 'invoice_payment_term_id': payment_term,'invoice_date': datetime.datetime.now()})
        if len(self.sheet_id.expense_line_ids)>1:
            move_values.update({'transmission_type': 'accumulated', 'start_date_period': self.sheet_id.start_date_expenses, 'final_date_period': date.today()})
        return move_values


