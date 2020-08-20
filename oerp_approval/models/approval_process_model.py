# encoding: utf-8

import logging
from lxml import etree
from odoo import models, fields, api
from odoo.exceptions import UserError, Warning

_logger = logging.getLogger(__name__)


class ApprovalProcessConfig(models.Model):
    _name = 'custom.approve.process.config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = '自定义审批流配置'

    name = fields.Char(string='审批名称', required=True, track_visibility='onchange')
    oa_model_id = fields.Many2one('ir.model', string='业务模型', index=True, ondelete='set null', required=True)
    oa_model_name = fields.Char(string='模型名称', related='oa_model_id.model', store=True, index=True)
    company_id = fields.Many2one('res.company', string='适用公司', required=True,
                                 default=lambda self: self.env.user.company_id, track_visibility='onchange')
    active = fields.Boolean(string='有效', default=True)
    approve_type = fields.Selection(string="审批类型", selection=[('ordinal', '依次审批'), ('complicated', '会签/或签')])
    approve_line_ids = fields.One2many('custom.approve.node.line', 'custom_approve_id', string='审批列表')
    cc_user_ids = fields.Many2many('res.users', 'custom_approve_recv_users_rel', string='抄送人')
    cc_type = fields.Selection(string="抄送时间", selection=[('START', '审批开始'), ('FINISH', '审批结束'), ('START_FINISH', '开始和结束')], default='FINISH')

    # _sql_constraints = [
    # ]

    @api.onchange('oa_model_id')
    def onchange_model_id(self):
        """
        根据选择的模型读取模型动作按钮
        :return:
        """
        for rec in self:
            if rec.oa_model_id:
                model_id = rec.oa_model_id
                rec.oa_model_name = model_id.model  # 保存模型_name属性
                result = self.env[model_id.model].fields_view_get()
                root = etree.fromstring(result['arch'])
                for item in root.xpath("//header/button"):
                    domain = [('model_id', '=', model_id.id), ('function', '=', item.get('name'))]
                    model_buts = self.env['custom.approve.model.button'].sudo().search(domain)
                    if not model_buts:
                        self.env['custom.approve.model.button'].create({
                            'model_id': model_id.id,
                            'name': item.get('string'),
                            'function': item.get('name'),
                            'modifiers': item.get('modifiers'),
                        })


    @api.multi
    def button_activate_config_on_click(self):
        # 多级审批给业务模型添加多个字段,一个字段记录审批审批模板实例
        # 通过指定的按钮修改按钮invisible属性
        # 验证审批
        self.ensure_one()
        target_model = self.env[self.oa_model_id.model]
        module_name = self.oa_model_id.modules
        module_names = module_name.replace(' ', '').split(',')
        current_module = self.env['ir.module.module'].search([('name', 'in', module_names)])
        current_module.button_immediate_upgrade()
        for record in self.approve_line_ids:
            record = record.agree_button_id

class CustomApproveResUsersRel(models.Model):
    _name = 'custom.approve.node.line'
    _inherit = ['mail.thread']
    _description = '自定义审批节点'

    custom_approve_id = fields.Many2one('custom.approve.process.config', string='自定义审批id', ondelete='set null')
    group_id = fields.Many2one('res.groups', string="适用权限组")
    user_ids = fields.Many2many('res.users', 'custom_approval_user_list_rel', string="审批人")
    approval_type = fields.Selection(string="审批类型", selection=[('AND', '会签'), ('OR', '或签'), ('ONE', '单人')],
                                     required=True, default='ONE')
    agree_button_id = fields.Many2one('custom.approve.model.button', string="通过后执行")
    refuse_button_id = fields.Many2one('custom.approve.model.button', string="拒绝后执行")

    # _sql_constraints = [
    # ]

    @api.constrains('approval_type', 'user_ids')
    def _constrains_approval_type(self):
        """
        检查是否配置正确
        会签/或签列表长度必须大于1，非会签/或签列表长度只能为1
        :return:
        """
        for res in self:
            if res.approval_type == 'ONE' and len(res.user_ids) > 1:
                raise UserError("单人时，审批人只能选择一个")
            if res.approval_type != 'ONE' and len(res.user_ids) <= 1:
                raise UserError("会签/或签时，审批人至少选择2个")

    @api.onchange('group_id')
    def onchange_update_approve_users(self):
        for record in self:
            if record.group_id:
                record.user_ids = record.group_id.users


class DingDingApprovalButton(models.Model):
    _name = 'custom.approve.model.button'
    _description = '自定义审批流模型按钮'
    _rec_name = 'name'

    model_id = fields.Many2one('ir.model', string='模型', index=True)
    model_model = fields.Char(string='模型名', related='model_id.model', store=True, index=True)
    name = fields.Char(string="按钮名称", index=True)
    function = fields.Char(string='按钮方法', index=True)
    modifiers = fields.Char(string="按钮属性值")

    def name_get(self):
        return [(rec.id, "%s:%s" % (rec.model_id.name, rec.name)) for rec in self]
