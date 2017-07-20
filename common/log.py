import logging
from os.path import join, dirname, realpath

from common.clr import add_color_log_levels

# Default logging variables
LOG_DIR = join(dirname(realpath(__file__)), '../log')
LOG_FILE = 'crx.log'
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s %(levelname) 8s -- %(message)s'


def log_setup(log_file=LOG_FILE, log_dir=LOG_DIR, log_level=LOG_LEVEL, log_format=LOG_FORMAT):
    logging.basicConfig(filename=join(log_dir, log_file), level=log_level, format=log_format)
    add_color_log_levels(center=True)
