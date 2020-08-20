# -*- coding: utf-8 -*-


import logging
from lxml import etree
# from lxml.etree import LxmlError
import ast
from odoo.addons.oerp_approval.models.ext_func import transfer_node_to_modifiers
from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.osv import orm
from lxml.builder import E
from odoo.tools.safe_eval import safe_eval
from functools import partial
from odoo.tools import pycompat

_logger = logging.getLogger(__name__)

ATTRS_WITH_FIELD_NAMES = {
    'context',
    'domain',
    'decoration-bf',
    'decoration-it',
    'decoration-danger',
    'decoration-info',
    'decoration-muted',
    'decoration-primary',
    'decoration-success',
    'decoration-warning',
}

UID = ", u_id"
U_UUID = "u_uuid"


class ir_ui_view(models.Model):
    _name = 'ir.ui.view'
    _inherit = 'ir.ui.view'

    @api.model
    def postprocess(self, model, node, view_id, in_tree_view, model_fields):
        """Return the description of the fields in the node.

        In a normal call to this method, node is a complete view architecture
        but it is actually possible to give some sub-node (this is used so
        that the method can call itself recursively).

        Originally, the field descriptions are drawn from the node itself.
        But there is now some code calling fields_get() in order to merge some
        of those information in the architecture.

        """
        result = False
        fields = {}
        children = True

        modifiers = {}
        if model not in self.env:
            self.raise_view_error(_('Model not found: %(model)s') % dict(model=model), view_id)
        Model = self.env[model]

        if node.tag in ('field', 'node', 'arrow'):
            if node.get('object'):
                attrs = {}
                views = {}
                xml_form = E.form(*(f for f in node if f.tag == 'field'))
                xarch, xfields = self.with_context(base_model_name=model).postprocess_and_fields(node.get('object'),
                                                                                                 xml_form, view_id)
                views['form'] = {
                    'arch': xarch,
                    'fields': xfields,
                }
                attrs = {'views': views}
                fields = xfields
            if node.get('name'):
                attrs = {}
                field = Model._fields.get(node.get('name'))
                if field:
                    editable = self.env.context.get('view_is_editable', True) and self._field_is_editable(field, node)
                    children = False
                    views = {}
                    for f in node:
                        if f.tag in ('form', 'tree', 'graph', 'kanban', 'calendar'):
                            node.remove(f)
                            xarch, xfields = self.with_context(
                                base_model_name=model,
                                view_is_editable=editable,
                            ).postprocess_and_fields(field.comodel_name, f, view_id)
                            views[str(f.tag)] = {
                                'arch': xarch,
                                'fields': xfields,
                            }
                    attrs = {'views': views}
                    if field.comodel_name in self.env and field.type in ('many2one', 'many2many'):
                        Comodel = self.env[field.comodel_name]
                        node.set('can_create',
                                 'true' if Comodel.check_access_rights('create', raise_exception=False) else 'false')
                        node.set('can_write',
                                 'true' if Comodel.check_access_rights('write', raise_exception=False) else 'false')
                fields[node.get('name')] = attrs

                field = model_fields.get(node.get('name'))
                if field:
                    orm.transfer_field_to_modifiers(field, modifiers)

        elif node.tag in ('form', 'tree'):
            result = Model.view_header_get(False, node.tag)
            if result:
                node.set('string', result)
            in_tree_view = node.tag == 'tree'

        elif node.tag == 'calendar':
            for additional_field in ('date_start', 'date_delay', 'date_stop', 'color', 'all_day'):
                if node.get(additional_field):
                    fields[node.get(additional_field).split('.', 1)[0]] = {}
            for f in node:
                if f.tag == 'filter':
                    fields[f.get('name')] = {}

        if not self._apply_group(model, node, modifiers, fields):
            # node must be removed, no need to proceed further with its children
            return fields

        # The view architeture overrides the python model.
        # Get the attrs before they are (possibly) deleted by check_group below
        transfer_node_to_modifiers(node, modifiers, self._context, in_tree_view, u_id=self.env.user.id)

        for f in node:
            if children or (node.tag == 'field' and f.tag in ('filter', 'separator')):
                fields.update(self.postprocess(model, f, view_id, in_tree_view, model_fields))

        orm.transfer_modifiers_to_node(modifiers, node)
        return fields

    def get_attrs_field_names(self, arch, model, editable):
        """ Retrieve the field names appearing in context, domain and attrs, and
            return a list of triples ``(field_name, attr_name, attr_value)``.
        """
        VIEW_TYPES = {item[0] for item in type(self).type.selection}
        symbols = self.get_attrs_symbols() | {None}
        result = []

        def get_name(node):
            """ return the name from an AST node, or None """
            if isinstance(node, ast.Name):
                return node.id

        def get_subname(get, node):
            """ return the subfield name from an AST node, or None """
            if isinstance(node, ast.Attribute) and get(node.value) == 'parent':
                return node.attr

        def process_expr(expr, get, key, val):
            """ parse `expr` and collect triples """
            for node in ast.walk(ast.parse(expr.strip(), mode='eval')):
                name = get(node)
                if name not in symbols:
                    result.append((name, key, val))

        def process_attrs(expr, get, key, val, **kwargs):
            """ parse `expr` and collect field names in lhs of conditions. """
            if UID in expr:
                # print('-----process_attrs-------', kwargs.get('u_id', '未获取到'))
                user_id = str(kwargs.get('u_id', 1))
                user_id = ', {}'.format(user_id)
                expr = expr.replace(UID, user_id)
            for domain in safe_eval(expr).values():
                if not isinstance(domain, list):
                    continue
                for arg in domain:
                    if isinstance(arg, (tuple, list)):
                        process_expr(str(arg[0]), get, key, expr)

        def process(node, model, editable, get=get_name, **kwargs):
            """ traverse `node` and collect triples """
            if node.tag in VIEW_TYPES:
                # determine whether this view is editable
                editable = editable and self._view_is_editable(node)
            elif node.tag == 'field':
                # determine whether the field is editable
                field = model._fields.get(node.get('name'))
                if field:
                    editable = editable and self._field_is_editable(field, node)

            for key, val in node.items():
                if not val:
                    continue
                if key in ATTRS_WITH_FIELD_NAMES:
                    process_expr(val, get, key, val)
                elif key == 'attrs':
                    process_attrs(val, get, key, val, **kwargs)

            if node.tag == 'field' and field and field.relational:
                if editable and not node.get('domain'):
                    domain = field._description_domain(self.env)
                    # process the field's domain as if it was in the view
                    if isinstance(domain, pycompat.string_types):
                        process_expr(domain, get, 'domain', domain)
                # retrieve subfields of 'parent'
                model = self.env[field.comodel_name]
                get = partial(get_subname, get)

            for child in node:
                process(child, model, editable, get)

        process(arch, model, editable)
        return result


fields_view_get_origin = models.BaseModel.fields_view_get


def modify_tree_view(obj, result):
    fields_info = obj.fields_get(allfields=['dd_doc_state', 'dd_approval_state', 'dd_approval_result'])
    if 'dd_doc_state' in fields_info:
        dd_doc_state = fields_info['dd_doc_state']
        dd_doc_state.update({'view': {}})
        result['fields']['dd_doc_state'] = dd_doc_state

        root = etree.fromstring(result['arch'])
        field = etree.Element('field')
        field.set('name', 'dd_doc_state')
        field.set('widget', 'dd_approval_widget')
        root.append(field)
        result['arch'] = etree.tostring(root)

    if 'dd_approval_state' in fields_info:
        dd_approval_state = fields_info['dd_approval_state']
        dd_approval_state.update({'view': {}})
        result['fields']['dd_approval_state'] = dd_approval_state

        root = etree.fromstring(result['arch'])
        field = etree.Element('field')
        field.set('name', 'dd_approval_state')
        root.append(field)
        result['arch'] = etree.tostring(root)

    if 'dd_approval_result' in fields_info:
        dd_approval_result = fields_info['dd_approval_result']
        dd_approval_result.update({'view': {}})
        result['fields']['dd_approval_result'] = dd_approval_result

        root = etree.fromstring(result['arch'])
        field = etree.Element('field')
        field.set('name', 'dd_approval_result')
        root.append(field)
        result['arch'] = etree.tostring(root)
    # 添加tree颜色区分
    root = etree.fromstring(result['arch'])
    root.set('decoration-info', "dd_approval_result == 'load'")
    root.set('decoration-warning', "dd_approval_result == 'redirect'")
    root.set('decoration-success', "dd_approval_result == 'agree'")
    root.set('decoration-danger', "dd_approval_result == 'refuse'")
    result['arch'] = etree.tostring(root)


def update_modifiers_of_element(self, str_modifiers):
    temp_dic = {}
    import json
    try:
        # str_modifiers = str_modifiers.replace('true', 'True').replace('false', 'False')
        temp_dic = json.loads(str_modifiers)
        temp_domain = []
        print(self.env.user.user_uuid, '===============user_uuid')
        domain_element = ['approve_users', 'not ilike', self.env.user.user_uuid]
        if 'invisible' not in str_modifiers:
            temp_domain.append(domain_element)
        else:
            temp_val = temp_dic['invisible']
            print('转换按钮时候的invisible值{}'.format(temp_val))
            temp_val = temp_val if isinstance(temp_val, (list,)) and temp_val else []
            temp_val.append(domain_element)
            if len(temp_val) > 1:
                temp_val.insert(0, '|')
            temp_domain = temp_val

        temp_dic['invisible'] = temp_domain
    except Exception as e:
        print('处理按钮时候出问题--{}'.format(str(e)))
        return str_modifiers
    return json.dumps(temp_dic)


def modify_form_view(self, result, button_list):
    """button_list--[(agree_button_function, agree_button_modifier,
        refuse_button_function, refuse_button_modifier), ...]"""

    root = etree.fromstring(result['arch'])

    headers = root.xpath('header')
    if not headers:
        _logger.warning('在获取到的视图中未找到header, 配置结束')
        return
    header = headers[0]
    # 添加字段
    approve_users_field = etree.Element('field')
    approve_users_field.set('name', 'approve_users')
    approve_users_field.set('modifiers', '{"invisible": true}')
    header.insert(len(header.xpath('button')), approve_users_field)
    # header_str = header.tostring()
    import json
    print('====self======>', self)
    for button in button_list:
        agree_btn_func, agree_btn_attr, refuse_btn_func, refuse_btn_attr = button
        btns = header.xpath("//button[@name='{}']".format(agree_btn_func or 'sfdfasdfsafs'))
        btns += header.xpath("//button[@name='{}']".format(refuse_btn_func or 'sfadfadsfadsf'))
        for btn in btns:
            modifier = update_modifiers_of_element(self, btn.get('modifiers', '{}'))
            print('========转化后====', modifier)
            btn.set('modifiers', modifier)
            # btn.set('modifiers', '{"invisible": true}')
    result['arch'] = etree.tostring(root)
    return


def modify_views_by_config(self, result, view_type):
    if view_type not in ['form']: return
    config_model = self.env.get('custom.approve.process.config')
    if config_model is None: return
    config_obj = config_model.sudo().search([('oa_model_name', '=', self._name)], limit=1)
    if not config_obj: return
    if view_type == 'form':
        button_list = config_obj.approve_line_ids.mapped(lambda line: (
            line.agree_button_id.function,
            line.agree_button_id.modifiers,
            line.refuse_button_id.function,
            line.refuse_button_id.modifiers,
        ))
        modify_form_view(self, result, button_list)


@api.model
def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
    result = fields_view_get_origin(self, view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
    modify_views_by_config(self, result, view_type)
    return result


models.BaseModel.fields_view_get = fields_view_get
