import asyncio
import threading
import time
import traceback

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.translate import _

from ..common.ding_request import ding_request_instance
from ..common.utils import to_sync, get_now_time_str, list_to_str


class App(models.Model):
    _name = 'dingtalk.app'
    _description = 'Dingtalk App'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    agentid = fields.Char(string='Agent ID', required=True)
    app_key = fields.Char(string='AppKey', required=True)
    app_secret = fields.Char(string='AppSecret', required=True)

    sync_with_user = fields.Boolean(string='Sync with res.user', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True)
    # callback settings
    token = fields.Char(string='Token')
    encoding_aes_key = fields.Char(string='EncodingAESKey')

    def run_ding_sync(self):
        self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
            'title': 'Sync Start......',
            'message': _('Start sync organization now, please wait......'),
            'warning': True
        })

        # create a threading to avoid odoo ui blocking
        def _sync():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            asyncio.run(self.sync_ding_organization())

        thread = threading.Thread(target=_sync)
        thread.start()

    async def sync_ding_organization(self):
        start = time.time()
        uid = self.env.uid
        is_success = True
        with self.env.registry.cursor() as new_cr:
            self.env = api.Environment(new_cr, uid, self.env.context)

            detail_log = f'start sync at {get_now_time_str()}......'
            try:
                ding_request = ding_request_instance(self.app_key, self.app_secret)

                # get dingtalk auth scope
                auth_scopes = await ding_request.get_auth_scopes()

                await self.env['hr.department'].with_context(
                    self.env.context, ding_app=self, ding_request=ding_request,
                    auth_scopes=auth_scopes
                ).sync_ding_department()
                detail_log += f'\nsync success!'
            except Exception:
                is_success = False
                detail_log += f'\nsync failed, error: \n{traceback.format_exc()}'
            finally:
                detail_log += f'\nsync end at {get_now_time_str()}, cost {round(time.time() - start, 2)}s'
                company_id = self.company_id.id
                self.env['dingtalk.log'].create({
                    'company_id': company_id,
                    'ding_app_id': self.id,
                    'detail': detail_log
                })
                self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                    'title': 'Sync End......',
                    'message': f'Sync organization end, {"success" if is_success else "failed"}',
                    'warning': True if is_success else False
                })

    def on_ding_bpms_task_change(self, content, app):
        """
        when dingtalk bpms task change the method will be callback, can override this method in model
        :param content: dingtalk bpms task change content
        :param app:
        :return:
        """
        pass

    def on_ding_bpms_instance_change(self, content, app):
        """
        when dingtalk bpms instance change the method will be callback, can override this method in model
        :param content: dingtalk bpms instance change content
        :param app:
        :return:
        """
        pass

    @api.model
    @to_sync
    async def upload_media(self, media_type, media_file, filename):
        """
        upload media to DingTalk
        :param media_type: image, voice, video or file
        :param media_file: media file
        :param filename: media filename
        :return: media_id
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.upload_media(media_type, media_file, filename)

    @api.model
    @to_sync
    async def send_ding_message(self, to_users, msg, to_departments=None):
        """
        send message in Dingtalk
        :param to_users: dingtalk user ding_userid list, if to all user, set to 'to_all_user'
        :param to_departments: dingtalk department ding_id list
        :param msg: other parameters, reference https://open.dingtalk.com/document/orgapp-server/message-types-and-data-format
        :return: message id
        """
        assert msg, 'msg is required'
        if len(to_users) == 0 and len(to_departments) == 0:
            raise UserError(_('Please select the user or department to send the message!'))

        ding_request = ding_request_instance(self.app_key, self.app_secret)

        userid_list = None if to_users == 'to_all_user' else list_to_str(to_users)
        to_all_user = None if to_users != 'to_all_user' else True

        return await ding_request.send_message(dict(
            agentid=self.agentid,
            agent_id=self.agentid,
            userid_list=userid_list,
            to_all_user=to_all_user,
            dept_id_list=list_to_str(to_departments),
            msg=msg
        ))

    @api.model
    @to_sync
    async def create_or_update_custom_oa_template(self, process_code, name, form_components, description=None,
                                                  process_feature_config=None):
        """
        create or update custom oa template
        :param process_code: form ProcessCode, if is update, this is required, otherwise is None
        :param name: form name, required
        :param form_components: form components list, required
        :param description: form description, not required
        :param process_feature_config: process feature config, not required
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_or_update_custom_oa_template(process_code, name, form_components, description,
                                                                      process_feature_config)

    @api.model
    @to_sync
    async def get_custom_oa_process_code(self, name):
        """
        get custom oa process code
        :param name: form name
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_custom_oa_process_code(name)

    @api.model
    @to_sync
    async def delete_custom_oa_template(self, process_code, clean_running_task=False):
        """
        delete custom oa template
        :param process_code: form ProcessCode
        :param clean_running_task: Whether to delete the running task
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.delete_custom_oa_template(process_code, clean_running_task)

    @api.model
    @to_sync
    async def create_custom_oa_instance(self, process_code, originator_user_id, url, form_component_value_list=None,
                                        title=None, notifiers=None):
        """
        create custom oa instance
        :param process_code: form ProcessCode
        :param originator_user_id: originator user id
        :param url: Address of the approval sheet details page in the third-party approval system.
        :param form_component_value_list: form component values list
        :param title: instance title
        :param notifiers: notifiers list
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_custom_oa_instance(process_code, originator_user_id, url,
                                                            form_component_value_list, title, notifiers)

    @api.model
    @to_sync
    async def update_custom_oa_instance_state(self, process_instance_id, to_status, result=None, notifiers=None):
        """
        update custom oa instance state
        :param process_instance_id: process instance id
        :param to_status: to status, COMPLETED or TERMINATED
        :param result: result, if to_status is COMPLETED, this is agree or refuse, otherwise is None
        :param notifiers: notifiers list
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.update_custom_oa_instance_state(process_instance_id, to_status, result, notifiers)

    @api.model
    @to_sync
    async def update_custom_oa_instance_state_batch(self, update_process_instance_requests):
        """
        update custom oa instance state batch
        :param update_process_instance_requests: is a list of function update_custom_oa_instance_state's params,
        reference https://open.dingtalk.com/document/orgapp-server/update-the-status-of-multiple-instances-at-a-time-new
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.update_custom_oa_instance_state_batch(update_process_instance_requests)

    @api.model
    @to_sync
    async def create_custom_oa_task(self, process_instance_id, activity_id=None, tasks=None):
        """
        create custom oa process task
        :param process_instance_id: process instance id
        :param activity_id: activity id
        :param tasks: tasks list
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_custom_oa_task(process_instance_id, activity_id, tasks)

    @api.model
    @to_sync
    async def get_custom_oa_tasks(self, user_id, page_number=1, page_size=40, create_before=None):
        """
        get custom oa process tasks
        :param user_id: user dingtalk id
        :param page_number: page number
        :param page_size: page size
        :param create_before: start timestamp when select, the current time cannot exceed one year
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_custom_oa_tasks(user_id, page_number, page_size, create_before)

    @api.model
    @to_sync
    async def update_custom_oa_task_state(self, tasks, process_instance_id=None):
        """
        update custom oa task state batch, reference: https://open.dingtalk.com/document/orgapp-server/update-process-center-task-status
        :param tasks: tasks list
        :param process_instance_id: process instance id
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.update_custom_oa_task_state(tasks, process_instance_id)

    @api.model
    @to_sync
    async def cancel_custom_oa_tasks_batch(self, process_instance_id, activity_id, activity_ids=None):
        """
        cancel custom oa tasks batch, reference: https://open.dingtalk.com/document/orgapp-server/cancel-multiple-oa-approval-tasks
        :param process_instance_id: process instance id
        :param activity_id: ID of the backlog group
        :param activity_ids: ID of the backlog group list
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.cancel_custom_oa_tasks_batch(process_instance_id, activity_id, activity_ids)

    @api.model
    @to_sync
    async def create_or_update_official_oa_template(self, process_code, name, form_components, description=None,
                                                    template_config=None):
        """
        create or update official OA template
        :param process_code: process code
        :param name: template name
        :param form_components: form components list
        :param description: template description
        :param template_config: template global config
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_or_update_official_oa_template(
            process_code, name, form_components, description, template_config
        )

    @api.model
    @to_sync
    async def get_official_oa_form_schemas(self, process_code, app_uuid=None):
        """
        get official OA form schemas
        :param process_code: process code
        :param app_uuid: Application builds quarantine information
        :return: form schemas
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_form_schemas(process_code, app_uuid)

    @api.model
    @to_sync
    async def create_or_update_official_oa_template(self, process_code, name, form_components, description=None,
                                                    template_config=None):
        """
        create or update official oa template
        :param process_code: process code
        :param name: template name
        :param form_components: form components list
        :param description: template description
        :param template_config: template global config
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_or_update_official_oa_template(
            process_code, name, form_components, description, template_config
        )

    @api.model
    @to_sync
    async def get_official_oa_form_schemas(self, process_code, app_uuid=None):
        """
        get official oa form schemas
        :param process_code: process code
        :param app_uuid: Application builds quarantine information
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_form_schemas(process_code, app_uuid)

    @api.model
    @to_sync
    async def get_official_oa_processes_nodes(self, process_code, dept_id, user_id, form_component_values):
        """
        get official oa processes nodes
        :param process_code: process code
        :param dept_id: dingtalk id of the department of the employee who is to send the approval order
        :param user_id: dingtalk id of the user who is to send the approval order
        :param form_component_values: form component values
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_processes_nodes(process_code, dept_id, user_id, form_component_values)

    @api.model
    @to_sync
    async def create_official_oa_instance(self, originator_user_id, process_code, form_component_values, dept_id=None,
                                          microapp_agent_id=None, approvers=None, cc_list=None, cc_position=None,
                                          target_select_actioners=None):
        """
        create official oa instance
        :param originator_user_id: Approval sponsor dingtalk id
        :param process_code: process code
        :param form_component_values: form component values
        :param dept_id: dingtalk id of the department of the employee who is to send the approval order
        :param microapp_agent_id: Application identification AgentId
        :param approvers: A list of approvers specified directly when the approval flow template is not used
        :param cc_list: carbon copy recipients dingtalk id list
        :param cc_position: carbon copy recipients time
        :param target_select_actioners: When using the approval flow template, the mandatory list of optional operators on the node rule in the process prediction result
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_official_oa_instance(
            originator_user_id, process_code, form_component_values, dept_id, microapp_agent_id, approvers, cc_list,
            cc_position, target_select_actioners
        )

    @api.model
    @to_sync
    async def get_official_oa_instance_id_list(self, process_code, start_time, end_time=None, next_token=None,
                                               max_results=20, user_ids=None, statuses=None):
        """
        get official oa instance id list
        :param process_code: process code
        :param start_time: start timestamp
        :param end_time: end timestamp
        :param next_token: page cursor, the first page is not required
        :param max_results: page size, max is 20
        :param user_ids: user dingtalk ids who created the instance
        :param statuses: NEW/RUNNING/COMPLETED/TERMINATED/CANCELED
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_instance_id_list(
            process_code, start_time, end_time, next_token, max_results, user_ids, statuses
        )

    @api.model
    @to_sync
    async def get_official_oa_instance_detail(self, process_instance_id):
        """
        get official oa instance
        :param process_instance_id: process instance id
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_instance_detail(process_instance_id)

    @api.model
    @to_sync
    async def redirect_official_oa_task(self, task_id, to_user_id, operate_user_id, remark=None, action_name=None):
        """
        redirect official oa task
        :param task_id: OA task id
        :param to_user_id: the user dingtalk id to be redirected to
        :param operate_user_id: Operator dingtalk id
        :param remark: remark
        :param action_name: action node name
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.redirect_official_oa_task(
            task_id, to_user_id, operate_user_id, remark, action_name
        )

    @api.model
    @to_sync
    async def get_official_oa_spaces_infos(self, user_id, agent_id=None):
        """
        get official oa spaces infos
        :param user_id: dingtalk user id
        :param agent_id: app agent id
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_spaces_infos(user_id, agent_id)

    @api.model
    @to_sync
    async def create_official_oa_approve_comment(self, process_instance_id, text, comment_user_id, file=None):
        """
        create official oa approve comment
        :param process_instance_id: process instance id
        :param text: comment content
        :param comment_user_id: comment user dingtalk id
        :param file: comment dingtalk file info, reference to https://open.dingtalk.com/document/orgapp-server/add-an-approval-comment-pop
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.create_official_oa_approve_comment(
            process_instance_id, text, comment_user_id, file
        )

    @api.model
    @to_sync
    async def execute_official_oa_task(self, process_instance_id, task_id, result, actioner_user_id, remark=None,
                                       file=None):
        """
        execute official oa task
        :param process_instance_id: process instance id
        :param task_id: task id
        :param result: agree or refuse
        :param actioner_user_id: actioner user dingtalk id
        :param remark: remark
        :param file: dingtalk file info
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.execute_official_oa_task(
            process_instance_id, task_id, result, actioner_user_id, remark, file
        )

    @api.model
    @to_sync
    async def terminate_official_oa_instance(self, process_instance_id, operating_user_id=None, is_system=None,
                                             remark=None):
        """
        terminate official oa instance
        :param process_instance_id: process instance id
        :param operating_user_id: user dingtalk id who terminate instance
        :param remark: remark
        :param is_system: is system terminate
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.terminate_official_oa_instance(
            process_instance_id, operating_user_id, is_system, remark
        )

    @api.model
    @to_sync
    async def get_official_oa_todo_tasks_number(self, user_id):
        """
        get official oa to do tasks number
        :param user_id: who's to do tasks number in select
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_official_oa_todo_tasks_number(user_id)

    @api.model
    @to_sync
    async def get_user_official_oa_tasks(self, user_id, max_results=100, next_token=None):
        """
        get specified user's official oa tasks
        :param user_id: who's to do tasks in select
        :param max_results: page size, max is 100
        :param next_token: page cursor, first page is None
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_user_official_oa_tasks(user_id, max_results, next_token)

    @api.model
    @to_sync
    async def get_user_official_oa_templates(self, user_id):
        """
        get the form templates which user has a manageable approval form in the current enterprise
        :return:
        """
        ding_request = ding_request_instance(self.app_key, self.app_secret)
        return await ding_request.get_user_official_oa_templates(user_id)
