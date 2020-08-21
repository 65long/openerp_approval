# encoding: utf-8

import logging
from lxml import etree
from odoo import models, fields, api, http, _
from odoo.http import request
from odoo.exceptions import UserError, Warning
from odoo.addons.web.controllers.main import DataSet

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
    cc_type = fields.Selection(string="抄送时间",
                               selection=[('START', '审批开始'), ('FINISH', '审批结束'), ('START_FINISH', '开始和结束')],
                               default='FINISH')

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
    oa_model_name = fields.Char(related='custom_approve_id.oa_model_name', string="审批模型_name", help='例如sale.order')
    group_id = fields.Many2one('res.groups', string="适用权限组")
    user_ids = fields.Many2many('res.users', 'custom_approval_user_list_rel', string="审批人")
    approval_type = fields.Selection(string="审批类型", selection=[('AND', '会签'), ('OR', '或签'), ('ONE', '单人')],
                                     required=True, default='ONE')
    agree_button_id = fields.Many2one('custom.approve.model.button', string="通过后执行")
    agree_button_func = fields.Char(string='同意执行方法', related='agree_button_id.function', store=True)
    refuse_button_id = fields.Many2one('custom.approve.model.button', string="拒绝后执行")
    refuse_button_func = fields.Char(string='拒绝执行方法', related='refuse_button_id.function', store=True)

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


class CustomApproveDataSet(DataSet):

    @http.route('/web/dataset/call_button', type='json', auth="user")
    def call_button(self, model, method, args, domain_id=None, context_id=None):
        approve_conf = request.env['custom.approve.process.config'].sudo().search([
            ('oa_model_name', '=', model),
            # ('active', '=', True),
        ], limit=1, order='id desc')
        print(22222222222222222222, approve_conf)
        # def origin_res()

        # 遍历查找当前按钮
        btn_type = ''
        for line in approve_conf.approve_line_ids:
            if line.agree_button_func == method:
                btn_type = 'approve_users'
                break
            if line.refuse_button_func == method:
                btn_type = 'refuse_users'
                break
        # 获取当前单据的id
        if args[0]:
            res_id = args[0][0]
        else:
            params = args[1].get('params', {})
            res_id = params.get('id', -1)

        # 获取当前记录
        cur_record = request.env[model].sudo().browse(res_id)
        cur_approve_users = getattr(cur_record, 'approve_users', '')
        cur_refuse_users = getattr(cur_record, 'approve_users', '')
        if 'init' in [cur_approve_users, cur_refuse_users]:
            # 此时需要更新approve_users 和 cur_refuse_users
            users_uuid = ','.join(approve_conf.approve_line_ids[0].sudo().user_ids.mapped('user_uuid'))
            print('==============》此时为init 更新当前审核人', users_uuid)
            cur_record.approve_users = users_uuid
            cur_record.refuse_users = users_uuid
        if not btn_type:
            # 未匹配到当前按钮的类型，就直接返回原来按钮调用
            return super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)


        # 如果匹配到按钮类型，则判断line的审批类型，同时做审批记录返回页面刷新
        cur_approve_users = cur_record.approve_users
        print('=======btn  type=======', btn_type)
        if btn_type == 'approve_users':
            if line.approval_type == 'AND':
                # ('AND', '会签'), ('OR', '或签'), ('ONE', '单人审批
                # 通过之后需要做，将现在用户id的u_uuid替换成空
                u_uuid = self.env.user.user_uuid
                temp_approve_users = cur_refuse_users.replace(u_uuid, '')
                # 判断本级审批是否需要继续,
                #   需要 则刷新屏幕
                #   不需要 则更新为配置的下一级审批,调用原生方法
                print('===============审批过后的approve——uuid', temp_approve_users)
                cur_record.approve_users = temp_approve_users
                cur_record.refuse_users = temp_approve_users
                return super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)
            elif line.approval_type in ['OR', 'ONE']:
                pass
                # 更新到下一级的状态
        else:
            # 审批拒绝不用做任何更改
            pass

        return super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)
