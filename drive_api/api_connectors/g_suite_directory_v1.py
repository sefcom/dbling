from apiclient import discovery

from util import print_json


class GSuiteDirectoryAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google

        https://developers.google.com/admin-sdk/directory/v1/quickstart/python

        :param http: http object
        """
        self.service = discovery.build('admin', 'directory_v1', http=http)

    def test(self):
        """
        example method from Google API quickstart page

        https://developers.google.com/admin-sdk/directory/v1/quickstart/python

        :return: nothing
        """
        results = self.service.users().list(customer='my_customer', maxResults=10, orderBy='email').execute()
        users = results.get('users', [])

        if not users:
            print('No users in the domain.')
        else:
            print('Users:')
            for user in users:
                print('{0} ({1})'.format(user['primaryEmail'], user['name']['fullName']))

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

    def list_users_chrome_os_device(self, customer_id):
        """
        Lists all chromeos_devices owned by a customer.

        https://developers.google.com/admin-sdk/directory/v1/reference/chromeosdevices/list

        :param customer_id: The unique ID for the customer's G Suite account.
        :return: JSON
        """
        devices = self.service.chromeosdevices().list(customerId=customer_id).execute()
        return devices

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

    def get_all(self):
        """
        Testing method

        :return: Nothing
        """
        if True:
            print_json(self.get_all_users('adamdoupe.com'))
