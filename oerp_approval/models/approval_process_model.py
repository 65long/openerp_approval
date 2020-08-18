# encoding: utf-8

import logging
from odoo import models, fields, api
from odoo.exceptions import UserError, Warning

_logger = logging.getLogger(__name__)


class ApprovalProcessConfig(models.Model):
    _name = 'custom.approve.process.config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = '自定义审批流配置'

    name = fields.Char(string='审批名称', required=True, track_visibility='onchange')
    oa_model_id = fields.Many2one('ir.model', string='业务模型', index=True, ondelete='set null')
    company_id = fields.Many2one('res.company', string='适用公司', required=True,
                                 default=lambda self: self.env.user.company_id, track_visibility='onchange')
    active = fields.Boolean(string='有效', default=True)
    approve_type = fields.Selection(string="审批类型", selection=[('ordinal', '依次审批'), ('complicated', '会签/或签')])
    recv_user_ids = fields.Many2many('res.users', 'custom_approve_recv_users_rel', string='抄送人列表')
    # complicated_approve_user_ids = fields.One2many('custom.approve.res.users.rel', 'custom_approve_id', string='审批列表')
    approve_user_ids = fields.One2many('custom.approve.node.line', 'custom_approve_id', string='审批列表')
    cc_user_ids = fields.Many2many('res.users', 'custom_approve_recv_users_rel', string='抄送人')
    cc_type = fields.Selection(string="抄送时间", selection=[('START', '审批开始'), ('FINISH', '审批结束'), ('START_FINISH', '开始和结束')], default='FINISH')

    # _sql_constraints = [
    # ]


class CustomApproveResUsersRel(models.Model):
    _name = 'custom.approve.node.line'
    _inherit = ['mail.thread']
    _description = '自定义审批节点'

    custom_approve_id = fields.Many2one('custom.approve.process.config', string='自定义审批id', required=True)
    group_id = fields.Many2one('res.groups', string="适用权限组")
    user_ids = fields.Many2many('res.users', 'custom_approval_user_list_rel', string="审批人")
    approval_type = fields.Selection(string="审批类型", selection=[('AND', '会签'), ('OR', '或签'), ('ONE', '单人')],
                                     required=True, default='ONE')

    # _sql_constraints = [
    # ]

    @api.onchange('group_id')
    def onchange_update_approve_users(self):
        print('--------------', self)
        for record in self:
            print(record)
            if record.group_id:
                record.user_ids = record.group_id.users
