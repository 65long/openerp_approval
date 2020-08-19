# encoding: utf-8
import logging
import uuid
from odoo import models, fields, api, tools

# from odoo.exceptions import Warning

_logger = logging.getLogger(__name__)


class InheritUsers(models.Model):
    _inherit = 'res.users'
    _description = '继承原users扩展字段'

    def get_uuid(self):
        return str(uuid.uuid4()).replace('-', '')

    user_uuid = fields.Char(string="用户唯一码", required=True, default=get_uuid, readonly=True)
