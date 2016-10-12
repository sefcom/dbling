#!/bin/sh
celery -A crawl worker -P eventlet -l info