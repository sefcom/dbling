# *-* coding: utf-8 *-*

# Some code borrowed from http://www.prschmid.com/2013/04/using-sqlalchemy-with-celery-tasks.html


from celery import Task
from sqlalchemy.orm import scoped_session, sessionmaker

from crawl.chrome_db import DB_ENGINE

db_session = scoped_session(sessionmaker(
    autocommit=False, autoflush=False, bind=DB_ENGINE))


class SqlAlchemyTask(Task):
    """An abstract Celery Task that ensures that the connection the the
    database is closed on task completion"""

    abstract = True

    def run(self, *args, **kwargs):
        """The body of the task executed by workers."""
        raise NotImplementedError('Tasks must define the run method.')

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        db_session.remove()
