# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DingDingApprovalRecord(models.Model):
    _name = 'custom.approve.record'
    _description = '自定义审批记录'

    APPROVALRESULT = [('submit', '提交'), ('agree', '同意'), ('refuse', '拒绝'), ('cancel', '取消')]

    model_name = fields.Char(string='模型名称', index=True, help='例如sale.order')
    model_description = fields.Char(string='模型描述', help='例如其他出库申请')
    rec_display_name = fields.Char(string='记录显示名称', help='QT-300-00000034')
    rec_id = fields.Integer(string="记录ID", index=True)
    # process_instance = fields.Char(string="审批实例ID", index=True, required=True)
    oper_uid = fields.Many2one('res.users', string="操作人", required=True)
    approval_type = fields.Selection(string="类型", selection=[('AND', '会签'), ('OR', '或签'), ('ONE', '单人')])
    approval_result = fields.Selection(string=u'审批结果', selection=APPROVALRESULT)
    approval_content = fields.Char(string="内容")
    approval_time = fields.Datetime(string="记录时间", default=fields.Datetime.now)


