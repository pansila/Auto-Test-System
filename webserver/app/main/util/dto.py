from sanic_openapi import doc

class json_response:
    code = doc.Integer()
    message = doc.String()
    data = doc.JsonBody()

class UserDto:
    class account:
        password = doc.String()
        email = doc.String()
        username = doc.String()
        introduction = doc.String()
        region = doc.String()
    class user_list(json_response):
        class _user_list:
            class _user_info:
                user_id = doc.String(description='User identifier')
                email = doc.String()
                username = doc.String()
                introduction = doc.String()
                region = doc.String()
            user = doc.List(_user_info)
        data = doc.Object(_user_list)
    class user_info(user_list._user_list._user_info):
        roles = doc.List(doc.String())
        registered_on = doc.Integer(description='The registered date in form of timestamp from the epoch in milliseconds')
    class avatar:
        type = doc.String()
    class password:
        password = doc.String()
    class password_update:
        oldPassword = doc.String(required=True)
        newPassword = doc.String(required=True)
    class user_avatar(json_response):
        class _user_avatar:
            type = doc.String()
            data = doc.String(description='the file content being base64 encoded')
        data = doc.Object(_user_avatar)

class AuthDto:
    class user_auth:
        email = doc.String(required=True, description='The email address')
        password = doc.String(required=True, description='The user password ')

class CertDto:
    class cert_key:
        test = doc.String(description='test')

class SettingDto:
    pass

class TestDto:
    class test_cases(json_response):
        class _test_cases:
            test_cases = doc.List(doc.String())
            test_suite = doc.String()
        data = doc.Object(_test_cases)
    class test_suite_list(json_response):
        class _test_suite_list:
            class _test_suite:
                id = doc.String()
                test_suite = doc.String()
                path = doc.String()
                test_cases = doc.List(doc.String())
                variables = doc.JsonBody()
                author = doc.String()
            test_suites = doc.List(_test_suite)
        data = doc.Object(_test_suite_list)

class organization_team:
    organization = doc.String(required=True, description='The organization id')
    team = doc.String(description='The team id')

class TaskDto:
    class task_query(organization_team):
        start_date = doc.Integer(description='The start date in form of timestamp from the epoch in milliseconds')
        end_date = doc.Integer(description='The end date in form of timestamp from the epoch in milliseconds')
    class task_id(organization_team):
        task_id = doc.String(required=True, description='The task id')
    class task_result_files(json_response):
        class _task_result_files:
            class _file_list:
                label = doc.String(description='The file name')
                type = doc.String(description='The file type: file or directory')
                children = doc.List(doc.JsonBody())
            files = doc.List(_file_list, description='The test script file list')
        data = doc.Object(_task_result_files)

    class run_task(json_response):
        class _run_task:
            running = doc.List(doc.String())
            failed = doc.List(doc.String())
            succeeded = doc.List(doc.String())
        data = doc.Object(_run_task)
    class task_update(task_id):
        comment = doc.String(required=True, description='The task comment')
    class task_cancel(task_id):
        endpoint_uid = doc.String(description='The endpoint uid that is running the test')
        priority = doc.Integer(description='The priority of the task')
    class task_stat_list(json_response):
        class _task_stat_list:
            class _task_stat_of_a_day:
                succeeded = doc.Integer(description='The count of tasks ran successfully in the day')
                failed = doc.Integer(description='The count of tasks failed to run in the day')
                running = doc.Integer(description='The count of tasks running right now')
                waiting = doc.Integer(description='The count of tasks waiting right now')
            stats = doc.List(_task_stat_of_a_day)
        data = doc.Object(_task_stat_list)
    class task(organization_team):
        test_suite = doc.String(required=True, description='The test suite name')
        path = doc.String(required=True, description='The test suite\'s path name')
        endpoint_list = doc.List(doc.String(description='The endpoints to run the test'))
        priority = doc.Integer(description='The priority of the task(larger number means higher importance)')
        parallelization = doc.Boolean() #default=False)
        variables = doc.List(doc.String())
        test_cases = doc.List(doc.String())
        upload_dir = doc.String(description='The directory id of the upload files')

class TestResultDto:
    class test_result_query:
        page = doc.Integer(description='The page number of the whole test report list')
        limit = doc.Integer(description='The item number of a page')
        title = doc.String(description='The test suite name')
        priority = doc.Integer(description='The priority of the task')
        endpoint = doc.String(description='The endpoint that runs the test')
        sort = doc.String(description='The sort field') #default='-run_date'
        start_date = doc.String(description='The start date')
        end_date = doc.String(description='The end date')

    class test_report(json_response):
        class _test_report:
            class _test_report_summary:
                id = doc.String(description='The task id')
                test_id = doc.String(description='The test id of the associated task')
                test_suite = doc.String(description='The test suite name')
                testcases = doc.List(doc.String())
                comment = doc.String()
                priority = doc.Integer(description='The priority of the task')
                run_date = doc.Integer(description='The date in form of timestamp from the epoch in milliseconds')
                tester = doc.String()
                status = doc.String()
            test_reports = doc.List(_test_report_summary)
            total = doc.Integer()
        data = doc.Object(_test_report)
    class task_id:
        task_id = doc.String(required=True, description='The task id')
    class record_test_result(task_id):
        test_case = doc.String(required=True, description='The test case of a test suite')
    class test_result:
        test_date = doc.DateTime()
        duration = doc.Integer()
        summary = doc.String()
        status = doc.String() #default='FAIL')
        more_result = doc.JsonBody()

class TaskResourceDto:
    class task_id(organization_team):
        task_id = doc.String(required=True, description='The task id')
    class task_resource(organization_team):
        resource_id = doc.String(description='The directory id to accommodate uploaded files')
        retrigger_task = doc.String(description='The task id to retrigger')
        file = doc.List(doc.String())
    class task_resource_response(json_response):
        class _task_resource_resp:
            resource_id = doc.String()
        data = doc.Object(_task_resource_resp)
    class task_resource_file_list(json_response):
        class _task_resource_file_list:
            class _file_list:
                label = doc.String(description='The file name')
                type = doc.String(description='The file type: file or directory')
                children = doc.List(doc.JsonBody())

            files = doc.List(doc.Object(_file_list), description='The test script file list')
        data = doc.Object(_task_resource_file_list)

class EndpointDto:
    class endpoint_query(organization_team):
        page = doc.Integer(description='The page number of the whole test report list') #default=1, 
        limit = doc.Integer(description='The item number of a page') #default=10, 
        title = doc.String(description='The test suite name')
        forbidden = doc.String(description='Get endpoints that are forbidden to connect')
        unauthorized = doc.String(description='Get endpoints that have not authorized to connect')

    class endpoint_list(json_response):
        class _endpoint_list:
            class _endpoint_item:
                endpoint_uid = doc.String()
                name = doc.String()
                status = doc.String()
                enable = doc.Boolean()
                last_run = doc.Integer(description="Timestamp in milliseconds, 0 if not run yet")
                tests = doc.List(doc.String())
                test_refs = doc.List(doc.String())
                endpoint_uid = doc.String()
            endpoints = doc.List(doc.Object(_endpoint_item), description='endpoints of the current queried page')
            total = doc.Integer(description='total number of the queried the endpoints')
        data = doc.Object(_endpoint_list)
    class endpoint_uid(organization_team):
        endpoint_uid = doc.String()
    class endpoint(organization_team):
        endpoint_uid = doc.String(name='uid', description='The endpoint\'s uid')
        tests = doc.List(doc.String(), description='The tests that the endpoint supports')
        endpoint_name = doc.String()
        enable = doc.Boolean() #default=False)
    class queuing_task_list(json_response):
        class _queuing_task_list:
            class _queuing_tasks:
                class _queuing_task:
                    endpoint = doc.String(description="The endpoint name")
                    endpoint_uid = doc.String(description="The endpoint uid")
                    priority = doc.Integer()
                    task = doc.String(description="The test name")
                    task_id = doc.String(description="The task id")
                    status = doc.String()
                endpoint_uid = doc.String(description="The endpoint uid")
                endpoint = doc.String(description="The endpoint name")
                priority = doc.Integer()
                waiting = doc.Integer()
                status = doc.String()
                tasks = doc.List(doc.Object(_queuing_task))
            task_queues = doc.List(_queuing_tasks)
        data = doc.Object(_queuing_task_list)
    class endpoint_online_check(json_response):
        class _endpoint_online_check:
            status = doc.Boolean()
        data = doc.Object(_endpoint_online_check)

class ScriptDto:
    class update_script(organization_team):
        file = doc.String(description='Path to the queried file')
        script_type = doc.String(description='File type {test_scripts | test_libraries}')
        new_name = doc.String(description='New file name if want to rename')
        content = doc.String(description='The file content')

    class script_query(organization_team):
        file = doc.String(description='Path to the queried file')
        script_type = doc.String(description='File type {test_scripts | test_libraries}')

    class upload_scripts(organization_team):
        script_type = doc.String(description='File type {test_scripts | test_libraries}')
        file = doc.File()

    class script_file_list(json_response):
        class _script_file_list:
            class _file_list:
                label = doc.String(description='The file name')
                type = doc.String(description='The file type: file or directory')
                children = doc.List(doc.JsonBody())

            test_scripts = doc.List(doc.Object(_file_list), description='The test script file list')
            test_libraries = doc.List(doc.Object(_file_list), description='The python script file list')
        data = doc.Object(_script_file_list)

class OrganizationDto:
    class organization_list(json_response):
        class _organization_list:
            class _organization:
                label = doc.String(description='The organization name')
                owner = doc.String(description='The organization owner\'s name')
                owner_email = doc.String(description='The organization owner\'s email')
                personal = doc.Boolean(description='The organization is of person') #, default=False)
                value = doc.String(description='The organization ID')
            organizations = doc.List(_organization)
        data = doc.Object(_organization_list)

    class new_organization:
        name = doc.String(description='The organization name')

    class organization_id:
        organization_id = doc.String(name='organization_id', description='The organization ID')

    # we could have inherited the model organization, but swagger UI has a problem to show it correctly, thus we embed organization definition here.
    class organization_team_list(json_response):
        class _organization_team_list:
            class _organization_team:
                class _team:
                    label = doc.String(description='The team name')
                    owner = doc.String(description='The team owner\'s name')
                    owner_email = doc.String(description='The team owner\'s email')
                    value = doc.String(description='The team ID')
                label = doc.String(description='The organization name')
                owner = doc.String(description='The organization owner\'s name')
                owner_email = doc.String(description='The organization owner\'s email')
                value = doc.String(description='The organization ID')
                children = doc.List(doc.Object(_team))
            organization_team = doc.List(_organization_team)
        data = doc.Object(_organization_team_list)

    class user_list(json_response):
        class _user_list:
            class _user:
                label = doc.String(description='The user name')
                email = doc.String(description='The user email')
                value = doc.String(description='The user ID')
            users = doc.List(_user)
        data = doc.Object(_user_list)

    class transfer_ownership(organization_id):
        new_owner = doc.String(description='The new owner\'s ID')

    class organization_avatar(json_response):
        class _organization_avatar:
            type = doc.String()
            data = doc.String(description='the file content being base64 encoded')
        data = doc.Object(_organization_avatar)

class TeamDto:
    class team_list(json_response):
        class _team_list:
            class _team:
                label = doc.String(description='The team name')
                owner = doc.String(description='The team owner\'s name')
                owner_email = doc.String(description='The team owner\'s email')
                organization_id = doc.String(description='The ID of the organization that the team belongs to')
                value = doc.String(description='The team ID')
            teams = doc.List(_team)
        data = doc.Object(_team_list)

    class new_team:
        name = doc.String(description='The team name')
        organization_id = doc.String(description='The organization ID')

    class team_id:
        team_id = doc.String(description='The team ID')

    class user:
        label = doc.String(description='The user name')
        email = doc.String(description='The user email')
        value = doc.String(description='The user ID')

    class team_avatar(json_response):
        class _team_avatar:
            type = doc.String()
            data = doc.String(description='the file content being base64 encoded')
        data = doc.Object(_team_avatar)

    class user_list(json_response):
        class _user_list:
            class _user:
                label = doc.String(description='The user name')
                email = doc.String(description='The user email')
                value = doc.String(description='The user ID')
            users = doc.List(_user)
        data = doc.Object(_user_list)


class StoreDto:
    class package_query:
        page = doc.Integer()
        limit = doc.Integer()
        title = doc.String()
        proprietary = doc.String()
        package_type = doc.String()

    class package_info_query:
        name = doc.String()
        proprietary = doc.String()
        package_type = doc.String()
        version = doc.String()

    class package_description(json_response):

        class _package_description:
            description = doc.String()
        data = doc.Object(_package_description)

    class package_star(json_response):

        class _package_star:
            stars = doc.Integer()
        data = doc.Object(_package_star)

    class delete_package(organization_team):
        file = doc.String(description='Path to the queried file')

    class upload_package(organization_team):
        proprietary = doc.String()
        package_type = doc.String()
        file = doc.File()

    class package_list(json_response):
        class _package_list:
            class _package_summary:
                name = doc.String()
                summary = doc.String()
                description = doc.String()
                stars = doc.Integer()
                download_times = doc.Integer()
                package_type = doc.String()
                versions = doc.List(doc.String())
                upload_date = doc.Integer(description='The upload date in form of timestamp from the epoch in milliseconds')
            packages = doc.List(doc.Object(_package_summary))
            total = doc.Integer()
        data = doc.Object(_package_list)

class PypiDto:
    pass

class DocDto:
    class doc_roots(json_response):
        class _doc_roots:
            class __doc_roots:
                value = doc.Integer(description='the item index')
                label = doc.String(description='the path\'s value')
            paths = doc.List(doc.Object(__doc_roots))
        data = doc.Object(_doc_roots)

    class doc_history(json_response):
        class _doc_history:
            class __doc_history:
                title = doc.String()
                revision = doc.String()
                description = doc.String()
            history = doc.List(doc.Object(__doc_history))
        data = doc.Object(_doc_history)

    class doc_pictures(json_response):
        class _doc_pictures:
            class __doc_pictures:
                name = doc.String()
                data = doc.String()
                type = doc.String()
                size = doc.Integer()
            file_list = doc.List(doc.Object(__doc_pictures))
        data = doc.Object(_doc_pictures)

    class doc_content(json_response):
        class _doc_content:
            content = doc.String()
            locked = doc.Boolean()
        data = doc.Object(_doc_content)

    class doc_query:
        proprietary = doc.Boolean()
        language = doc.String()
        path = doc.String()