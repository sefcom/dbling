#!/usr/bin/env python3
"""
Initialize the database by ensuring the engine is instantiated and the
'extension' table has been created with the proper columns.
"""

__all__ = ['DB_ENGINE', 'DB_META', 'USED_TO_DB']

import json
from os import path
from sqlalchemy import create_engine, engine_from_config, MetaData, Table, Column, Integer, String, DateTime, Float, \
    Index

with open(path.abspath(path.join(path.dirname(path.realpath(__file__)), 'crx_conf.json'))) as fin:
    db_conf = json.load(fin)['db']


if 'sqlalchemy.url' not in db_conf:
    create_str = db_conf['type'] + '://'
    if len(db_conf['user']):
        create_str += db_conf['user']
        if len(db_conf['pass']):
            create_str += ':' + db_conf['pass']
        create_str += '@'
    create_str += path.join(db_conf['url'], db_conf['name'])
    DB_ENGINE = create_engine(create_str)
else:
    DB_ENGINE = engine_from_config(db_conf)

DB_META = MetaData()
DB_META.bind = DB_ENGINE
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
                  Column('version', String(20)),
                  Column('last_known_available', DateTime(True)),
                  Column('last_known_unavailable', DateTime(True)),
                  Column('profiled', DateTime(True)),

                  # Centroid fields
                  Column('size', Float),
                  Column('ctime', Float),
                  Column('num_dirs', Float),
                  Column('num_files', Float),
                  Column('perms', Float),
                  Column('depth', Float),
                  Column('type', Float),
                  Column('centroid_group', Integer),

                  # Image centroid fields, calculated after installing
                  Column('i_size', Float),
                  Column('i_ctime', Float),
                  Column('i_num_dirs', Float),
                  Column('i_num_files', Float),
                  Column('i_perms', Float),
                  Column('i_depth', Float),
                  Column('i_type', Float),
                  Column('i_centroid_group', Integer),

                  # Unique index on the extension ID and version
                  Index('idx_id_ver', 'ext_id', 'version', unique=True)
                  )
extension.create(checkfirst=True)

# Create the id_list table
id_list = Table('id_list', DB_META,
                Column('ext_id', String(32), primary_key=True)
                )
id_list.create(checkfirst=True)
