# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

Model = models.Model
origin_setup_base = Model._setup_base


@api.model
def _setup_base(self):
    origin_setup_base(self)
    setup_custom_approve_fields_for_button(self)


def setup_custom_approve_fields_for_button(self):
    """添加字段"""

    def add(name, field):
        if name not in self._fields:
            self._add_field(name, field)

    # 查询自定义审批配置
    self._cr.execute("SELECT COUNT(*) FROM pg_class WHERE relname = 'custom_approve_process_config'")
    table = self._cr.fetchall()
    if table[0][0] > 0:
        query_sql = """select * from custom_approve_process_config"""
        self._cr.execute(query_sql)
        res = self._cr.fetchall()
        if not res or len(res[0]) < 6:
            # 再次安装清除剩余垃圾
            query_sql = """delete from custom_approve_process_config;
                            delete from custom_approve_model_button;
                            delete from custom_approve_record;
                        """
            self._cr.execute(query_sql)
            return True
        self._cr.execute(
            """SELECT im.model FROM custom_approve_process_config capc 
                JOIN ir_model im  ON capc.oa_model_id = im.id  WHERE im.model = '%s'
            """ % self._name)
        res = self._cr.fetchall()
        if len(res) != 0:
            add('approve_users', fields.Char(string=u'审批人列表', default='init', copy=False))
            add('submit_users', fields.Char(string=u'提交申请的人', default='init', copy=False))
            add('cancel_users', fields.Char(string=u'取消申请的人', default='init', copy=False))

    return True


Model._setup_base = _setup_base


# 全局修改create方法
create_origin = models.BaseModel.create

@api.model
def create(self, vals):
    res = create_origin(self, vals)
    custom_approve_create(self, res)
    return res


def custom_approve_create(self, res):
    """创建单据时候修改提交人或者取消人"""
    config_model = self.env.get('custom.approve.process.config')
    if config_model is None: return
    config_obj = config_model.sudo().search([
        ('oa_model_name', '=', self._name),
        ('active', '=', True),
    ], limit=1)
    if not config_obj: return
    node_lines = config_obj.approve_line_ids.filtered(lambda line: line.approval_type in ['submit', 'cancel'])
    for line in node_lines:
        if line.approval_type == 'submit' and res.submit_users == 'init':
            if line.only_self:
                # 仅仅本人可用
                res.submit_users = res.create_uid.user_uuid
            else:
                res.submit_users = ','.join(line.user_ids.mapped('user_uuid'))
        elif line.approval_type == 'cancel' and res.submit_users == 'init':
            if line.only_self:
                # 仅仅本人可用
                res.cancel_users = res.create_uid.user_uuid
            else:
                res.cancel_users = ','.join(line.user_ids.mapped('user_uuid'))
    return True


models.BaseModel.create = create