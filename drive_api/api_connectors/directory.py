# -*- coding: utf-8 -*-

from api_connectors.google import GoogleAPI


class DirectoryAPI(GoogleAPI):

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
        """
        Gets information for a single user specified by their email

        https://developers.google.com/admin-sdk/directory/v1/reference/users/get

        :param user_email: user's email
        :return: JSON
        """
        user = self.service.users().get(userKey=user_email).execute()
        return user

    def get_all_users(self, domain_name):
        """
        Returns all users in the domain

        https://developers.google.com/admin-sdk/directory/v1/reference/users/list

        :param domain_name: the name of the domain
        :return: JSON
        """
        users = self.service.users().list(domain=domain_name).execute()
        return users

    def get_chrome_os_devices_properties(self, customer_id, device_id):
        """
        Get data pertaining to a single ChromeOS device

        https://developers.google.com/admin-sdk/directory/v1/reference/chromeosdevices/get

        :param customer_id: The unique ID for the customer's G Suite account
        :param device_id: unique ID for the device.
        :return: JSON
        """
        device_info = self.service.chromeosdevices().get(customerId=customer_id, deviceId=device_id).execute()
        return device_info

    def list_customers_mobile_devices_properties(self, customer_id):
        """
        Gets list of mobile devices owned by a customer.

        https://developers.google.com/admin-sdk/directory/v1/reference/mobiledevices/list

        :param customer_id: The unique ID for the customer's G Suite account
        :return: JSON
        """
        mobiles = self.service.mobiledevices().list(customerId=customer_id).execute()
        return mobiles

    def get_mobile_devices_properties(self, customer_id, resource_id):
        """
        Get data pertaining to a single mobile device

        https://developers.google.com/admin-sdk/directory/v1/reference/mobiledevices/get

        :param customer_id: The unique ID for the customer's G Suite account
        :param resource_id: The unique ID the API service uses to identify the mobile device.
        :return: JSON
        """
        mobile_info = self.service.mobiledevices().get(customerId=customer_id, resourceId=resource_id).execute()
        return mobile_info

    def suspend_user_account(self, user_email):
        """
        Suspends an user's account

        https://developers.google.com/admin-sdk/directory/v1/reference/users/update
        https://developers.google.com/admin-sdk/directory/v1/guides/manage-users

        :param user_email: Email for the user to be suspended
        :return: JSON
        """
        request_body = {'suspended': True}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info

    def unsuspend_user_account(self, user_email):
        """
        Un-suspends a user's account

        https://developers.google.com/admin-sdk/directory/v1/reference/users/update
        https://developers.google.com/admin-sdk/directory/v1/guides/manage-users

        :param user_email: Email for the user to be un-suspended
        :return: JSON
        """
        request_body = {'suspended': False}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info
