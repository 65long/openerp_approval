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
                xarch, xfields = self.with_context(base_model_name=model).postprocess_and_fields(node.get('object'), xml_form, view_id)
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
                        node.set('can_create', 'true' if Comodel.check_access_rights('create', raise_exception=False) else 'false')
                        node.set('can_write', 'true' if Comodel.check_access_rights('write', raise_exception=False) else 'false')
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

