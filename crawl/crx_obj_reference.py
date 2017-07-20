crx_obj = {
    'id': '',
    'version': '',
    'dt_avail': {},  # When list was downloaded that this ID was in
    'msgs': [],  # Progress messages, compiled and emailed after an entire run
    'job_num': 0,  # Index within current crawl
    'job_ttl': 0,  # Total number of CRXs in current crawl
    'filename': '',  # Basename of CRX file (not full path)
    'full_path': '',  # Location (full path) of downloaded CRX file
    'dt_downloaded': {},
    'extracted_path': '',
    'dt_extracted': {},  # When extraction was successfully completed
    'cent_dict': {  # Keys correspond to names in USED_TO_DB. Used to actually insert data into the DB.
        'num_dirs',
        'num_files',
        'perms',
        'depth',
        'type',
        'size',
        # Added right before DB operation
        'ext_id',
        'version',
        'last_known_available',  # From dt_avail
        'profiled',  # From dt_profiled
    },
    'dt_profiled': {},  # When the profile (centroid) was created
    'stop_processing': False,
}
