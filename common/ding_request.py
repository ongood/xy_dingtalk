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
        assert len(form_components) > 0, "form_components's length must be greater than 0"
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
        assert len(form_components) > 0, "form_components's length must be greater than 0"
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
    # endregion


def ding_request_instance(app_key, app_secret):
    """
    if you want to use custom DingRequest class or Store class, you can set monkey patch to this function
    :param app_key:
    :param app_secret:
    :return:
    """
    return DingRequest(app_key, app_secret)
