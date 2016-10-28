# *-* coding: utf-8 *-*
# ## To use Eventlet concurrency, Start worker with -P eventlet
# Never use the worker_pool setting as that'll patch
# the worker too late.
#
# The default concurrency number is the number of CPU’s on that machine (including cores), you can specify a custom
# number using -c option. There is no recommended value, as the optimal number depends on a number of factors, but if
# your tasks are mostly I/O-bound then you can try to increase it, experimentation has shown that adding more than
# twice the number of CPU’s is rarely effective, and likely to degrade performance instead.

from celery.schedules import crontab
from datetime import timedelta


BROKER_URL = 'amqp://'
CELERY_RESULT_BACKEND = 'amqp://'
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Acknowledge tasks only once they've completed. If the worker crashes, the job will be requeued.
CELERY_ACKS_LATE = True

# Email settings for when tasks fail
CELERY_SEND_TASK_ERROR_EMAILS = False  # This is the default. Tasks should explicitly set the send_error_emails flag.
ADMINS = (
)
SERVER_EMAIL = ''


# A "beat" service can be started with `celery -A proj beat` that uses the time information to periodically start
# the specified task. See http://docs.celeryproject.org/en/latest/tutorials/daemonizing.html for infor on daemonizing
# this kind of service.
CELERYBEAT_SCHEDULE = {
    'download-every-12-hrs': {
        'task': 'crawl.tasks.start_list_download',
        # 'schedule': crontab(minute=42, hour='9,21'),
        'schedule': timedelta(seconds=20),
    },
}
