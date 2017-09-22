# -*- coding: utf-8 -*-

from api_connectors.google import GoogleAPI
from const import PAGE_SIZE
from util import print_json


class ReportsAPI(GoogleAPI):
    """Class to interact with G Suite Admin Reports APIs.

    Documentation for the Python API:
    - https://developers.google.com/resources/api-libraries/documentation/admin/reports_v1/python/latest/

    See also:
    https://developers.google.com/admin-sdk/reports/v1/quickstart/python
    """

    _service_name = 'admin'
    _version = 'reports_v1'

    def activity(self, user_key='all', app_name=None, **kwargs):
        """Return the last 180 days of activities.

        https://developers.google.com/admin-sdk/reports/v1/reference/activities/list

        The ``application_name`` parameter specifies which events are to be
        retrieved. The possible values include:

        - ``admin`` – The Admin console application's activity reports return
          account information about different types of `administrator activity
          events
          <https://developers.google.com/admin-sdk/reports/v1/reference/activity-ref-appendix-a/admin-event-names.html>`_.
        - ``calendar`` – The G Suite Calendar application's activity reports
          return information about various `Calendar activity events
          <https://developers.google.com/admin-sdk/reports/v1/reference/activity-ref-appendix-a/calendar-event-names>`_.
        - ``drive`` – The Google Drive application's activity reports return
          information about various `Google Drive activity events
          <https://developers.google.com/admin-sdk/reports/v1/reference/activity-ref-appendix-a/drive-event-names>`_.
          The Drive activity report is only available for G Suite Business
          customers.
        - ``groups`` – The Google Groups application's activity reports return
          information about various `Groups activity events
          <https://developers.google.com/admin-sdk/reports/v1/reference/activity-ref-appendix-a/groups-event-names>`_.
        - ``gplus`` – The Google+ application's activity reports return
          information about various `Google+ activity events
          <https://developers.google.com/admin-sdk/reports/v1/appendix/activity/gplus>`_.
        - ``login`` – The G Suite Login application's activity reports return
          account information about different types of `Login activity events
          <https://developers.google.com/admin-sdk/reports/v1/reference/activity-ref-appendix-a/login-event-names.html>`_.
        - ``mobile`` – The G Suite Mobile Audit activity report return
          information about different types of `Mobile Audit activity events
          <https://developers.google.com/admin-sdk/reports/v1/reference/appendix/mobile>`_.
        - ``rules`` – The G Suite Rules activity report return information
          about different types of `Rules activity events,
          <https://developers.google.com/admin-sdk/reports/v1/appendix/activity/rules>`_.
        - ``token`` – The G Suite Token application's activity reports return
          account information about different types of `Token activity events
          <https://developers.google.com/admin-sdk/reports/v1/reference/activity-ref-appendix-a/token-event-names.html>`_.

        :param str user_key: The value can be ``'all'``, which returns all
            administrator information, or a ``userKey``, which represents a
            user's unique G Suite profile ID or the primary email address of
            a person or entity.
        :param str app_name: Name of application from the list above. If set
            to ``None``, data will be retrieved from *all* the applications
            listed above.
        :return: JSON
        """
        args = {
            'userKey': user_key,
            # 'applicationName': application_name,
            'maxResults': PAGE_SIZE,  # Accepted range is [1, 1000]
        }
        data = {}

        # If no application was specified, just get everything
        all_apps = ('admin', 'calendar', 'drive', 'groups', 'gplus', 'login', 'mobile', 'rules', 'token')
        if app_name is None:
            app_name = all_apps
        else:
            app_name = [app_name]

        for app in app_name:
            items = []
            page_token = None
            while True:
                act = self.service.activities().list(applicationName=app, pageToken=page_token, **args).execute()
                page_token = act.get('nextPageToken')
                items += act.get('items', [])

                if page_token is None:
                    break

            data[app] = items

        print_json(data)
        raise EnvironmentError
        return items

    # Not useful for this project
    def get_customer_usage_reports(self, date, customer_id=False):
        """Get customer usage reports.

        https://developers.google.com/admin-sdk/reports/v1/reference/customerUsageReports/get

        :param date:
        :param customer_id:
        :return: JSON
        """
        if not customer_id:
            report = self.service.customerUsageReports().get(date=date).execute()
        else:
            report = self.service.activities().list().execute()
        return report

    # Not useful for this project
    def get_user_usage_report(self, date, user_key='all'):
        """Get user usage report.

        https://developers.google.com/admin-sdk/reports/v1/reference/userUsageReport/get

        :param date:
        :param user_key:
        :return: JSON
        """
        report = self.service.userUsageReport().get(date=date, userKey=user_key).execute()
        return report


class DirectoryAPI(GoogleAPI):
    """Class to interact with G Suite Admin Directory APIs.

    Documentation for the Python API:
    - https://developers.google.com/resources/api-libraries/documentation/admin/directory_v1/python/latest/

    See also:
    https://developers.google.com/admin-sdk/directory/v1/quickstart/python
    """

    _service_name = 'admin'
    _version = 'directory_v1'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def list_chromeos_devices(self, fields='*'):
        """List up to 100 Chrome OS devices in the organization.

        API:
        https://developers.google.com/resources/api-libraries/documentation/admin/directory_v1/python/latest/admin_directory_v1.chromeosdevices.html

        Reference:
        https://developers.google.com/admin-sdk/directory/v1/reference/chromeosdevices/list

        :param str fields: Comma-separated list of metadata fields to request.
        :return: The list of Chrome OS devices. See one of the documentation
            links above for the format of the return value.
        :rtype: list
        """
        items = []
        page_token = None
        args = {'customerId': self.customer_id,
                'projection': 'FULL',
                'fields': fields}

        while True:
            dev_set = self.service.chromeosdevices().list(pageToken=page_token, **args).execute()
            page_token = dev_set.get('nextPageToken')
            items += dev_set.get('chromeosdevices', [])

            if page_token is None:
                break
        return items

    def get_user(self, user_email):
        """Get information for a single user specified by their email.

        https://developers.google.com/admin-sdk/directory/v1/reference/users/get

        :param str user_email: user's email
        :return: JSON
        """
        user = self.service.users().get(userKey=user_email).execute()
        return user

    def get_all_users(self, domain_name):
        """Return all users in the domain.

        https://developers.google.com/admin-sdk/directory/v1/reference/users/list

        :param str domain_name: the name of the domain
        :return: JSON
        """
        users = self.service.users().list(domain=domain_name).execute()
        return users

    def get_chrome_os_devices_properties(self, device_id):
        """Get data pertaining to a single ChromeOS device.

        https://developers.google.com/admin-sdk/directory/v1/reference/chromeosdevices/get

        :param str device_id: unique ID for the device.
        :return: JSON
        """
        device_info = self.service.chromeosdevices().get(customerId=self.customer_id, deviceId=device_id).execute()
        return device_info

    def list_customers_mobile_devices_properties(self):
        """Get a list of mobile devices.

        https://developers.google.com/admin-sdk/directory/v1/reference/mobiledevices/list

        :return: JSON
        """
        mobiles = self.service.mobiledevices().list(customerId=self.customer_id).execute()
        return mobiles

    def get_mobile_devices_properties(self, resource_id):
        """Get data pertaining to a single mobile device.

        https://developers.google.com/admin-sdk/directory/v1/reference/mobiledevices/get

        :param str resource_id: The unique ID the API service uses to identify
            the mobile device.
        :return: JSON
        """
        mobile_info = self.service.mobiledevices().get(customerId=self.customer_id, resourceId=resource_id).execute()
        return mobile_info

    def suspend_user_account(self, user_email):
        """Suspend an user's account.

        https://developers.google.com/admin-sdk/directory/v1/reference/users/update
        https://developers.google.com/admin-sdk/directory/v1/guides/manage-users

        :param str user_email: Email for the user to be suspended.
        :return: JSON
        """
        request_body = {'suspended': True}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info

    def unsuspend_user_account(self, user_email):
        """Un-suspend a user's account.

        https://developers.google.com/admin-sdk/directory/v1/reference/users/update
        https://developers.google.com/admin-sdk/directory/v1/guides/manage-users

        :param str user_email: Email for the user to be un-suspended.
        :return: JSON
        """
        request_body = {'suspended': False}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info
