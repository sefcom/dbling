import re
import stat
from enum import IntEnum  # Requires Python 3.4+

MIN_DEPTH = -1
EVAL_NONE = 2
EVAL_TRUE = 1
EVAL_FALSE = 0

IN_PAT_VAULT = re.compile('^/?home/\.shadow/[0-9a-z]*?/vault/user/')
ENC_PAT = re.compile('/ECRYPTFS_FNEK_ENCRYPTED\.([^/]*)$')
SLICE_PAT = re.compile('.*(/home.*)')

CRX_URL = 'https://chrome.google.com/webstore/detail/%s'

ISO_TIME = '%Y-%m-%dT%H:%M:%SZ'

# Number of bytes used by the dir entry fields (preceding the filename)
DENTRY_FIELD_BYTES = 8


class FType(IntEnum):
    """File types as stored in directory entries in ext2, ext3, and ext4."""
    unk = 0
    reg = 1
    dir = 2
    chr = 3
    blk = 4
    pip = 5
    soc = 6
    sym = 7
    # Aliases
    unknown = 0
    regular = 1
    directory = 2
    character_device = 3
    block_device = 4
    pipe = 5
    fifo = 5
    named_pipe = 5
    socket = 6
    symlink = 7
    symbolic_link = 7

# Maps the octal values that `stat` returns from `S_IFMT()` to one of the regular Unix file types
MODE_UNIX = {stat.S_IFREG: 1,
             stat.S_IFDIR: 2,
             stat.S_IFCHR: 3,
             stat.S_IFBLK: 4,
             stat.S_IFIFO: 5,
             stat.S_IFSOCK: 6,
             stat.S_IFLNK: 7}

# Maps Unix file type numbers to the character used in DFXML to represent that file type
# See: https://github.com/dfxml-working-group/dfxml_schema/blob/4c8aab566ea44d64313a5e559b1ecdce5348cecf/dfxml.xsd#L412
TYPE_TO_NAME = {0: '-',  # Unknown
                1: 'r',  # Regular
                2: 'd',  # Directory
                3: 'c',  # Character device
                4: 'b',  # Block device
                5: 'p',  # Named pipe
                6: 's',  # Socket
                7: 'l'}  # Symbolic link
# Other file types defined in DFXML schema
# h - Shadow inode (Solaris)
# w - Whiteout (OpenBSD)
# v - Special (Used in The SleuthKit for added "Virtual" files, e.g. $FAT1)


class ModeTypeDT(IntEnum):
    """File types as stored in the file's mode.

    In Linux, `fs.h` defines these values and stores them in bits 12-15 of
    ``stat.st_mode``, e.g. ``(i_mode >> 12) & 15``. In `fs.h`, the names are
    prefixed with `DT_`, hence the name of this enum class. Here are the
    original definitions:

    .. code-block::

        #define DT_UNKNOWN      0
        #define DT_FIFO         1
        #define DT_CHR          2
        #define DT_DIR          4
        #define DT_BLK          6
        #define DT_REG          8
        #define DT_LNK          10
        #define DT_SOCK         12
        #define DT_WHT          14
    """
    unknown = 0
    fifo = 1
    chr = 2
    dir = 4
    blk = 6
    reg = 8
    lnk = 10
    sock = 12
    wht = 14


def mode_to_unix(x):
    return MODE_UNIX.get(x, 0)

# The index of these correspond with i such that 16*i is the lower bound and (16*(i+1))-1 is the upper bound for
# file name lengths that correspond to this value. Anything 16*9=144 or longer is invalid.
ECRYPTFS_SIZE_THRESHOLDS = (84, 104, 124, 148, 168, 188, 212, 232, 252, float('-inf'))

# Number of bytes used by eCryptfs for its header
ECRYPTFS_FILE_HEADER_BYTES = 8192


# Database info

# USED_FIELDS = ('_c_ctime', '_c_num_child_dirs', '_c_num_child_files', '_c_mode', '_c_depth', '_c_type')
USED_FIELDS = ('_c_num_child_dirs', '_c_num_child_files', '_c_mode', '_c_depth', '_c_type')

# USED_TO_DB doesn't have the ttl_files field because it's not explicitly stored in the graph object
USED_TO_DB = {'_c_ctime': 'ctime',
              '_c_num_child_dirs': 'num_dirs',
              '_c_num_child_files': 'num_files',
              '_c_mode': 'perms',
              '_c_depth': 'depth',
              '_c_type': 'type',
              '_c_size': 'size'}

EXT_NAME_LEN_MAX = 45
