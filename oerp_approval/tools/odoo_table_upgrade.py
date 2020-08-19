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
        print('------------此处执行')
        self._cr.execute(
            """SELECT im.model, capc.id FROM custom_approve_process_config capc 
                JOIN ir_model im  ON capc.oa_model_id = im.id  WHERE im.model = '%s'
            """ % self._name)
        res = self._cr.fetchall()
        if len(res) != 0:
            config_id = res[0][1]
            query_s1 = """
                select agree_button_id, refuse_button_id from custom_approve_node_line as canl 
                where canl.custom_approve_id= '%s';
            """ % config_id
            self._cr.execute(query_s1)
            button_res = self._cr.fetchall()
            print(button_res, '查询到的模型名称')

    return True


Model._setup_base = _setup_base

