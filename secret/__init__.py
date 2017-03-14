# The `secret` dir should have a `creds.py` file. It has been excluded from the
# repository for obvious reasons, but should have a form such as displayed
# below.
#
# crx_save_path = ''  # Path where the CRXs should be saved when downloaded
# crx_extract_path = ''  # Path where the CRXs should be unpacked
# db_info = {  # Database access information
#     'uri': '',  # Full URI for accessing the DB. See SQLAlchemy docs for more info.
#     'user': '',
#     'pass': '',
#     'nodes': ['host1', ],  # Host names of machines that should use 127.0.0.1 instead of the value for full_url below
#     'full_url': '1.2.3.4',  # IP address of host with the database (usually dbling master)
# }
# # Login info for workers to access the celery server on the dbling master
# celery_login = {'user': 'sample_username', 'pass': 'secure_password', 'port': 5672}
# admin_emails = (  # Names and email addresses of admins that should receive emails from Celery
#     ('Admin Name', 'admin_email@example.com'),
# )
# sender_email_addr = ''  # The email address Celery should use when sending admin emails
