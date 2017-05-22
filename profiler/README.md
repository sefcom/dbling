# Driver

In this README I'm attempting to document the details that I've found while digging through the source code of eCryptfs
as well as my findings from running the size test (`size_test.py`). It's not very complete, but it's what I have so far.


## eCryptfs Filename Details

Take an example filename:

```
ECRYPTFS_FNEK_ENCRYPTED.FWbQ51sP41qdiUSCJoXGskhYOFgAgSH66reIZ1hX0TzA7UVGpAWWaNy5rE--
```

It has the following components:

| Name           | Length | Description |
| -------------- | :----: | ----------- |
| Prefix         |     24 | `ECRYPTFS_FNEK_ENCRYPTED.` |
| Packet Type    |      1 | Should always be `F`, which is 70 in decimal, 0x46 in hex |
| Packet Length  |    1-2 | Depends on ... |
| FNEK Signature |      8 | blah...
| Cipher code    |      1 | Number indicating the cipher used to encrypt the filename |
| l
| Filename       |   n*20 | Encrypted and encoded |


The prefix is prepended to all filenames when both of the following are true (1) the option to encrypt filenames is on,
and (2) the same key isn't used to encrypt both the file contents and the filename.
For Chrome OS, this will always be the case 
       since it always uses different keys for this.

`ECRYPTFS_FILENAME_MIN_RANDOM_PREPEND_BYTES`, defined to be 16


Seems even files have 8192 bytes prepended to their contents

```c
ECRYPTFS_TAG_70_MAX_METADATA_SIZE = 1+2+8+1+1
s->num_rand_bytes = 16+1
s->block_aligned_filename_size = s->num_rand_bytes + filename_size
max_packet_size = ECRYPTFS_TAG_70_MAX_METADATA_SIZE + s->block_aligned_filename_size
max_packet_size = 13 + 17 + filename_size
```
`max_packet_size` is later increased so as to be a multiple of the block size used by the chosen cipher


## Thresholds

| Upper Min | Upper Max | Lower|
|      ---: |      ---: | ---: |
|         1 |        15 |   84 |
|        16 |        31 |  104 |
|        32 |        47 |  124 |
|        48 |        63 |  148 |
|        64 |        79 |  168 |
|        80 |        95 |  188 |
|        96 |       111 |  212 |
|       112 |       127 |  232 |
|       128 |       143 |  252 |
|       144 |       ??? |\>255 |

