from drive_api import DriveAPI


def main():
    drive = DriveAPI()
    # Get Drive Data

    drive.get_all()

"""
    if not items:
        print('No files found.')
    else:
        print('Files:')
        for item in items:
            print('{0} ({1})'.format(item['name'], item['id']))
"""

if __name__ == '__main__':
    main()
