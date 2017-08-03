from util import print_json
from apiclient import discovery


class GSuiteReportsAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google
        :param http: http object
        """
        self.service = discovery.build('admin', 'reports_v1', http=http)

    def test(self):
        """

        :return:
        """
        results = self.service.activities().list(userKey='all', applicationName='login', maxResults=10).execute()
        activities = results.get('items', [])

        if not activities:
            print('No logins found.')
        else:
            print('Logins:')
            for activity in activities:
                print('{0}: {1} ({2})'.format(activity['id']['time'], activity['actor']['email'],
                                              activity['events'][0]['name']))

    def list_activities(self, user_key='all', application_name='login'):
        """
        Returns the last 180 days of activities.

        :param user_key:
        :param application_name:
        :return:
        """
        activities = self.service.activities().list(userKey=user_key, applicationName=application_name).execute()
        return activities

    def list_customer_usage_reports(self, date, customer_id=False):
        """

        :param date:
        :param customer_id:
        :return:
        """
        if not customer_id:
            report = self.service.customerUsageReports().get(date=date).execute()
        else:
            report = self.service.activities().list().execute()
        return report

    def get_user_usage_report(self, date, user_key='all'):
        """

        :param date:
        :param user_key:
        :return:
        """
        report = self.service.userUsageReport().get(date=date, userKey=user_key).execute()
        return report

    def get_all(self):
        """
        Testing method
        :return: Nothing
        """
        if False:
            self.test()
        if False:
            activities = self.list_activities()
            print_json(activities)
        if False:
            reports = self.list_customer_usage_reports('2017-07-20')
            print_json(reports)
        if True:
            reports = self.get_user_usage_report('2017-07-31')
            print_json(reports)
