# *-* coding: utf-8 *-*
from celery import Celery

app = Celery('crawl', broker='amqp://', backend='amqp://', include=['crawl.tasks'])
app.config_from_object('crawl.celeryconfig')


if __name__ == '__main__':
    app.start()
