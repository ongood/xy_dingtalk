import base64
import hmac
from urllib import parse

import aiohttp

from .store.token_store import TokenStore


def get_sign(data, key):
    """
    signature for dingtalk request
    :param data:
    :param key:
    """
    sign = base64.b64encode(
        hmac.new(key.encode('utf-8'), str(data).encode('utf-8'), digestmod='SHA256').digest())
    return str(sign, 'utf-8')


def check_response_error(response, error_code=0, error_msg_key='errmsg'):
    if response['errcode'] != error_code:
        raise Exception(f'{response["errcode"]}: {response[error_msg_key]}')


def check_new_response_error(response, error_code_key='code', error_msg_key='message'):
    if response.get(error_code_key) is not None:
        raise Exception(response[error_msg_key])


def join_url(base_url, *args):
    if not args:
        return base_url
    return parse.urljoin(base_url, ''.join(args))


class DingRequest(object):
    url_prefix = 'https://oapi.dingtalk.com'
    new_api_url_prefix = 'https://api.dingtalk.com'

    def __init__(self, app_key, app_secret):
        """
        set Dingtalk app_key and app_secret
        :param app_key: Dingtalk app app_key
        :param app_secret: Dingtalk app app_secret
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.token_store = TokenStore(app_key)

    async def refresh_token(self):
        """
        refresh token if it expires
        :return:
        """
        current_token = self.token_store.get()
        if not current_token:
            token = await self.get_token()
            self.token_store.save(token['token'], token['expires_in'])

    async def latest_token(self):
        """
        get latest token
        :return:
        """
        await self.refresh_token()
        return self.token_store.get()

    @staticmethod
    async def get_response(url, params=None, response_callback=None, **kwargs):
        """
        get response from server
        :param url: url join with url_prefix
        :param params:
        :param response_callback: response callback function
        :return:
        """
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.get(url, params=params, **kwargs) as response:
                return await response_callback(response) if response_callback else await response.json()

    @staticmethod
    async def post_response(url, json, data=None, response_callback=None, **kwargs):
        """
        post response to server, if json is not None, use json, else use data
        :param url: url join with url_prefix
        :param data: json data
        :param json: form data
        :param response_callback: response callback function
        :return:
        """
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.post(url, json=json, data=data, **kwargs) as response:
                return await response_callback(response) if response_callback else await response.json()

    @staticmethod
    async def put_response(url, json, data=None, response_callback=None, **kwargs):
        """
        put response to server, if json is not None, use json, else use data
        :param url: url join with url_prefix
        :param data: json data
        :param json: form data
        :param response_callback: response callback function
        :return:
        """
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.put(url, json=json, data=data, **kwargs) as response:
                return await response_callback(response) if response_callback else await response.json()

    @staticmethod
    async def delete_response(url, params=None, response_callback=None, **kwargs):
        """
        delete response from server
        :param url: url join with url_prefix
        :param params:
        :param response_callback: response callback function
        :return:
        """
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.delete(url, params=params, **kwargs) as response:
                return await response_callback(response) if response_callback else await response.json()

    async def get_token(self):
        """
        get token from server
        :return:
        """
        response = await self.get_response(join_url(self.url_prefix, 'gettoken'), {
            'appkey': self.app_key,
            'appsecret': self.app_secret
        })
        check_response_error(response)
        return {
            'token': response['access_token'],
            'expires_in': response['expires_in']
        }

    async def get_user_access_token(self, app_key, app_secret, temp_auth_code):
        """
        get user access token
        :param app_key: Dingtalk app app_key
        :param app_secret: Dingtalk
        :param temp_auth_code: temporary authorization code
        :return: {"expireIn":7200,"accessToken":"xx","refreshToken":"xx"}
        """
        response = await self.post_response(join_url(self.new_api_url_prefix, 'v1.0/oauth2/userAccessToken'), {
            "clientSecret": app_secret,
            "clientId": app_key,
            "code": temp_auth_code,
            "grantType": "authorization_code"
        })
        if response.get('code') is not None:
            raise Exception(response['message'])
        return response

    async def get_user_info_by_access_token(self, user_access_token, union_id='me'):
        """
        get user info with user access_token
        :param user_access_token: user_access_token, not app access_token
        :param union_id: info whose union_id is this, self is 'me'
        :return:
        """
        response = await self.get_response(
            f'https://api.dingtalk.com/v1.0/contact/users/{union_id}',
            headers={
                'x-acs-dingtalk-access-token': user_access_token
            }
        )
        check_new_response_error(response)
        return response

    async def get_user_info_by_userid(self, userid, language='zh_CN'):
        """
        get user info with userid
        :param userid: userid in dingtalk
        :param language zh_CN or en_US
        :return:
        """
        response = await self.post_response(
            join_url(self.url_prefix, f'topapi/v2/user/get?access_token={await self.latest_token()}'),
            {
                'userid': userid,
                'language': language
            }
        )
        check_response_error(response)
        return response['result']

    async def get_auth_scopes(self):
        """
        get auth scopes
        :return:
        """
        response = await self.get_response(
            join_url(self.url_prefix, f'auth/scopes?access_token={await self.latest_token()}'))
        check_response_error(response)
        return {
            'auth_user_field': response['auth_user_field'],
            'auth_org_scopes': response['auth_org_scopes']
        }

    async def department_listsubid(self, dept_id=None):
        """
        get department listsubid
        :param dept_id: department id
        :return:
        """
        response = await self.post_response(
            join_url(self.url_prefix, f'topapi/v2/department/listsubid?access_token={await self.latest_token()}'), {
                'dept_id': dept_id
            })
        check_response_error(response)
        return response['result']['dept_id_list']

    async def department_detail(self, dept_id, language='zh_CN'):
        """
        get department detail
        :param dept_id: department id in dingtalk
        :param language: language
        :return:
        """
        assert dept_id is not None, 'dept_id is required'
        response = await self.post_response(
            join_url(self.url_prefix, f'topapi/v2/department/get?access_token={await self.latest_token()}'), {
                'dept_id': dept_id,
                'language': language
            })
        check_response_error(response)
        return response['result']

    async def department_users(self, dept_id, cursor=0, size=100, language='zh_CN', contain_access_limit=False):
        """
        get department users
        :param dept_id: department id
        :param cursor: offset
        :param size: size
        :param language: language
        :param contain_access_limit: Whether to return an employee with restricted access
        :return:
        """
        assert dept_id is not None, 'dept_id is required'
        response = await self.post_response(
            join_url(self.url_prefix, f'topapi/v2/user/list?access_token={await self.latest_token()}'), {
                'dept_id': dept_id,
                'cursor': cursor,
                'size': size,
                'language': language,
                'contain_access_limit': contain_access_limit
            })
        check_response_error(response)
        return response['result']

    async def upload_media(self, media_type, media_file, filename):
        """
        upload media
        :param media_type: image, voice, video or file
        :param media_file: media file
        :param filename: media filename
        :return: media_id
        """
        data = aiohttp.FormData()
        data.add_field('type', media_type)
        data.add_field('media', media_file, filename=filename, content_type='application/octet-stream')
        response = await self.post_response(
            join_url(self.url_prefix, f'media/upload?access_token={await self.latest_token()}&type={media_type}'),
            None, data)
        check_response_error(response)
        return response['media_id']

    async def send_message(self, message):
        """
        send message
        :param message: message dict
        :return:
        """
        response = await self.post_response(
            join_url(self.url_prefix,
                     f'topapi/message/corpconversation/asyncsend_v2?access_token={await self.latest_token()}'), message)
        check_response_error(response)
        return {
            'request_id': response['request_id'],
            'task_id': response['task_id']
        }

    # region custom oa approve
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
        assert name is not None, 'name is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, 'v1.0/workflow/processCentres/schemas'), {
                'processCode': process_code,
                'name': name,
                'description': description,
                'formComponents': form_components,
                'processFeatureConfig': process_feature_config
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_custom_oa_process_code(self, name):
        """
        get custom oa process code
        :param name: form name
        :return:
        """
        assert name is not None, 'name is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/schemaNames/processCodes'), {
                'name': name
            }, headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            })
        check_new_response_error(response)
        return response['result']

    async def delete_custom_oa_template(self, process_code, clean_running_task=False):
        """
        delete custom oa template
        :param process_code: form ProcessCode
        :param clean_running_task: Whether to delete the running task
        :return:
        """
        assert process_code is not None, 'process_code is required'
        response = await self.delete_response(
            join_url(self.new_api_url_prefix, f'/v1.0/workflow/processCentres/schemas'), {
                'processCode': process_code,
                'cleanRunningTask': False if clean_running_task == 'false' else True
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            })
        check_new_response_error(response)
        return response['result']

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
        assert process_code is not None, 'process_code is required'
        assert originator_user_id is not None, 'originator_user_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/instances'), {
                'processCode': process_code,
                'originatorUserId': originator_user_id,
                'formComponentValueList': form_component_value_list,
                'title': title,
                'url': url,
                'notifiers': notifiers
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def update_custom_oa_instance_state(self, process_instance_id, to_status, result=None, notifiers=None):
        """
        update custom oa instance state
        :param process_instance_id: process instance id
        :param to_status: to status, COMPLETED or TERMINATED
        :param result: result, if to_status is COMPLETED, this is agree or refuse, otherwise is None
        :param notifiers: notifiers list
        :return:
        """
        assert process_instance_id is not None, 'process_instance_id is required'
        assert to_status is not None, 'to_status is required'
        response = await self.put_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/instances'), {
                'processInstanceId': process_instance_id,
                'status': to_status,
                'result': result,
                'notifiers': notifiers
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['success']

    async def update_custom_oa_instance_state_batch(self, update_process_instance_requests):
        """
        update custom oa instance state batch
        :param update_process_instance_requests: is a list of function update_custom_oa_instance_state's params
        :return:
        """
        assert len(
            update_process_instance_requests) > 0, "update_process_instance_requests's length must be greater than 0"
        response = await self.put_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/instances/batch'), {
                'updateProcessInstanceRequests': update_process_instance_requests
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['success']

    async def create_custom_oa_task(self, process_instance_id, activity_id=None, tasks=None):
        """
        create custom oa process task
        :param process_instance_id: process instance id
        :param activity_id: activity id
        :param tasks: tasks list
        :return:
        """
        assert process_instance_id is not None, 'process_instance_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/tasks'), {
                'processInstanceId': process_instance_id,
                'activityId': activity_id,
                'tasks': tasks
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return {
            'result': response['result'],
            'success': response['success']
        }

    async def get_custom_oa_tasks(self, user_id, page_number=1, page_size=40, create_before=None):
        """
        get custom oa process tasks
        :param user_id: user id
        :param page_number: page number
        :param page_size: page size
        :param create_before: create before
        :return:
        """
        assert user_id is not None, 'user_id is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/todoTasks'), {
                'userId': user_id,
                'pageNumber': page_number,
                'pageSize': page_size,
                'createBefore': create_before
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return {
            'requestId': response['requestId'],
            'taskPage': response['taskPage']
        }

    async def update_custom_oa_task_state(self, tasks, process_instance_id=None):
        """
        update custom oa task state batch, reference: https://open.dingtalk.com/document/orgapp-server/update-process-center-task-status
        :param tasks: tasks list
        :param process_instance_id: process instance id
        :return:
        """
        assert len(tasks) > 0, "tasks's length must be greater than 0"
        response = await self.put_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/tasks'), {
                'tasks': tasks,
                'processInstanceId': process_instance_id
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['success']

    async def cancel_custom_oa_tasks_batch(self, process_instance_id, activity_id, activity_ids=None):
        """
        cancel custom oa tasks batch, reference: https://open.dingtalk.com/document/orgapp-server/cancel-multiple-oa-approval-tasks
        :param process_instance_id: process instance id
        :param activity_id: ID of the backlog group
        :param activity_ids: ID of the backlog group list
        :return:
        """
        assert process_instance_id is not None, 'process_instance_id is required'
        assert activity_id is not None, 'activity_id is required'
        response = await self.delete_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processCentres/tasks/cancel'), {
                'processInstanceId': process_instance_id,
                'activityId': activity_id,
                'activityIds': activity_ids,
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['success']

    # endregion

    # region official OA
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
        assert name is not None, 'name is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/forms'), {
                'processCode': process_code,
                'name': name,
                'description': description,
                'formComponents': form_components,
                'templateConfig': template_config
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_official_oa_form_schemas(self, process_code, app_uuid=None):
        """
        get official oa form schemas
        :param process_code: process code
        :param app_uuid: Application builds quarantine information
        :return:
        """
        assert process_code is not None, 'process_code is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/forms/schemas/processCodes'), {
                'processCode': process_code,
                'appUuid': app_uuid
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_official_oa_processes_nodes(self, process_code, dept_id, user_id, form_component_values):
        """
        get official oa processes nodes
        :param process_code: process code
        :param dept_id: dingtalk id of the department of the employee who is to send the approval order
        :param user_id: dingtalk id of the user who is to send the approval order
        :param form_component_values: form component values
        :return:
        """
        assert process_code is not None, 'process_code is required'
        assert dept_id is not None, 'dept_id is required'
        assert user_id is not None, 'user_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processes/forecast'), {
                'processCode': process_code,
                'deptId': dept_id,
                'userId': user_id,
                'formComponentValues': form_component_values
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

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
        assert originator_user_id is not None, 'originator_user_id is required'
        assert process_code is not None, 'process_code is required'
        assert form_component_values is not None, 'form_component_values is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processInstances'), {
                'originatorUserId': originator_user_id,
                'deptId': dept_id,
                'processCode': process_code,
                'formComponentValues': form_component_values,
                'microappAgentId': microapp_agent_id,
                'approvers': approvers,
                'ccList': cc_list,
                'ccPosition': cc_position,
                'targetSelectActioners': target_select_actioners
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['instanceId']

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
        assert process_code is not None, 'process_code is required'
        assert start_time is not None, 'start_time is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processes/instanceIds/query'), {
                'processCode': process_code,
                'startTime': start_time,
                'endTime': end_time,
                'nextToken': next_token,
                'maxResults': max_results,
                'userIds': user_ids,
                'statuses': statuses
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_official_oa_instance_detail(self, process_instance_id):
        """
        get official oa instance
        :param process_instance_id: process instance id
        :return:
        """
        assert process_instance_id is not None, 'process_instance_id is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processInstances'), {
                'processInstanceId': process_instance_id
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

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
        assert task_id is not None, 'task_id is required'
        assert to_user_id is not None, 'to_user_id is required'
        assert operate_user_id is not None, 'operate_user_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/tasks/redirect'), {
                'taskId': task_id,
                'toUserId': to_user_id,
                'operateUserId': operate_user_id,
                'remark': remark,
                'actionName': action_name
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_official_oa_spaces_infos(self, user_id, agent_id=None):
        """
        get official oa spaces infos
        :param user_id: dingtalk user id
        :param agent_id: app agent id
        :return:
        """
        assert user_id is not None, 'user_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processInstances/spaces/infos/query'), {
                'userId': user_id,
                'agentId': agent_id
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def create_official_oa_approve_comment(self, process_instance_id, text, comment_user_id, file=None):
        """
        create official oa approve comment
        :param process_instance_id: process instance id
        :param text: comment content
        :param comment_user_id: comment user dingtalk id
        :param file: comment dingtalk file info, reference to https://open.dingtalk.com/document/orgapp-server/add-an-approval-comment-pop
        :return:
        """
        assert process_instance_id is not None, 'process_instance_id is required'
        assert text is not None, 'text is required'
        assert comment_user_id is not None, 'comment_user_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processInstances/comments'), {
                'processInstanceId': process_instance_id,
                'text': text,
                'commentUserId': comment_user_id,
                'file': file
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

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
        assert process_instance_id is not None, 'process_instance_id is required'
        assert task_id is not None, 'task_id is required'
        assert result == 'agree' or result == 'refuse', 'result must be agree or refuse'
        assert actioner_user_id is not None, 'actioner_user_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processInstances/execute'), {
                'processInstanceId': process_instance_id,
                'taskId': task_id,
                'result': result,
                'actionerUserId': actioner_user_id,
                'remark': remark,
                'file': file
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

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
        assert process_instance_id is not None, 'process_instance_id is required'
        response = await self.post_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processInstances/terminate'), {
                'processInstanceId': process_instance_id,
                'operatingUserId': operating_user_id,
                'remark': remark,
                'isSystem': is_system
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_official_oa_todo_tasks_number(self, user_id):
        """
        get official oa to do tasks number
        :param user_id: who's to do tasks number in select
        :return:
        """
        assert user_id is not None, 'user_id is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processes/todoTasks/numbers'), {
                'userId': user_id
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_user_official_oa_tasks(self, user_id, max_results=100, next_token=None):
        """
        get specified user's official oa tasks
        :param user_id: who's to do tasks in select
        :param max_results: page size, max is 100
        :param next_token: page cursor, first page is None
        :return:
        """
        assert user_id is not None, 'user_id is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processes/userVisibilities/templates'), {
                'userId': user_id,
                'maxResults': max_results,
                'nextToken': next_token
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']

    async def get_user_official_oa_templates(self, user_id):
        """
        get the form templates which user has a manageable approval form in the current enterprise
        :return:
        """
        assert user_id is not None, 'user_id is required'
        response = await self.get_response(
            join_url(self.new_api_url_prefix, '/v1.0/workflow/processes/managements/templates'), {
                'userId': user_id
            },
            headers={
                'x-acs-dingtalk-access-token': await self.latest_token()
            }
        )
        check_new_response_error(response)
        return response['result']
# endregion


def ding_request_instance(app_key, app_secret):
    """
    if you want to use custom DingRequest class or Store class, you can set monkey patch to this function
    :param app_key:
    :param app_secret:
    :return:
    """
    return DingRequest(app_key, app_secret)
