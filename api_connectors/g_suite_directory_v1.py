from util import print_json
from apiclient import discovery


class GSuiteDirectoryAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google
        :param http: http object
        """
        self.service = discovery.build('admin', 'directory_v1', http=http)

    def test(self):
        """
        example method from Google API quickstart page
        :return:
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
        :param user_email: user's email
        :return: JSON
        """
        user = self.service.users().get(userKey=user_email).execute()
        return user

    def get_all_users(self, domain_name):
        """
        Returns all users in the domain
        :param domain_name: the name of the domain
        :return: JSON
        """
        users = self.service.users().list(domain=domain_name).execute()
        return users

    def list_users_chromeos_device(self, customer_id):
        """
        Lists all chromeos_devices owned by a customer.
        :param customer_id: The unique ID for the customer's G Suite account.
        :return: JSON
        """
        devices = self.service.chromeosdevices().list(customerId=customer_id).execute()
        return devices

    def get_chrome_os_devices_properties(self, customer_id, device_id):
        """
        Get data pertaining to a single chrome os device
        :param customer_id: The unique ID for the customer's G Suite account
        :param device_id: unique ID for the device.
        :return: JSON
        """
        device_info = self.service.chromeosdevices().get(customerId=customer_id, deviceId=device_id).execute()
        return device_info

    def list_customers_mobile_devices_properties(self, customer_id):
        """
        lists device properties for all devices on the account.
        :param customer_id: The unique ID for the customer's G Suite account
        :return:
        """
        mobiles = self.service.mobiledevices().list(customerId=customer_id).execute()
        return mobiles

    def get_mobile_devices_properties(self, customer_id, resource_id):
        """
        Returns information for a single device
        :param customer_id: The unique ID for the customer's G Suite account
        :param resource_id: The unique ID the API service uses to identify the mobile device.
        :return: JSON
        """
        mobile_info = self.service.chromeosdevices().get(customerId=customer_id, resourceId=resource_id).execute()
        return mobile_info

    def suspend_user_account(self, user_email):
        """
        Suspends an user's account
        :param user_email: Email for the user to be suspended
        :return: JSON
        """
        request_body = {'suspended': True}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info

    def unsuspend_user_account(self, user_email):
        """
        Un-suspends a user's account
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
