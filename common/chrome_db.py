#!/usr/bin/env python3
"""
Initialize the database by ensuring the engine is instantiated and the
'extension' table has been created with the proper columns.
"""

from os import path, uname

from sqlalchemy import create_engine, engine_from_config, MetaData, Table, Column, Integer, DateTime, Float, \
    Index, ForeignKey
from sqlalchemy.dialects.mysql import VARCHAR

from common.crx_conf import conf as _conf
from common.const import EXT_NAME_LEN_MAX

__all__ = ['DB_ENGINE', 'DB_META']

db_conf = _conf['db']


try:
    _nodename = uname().nodename
except AttributeError:
    # Python < 3.3 doesn't return a named tuple
    _nodename = uname()[1]

if _nodename not in db_conf['nodenames']:
    db_conf['_url'] = path.join(db_conf['full_url'], db_conf['name'])
    create_str = '{type}://{user}:{pass}@{_url}'.format(**db_conf)
    DB_ENGINE = create_engine(create_str, convert_unicode=True, pool_recycle=3600, pool_size=10)

elif 'sqlalchemy.url' not in db_conf:
    # User name and password may be optional in this situation
    db_conf['_u'] = len(db_conf['user']) and '@' or ''
    db_conf['_p'] = len(db_conf['user']) and len(db_conf['pass']) and ':' or ''
    db_conf['_url'] = path.join(db_conf['url'], db_conf['name'])
    create_str = '{type}://{user}{_p}{pass}{_u}{_url}'.format(**db_conf)
    DB_ENGINE = create_engine(create_str)

else:
    DB_ENGINE = engine_from_config(db_conf)

DB_META = MetaData(bind=DB_ENGINE)

# Create the extension table
extension = Table('extension', DB_META,
                  Column('pk', Integer, primary_key=True),
                  Column('ext_id', VARCHAR(32, charset='utf8mb4', collation='utf8mb4_unicode_ci')),
                  Column('version', VARCHAR(23, charset='utf8mb4', collation='utf8mb4_unicode_ci')),  # See https://developer.chrome.com/extensions/manifest/version
                  Column('m_version', VARCHAR(23, charset='utf8mb4', collation='utf8mb4_unicode_ci')),  # Version as specified in the manifest.
                  Column('name', VARCHAR(EXT_NAME_LEN_MAX, charset='utf8mb4', collation='utf8mb4_unicode_ci')),  # See https://developer.chrome.com/extensions/manifest/name#name
                  Column('last_known_available', DateTime(True)),
                  Column('last_known_unavailable', DateTime(True)),
                  Column('downloaded', DateTime(True)),
                  Column('extracted', DateTime(True)),
                  Column('profiled', DateTime(True)),

                  # Centroid fields
                  Column('size', Float),
                  Column('ctime', Float),
                  Column('num_dirs', Float),
                  Column('num_files', Float),
                  Column('perms', Float),
                  Column('depth', Float),
                  Column('type', Float),
                  Column('centroid_group', Integer, ForeignKey("centroid_family.pk")),
                  Column('ttl_files', Integer),

                  # Image centroid fields, calculated after installing
                  Column('i_size', Float),
                  Column('i_ctime', Float),
                  Column('i_num_dirs', Float),
                  Column('i_num_files', Float),
                  Column('i_perms', Float),
                  Column('i_depth', Float),
                  Column('i_type', Float),
                  Column('i_centroid_group', Integer, ForeignKey("centroid_family.pk")),

                  # Unique index on the extension ID and version
                  Index('idx_id_ver', 'ext_id', 'version', unique=True),

                  # Other settings
                  extend_existing=True,  # Adds new columns to backend DB table if necessary (user must have ALTER perm)
                  mysql_engine='InnoDB',
                  mysql_default_charset='utf8mb4',
                  )
extension.create(checkfirst=True)

# Create the id_list table
id_list = Table('id_list', DB_META,
                Column('ext_id', VARCHAR(32, charset='utf8mb4', collation='utf8mb4_unicode_ci'), primary_key=True),

                # Other settings
                extend_existing=True,
                mysql_engine='InnoDB',
                mysql_default_charset='utf8mb4',
                )
id_list.create(checkfirst=True)

# Create the centroid_family table
cent_fam = Table('centroid_family', DB_META,
                 Column('pk', Integer, primary_key=True),

                 # Centroid fields
                 Column('size', Float),
                 Column('ctime', Float),
                 Column('num_dirs', Float),
                 Column('num_files', Float),
                 Column('perms', Float),
                 Column('depth', Float),
                 Column('type', Float),
                 Column('centroid_group', Integer),
                 Column('ttl_files', Integer),

                 # Stats
                 Column('num_members', Integer),  # Number of rows from 'extension' matching this centroid
                 Column('members_updated', DateTime(True)),
                 Column('num_i_members', Integer),  # Number of rows whose i_centroid_group matches this record
                 Column('i_members_updated', DateTime(True)),
                 Column('distinct_id_members', Integer),  # Number of members w/distinct IDs
                 Column('distinct_members_updated', DateTime(True)),

                 # Other settings
                 extend_existing=True,
                 mysql_engine='InnoDB',
                 mysql_default_charset='utf8mb4',
                 )
cent_fam.create(checkfirst=True)
