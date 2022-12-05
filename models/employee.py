import asyncio

from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError
from ..common.ding_request import ding_request_instance


def send_list_to_str(send_list):
    """
    convert send list to str
    :param send_list: ding_id list or None
    :return:
    """
    if send_list is None:
        return send_list
    return ','.join(send_list)


class Employee(models.Model):
    _inherit = 'hr.employee'

    ding_id = fields.Char(string='Dingtalk User unionid ID')
    ding_userid = fields.Char(string='Dingtalk User ID')
    ding_department_ids = fields.Many2many('hr.department', 'ding_employee_department_rel', 'employee_id',
                                           'department_id', string='Dingtalk Departments')
    ding_extattr = fields.Json(string='Dingtalk User Extattr')

    @api.depends('department_id.manager_id')
    def _compute_parent_id(self):
        for employee in self.filtered('department_id.manager_id'):
            employee.parent_id = employee.department_id.manager_id

    def ding_write_with_user(self, val):
        if self.user_id.id is False:
            user = self.env['res.users'].sudo().create({
                'name': val['name'],
                'login': val['ding_id'],
                'company_id': val['company_id'],
                'company_ids': [(4, val['company_id'])],
                'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
                'active': val['active']
            })
            val['user_id'] = user.id
        else:
            self.user_id.sudo().write({
                'name': val['name'],
                'active': val['active']
            })
        self.write(val)

    def ding_create_with_user(self, val_list):
        for val in val_list:
            user = self.env['res.users'].sudo().search(
                [('login', '=', val['ding_id']), ('active', 'in', [True, False])])
            if user.id is False:
                user = self.env['res.users'].sudo().create({
                    'name': val['name'],
                    'login': val['ding_id'],
                    'company_id': val['company_id'],
                    'company_ids': [(4, val['company_id'])],
                    'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
                    'active': val['active']
                })
            val['user_id'] = user.id
        return self.create(val_list)

    def get_employee_job(self, job_name, company_id):
        job = self.env['hr.job'].sudo().search(
            [('name', '=', job_name), ('company_id', '=', company_id)])
        if job_name and job.id is False:
            job = self.env['hr.job'].sudo().create({
                'name': job_name,
                'company_id': company_id
            })
        return job

    async def sync_ding_user(self, ding_department, server_dep_id):
        ding_request = self.env.context.get('ding_request')
        ding_app = self.env.context.get('ding_app')
        sync_with_user = ding_app.sync_with_user

        users = await ding_request.department_users(server_dep_id)
        # users has multipage, so we need get all users
        next_cursor = users.get('next_cursor', None)

        user_list = users['list']
        while next_cursor is not None:
            _users = await ding_request.department_users(server_dep_id, cursor=next_cursor)
            next_cursor = _users.get('next_cursor', None)
            user_list.extend(_users['list'])

        create_users = []
        manager_id = None

        for user in user_list:
            # job
            job = self.get_employee_job(user.get('title', None), ding_app.company_id.id)

            user_id = user['userid']
            unionid = user['unionid']

            employee = self.search([('ding_id', '=', unionid), ('active', 'in', [True, False])])
            main_department = ding_department.search([('ding_id', '=', user['dept_id_list'][0])])

            modify_data = {
                'name': user['name'],
                'ding_id': unionid,
                'ding_userid': user_id,
                'company_id': ding_app.company_id.id,
                'department_id': main_department.id,
                'ding_department_ids': [(4, ding_department.id)],
                'job_id': job.id,
                'work_email': user.get('email', None),
                'mobile_phone': user.get('mobile', None),
                'ding_extattr': user.get('extension', None),
                'parent_id': False,
                'active': user['active']
            }

            if employee.id is False:
                modify_data['marital'] = False
                create_users.append(modify_data)
            else:
                employee.ding_write_with_user(modify_data) if sync_with_user else employee.write(modify_data)

            # set department manager
            if user['leader'] == 1 and not manager_id:
                manager_id = unionid

        if len(create_users) > 0:
            # create users limit 500
            limit = 500
            for i in range(0, len(create_users), limit):
                create_vals = create_users[i:i + limit]
                # if config set not sync user, not create user
                self.ding_create_with_user(create_vals) if sync_with_user else self.create(create_vals)
        if manager_id:
            ding_department.write({'manager_id': self.search([('ding_id', '=', manager_id)]).id})

    def send_ding_message(self, app_id, to_users, to_departments=None, msg=None):
        """
        send message in Dingtalk
        :param app_id: dingtalk app id used to send message
        :param to_users: dingtalk user ding_userid list, if to all user, set to 'to_all_user'
        :param to_departments: dingtalk department ding_id list
        :param msg: other parameters, reference https://open.dingtalk.com/document/orgapp-server/message-types-and-data-format
        :return: message id
        """
        assert app_id, 'app_id is required'
        assert msg, 'msg is required'
        if len(to_users) == 0 and len(to_departments) == 0:
            raise UserError(_('Please select the user or department to send the message!'))

        app = self.env['dingtalk.app'].sudo().browse(int(app_id))
        ding_request = ding_request_instance(app.app_key, app.app_secret)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        userid_list = None if to_users == 'to_all_user' else send_list_to_str(to_users)
        to_all_user = None if to_users != 'to_all_user' else True

        send_message_task = loop.create_task(ding_request.send_message(dict(
            agentid=app.agentid,
            agent_id=app.agentid,
            userid_list=userid_list,
            to_all_user=to_all_user,
            dept_id_list=send_list_to_str(to_departments),
            msg=msg
        )))
        loop.run_until_complete(send_message_task)
        loop.close()
        return send_message_task.result()

    @staticmethod
    def get_user_info_by_ding_ids(app_key, app_secret, ding_ids):
        """
        get user info by dingtalk user ding_id list
        :param app_key:
        :param app_secret:
        :param ding_ids:
        :return: info list
        """
        user_infos = []

        ding_request = ding_request_instance(app_key, app_secret)
        tasks = []

        async def _add_wait(id):
            user_info = await ding_request.get_user_info_by_userid(id)
            user_infos.append(user_info)

        for ding_id in ding_ids:
            tasks.append(_add_wait(ding_id))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
        return user_infos

    def on_ding_user_add_org(self, content, app):
        """
        when user add org, create user and set department leader
        :param content:
        :param app:
        :return:
        """
        user_infos = self.get_user_info_by_ding_ids(app.app_key, app.app_secret, content['UserId'])
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        for user in user_infos:
            unionid = user['unionid']
            job = self.get_employee_job(user.get('title', None), app.company_id.id)
            main_department = self.env['hr.department'].search([('ding_id', '=', user['dept_id_list'][0])])
            departments = self.env['hr.department'].search([('ding_id', 'in', user['dept_id_list'])])

            employee = self.create({
                'name': user['name'],
                'ding_id': unionid,
                'ding_userid': user['userid'],
                'company_id': app.company_id.id,
                'department_id': main_department.id,
                'ding_department_ids': [(6, 0, departments.ids)],
                'job_id': job.id,
                'work_email': user.get('email', None),
                'mobile_phone': user.get('mobile', None),
                'ding_extattr': user.get('extension', None),
                'parent_id': False,
                'marital': False,
                'active': user['active']
            })
            leader_dep_ding_ids = [i['dept_id'] for i in user['leader_in_dept'] if i['leader'] is True]
            # set new department manager if leader_dep_ding_ids is not empty
            if len(leader_dep_ding_ids) > 0:
                self.env['hr.department'].search([('ding_id', 'in', leader_dep_ding_ids)]).write(
                    {'manager_id': employee.id})

    def on_ding_user_modify_org(self, content, app):
        """
        when user modify org, update user info and department leader
        :param content:
        :param app:
        :return:
        """
        user_infos = self.get_user_info_by_ding_ids(app.app_key, app.app_secret, content['UserId'])
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        for user in user_infos:
            unionid = user['unionid']
            job = self.get_employee_job(user.get('title', None), app.company_id.id)
            employee = self.search([('ding_id', '=', unionid), ('active', 'in', [True, False])])
            main_department = self.env['hr.department'].search([('ding_id', '=', user['dept_id_list'][0])])
            departments = self.env['hr.department'].search([('ding_id', 'in', user['dept_id_list'])])

            if employee.id is not False:
                employee.write({
                    'name': user['name'],
                    'ding_id': unionid,
                    'ding_userid': user['userid'],
                    'company_id': app.company_id.id,
                    'department_id': main_department.id,
                    'ding_department_ids': [(6, 0, departments.ids)],
                    'job_id': job.id,
                    'work_email': user.get('email', None),
                    'mobile_phone': user.get('mobile', None),
                    'ding_extattr': user.get('extension', None),
                    'parent_id': False,
                    'active': user['active']
                })
                if employee.user_id.id is not False:
                    employee.user_id.write({
                        'name': user['name'],
                        'active': user['active']
                    })
                leader_dep_ding_ids = [i['dept_id'] for i in user['leader_in_dept'] if i['leader'] is True]
                # clear department manager and then set new department manager
                self.env['hr.department'].search([('manager_id', '=', employee.id)]).write({'manager_id': False})
                self.env['hr.department'].search([('ding_id', 'in', leader_dep_ding_ids)]).write(
                    {'manager_id': employee.id})

    def on_ding_user_leave_org(self, content, app):
        """
        when user leave org, set user active to False
        :param content:
        :param app:
        :return:
        """
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        self.search(
            [('ding_id', 'in', content['UserId']), ('active', 'in', [True, False]),
             ('company_id', '=', app.company_id.id)]
        ).write({'active': False})

    def on_ding_user_active_org(self, content, app):
        """
        when user active org, set user active to True
        :param content:
        :param app:
        :return:
        """
        self.env = api.Environment(self._cr, SUPERUSER_ID, {})

        self.search(
            [('ding_id', 'in', content['UserId']), ('active', 'in', [True, False]),
             ('company_id', '=', app.company_id.id)]
        ).write({'active': True})
