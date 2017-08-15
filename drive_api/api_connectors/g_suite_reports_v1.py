from apiclient import discovery

from util import print_json


class GSuiteReportsAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google

        https://developers.google.com/admin-sdk/reports/v1/quickstart/python

        :param http: http object
        """
        self.service = discovery.build('admin', 'reports_v1', http=http)

    def test(self):
        """
        Test method from Google quickstart page

        https://developers.google.com/admin-sdk/reports/v1/quickstart/python

        :return: nothing
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

        https://developers.google.com/admin-sdk/reports/v1/reference/activities/list

        :param user_key: The value can be all or a userKey.
        :param application_name: name of application from a list viewable on the reference page
        :return: JSON
        """
        activities = self.service.activities().list(userKey=user_key, applicationName=application_name, maxResults=10).execute()
        items = activities.get('items', [])
        while 'nextPageToken' in activities:
            activities = self.service.activities().list(userKey=user_key, applicationName=application_name, maxResults=10, pageToken=str(activities["nextPageToken"])).execute()
            items.append(activities.get('items', []))

        if not items:
            return None
        else:
            return items

    # Not useful for this project
    def get_customer_usage_reports(self, date, customer_id=False):
        """
        Gets customer usage reports

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
        """
        Gets user usage report

        https://developers.google.com/admin-sdk/reports/v1/reference/userUsageReport/get

        :param date:
        :param user_key:
        :return: JSON
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
        if True:
            activities = self.list_activities()
            print_json(activities)
        if False:
            reports = self.get_customer_usage_reports('2017-07-20')
            print_json(reports)
        if False:
            reports = self.get_user_usage_report('2017-07-31')
            print_json(reports)
