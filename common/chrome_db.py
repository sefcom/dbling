#!/usr/bin/env python3
"""
Initialize the database by ensuring the engine is instantiated and the
'extension' table has been created with the proper columns.
"""

from os import path, uname

from sqlalchemy import create_engine, engine_from_config, MetaData, Table, Column, Integer, String, DateTime, Float, \
    Index, ForeignKey

from common.crx_conf import conf as _conf

__all__ = ['DB_ENGINE', 'DB_META', 'USED_TO_DB']

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
# USED_TO_DB doesn't have the ttl_files field because it's not explicitly stored in the graph object
USED_TO_DB = {'_c_ctime': 'ctime',
              '_c_num_child_dirs': 'num_dirs',
              '_c_num_child_files': 'num_files',
              '_c_mode': 'perms',
              '_c_depth': 'depth',
              '_c_type': 'type',
              '_c_size': 'size'}

# Create the extension table
extension = Table('extension', DB_META,
                  Column('pk', Integer, primary_key=True),
                  Column('ext_id', String(32)),
                  Column('version', String(23)),  # See https://developer.chrome.com/extensions/manifest/version
                  Column('m_version', String(23)),  # Version as specified in the manifest.
                  Column('name', String(45)),  # See https://developer.chrome.com/extensions/manifest/name#name
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
                  )
extension.create(checkfirst=True)

# Create the id_list table
id_list = Table('id_list', DB_META,
                Column('ext_id', String(32), primary_key=True),

                # Other settings
                extend_existing=True,
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
                 )
cent_fam.create(checkfirst=True)
