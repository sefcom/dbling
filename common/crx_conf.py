from copy import copy
from os import path, mkdir
from tempfile import gettempdir

from munch import Munch

from secret.creds import crx_save_path, db_info

__all__ = ['conf']

crx_extract_path = path.join(gettempdir(), 'dbling')
if not path.isdir(crx_extract_path):
    mkdir(crx_extract_path)

conf = Munch({
  "version": "57.0",
  "release_date": [2017, 3, 9],  # See https://en.wikipedia.org/wiki/Google_Chrome_version_history
  "url": "https://clients2.google.com/service/update2/crx?response=redirect&prodversion={}&x=id%3D{}%26installsource%3Dondemand%26uc",
  "extension_list_url": "https://chrome.google.com/webstore/sitemap?shard=0&numshards=1",
  "save_path": crx_save_path,
  "extract_dir": crx_extract_path,
  "db": {
    "type": "mysql+mysqlconnector",
    "user": db_info['user'],
    "pass": db_info['pass'],
    "url": "127.0.0.1",
    "name": "chrome",
    "nodenames": copy(db_info['nodes']),
    "full_url": db_info['full_url'],
  }
})

_uri = db_info.get('uri')
if _uri is not None:
    conf['db']['sqlalchemy.url'] = _uri
