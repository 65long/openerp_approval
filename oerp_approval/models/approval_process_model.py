# encoding: utf-8

import logging
from odoo import models, fields, api
from odoo.exceptions import UserError, Warning

_logger = logging.getLogger(__name__)


class ApprovalProcessConfig(models.Model):
    _name = 'custom.approval.process.config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = '自定义审批流配置'

    name = fields.Char(string='审批名称', required=True, track_visibility='onchange')
    oa_model_id = fields.Many2one('ir.model', string='业务模型', index=True, ondelete='set null')
    shop_code = fields.Char(string='店铺编码', required=True, readonly=True, default='New')
    company_id = fields.Many2one('res.company', string='适用公司', required=True,
                                 default=lambda self: self.env.user.company_id, track_visibility='onchange')
    active = fields.Boolean(string='有效', default=True)
    approval_type = fields.Selection(string="审批类型", selection=[('ordinal', '依次审批'), ('complicated', '会签/或签')])
    approval_user_ids = fields.Many2many('res.users', 'custom_approval_users_approval_rel', string='审批列表')

    _sql_constraints = [
        ('shop_code_uniq', 'unique (name, active)', '店铺名称必须唯一！！！'),
        ('cerp_code_uniq', 'unique (cerp_code, active)', '管易编码必须唯一！！！'),
        ('finance_code_uniq', 'unique (finance_code, active)', '财务系统编码必须唯一！！！'),
    ]

    @api.model
    def create(self, val_dict):
        partner_dict = dict(name=val_dict['name'],
                            company_id=val_dict['company_id'],
                            dept_id=val_dict['department_id'],
                            sale_finance_code=val_dict['finance_code'],
                            lang='zh_CN',
                            customer=True)
        res = self.env['res.partner'].create(partner_dict)

        val_dict.update(dict(partner_id=res.id))
        res_id = super(Shop, self).create(val_dict)
        if val_dict.get('shop_code', 'New') == 'New':
            code = self.env['ir.sequence'].next_by_code('haierbaby.shop')
            res_id.shop_code = code.format(res_id.shop_type.code)
        return res_id

    @api.multi
    def write(self, vals):
        self.ensure_one()
        partner_dict = {}
        fields_dict = {
            'name': 'name',
            'company_id': 'company_id',
            'department_id': 'dept_id',
            'finance_code': 'sale_finance_code'
        }
        for k, v in vals.items():
            if k in fields_dict:
                partner_dict[fields_dict.get(k)] = v
        if partner_dict:
            self.partner_id.write(partner_dict)
        return super(Shop, self).write(vals)
    
    @api.multi
    def unlink(self):
        for record in self:
            partner_id = record.partner_id
            record.partner_id = False
            # partner_id.unlink()
            partner_id.active = False
        # return super(Shop, self).unlink()
        return True

    @api.onchange('company_id')
    def _check_company(self):
        '改变公司时候，清空部门'
        if self.company_id:
            temp_rs = self.env['haierbaby.department.company.account'].search([('company_id', '=', self.company_id.id)])
            dept_ids = [temp.dept_id.id for temp in temp_rs]
            # 防止选择的部门不在公司下（适用于反复修改）
            if self.department_id and self.department_id.id not in dept_ids:
                self.department_id = False
            return {'domain': {'department_id': [('id', 'in', dept_ids)]}}

        self.department_id = False
        return {'domain': {'department_id': [('id', 'in', [])]}}

        # temp_rs = self.env['haierbaby.department.company.account'].search([('company_id', '=', self.company_id.id)])
        # dept_ids = [temp.dept_id.id for temp in temp_rs]
        # return {
        #     'domain': {'department_id': [('id', 'in', dept_ids)]}
        # }


class ShopType(models.Model):
    '店铺类型model'
    _name = 'haierbaby.shop.type'
    _inherit = ['mail.thread']
    _description = '海尔童婴 | 店铺类型'

    name = fields.Char(string='店铺类型名称', required=True, track_visibility='onchange')
    code = fields.Char(string='店铺类型编码', required=True)
    active = fields.Boolean(string='有效', default=True)
    shop_ids = fields.One2many('haierbaby.shop', 'shop_type')

    _sql_constraints = [
        ('shop_type_code_uniq', 'unique (code)', '类型编码必须唯一！！！'),
        ('shop_type_code_uniq', 'unique (name)', '类型名称必须唯一！！！'),
    ]
