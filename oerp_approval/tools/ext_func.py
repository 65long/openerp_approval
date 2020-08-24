# -*- coding: utf-8 -*-

import logging
from odoo.tools.safe_eval import safe_eval
_logger = logging.getLogger(__name__)

# Don't deal with groups, it is done by check_group().
# Need the context to evaluate the invisible attribute on tree views.
# For non-tree views, the context shouldn't be given.
UID = ", u_id"


def transfer_node_to_modifiers(node, modifiers, context=None, in_tree_view=False, **kwargs):
    if node.get('attrs'):
        try:
            if UID in node.get('attrs'):
                user_id = str(kwargs.get('u_id', 1))
                user_id = ', ' + user_id
                attrs = node.get('attrs')
                attrs = attrs.replace(UID, user_id)
                node.set('attrs', attrs)
            attrs_str = node.get('attrs').replace('\n', '')
            modifiers.update(eval(attrs_str))
        except Exception as e:
            _logger.error('---转换自定义的UID--{}时候错误:{}'.format(UID, str(e)))
            raise
        # modifiers.update(eval(node.get('attrs')))

    if node.get('states'):
        if 'invisible' in modifiers and isinstance(modifiers['invisible'], list):
            # TODO combine with AND or OR, use implicit AND for now.
            modifiers['invisible'].append(('state', 'not in', node.get('states').split(',')))
        else:
            modifiers['invisible'] = [('state', 'not in', node.get('states').split(','))]

    for a in ('invisible', 'readonly', 'required'):
        if node.get(a):
            v = bool(safe_eval(node.get(a), {'context': context or {}}))
            if in_tree_view and a == 'invisible':
                # Invisible in a tree view has a specific meaning, make it a
                # new key in the modifiers attribute.
                modifiers['column_invisible'] = v
            elif v or (a not in modifiers or not isinstance(modifiers[a], list)):
                # Don't set the attribute to False if a dynamic value was
                # provided (i.e. a domain from attrs or states).
                modifiers[a] = v
