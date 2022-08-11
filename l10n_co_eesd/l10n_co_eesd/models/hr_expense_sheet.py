# -*- coding:utf-8 -*-

from odoo import models, api, fields
import datetime
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    partner_id = fields.Many2one('res.partner', string='Tercero')
    start_date_expenses = fields.Date(string='Fecha mínima de gastos')

    def _select_journal_id(self):
        for record in self:
            journal_id = record.journal_id
            if record.company_id.enable_support_document:
                if record.partner_id.sd_enable and record.journal_id.categoria!='support_document':
                    journal_id = self.env['account.journal'].sudo().search([('categoria','=','support_document'),('type','=','purchase'), ('company_id','=',record.company_id.id)],limit=1)
                elif not record.partner_id.sd_enable and record.journal_id.categoria=='support_document':
                    journal_id = self.env['account.journal'].sudo().search([('categoria', 'not in', ('support_document','adjustment_support_document')), ('type', '=', 'purchase'), ('company_id','=',record.company_id.id)], limit=1)
            else:
                journal_id = self.env['account.journal'].sudo().search([('categoria', 'not in', ('support_document','adjustment_support_document')), ('type', '=', 'purchase'), ('company_id','=',record.company_id.id)], limit=1)
            return journal_id

    def validate_dates_expenses(self):
        for sheet in self:
            date_min = datetime.date.today()
            date_today = date_min
            if sheet.partner_id.sd_enable and sheet.company_id.enable_support_document:
                for expense in sheet.expense_line_ids:
                    if expense.date < date_min:
                        date_min = expense.date
                sheet.start_date_expenses = date_min
                if (date_today - date_min).days > 7:
                    _logger.info('\nNo se puede crear una hoja de gastos para documento soporte en el que la diferencia entre las fechas supere los 7 días')
                    raise ValidationError('\nNo se puede crear una hoja de gastos para documento soporte en el que la diferencia entre las fechas supere los 7 días')
