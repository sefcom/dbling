
import re

MIN_DEPTH = -1
EVAL_NONE = 2
EVAL_TRUE = 1
EVAL_FALSE = 0

IN_PAT_VAULT = re.compile('^/?home/\.shadow/[0-9a-z]*?/vault/user/')
ENC_PAT = re.compile('/ECRYPTFS_FNEK_ENCRYPTED\.([^/]*)$')
