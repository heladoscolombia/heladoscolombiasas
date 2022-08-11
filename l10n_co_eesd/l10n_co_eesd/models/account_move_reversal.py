# -*- coding:utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def reverse_moves(self):
        action = super(AccountMoveReversal, self).reverse_moves()
        if self.move_ids.is_support_document and self.move_ids.move_type == 'entry':
            if self.new_move_ids:
                reversed_entries = self.env['account.move'].search([('reversed_entry_id','in',self.move_ids.ids),('id','not in',self.new_move_ids.ids)])
            else:
                reversed_entries = self.env['account.move'].search([('reversed_entry_id','in',self.move_ids.ids)])
            if reversed_entries:
                raise ValidationError('El asiento ya se ha reversado anteriormente, ids: {} '.format(reversed_entries.ids))
        return action
