# *-* coding: utf-8 *-*

from __future__ import absolute_import

from logging import getLogger, WARNING

from celery import Celery

app = Celery('crawl', include=['crawl.tasks', 'crawl.db_iface'])
app.config_from_object('crawl.celeryconfig')

getLogger('celery').setLevel(WARNING)


if __name__ == '__main__':
    app.start()
