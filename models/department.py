import asyncio

from odoo import models, fields, SUPERUSER_ID, api
from ..common.ding_request import ding_request_instance


class Department(models.Model):
    _inherit = 'hr.department'

    ding_id = fields.Char(string='Dingtalk Department ID')
    ding_parent_id = fields.Char(string='Dingtalk Parent Department ID')
    ding_order = fields.Integer(string='Dingtalk Department Order')
    '''because a Dingtalk user can have multi departments, so we need a many2many field, 
    the department_id field is only main department'''
    ding_employee_ids = fields.Many2many('hr.employee', 'ding_employee_department_rel', 'department_id', 'employee_id',
                                         string='Dingtalk Employees')

    async def get_ding_server_depart_tree(self, dep_ids, for_in_callback=None):
        """
        get Dingtalk server department id tree
        :param dep_ids: server department id list
        :param for_in_callback: callback function in for loop
        :return:
        """
        ding_request = self.env.context.get('ding_request')
        tree = []

        _tasks = []

        async def _append_to_tree(parent_dep_id, _tree):
            sublist = await ding_request.department_listsubid(parent_dep_id)
            _tree.append({
                'id': parent_dep_id,
                'children': await self.get_ding_server_depart_tree(sublist, for_in_callback)
            })

        for dep_id in dep_ids:
            if for_in_callback:
                for_in_callback(dep_id)
            _tasks.append(_append_to_tree(dep_id, tree))

        await asyncio.gather(*_tasks)

        return tree

    async def sync_ding_department(self):
        """
        sync department from Dingtalk server
        :return:
        """
        ding_request = self.env.context.get('ding_request')
        ding_app = self.env.context.get('ding_app')
        auth_scopes = self.env.context.get('auth_scopes')

        dep_ding_id_list = []
        depart_tree = await self.get_ding_server_depart_tree(
            auth_scopes['auth_org_scopes']['authed_dept'],
            lambda dep_id: dep_ding_id_list.append(dep_id)
        )

        tasks = []

        # change where the employee in the department status to active = False
        self.env['hr.employee'].search([('ding_department_ids.ding_id', 'in', dep_ding_id_list)]).write(
            {'active': False})

        async def _sync_dep(_dep_leaf, parent_id):
            _tasks = []
            dep_detail = await ding_request.department_detail(_dep_leaf['id'])

            dep = self.search([('ding_id', '=', dep_detail['dept_id'])])
            # dep need commit to db because sync user need use it
            modify_data = {
                'company_id': ding_app.company_id.id,
                'name': dep_detail['name'],
                'ding_id': dep_detail['dept_id'],
                'ding_parent_id': dep_detail.get('parent_id', None),  # root department has no parent_id
                'parent_id': parent_id,
                'ding_order': dep_detail['order'],
                'manager_id': False
            }

            if dep.id is False:
                dep = self.create(modify_data)
            else:
                dep.write(modify_data)

            await self.env['hr.employee'].sync_ding_user(dep, dep_detail['dept_id'])

            if len(_dep_leaf['children']) > 0:
                for child in _dep_leaf['children']:
                    _tasks.append(_sync_dep(child, dep.id))
                await asyncio.gather(*_tasks)

        for dep_leaf in depart_tree:
            tasks.append(_sync_dep(dep_leaf, False))

        await asyncio.gather(*tasks)

    @staticmethod
    def get_depart_info_by_ding_ids(app_key, app_secret, ding_ids):
        """
        get departmengt info by dingtalk dept ding_id list
        :param app_key:
        :param app_secret:
        :param ding_ids:
        :return: info list
        """
        department_infos = []

        ding_request = ding_request_instance(app_key, app_secret)
        tasks = []

        async def _add_wait(id):
            dept_info = await ding_request.department_detail(id)
            department_infos.append(dept_info)

        for ding_id in ding_ids:
            tasks.append(_add_wait(ding_id))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
        return department_infos

    def get_main_manager_by_user_ding_ids(self, ding_ids, company_id):
        """
        get main manager by user dingtalk id list
        :param ding_ids:
        :param company_id:
        :return:
        """
        manager_user_id = ding_ids[0] if len(ding_ids) > 0 else False
        manager = self.env['hr.employee'].search(
            [('ding_userid', '=', manager_user_id), ('company_id', '=', company_id)])
        return manager

    def on_ding_org_dept_create(self, content, app):
        department_infos = self.get_depart_info_by_ding_ids(app.app_key, app.app_secret, content['DeptId'])
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        for dept in department_infos:
            manager = self.get_main_manager_by_user_ding_ids(dept['dept_manager_userid_list'], app.company_id.id)

            parent_id = dept.get('parent_id', None)  # root department has no parent_id
            parent_department = self.search([('ding_id', '=', parent_id)])
            self.create({
                'company_id': app.company_id.id,
                'ding_id': dept['dept_id'],
                'name': dept['name'],
                'ding_parent_id': parent_id,
                'parent_id': parent_department.id,
                'ding_order': dept['order'],
                'manager_id': manager.id
            })

    def on_ding_org_dept_modify(self, content, app):
        """
        when dingtalk department modify, update the department info and manager
        :param content:
        :param app:
        :return:
        """
        department_infos = self.get_depart_info_by_ding_ids(app.app_key, app.app_secret, content['DeptId'])
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        for dept in department_infos:
            manager = self.get_main_manager_by_user_ding_ids(dept['dept_manager_userid_list'], app.company_id.id)

            department = self.search([('ding_id', '=', dept['dept_id'])])
            parent_id = dept.get('parent_id', None)  # root department has no parent_id
            parent_department = self.search([('ding_id', '=', parent_id)])
            if department:
                department.write({
                    'name': dept['name'],
                    'ding_parent_id': parent_id,
                    'parent_id': parent_department.id,
                    'ding_order': dept['order'],
                    'manager_id': manager.id
                })

    def on_ding_org_dept_remove(self, content, app):
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        self.search(
            [('ding_id', 'in', content['DeptId']), ('company_id', '=', app.company_id.id)]
        ).unlink()
