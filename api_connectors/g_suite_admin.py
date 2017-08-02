from util import print_json
from apiclient import discovery


class GSuiteAdminAPI:

    def __init__(self, http):
        self.service = discovery.build('admin', 'directory_v1', http=http)

    # users

    def test(self):
        results = self.service.users().list(customer='my_customer',
                                            maxResults=10, orderBy='email').execute()
        users = results.get('users', [])

        if not users:
            print('No users in the domain.')
        else:
            print('Users:')
            for user in users:
                print('{0} ({1})'.format(user['primaryEmail'],
                                         user['name']['fullName']))

    def get_user(self, user_email):
        user = self.service.users().get(userKey=user_email).execute()
        return user

    def get_all_users(self, domain_name):
        users = self.service.users().list(domain=domain_name).execute()
        return users

    # chromeosdevices

    def list_users_chromeos_device(self, customer_id):
        devices = self.service.chromeosdevices().list(customerId=customer_id).execute()
        return devices

    def get_chrome_os_devices_properties(self, customer_id, device_id):
        device_info = self.service.chromeosdevices().get(customerId=customer_id, deviceId=device_id).execute()
        return device_info

    def list_users_mobile_devices_properties(self, customer_id):
        mobiles = self.service.mobiledevices().list(customerId=customer_id).execute()
        return mobiles

    def get_mobile_devices_properties(self, customer_id, resource_id):
        mobile_info = self.service.chromeosdevices().get(customerId=customer_id, resourceId=resource_id).execute()
        return mobile_info

    def suspend_user_account(self, user_email):
        request_body = {"suspended": True}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info

    def unsuspend_user_account(self, user_email):
        request_body = {"suspended": False}
        return_info = self.service.users.update(userKey=user_email, body=request_body).execute()
        return return_info
    
    def get_all(self):
        if True:
            print_json(self.get_all_users("adamdoupe.com"))
