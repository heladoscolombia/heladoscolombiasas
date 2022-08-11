# -*- coding:utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import ValidationError
import logging
from datetime import date, timedelta
import datetime
import hashlib
import base64
from xml.sax import saxutils
import pytz
from jinja2 import Template

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def generate_support_document(self):
        res = super(AccountMove,self).generate_support_document()
        for invoice in self:
            if not invoice.file:
                output = ''
                if (invoice.move_type == 'entry' and invoice.is_support_document and not invoice.reversed_entry_id):
                    output = invoice.generate_support_document_xml_entry()
                    _logger.info('Documento soporte {} generado'.format(invoice.name))
                if (invoice.move_type == 'entry' and invoice.is_support_document and invoice.reversed_entry_id):
                    output = invoice.generate_support_document_xml_entry()
                    _logger.info('Nota de ajuste documento soporte {} generada'.format(invoice.name))
                if output != '':
                    invoice.sudo().write({'file': base64.b64encode(output.encode())})
        return res

    def generate_support_document_xml_entry(self):
        try:
            company_contact = (self.env['res.partner'].search([('id', '=', self.company_id.partner_id.id)]))
            invoice = self
            self.fecha_xml = datetime.datetime.combine(self.invoice_date, datetime.datetime.now().time())
            if not self.fecha_entrega:
                self.fecha_entrega = datetime.datetime.combine(self.invoice_date, datetime.datetime.now().time())
            if not self.invoice_date_due:
                self._onchange_invoice_date()
                if self.move_type != 'entry':
                    self._recompute_payment_terms_lines()
            create_date = self._str_to_datetime(self.fecha_xml)
            deliver_date = self._str_to_datetime(self.fecha_entrega)

            key_data = '{}{}{}'.format(
                invoice.company_id.sd_software_id, invoice.company_id.sd_software_pin, invoice.name
            )
            sha384 = hashlib.sha384()
            sha384.update(key_data.encode())
            software_security_code = sha384.hexdigest()

            reconciled_vals = self._get_reconciled_info_JSON_values()
            invoice_prepaids = []
            invoice_lines = []

            tax_exclusive_amount = 0
            self.total_withholding_amount = 0.0
            tax_total_values = {}
            ret_total_values = {}

            # Bloque de código para imitar la estructura requerida por el XML de la DIAN para los totales externos
            # a las líneas de la factura.
            lines_ids = self.line_ids.filtered(lambda l: l.product_id)
            for line_id in lines_ids:
                for tax in line_id.tax_ids:
                    # Impuestos
                    if '-' not in str(tax.amount):
                        # Inicializa contador a cero para cada ID de impuesto
                        if tax.codigo_fe_dian not in tax_total_values:
                            tax_total_values[tax.codigo_fe_dian] = dict()
                            tax_total_values[tax.codigo_fe_dian]['total'] = 0
                            tax_total_values[tax.codigo_fe_dian]['info'] = dict()

                        # Suma al total de cada código, y añade información por cada tarifa.
                        price_subtotal_calc = abs(line_id.balance)

                        if tax.amount not in tax_total_values[tax.codigo_fe_dian]['info']:
                            aux_total = tax_total_values[tax.codigo_fe_dian]['total']
                            aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                            aux_total = round(aux_total, 2)
                            tax_total_values[tax.codigo_fe_dian]['total'] = aux_total
                            tax_total_values[tax.codigo_fe_dian]['info'][tax.amount] = {
                                'taxable_amount': price_subtotal_calc,
                                'value': round(price_subtotal_calc * tax['amount'] / 100, 2),
                                'technical_name': tax.tipo_impuesto_id.name,
                            }

                        else:
                            aux_tax = tax_total_values[tax.codigo_fe_dian]['info'][tax.amount]['value']
                            aux_total = tax_total_values[tax.codigo_fe_dian]['total']
                            aux_taxable = tax_total_values[tax.codigo_fe_dian]['info'][tax.amount]['taxable_amount']
                            aux_tax = aux_tax + price_subtotal_calc * tax['amount'] / 100
                            aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                            aux_taxable = aux_taxable + price_subtotal_calc
                            aux_tax = round(aux_tax, 2)
                            aux_total = round(aux_total, 2)
                            aux_taxable = round(aux_taxable, 2)
                            tax_total_values[tax.codigo_fe_dian]['info'][tax.amount]['value'] = aux_tax
                            tax_total_values[tax.codigo_fe_dian]['total'] = aux_total
                            tax_total_values[tax.codigo_fe_dian]['info'][tax.amount]['taxable_amount'] = aux_taxable

                    # retenciones
                    else:
                        # Inicializa contador a cero para cada ID de impuesto
                        price_subtotal_calc = abs(line_id.balance)

                        if tax.codigo_fe_dian not in ret_total_values:
                            ret_total_values[tax.codigo_fe_dian] = dict()
                            ret_total_values[tax.codigo_fe_dian]['total'] = 0
                            ret_total_values[tax.codigo_fe_dian]['info'] = dict()

                        # Suma al total de cada código, y añade información por cada tarifa.
                        if abs(tax.amount) not in ret_total_values[tax.codigo_fe_dian]['info']:
                            aux_total = ret_total_values[tax.codigo_fe_dian]['total']
                            aux_total = aux_total + price_subtotal_calc * abs(tax['amount']) / 100
                            aux_total = round(aux_total, 2)
                            ret_total_values[tax.codigo_fe_dian]['total'] = abs(aux_total)

                            ret_total_values[tax.codigo_fe_dian]['info'][abs(tax.amount)] = {
                                'taxable_amount': abs(price_subtotal_calc),
                                'value': abs(round(price_subtotal_calc * tax['amount'] / 100, 2)),
                                'technical_name': tax.tipo_impuesto_id.name,
                            }

                        else:
                            aux_tax = ret_total_values[tax.codigo_fe_dian]['info'][abs(tax.amount)]['value']
                            aux_total = ret_total_values[tax.codigo_fe_dian]['total']
                            aux_taxable = ret_total_values[tax.codigo_fe_dian]['info'][abs(tax.amount)]['taxable_amount']
                            aux_tax = aux_tax + price_subtotal_calc * abs(tax['amount']) / 100
                            aux_total = aux_total + price_subtotal_calc * abs(tax['amount']) / 100
                            aux_taxable = aux_taxable + price_subtotal_calc
                            aux_tax = round(aux_tax, 2)
                            aux_total = round(aux_total, 2)
                            aux_taxable = round(aux_taxable, 2)
                            ret_total_values[tax.codigo_fe_dian]['info'][abs(tax.amount)]['value'] = abs(aux_tax)
                            ret_total_values[tax.codigo_fe_dian]['total'] = abs(aux_total)
                            ret_total_values[tax.codigo_fe_dian]['info'][abs(tax.amount)]['taxable_amount'] = abs(
                                aux_taxable)

            for ret in ret_total_values.items():
                self.total_withholding_amount += abs(ret[1]['total'])

            contador = 1
            total_impuestos = 0
            for index, invoice_line_id in enumerate(self.line_ids.filtered(lambda l: l.product_id)):
                if not invoice_line_id.product_id.enable_charges and invoice_line_id.balance != 0:
                    price_subtotal_calc = abs(invoice_line_id.balance)

                    taxes = invoice_line_id.tax_ids
                    tax_values = [price_subtotal_calc * tax['amount'] / 100 for tax in taxes]
                    tax_values = [round(value, 2) for value in tax_values]
                    tax_info = dict()

                    for tax in invoice_line_id.tax_ids:
                        if '-' not in str(tax.amount):
                            # Inicializa contador a cero para cada ID de impuesto
                            if tax.codigo_fe_dian not in tax_info:
                                tax_info[tax.codigo_fe_dian] = dict()
                                tax_info[tax.codigo_fe_dian]['total'] = 0
                                tax_info[tax.codigo_fe_dian]['info'] = dict()

                            # Suma al total de cada código, y añade información por cada tarifa para cada línea.
                            price_subtotal_calc = abs(invoice_line_id.balance)

                            total_impuestos += round(price_subtotal_calc * tax['amount'] / 100, 2)
                            if tax.amount not in tax_info[tax.codigo_fe_dian]['info']:
                                aux_total = tax_info[tax.codigo_fe_dian]['total']
                                aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                                aux_total = round(aux_total, 2)
                                tax_info[tax.codigo_fe_dian]['total'] = aux_total

                                tax_info[tax.codigo_fe_dian]['info'][tax.amount] = {
                                    'taxable_amount': price_subtotal_calc,
                                    'value': round(price_subtotal_calc * tax['amount'] / 100, 2),
                                    'technical_name': tax.tipo_impuesto_id.name,
                                }

                            else:
                                aux_tax = tax_info[tax.codigo_fe_dian]['info'][tax.amount]['value']
                                aux_total = tax_info[tax.codigo_fe_dian]['total']
                                aux_taxable = tax_info[tax.codigo_fe_dian]['info'][tax.amount]['taxable_amount']
                                aux_tax = aux_tax + price_subtotal_calc * tax['amount'] / 100
                                aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                                aux_taxable = aux_taxable + price_subtotal_calc
                                aux_tax = round(aux_tax, 2)
                                aux_total = round(aux_total, 2)
                                aux_taxable = round(aux_taxable, 2)
                                tax_info[tax.codigo_fe_dian]['info'][tax.amount]['value'] = aux_tax
                                tax_info[tax.codigo_fe_dian]['total'] = aux_total
                                tax_info[tax.codigo_fe_dian]['info'][tax.amount]['taxable_amount'] = aux_taxable


                    discount_line = 0
                    discount_percentage = 0
                    base_discount = 0

                    mapa_line = {
                        'id': index + contador,
                        'product_id': invoice_line_id.product_id.id,
                        'invoiced_quantity': invoice_line_id.quantity,
                        'credited_quantity': invoice_line_id.quantity,
                        'uom_product_id': invoice_line_id.product_uom_id.codigo_fe_dian if invoice_line_id.product_uom_id else False,
                        'line_extension_amount': abs(invoice_line_id.balance),
                        'item_description': saxutils.escape(invoice_line_id.name),
                        'price': abs(invoice_line_id.balance) / invoice_line_id.quantity,
                        'tax_info': tax_info,
                        'discount': discount_line,
                        'discount_percentage': discount_percentage,
                        'base_discount': base_discount,
                        'discount_text': self.calcular_texto_descuento(invoice_line_id.invoice_discount_text),
                        'discount_code': invoice_line_id.invoice_discount_text,
                        'multiplier_discount': discount_percentage,
                    }
                    invoice_lines.append(mapa_line)

                    taxs = 0
                    if invoice_line_id.tax_ids.ids:
                        for item in invoice_line_id.tax_ids:
                            if not item.amount < 0:
                                taxs += 1
                                # si existe tax para una linea, entonces el price_subtotal
                                # de la linea se incluye en tax_exclusive_amount
                                if taxs > 1:  # si hay mas de un impuesto no se incluye  a la suma del tax_exclusive_amount
                                    pass
                                else:
                                    price_subtotal_calc = abs(invoice_line_id.balance)
                                    tax_exclusive_amount += (price_subtotal_calc)
                else:
                    contador -= 1
            # fin for

            invoice.compute_discount()
            invoice.compute_charges_freight()
            if invoice.partner_id.sd_enable_son and invoice.partner_id.fe_primer_nombre:
                invoice_supplier_first_name = invoice.partner_id.fe_primer_nombre
            elif not invoice.partner_id.sd_enable_son and invoice.partner_id.parent_id.fe_primer_nombre:
                invoice_supplier_first_name = invoice.partner_id.parent_id.fe_primer_nombre
            else:
                invoice_supplier_first_name = ''
            if invoice.partner_id.sd_enable_son and invoice.partner_id.fe_primer_apellido:
                invoice_supplier_family_name = invoice.partner_id.fe_primer_apellido
            elif not invoice.partner_id.sd_enable_son and invoice.partner_id.parent_id.fe_primer_apellido:
                invoice_supplier_family_name = invoice.partner_id.parent_id.fe_primer_apellido
            else:
                invoice_supplier_family_name = ''
            if invoice.partner_id.sd_enable_son and invoice.partner_id.fe_segundo_apellido:
                invoice_supplier_family_last_name = invoice.partner_id.fe_segundo_apellido
            elif not invoice.partner_id.sd_enable_son and invoice.partner_id.parent_id.fe_segundo_apellido:
                invoice_supplier_family_last_name = invoice.partner_id.parent_id.fe_segundo_apellido
            else:
                invoice_supplier_family_last_name = ''
            if invoice.partner_id.sd_enable_son and invoice.partner_id.fe_segundo_nombre:
                invoice_supplier_middle_name = invoice.partner_id.fe_segundo_nombre
            elif not invoice.partner_id.sd_enable_son and invoice.partner_id.parent_id.fe_segundo_nombre:
                invoice_supplier_middle_name = invoice.partner_id.parent_id.fe_segundo_nombre
            else:
                invoice_supplier_middle_name = ''
            if invoice.partner_id.sd_enable_son and invoice.partner_id.fe_matricula_mercantil:
                invoice_supplier_commercial_registration = invoice.partner_id.fe_matricula_mercantil
            elif not invoice.partner_id.sd_enable_son and invoice.partner_id.parent_id.fe_matricula_mercantil:
                invoice_supplier_commercial_registration = invoice.partner_id.parent_id.fe_matricula_mercantil
            else:
                invoice_supplier_commercial_registration = 0
            if invoice.partner_id.sd_enable_son:
                customization_id = invoice.partner_id.country_id.code == 'CO'
            else:
                customization_id = invoice.partner_id.parent_id.country_id.code == 'CO'

            if invoice.partner_id.sd_enable_son:
                if type(invoice.partner_id.responsabilidad_fiscal_fe).__name__ != 'list':
                    invoice_supplier_tax_level_code = invoice.partner_id.responsabilidad_fiscal_fe.codigo_fe_dian
                else:
                    invoice_supplier_tax_level_code = ";".join(invoice.partner_id.responsabilidad_fiscal_fe.codigo_fe_dian)
            else:
                if type(invoice.partner_id.parent_id.responsabilidad_fiscal_fe).__name__ != 'list':
                    invoice_supplier_tax_level_code = invoice.partner_id.parent_id.responsabilidad_fiscal_fe.codigo_fe_dian
                else:
                    invoice_supplier_tax_level_code = ";".join(
                        invoice.partner_id.parent_id.responsabilidad_fiscal_fe.codigo_fe_dian)

            duration_measure_array = []
            if len(self.invoice_payment_term_id.line_ids) > 1:
                for invoice_pay_term in self.invoice_payment_term_id.line_ids:
                    duration_measure_array.append(invoice_pay_term.days)
                    duration_measure = max(duration_measure_array)
                    date_due = create_date.astimezone(pytz.timezone("America/Bogota")) + timedelta(days=duration_measure).strftime('%Y-%m-%d')
            else:
                duration_measure = False
                date_due = create_date.astimezone(pytz.timezone("America/Bogota")).strftime('%Y-%m-%d')

            qr_code, cuds = invoice.calcular_cuds(tax_total_values, invoice.amount_total - total_impuestos)

            invoice_fe_data = {
                'invoice_authorization': invoice.company_resolucion_id.number if not invoice.reversed_entry_id else '',
                'start_date': invoice.company_resolucion_id.fecha_inicial if not invoice.reversed_entry_id else '',
                'end_date': invoice.company_resolucion_id.fecha_final if not invoice.reversed_entry_id else '',
                'invoice_prefix': (
                    invoice.company_resolucion_id.sequence_id.prefix
                    if invoice.company_resolucion_id.sequence_id.prefix
                    else ''
                ),
                'invoice_prefix_nc': (
                    invoice.company_resolucion_id.sequence_id.prefix
                    if invoice.reversed_entry_id and invoice.company_resolucion_id.sequence_id.prefix
                    else ''
                ),
                'authorization_from': self.company_resolucion_id.rango_desde if not invoice.reversed_entry_id else '',
                'authorization_to': self.company_resolucion_id.rango_hasta if not invoice.reversed_entry_id else '',
                'provider_id': str(company_contact.fe_nit),
                'provider_id_digit': str(company_contact.fe_digito_verificacion),
                'software_id': self.company_id.sd_software_id,
                'software_security_code': software_security_code,
                'invoice_number': self.name,

                'invoice_discount': '{:.2f}'.format(self.invoice_discount)
                if self.invoice_discount
                else 0.00,
                'invoice_discount_percent': self.invoice_discount_percent
                if self.invoice_discount_percent
                else 0.00,
                'invoice_discount_text': self.calcular_texto_descuento(self.invoice_discount_text)
                if self.invoice_discount_text
                else '',
                'invoice_discount_code': self.invoice_discount_text
                if self.invoice_discount_text
                else 0.00,
                'invoice_charges_freight': self.invoice_charges_freight
                if self.invoice_charges_freight
                else 0.00,
                'invoice_charges_freight_percent': self.invoice_charges_freight_percent
                if self.invoice_charges_freight_percent
                else 0.00,
                'invoice_charges_freight_text': self.invoice_charges_freight_text if self.invoice_charges_freight_text else 'Fletes',
                'creditnote_cuds': cuds,
                'invoice_cuds': cuds,
                'creditnote_qrcode': qr_code,
                'invoice_qr': qr_code,
                'invoice_issue_date': create_date.astimezone(pytz.timezone("America/Bogota")).strftime('%Y-%m-%d'),
                'invoice_start_date': datetime.datetime.now().astimezone(pytz.timezone("America/Bogota")).strftime('%Y-%m-%d') if invoice.transmission_type == 'by_operation' else invoice.start_date_period,
                'invoice_issue_time': create_date.astimezone(pytz.timezone("America/Bogota")).strftime('%H:%M:%S-05:00'),
                'invoice_customization_id': 10 if customization_id else 11,
                'transmission_type_code': 1 if invoice.transmission_type == 'by_operation' else 2,
                'transmission_description': 'Por operación' if invoice.transmission_type == 'by_operation' else 'Acumulado semanal',
                'invoice_note': self.narration or '',
                'credit_note_reason': invoice.reversed_entry_id.narration or 'Reversión de asiento de gasto',
                'billing_issue_date': create_date.astimezone(pytz.timezone("America/Bogota")).strftime('%Y-%m-%d'),
                # supplier
                'invoice_supplier_additional_account_id': invoice.partner_id.fe_es_compania
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.fe_es_compania,
                'invoice_supplier_document_type': self._tipo_de_documento(invoice.partner_id.fe_tipo_documento)
                if invoice.partner_id.sd_enable_son
                else self._tipo_de_documento(invoice.partner_id.parent_id.fe_tipo_documento),
                'invoice_supplier_identification': str(invoice.partner_id.fe_nit)
                if invoice.partner_id.sd_enable_son
                else str(invoice.partner_id.parent_id.fe_nit),
                'invoice_supplier_identification_digit': invoice.partner_id.fe_digito_verificacion
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.fe_digito_verificacion,
                'invoice_supplier_party_name': saxutils.escape(invoice.partner_id.name)
                if invoice.partner_id.sd_enable_son
                else saxutils.escape(invoice.partner_id.parent_id.name),
                'invoice_supplier_department': self.calcular_departamento(invoice.partner_id.state_id)
                if invoice.partner_id.sd_enable_son
                else self.calcular_departamento(invoice.partner_id.parent_id.state_id),
                'invoice_supplier_department_code': self.calcular_codigo_departamento(invoice.partner_id.state_id)
                if invoice.partner_id.sd_enable_son
                else self.calcular_codigo_departamento(invoice.partner_id.parent_id.state_id),
                'invoice_supplier_city': self.calcular_ciudad(invoice.partner_id.cities).capitalize()
                if invoice.partner_id.sd_enable_son
                else self.calcular_ciudad(invoice.partner_id.parent_id.cities).capitalize(),
                'invoice_supplier_city_code': self.calcular_codigo_ciudad(invoice.partner_id.cities)
                if invoice.partner_id.sd_enable_son
                else self.calcular_codigo_ciudad(invoice.partner_id.parent_id.cities),
                'invoice_supplier_postal_code': str(self.calcular_codigo_postal(invoice.partner_id.postal_id))
                if invoice.partner_id.sd_enable_son
                else str(self.calcular_codigo_postal(invoice.partner_id.parent_id.postal_id)),
                'invoice_supplier_country': self.calcular_pais(invoice.partner_id.country_id)
                if invoice.partner_id.sd_enable_son
                else self.calcular_pais(invoice.partner_id.parent_id.country_id),
                'invoice_supplier_country_code': self.calcular_codigo_pais(invoice.partner_id.country_id)
                if invoice.partner_id.sd_enable_son
                else self.calcular_codigo_pais(invoice.partner_id.parent_id.country_id),
                'invoice_supplier_address_line': invoice.partner_id.street
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.street,
                'invoice_supplier_is_company': invoice.partner_id.fe_es_compania
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.fe_es_compania,
                'invoice_supplier_first_name': invoice_supplier_first_name,
                'invoice_supplier_family_name': invoice_supplier_family_name,
                'invoice_supplier_family_last_name': invoice_supplier_family_last_name,
                'invoice_supplier_middle_name': invoice_supplier_middle_name,
                'invoice_supplier_phone': invoice.partner_id.phone
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.phone,
                'invoice_supplier_commercial_registration': invoice_supplier_commercial_registration,
                'invoice_supplier_email': invoice.partner_id.fe_correo_electronico
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.fe_correo_electronico,
                'invoice_supplier_tax_level_code': invoice_supplier_tax_level_code,
                'invoice_supplier_responsabilidad_tributaria': invoice.partner_id.fe_responsabilidad_tributaria
                if invoice.partner_id.sd_enable_son
                else invoice.partner_id.parent_id.fe_responsabilidad_tributaria,
                'invoice_supplier_responsabilidad_tributaria_text': self.calcular_texto_responsabilidad_tributaria(
                    invoice.partner_id.fe_responsabilidad_tributaria)
                if invoice.partner_id.sd_enable_son
                else self.calcular_texto_responsabilidad_tributaria(
                    invoice.partner_id.parent_id.fe_responsabilidad_tributaria),
                # customer
                'invoice_customer_additional_account_id': self.company_id.partner_id.fe_es_compania,
                'invoice_customer_document_type': self._tipo_de_documento(company_contact.fe_tipo_documento),
                'invoice_customer_identification': str(company_contact.fe_nit),
                'invoice_customer_identification_digit': company_contact.fe_digito_verificacion,
                'invoice_customer_party_name': saxutils.escape(invoice.company_id.name),
                'invoice_customer_postal_code': str(self.calcular_codigo_postal(company_contact.postal_id))
                if not self.fe_sucursal
                else str(self.calcular_codigo_postal(invoice.fe_sucursal.postal_id)),
                'invoice_customer_country_code': self.calcular_codigo_pais(company_contact.country_id)
                if not self.fe_sucursal
                else self.calcular_codigo_pais(invoice.fe_sucursal.country_id),
                'invoice_customer_department': self.calcular_departamento(company_contact.state_id)
                if not self.fe_sucursal
                else self.calcular_departamento(invoice.fe_sucursal.state_id),
                'invoice_customer_department_code': self.calcular_codigo_departamento(company_contact.state_id)
                if not self.fe_sucursal
                else self.calcular_codigo_departamento(invoice.fe_sucursal.state_id),
                'invoice_customer_city': self.calcular_ciudad(company_contact.cities).capitalize()
                if not self.fe_sucursal
                else self.calcular_ciudad(invoice.fe_sucursal.cities).capitalize(),
                'invoice_customer_city_code': self.calcular_codigo_ciudad(company_contact.cities)
                if not self.fe_sucursal
                else self.calcular_codigo_ciudad(invoice.fe_sucursal.cities),
                'invoice_customer_address_line': company_contact.street
                if not self.fe_sucursal
                else invoice.fe_sucursal.street,
                'invoice_customer_tax_level_code':
                    company_contact.responsabilidad_fiscal_fe.codigo_fe_dian
                    if type(company_contact.responsabilidad_fiscal_fe).__name__ != 'list'
                    else ";".join(company_contact.responsabilidad_fiscal_fe.codigo_fe_dian),
                'invoice_customer_tax_regime': int(company_contact.fe_regimen_fiscal),
                'invoice_customer_responsabilidad_tributaria': company_contact.fe_responsabilidad_tributaria,
                'invoice_customer_responsabilidad_tributaria_text': self.calcular_texto_responsabilidad_tributaria(
                    company_contact.fe_responsabilidad_tributaria),
                'invoice_customer_commercial_registration':
                    company_contact.fe_matricula_mercantil
                    if company_contact.fe_matricula_mercantil
                    else 0,
                'invoice_customer_phone': company_contact.phone
                if not self.fe_sucursal
                else invoice.fe_sucursal.phone,
                'invoice_customer_email': company_contact.fe_correo_electronico
                if not self.fe_sucursal
                else invoice.fe_sucursal.fe_correo_electronico,
                'invoice_customer_party_name': company_contact.fe_razon_social if company_contact.fe_es_compania == '1' else company_contact.fe_primer_nombre + " " + company_contact.fe_primer_apellido,

                'line_extension_amount': '{:.2f}'.format(invoice.amount_total -total_impuestos),
                'tax_inclusive_amount': '{:.2f}'.format(invoice.amount_total),
                'tax_exclusive_amount': '{:.2f}'.format(tax_exclusive_amount),
                'payable_amount': '{:.2f}'.format(invoice.amount_total + invoice.total_withholding_amount) if self.move_type != 'entry' else '{:.2f}'.format(self.amount_total),
                'payable_amount_discount': '{:.2f}'.format(
                    invoice.amount_total + invoice.invoice_discount - invoice.invoice_charges_freight + invoice.total_withholding_amount),
                # invoice lines
                'invoice_lines': invoice_lines,
                'creditnote_lines': invoice_lines,
                'tax_total': tax_values,
                'tax_total_values': tax_total_values,
                'ret_total_values': ret_total_values,
                'date_due': invoice.invoice_date_due if invoice.invoice_date_due else date_due,
                # Info validación previa
                'payment_means_id': self.forma_de_pago,
                'payment_means_code': self.payment_mean_id.codigo_fe_dian,
                'payment_id': self.payment_mean_id.nombre_tecnico_dian,
                'duration_measure': duration_measure if duration_measure else self.invoice_payment_term_id.line_ids.days,
                'profile_execution_id': self.company_id.sd_environment_type if self.company_id.sd_environment_type != '3' else '2',
                'order_reference': self.order_reference,
                'order_reference_date': self.order_reference_date,
                'additional_document_reference': self.additional_document_reference,
                'despatch_document_reference': self.despatch_document_reference,
                'despatch_document_reference_date': self.despatch_document_reference_date,
                'receipt_document_reference': self.receipt_document_reference,
                'receipt_document_reference_date': self.receipt_document_reference_date,
                'invoice_trade_sample': self.invoice_trade_sample,
            }

            if invoice.partner_id.sd_enable_son and not invoice.partner_id.postal_id:
                raise ValidationError("El proveedor no tiene parametrizado Código Postal")
            if not invoice.partner_id.sd_enable_son and not invoice.partner_id.parent_id.postal_id:
                raise ValidationError("El padre del proveedor no tiene parametrizado Código Postal")
            if not self.company_id.partner_id.postal_id:
                raise ValidationError("La Compañia no tiene parametrizado Código Postal")
            if invoice.fe_sucursal and not invoice.fe_sucursal.postal_id:
                raise ValidationError("La sucursal no tiene parametrizado Código Postal")

            if invoice.partner_id.sd_enable_son:
                if invoice.partner_id.fe_es_compania == '1':
                    invoice_fe_data['invoice_supplier_party_name'] = saxutils.escape(invoice.partner_id.fe_razon_social)
                elif invoice.partner_id.fe_es_compania == '2':
                    invoice_fe_data['invoice_supplier_party_name'] = saxutils.escape(invoice.partner_id.fe_primer_nombre + (
                        " " + invoice.partner_id.fe_segundo_nombre if invoice.partner_id.fe_segundo_nombre else "") + invoice.partner_id.fe_primer_apellido + (
                                                                                         " " + invoice.partner_id.fe_segundo_apellido if invoice.partner_id.fe_segundo_apellido else ""))
            else:
                if invoice.partner_id.fe_es_compania == '1':
                    invoice_fe_data['invoice_supplier_party_name'] = saxutils.escape(invoice.partner_id.fe_razon_social)
                elif invoice.partner_id.fe_es_compania == '2':
                    invoice_fe_data['invoice_supplier_party_name'] = saxutils.escape(invoice.partner_id.fe_primer_nombre + (
                        " " + invoice.partner_id.fe_segundo_nombre if invoice.partner_id.fe_segundo_nombre else "") + invoice.partner_id.fe_primer_apellido + (
                                                                                         " " + invoice.partner_id.fe_segundo_apellido if invoice.partner_id.fe_segundo_apellido else ""))

            invoice_fe_data['currency_id'] = self.currency_id.name

            if self.reversed_entry_id:
                invoice_fe_data['discrepancy_response_code'] = self.concepto_correccion_credito
                if self.reversed_entry_id.prefix_invoice_number():
                    invoice_fe_data['billing_reference_id'] = self.reversed_entry_id.prefix_invoice_number()
                    invoice_fe_data['billing_reference_cufe'] = self.reversed_entry_id.cuds
                    invoice_fe_data['billing_reference_issue_date'] = (self.reversed_entry_id.date).strftime('%Y-%m-%d') if self.reversed_entry_id else ''
                if self.currency_id.name != 'COP':
                    invoice_fe_data['calculation_rate'] = self.env.context[
                        'value_rate_exchange'] if 'value_check_rate' in self.env.context and self.env.context[
                        'value_check_rate'] else round(1 / self.currency_id.rate, 2)
                    invoice_fe_data['rate_date'] = self.date
                xml_template = self.get_template_str_sd('../templates/AdjustmentSupportDocument.xml')
                invoice_template = Template(xml_template)
                output = invoice_template.render(invoice_fe_data)
            else:
                if self.es_factura_exportacion:
                    invoice_fe_data['calculation_rate'] = self.env.context[
                        'value_rate_exchange'] if 'value_check_rate' in self.env.context and self.env.context[
                        'value_check_rate'] else round(1 / self.currency_id.rate, 2)
                    invoice_fe_data['rate_date'] = self.date
                    invoice_fe_data['invoice_supplier_country'] = self.partner_id.country_id.iso_name
                    invoice_fe_data['invoice_incoterm_code'] = self.invoice_incoterm_id.code
                    invoice_fe_data['invoice_incoterm_description'] = self.invoice_incoterm_id.name
                    xml_template = self.get_template_str_sd('../templates/ExportSupportDocument.xml')
                    export_template = Template(xml_template)
                    output = export_template.render(invoice_fe_data)
                else:
                    if self.currency_id.name != 'COP':
                        invoice_fe_data['calculation_rate'] = self.env.context[
                            'value_rate_exchange'] if 'value_check_rate' in self.env.context and self.env.context[
                            'value_check_rate'] else round(1 / self.currency_id.rate, 2)
                        invoice_fe_data['rate_date'] = self.date
                    xml_template = self.get_template_str_sd('../templates/SupportDocument.xml')
                    invoice_template = Template(xml_template)
                    output = invoice_template.render(invoice_fe_data)

            return output
        except Exception as e:
            raise ValidationError(
                "Error validando el asiento de gasto para generar documento soporte : {}".format(e)
            )

    def _reverse_moves(self, default_values_list=None, cancel=False):
        reverse_moves = super(AccountMove, self)._reverse_moves(default_values_list, cancel)
        if self.is_support_document:
            for refund in reverse_moves:
                refund.is_support_document = True
                refund.concepto_correccion_credito = '2'
                payment_term = self.env['account.payment.term'].search([('active', '=', True)], limit=1)
                refund.invoice_payment_term_id = payment_term
        return reverse_moves