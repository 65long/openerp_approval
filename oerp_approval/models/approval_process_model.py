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
    # _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = '自定义审批流配置'

    name = fields.Char(string='审批名称', required=True, track_visibility='onchange')
    oa_model_id = fields.Many2one('ir.model', string='业务模型', index=True, ondelete='cascade', required=True)
    oa_model_name = fields.Char(string='模型名称', related='oa_model_id.model', store=True, index=True)
    company_id = fields.Many2one('res.company', string='适用公司', required=True,
                                 default=lambda self: self.env.user.company_id, track_visibility='onchange')
    active = fields.Boolean(string='有效', default=False)
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
                    func_name = item.get('name')
                    string_name = item.get('name')
                    if not func_name: continue
                    domain = [('model_id', '=', model_id.id), ('function', '=', func_name), ('name', '=', string_name)]
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
        self.active = True


class CustomApproveResUsersRel(models.Model):
    _name = 'custom.approve.node.line'
    # _inherit = ['mail.thread']
    _description = '自定义审批节点'

    APPROVE_TYPE = [('AND', '会签'), ('OR', '或签'), ('ONE', '单人'), ('submit', '提交'), ('cancel', '取消')]
    custom_approve_id = fields.Many2one('custom.approve.process.config', string='自定义审批id', ondelete='cascade')
    oa_model_name = fields.Char(related='custom_approve_id.oa_model_name', string="审批模型_name", help='例如sale.order')
    group_id = fields.Many2one('res.groups', string="适用权限组")
    user_ids = fields.Many2many('res.users', 'custom_approval_user_list_rel', string="审批人")
    approval_type = fields.Selection(string="审批类型", selection=APPROVE_TYPE,
                                     required=True, default='ONE')
    only_self = fields.Boolean(string='仅发起人可用', default=False)
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
            if res.approval_type in ['AND', 'OR'] and len(res.user_ids) <= 1:
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

    model_id = fields.Many2one('ir.model', string='模型', index=True, ondelete='cascade')
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
            ('active', '=', True),
        ], limit=1, order='id desc')

        # 遍历查找当前按钮
        btn_type = ''
        btn_type_func = ''
        temp_line_dict = {}
        approve_lines = approve_conf.approve_line_ids
        for line in approve_lines:
            temp_line_dict['next_line'] = line.sudo()  # 有btn_type则next_line必有值
            if temp_line_dict.get('cur_line'):
                break
            if line.agree_button_func == method:
                btn_type = 'agree'
                temp_line_dict['cur_line'] = line.sudo()
            if line.refuse_button_func == method:
                btn_type = 'refuse'
                temp_line_dict['cur_line'] = line.sudo()

            if not temp_line_dict.get('cur_line'):
                continue
            if line.approval_type in ['AND', 'OR', 'ONE']:
                # 审批类型的按钮更新approve_users
                btn_type_func = "approve_{}".format(btn_type)
            elif line.approval_type in ['submit']:
                # 提交类的按钮需要,通知抄送人
                btn_type_func = "submit_{}".format(btn_type)
            elif line.approval_type in ['cancel']:
                # 取消类的按钮需要干嘛？
                btn_type_func = "cancel_{}".format(btn_type)

        # 获取当前单据的id
        if args[0]:
            res_id = args[0][0]
        else:
            params = args[1].get('params', {})
            res_id = params.get('id', -1)

        # 获取当前记录
        cur_record = request.env[model].sudo().browse(res_id)
        cur_approve_users = getattr(cur_record, 'approve_users', '')
        if not btn_type_func:
            # 未匹配当前按钮的在管控列表，就直接返回原来按钮调用
            return super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)

        record_model = request.env['custom.approve.record'].sudo()
        record_dict = dict(
            model_name=cur_record._name,
            rec_id=res_id,
            oper_uid=request.env.user.id,
            approval_type='',
            approval_result='',
        )
        # approval_type 可选[and or one] approval_result可选submit ,agree, refuse, cancel
        if btn_type_func in ['approve_agree']:
            # 添加审批记录
            next_line = temp_line_dict['next_line']
            cur_line = temp_line_dict['cur_line']
            if cur_line.approval_type == 'AND':
                record_dict.update(dict(approval_type=cur_line.approval_type, approval_result='agree'))
                record_model.create(record_dict)
                # 通过之后需要做，将现在用户id的u_uuid替换成空
                u_uuid = request.env.user.user_uuid
                temp_approve_users = cur_approve_users.replace('{},'.format(u_uuid), '')
                temp_approve_users = temp_approve_users.replace(u_uuid, '')

                if temp_approve_users:
                    # 本级审批要继续,
                    res = {'type': 'ir.actions.client', 'tag': 'reload'}
                else:
                    # 更新当前审批的下一审批节点审批人
                    temp_approve_users = ''
                    if cur_line != next_line:  # 当前节点不是最后一个
                        temp_approve_users = ','.join(next_line.sudo().user_ids.mapped('user_uuid'))
                    res = super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)

                # print('===============审批过后的approve——uuid', temp_approve_users)
                cur_record.approve_users = temp_approve_users
                self.gen_msg_to_cur_doc(cur_line, cur_record, 'agree')
                return res
            elif cur_line.approval_type in ['OR', 'ONE']:
                record_dict.update(dict(approval_type=cur_line.approval_type, approval_result='agree'))
                record_model.create(record_dict)
                # 更新到下一级的状态
                temp_approve_users = ','.join(next_line.user_ids.mapped('user_uuid'))
                cur_record.approve_users = temp_approve_users
                self.gen_msg_to_cur_doc(cur_line, cur_record, 'agree')
                res = super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)
                return res
        elif btn_type_func in ['approve_refuse']:
            # 审批拒绝
            #     -添加审批记录,调用原来按钮
            # next_line = temp_line_dict['next_line']
            cur_line = temp_line_dict['cur_line']
            record_dict.update(dict(approval_result='refuse', approval_type=cur_line.approval_type))
            record_model.create(record_dict)
            # cur_record.approve_users = 'init'
            self.gen_msg_to_cur_doc(cur_line, cur_record, 'refuse')
            return super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)

        elif btn_type_func in ['submit_agree', 'submit_refuse']:
            # 提交审批所做的事情
            cur_line = temp_line_dict['cur_line']
            next_line = temp_line_dict['next_line']

            record_dict.update(dict(approval_result='submit'))
            record_model.create(record_dict)

            users_uuid = ','.join(next_line.user_ids.mapped('user_uuid'))
            cur_record.approve_users = users_uuid
            self.gen_msg_to_cur_doc(cur_line, cur_record, msg_type='submit', next_approve_line=next_line)

            return super(CustomApproveDataSet, self).call_button(model, method, args, domain_id, context_id)
        elif btn_type_func in ['cancel_agree', 'cancel_refuse']:
            # 取消审批所做的事情
            cur_line = temp_line_dict['cur_line']
            next_line = temp_line_dict['next_line']

            record_dict.update(dict(approval_result='cancel'))
            record_model.create(record_dict)

            users_uuid = ','.join(next_line.user_ids.mapped('user_uuid'))
            print('==============》此时为取消 更新当前审核人', users_uuid)
            cur_record.approve_users = 'init'
            self.gen_msg_to_cur_doc(cur_line, cur_record)


    @staticmethod
    def gen_msg_to_cur_doc(approve_line, cur_record, msg_type='tip', next_approve_line=None):
        type_str_dict = dict(approve_line.APPROVE_TYPE)
        approve_type = type_str_dict.get(approve_line.approval_type)
        cur_user_name = request.env.user.name
        msg_next = ''
        if msg_type == 'tip':

            msg = '该单据当前审批类型:{}, 审批人{}'. \
                format(approve_type,
                       ','.join(approve_line.user_ids.mapped('name')))
        elif msg_type == 'agree':
            msg = '该单据当前审批类型{}, {}通过了审批，悉知'.format(approve_type, cur_user_name)
        elif msg_type == 'refuse':
            msg = '该单据当前审批类型{}, {}拒绝了审批，悉知'.format(approve_type, cur_user_name)
        elif msg_type == 'submit':
            msg = '单据本次审核类型为:{}, 由{}提交审批，悉知'.format(approve_type, cur_user_name)
            next_approve_type = type_str_dict.get(next_approve_line.approval_type)
            next_approve_user = ','.join(next_approve_line.user_ids.mapped('name'))
            msg_next = '本单据当前审批类型为{}, 应由{}审批, 悉知'.format(next_approve_type, next_approve_user)
        elif msg_type == 'cancel':
            msg = '单据本次操作类型为:{}, 由{}取消审批，悉知'.format(approve_type, cur_user_name)

        cur_record.message_post(body=msg, message_type='notification')
        if msg_next:
            cur_record.message_post(body=msg_next, message_type='notification')


def _action_custom_approval_record(self):
    """
    跳转到自定义审批记录tree
    :param self:
    :return:
    """
    self.ensure_one()
    return {
        "type": "ir.actions.act_window",
        "res_model": "custom.approve.record",
        "views": [[False, "tree"]],
        "name": "审批记录",
        "domain": [["model_name", "=", self._name], ['rec_id', '=', self.id]],
        "context": {
            # 'search_default_group_by_model': 0,
            # 'search_default_group_by_process_instance': 0
        },
    }


setattr(models.Model, 'action_custom_approve_record', _action_custom_approval_record)