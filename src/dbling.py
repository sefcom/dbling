#!/usr/bin/env python
"""
Usage: dbling.py ??
"""
# TODO: Finish docstring

from bs4 import BeautifulSoup as BSoup
from bs4 import Tag
from chew import Chew
import json
import logging  # Reminder: Levels are (DEBUG, INFO, WARNING, ERROR, CRITICAL)
import netifaces
import os
from os import path
import pexpect
import re
import sqlite3
import subprocess
from time import sleep, time

TEST = True


def get_ip_addr(iface='eth0'):
    return netifaces.ifaddresses(iface)[2][0]['addr']


def get_imgvault_addr():
    # Make the assumption that the host machine has an IP address on the same subnet as us, but with the
    # last number as .1
    return get_ip_addr().rsplit('.', 1)[0] + '.1'


def test(args):
    # Make the assumption that we're running in a VM and that we have SSH access to the host machine
    with open('dbling_conf.json') as fin:
        conf = json.load(fin)

    srv_ip = args['SRV_IP'] or get_imgvault_addr()
    usr_name = args['USERNAME'] or conf['username']
    if args['ID_FILE']:
        id_file = ''
    else:
        id_file = '-i {0!s}'.format(conf['id_file'])

    _args = "ssh {0!s} {1!s}@{2!s}".format(id_file,
                                           usr_name,
                                           srv_ip)
    print(_args)
    proc = pexpect.spawn(_args)
    proc.interact()


def get_current_devs():
    devs = subprocess.check_output('cd /dev; ls -1 vd*', shell=True).splitlines()
    for i in range(len(devs)):
        devs[i] = str(devs[i])[2:-1]
    devs.sort()
    return devs


class ChromeRunner(object):

    def __init__(self, display):
        """
        Initialize the display on which Chrome will run.

        :param display: The display number to use when running Chrome.
        :type display: str | int
        :return: None
        :rtype: None
        """
        if isinstance(display, str):
            try:
                assert display.startswith(':')
            except AssertionError:
                if not display.isdigit():
                    raise
                display = ':' + display
        else:
            assert isinstance(display, int)
            display = ':%d' % display
        self.display = ' --display=' + display
        self._chrome = None

    def deinit(self):
        logging.info('De-initializing Chrome.')
        if self._chrome is None or not self._chrome.isalive():
            return
        closed = self._chrome.terminate(force=True)
        if not closed:
            logging.warning('Could not shut down Chrome successfully. Exiting anyway.')

    def start(self):
        if self._chrome is not None and self._chrome.isalive():
            return
        self._chrome = pexpect.spawn('google-chrome' + self.display)
        logging.info('Chrome running on display ' + self.display.rsplit(':', 1)[1])

    def stop(self):
        if self._chrome is None or not self._chrome.isalive():
            return
        closed = self._chrome.terminate(force=True)
        if not closed:
            logging.critical("Attempted to stop Chrome, but wasn't able to.")
            raise ChildProcessError


class Dbling(object):

    def __init__(self, id_file, username, imgvault_addr=None):
        # Initialize logging
        log_path = path.join(path.dirname(path.realpath(__file__)), '../log', "dbling.log")
        log_format = '%(asctime)s %(levelname) 8s -- %(message)s'
        logging.basicConfig(filename=log_path, level=logging.INFO, format=log_format)
        logging.info('dbling instance up and initializing.')

        self._devs = get_current_devs()
        logging.info('Attached devices now: %s' % self._devs)

        # Compile the patterns that matches the prompts
        self._prompt = re.compile(bytes('{0!s}@.*?$.*? '.format(username), 'utf-8'))
        self._img_prompt = re.compile(b'\?> ')
        self._name_prompt = re.compile(b'name> ')

        if imgvault_addr is None:
            imgvault_addr = get_imgvault_addr()

        args = "ssh -i {0!s} {1!s}@{2!s}".format(id_file, username, imgvault_addr)
        self._vault = pexpect.spawn(args)
        # Ensure we're logged in and everything is ready for us to send commands
        self._vault.expect(self._prompt)
        logging.info('SSH into ImgVault machine complete.')

        logging.info('Starting ImgVault and connecting to the hypervisor.')
        self._vault.write('cd $IMGVAULT_SRC\n')
        self._vault.expect(self._prompt)
        self._vault.write('python vault.py\n')
        self._vault.expect(self._img_prompt)
        logging.info('ImgVault ready.')

        self._display = 20
        logging.info('Starting xpra on display %d' % self._display)
        pexpect.run('xpra start :%d' % self._display)
        self._chrome = ChromeRunner(self._display)
        if TEST:
            input("xpra started on %d. Connect with `xpra attach ssh:USERNAME@REMOTE:DISPLAY and press Enter "
                  "when you're ready to continue." % self._display)

        db_name = path.join(path.dirname(path.realpath(__file__)), 'chrome_ext.db')
        self._conn = sqlite3.connect(db_name)
        c = self._conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS exts ('
                  'id TEXT, '
                  'url TEXT, '
                  'lastmod TEXT, '
                  'installed TEXT, '
                  'dfxml_inst TEXT, '
                  'uninstalled TEXT, '
                  'dfxml_uninst TEXT, '
                  'PRIMARY KEY(id))')
        self._conn.commit()
        logging.info('Connected to database at %s' % db_name)

        # Store the path to the sitemap, directory for extensions
        self._sitemap_path = path.join(path.dirname(path.realpath(__file__)), '../', 'chrome_sitemap.xml')
        self._ext_dir = '/opt/google/chrome/extensions/'
        if not path.exists(self._ext_dir):
            args = ['mkdir', self._ext_dir]
            if os.geteuid() != 0:
                args = ['sudo'] + args
            ret = subprocess.call(args, shell=True)  # Should return 0
            if ret:
                logging.critical('Failed to create the directory for extension JSON files: %s', self._ext_dir)
                raise ChildProcessError("Couldn't make the directory: %s" % self._ext_dir)

        # Times to sleep to let things do their work (seconds)
        self._install_time_driver = 0  # TODO
        self._install_time_target = 0  # TODO

    def deinit(self):
        logging.info('Deinit called. Shutting down SSH connection.')
        if self._vault.isalive():
            self._vault.write('q\n')
            self._vault.expect(self._prompt)
            self._vault.write('exit\n')
            self._vault.expect(pexpect.EOF)

        logging.info('Shutting down Chrome/xpra.')
        self._chrome.deinit()
        pexpect.run('xpra stop :%d' % self._display)

        logging.info('Closing database and saving any pending changes.')
        self._conn.commit()
        self._conn.close()

        logging.info('De-initialization complete. Exiting.')

    def _profile(self, ext_tag):
        """
        Generate a preliminary profile of the given extension.

        :param ext_tag: The BeautifulSoup tag for the extension.
        :type ext_tag: Tag
        :return:
        :rtype:
        """
        e_id = ext_tag.loc.string.rsplit('/', 1)[1]
        short_e_id = e_id[:5]
        url = ext_tag.loc.string
        lastmod = ext_tag.lastmod.string
        cur = self._conn.cursor()
        logging.info('Beginning preliminary profile of extension: %s' % e_id)

        ##################
        # STEP 1: Create the JSON file for the extension
        # TODO: Do some sanitization of the extension's ID before we use it in system calls
        fname = path.join(self._ext_dir, e_id + '.json')
        # Create the file
        ret = subprocess.call(['sudo', 'touch', fname], shell=True)  # Should return 0
        if ret:
            logging.critical('%s I: Failed to create extension JSON file at %s.' % (short_e_id, fname))
            raise ChildProcessError("Couldn't create file: %s" % fname)
        # Change the permissions on the file
        ret = subprocess.call(['sudo', 'chmod', '666', fname], shell=True)
        if ret:
            logging.critical('%s I: Failed to give 666 permissions to the extension JSON file at %s.' %
                             (short_e_id, fname))
            raise ChildProcessError("Couldn't chmod 666 file: %s" % fname)
        with open(fname, 'w') as fout:
            ext_info = {'external_update_url': 'https://clients2.google.com/service/update2/crx'}
            json.dump(ext_info, fout)
        # Restrict permissions on the file now that we've written its contents
        ret = subprocess.call(['sudo', 'chmod', '644', fname], shell=True)
        if ret:
            logging.warning('%s I: Failed to give 644 permissions to the extension JSON file at %s.' %
                            (short_e_id, fname))

        ##################
        # STEP 2: Start Chrome on the driver, and let Chrome install it, sync with cloud
        self._chrome.start()
        if TEST:
            start_time = time()
            input('Press Enter to continue.')
            end_time = time()
            print("You waited %f seconds." % (end_time-start_time))
        else:
            sleep(self._install_time_driver)
        logging.info('%s I: Installed on driver.' % short_e_id)

        ##################
        # STEP 3: Start up target instance into a "running" snapshot (so we don't have to log in), let it sync
        # with the cloud and install the extension, estimated <time> minutes
        self._vault.write('start target current\n')
        self._vault.expect(self._prompt)
        if TEST:
            start_time = time()
            input('Press Enter to continue.')
            end_time = time()
            print("You waited %f seconds." % (end_time-start_time))
        else:
            sleep(self._install_time_target)
        logging.info('%s I: Installed on target.' % short_e_id)

        ##################
        # STEP 4: Update the database
        cur.execute("UPDATE exts SET installed=datetime('now'), dfxml_inst=NULL, uninstalled=NULL, "
                    "dfxml_uninst=NULL WHERE id=?", e_id)
        self._conn.commit()

        ##################
        # STEP 5: Shut down Chrome on the driver
        # It's okay if this is non-blocking because the next step will take a while to complete, and we don't
        # do anything that affects Chrome again until Step 14.
        self._chrome.stop()

        ##################
        # STEP 6: Snapshot the target while it's running (see #3)
        self._vault.write('snapshot target\n')  # TODO: Double-check that this blocks until the snapshot is complete
        self._vault.expect(self._name_prompt)
        self._vault.write('%s_inst\n' % e_id)
        self._vault.expect(self._prompt)
        logging.info('%s I: Snapshot taken after installation on target.' % short_e_id)

        ##################
        # STEP 7: Shut down the target
        self._vault.write('close target\n')
        self._vault.expect(self._name_prompt)
        logging.info('%s I: Target shut down.' % short_e_id)

        ##################
        # STEP 8: Attach the target's disk to the driver
        self._vault.write('disk to driver\n')
        dev_path = self._validate_dev_path(self._vault.readline())
        self._vault.expect(self._prompt)
        logging.info('%s I: Target disk now attached at %s.' % (short_e_id, dev_path))

        ##################
        # STEP 9: Take an image of the disk
        chew = Chew(dev_path)
        img_path = chew.do_acquisition(chew.now)
        logging.info('%s I: Disk image created at: %s' % (short_e_id, img_path))

        ##################
        # STEP 10: Make a DFXML file from the disk image
        dfxml_path = chew.do_dfxml()
        logging.info('%s I: DFXML file created at: %s' % (short_e_id, dfxml_path))

        ##################
        # STEP 11: Update the database
        cur.execute("UPDATE exts SET dfxml_inst=datetime('now'), uninstalled=NULL, dfxml_uninst=NULL "
                    "WHERE id=?", e_id)
        self._conn.commit()

        ##################
        # STEP 12: Delete the disk image
        ret = subprocess.call(['sudo', 'rm', img_path])  # Should return 0
        if ret:
            logging.critical('%s I: Failed to delete image file: %s' % (short_e_id, img_path))
            raise ChildProcessError("Couldn't delete image file: %s" % img_path)

        ##################
        # STEP 13: Detach the target's disk from the driver
        self._vault.write('disk to target\n')
        self._vault.expect(self._prompt)
        logging.info('%s I: Target disk now detached from driver.' % short_e_id)

        ##################
        # End of install
        # Start of uninstall
        ##################
        if TEST:
            return

        ##################
        # STEP 14: Delete the JSON file for the extension
        ret = subprocess.call(['sudo', 'rm', fname])
        if ret:
            logging.critical('%s U: Failed to delete extension JSON file at %s.' % (short_e_id, fname))
            raise ChildProcessError("Couldn't delete extension JSON file: %s" % fname)

        ##################
        # STEP 15: Start Chrome on the driver, and let Chrome uninstall the extension, sync with cloud

        # TODO

        if TEST:
            start_time = time()
            input('Press Enter to continue.')
            end_time = time()
            print("You waited %f seconds." % (end_time-start_time))
        else:
            sleep(self._install_time_driver)

        ##################
        # STEP 16: Start up target instance from the snapshot (probably just a rollback/revert), let it sync
        # with the cloud and uninstall the extension, estimated <time> minutes
        self._vault.write('start target current\n')
        self._vault.expect(self._prompt)
        if TEST:
            start_time = time()
            input('Press Enter to continue.')
            end_time = time()
            print("You waited %f seconds." % (end_time-start_time))
        else:
            sleep(self._install_time_target)
        logging.info('%s U: Uninstalled from target.' % short_e_id)

        ##################
        # STEP 17: Update the database
        cur.execute("UPDATE exts SET uninstalled=datetime('now'), dfxml_uninst=NULL WHERE id=?", e_id)
        self._conn.commit()

        ##################
        # STEP 18: Shut down Chrome on the driver
        self._chrome.stop()

        ##################
        # STEP 19: Snapshot the target
        self._vault.write('snapshot target\n')
        self._vault.expect(self._name_prompt)
        self._vault.write('%s_uninst\n' % e_id)
        self._vault.expect(self._prompt)
        logging.info('%s U: Snapshot taken after un-installation from target.' % short_e_id)

        ##################
        # STEP 20: Shut down the target
        self._vault.write('close target\n')
        self._vault.expect(self._name_prompt)
        logging.info('%s U: Target shut down.' % short_e_id)

        ##################
        # STEP 21: Attach, image, DFXML similar to previous
        self._vault.write('disk to driver\n')
        dev_path = self._vault.readline()
        self._vault.expect(self._prompt)
        logging.info('%s U: Target disk now attached at %s.' % (short_e_id, dev_path))
        # TODO


        ##################
        # STEP 22: Update the database
        cur.execute("UPDATE exts SET dfxml_uninst=datetime('now') WHERE id=?", e_id)
        self._conn.commit()

        ##################
        # STEP 23: Delete the disk image


        ##################
        # STEP 24: Detach the target's disk
        self._vault.write('disk to target\n')
        self._vault.expect(self._prompt)
        logging.info('%s U: Target disk now detached from driver.' % short_e_id)

    def profile_random(self, limit=None):
        # TODO: Check whether chrome_sitemap.xml exists, download if it doesn't
        # TODO: If download is necessary, warn the user it will take several minutes
        if limit is None:
            return self._profile_all()

        # Please excuse me while I write some really inefficient code...
        assert isinstance(limit, int)
        with open(self._sitemap_path) as fin:
            soup = BSoup(fin.read(), "xml")
        delete_me = soup.find_all('url', limit=limit)
        exts = []
        cur = self._conn.cursor()

        while len(exts) < limit:
            e = delete_me.pop(0)
            e_id = e.loc.string.rsplit('/', 1)[1]
            cur.execute('SELECT id FROM exts WHERE id=?', e_id)
            if cur.fetchone() is not None:
                # This is not the extension you're looking for
                # because it's already in the database
                continue
            cur.execute('INSERT INTO exts (id, url, lastmod) VALUES (?, ?, ?)',
                        (e_id, e.loc.string, e.lastmod.string))
            exts.append(e)
        self._conn.commit()
        del delete_me
        del soup
        logging.info('%d extensions selected to profile, added to database.' % limit)

        for e in exts:
            self._profile(e)

    def _profile_all(self):
        raise NotImplementedError

    def _validate_dev_path(self, dev):
        dev = dev.strip()
        if isinstance(dev, bytes):
            dev = str(dev)[2:-1]
        devs = get_current_devs()
        assert dev in devs
        assert dev not in self._devs
        return dev


def main():
    """
    Assumptions:

    * This code is running in a VM
    * We have SSH access to the host machine (identity files and authorized_keys)
    * The host has exported the variable $IMGVAULT_SRC
    * chrome_sitemap.xml exists in ../ from here

    :return:
    """
    # Make the assumption that we're running in a VM and that we have SSH access to the host machine
    with open(path.join(path.dirname(path.realpath(__file__)), 'dbling_conf.json')) as fin:
        # TODO: Make a prompt that fills in this configuration file if it's missing
        conf = json.load(fin)

    dbing = Dbling(conf['id_file'], conf['username'])

    # TODO: Start the loop of picking an extension, installing it, waiting for the changes to take place on the
    # target, shutting down the target, detaching its disk, ...


if __name__ == '__main__':
    main()
