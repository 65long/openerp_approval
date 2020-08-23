# -*- coding: utf-8 -*-
{
    'name': "自定义审批流配置",

    'description': """
        自定义审批
    """,

    'author': "LFL",
    'website': "http://www.haierbaby.com",

    'category': '',
    'version': '1.0',
    'depends': ['base', 'mail'],
    'data': [
        'security/custom_approve_security.xml',
        'security/ir.model.access.csv',
        'views/custom_approve_config_views.xml',
        # 'views/shop_type_views.xml',
        # 'data/ir_sequence_data.xml',
        'views/custom_approve_record.xml',
    ],
    'installable': True,
    'auto_install': False
}
