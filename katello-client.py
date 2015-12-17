#!/usr/bin/python

try:
    import json
    import sys
    import logging
    import os
    import socket
    import argparse # import OptionParser, OptionGroup
    import requests
    import yum
    import random
    import string
    import platform

except ImportError:
    print >> sys.stderr, """\
There was a problem importing one of the required Python modules. The
error was:

    %s
""" % sys.exc_value
    sys.exit(1)

"""
TODO:
- Log to file?
- Accept answer file

"""

def parse_options():
    parser = argparse.ArgumentParser()

    basic_group = parser.add_argument_group("Basic options")
    basic_group.add_argument("-s", "--server", dest="server",
                      help="katello server")
    basic_group.add_argument("-o", "--org", dest="org",
                      help="organization to register with")
    basic_group.add_argument("-a", "--activationkey", dest="activationkey",
                      help="activation key to use for registation")
    basic_group.add_argument("--api", dest="useapi", action="store_true",
                      default=False, help="use the katello api to get possible answers (reguires username and password)")
    basic_group.add_argument("-u", "--unattended", dest="unattended", action="store_true",
                      default=False, help="unattended (un)installation never prompts the user")
    basic_group.add_argument("-d", "--debug", dest="debug", action="store_true",
                      default=False, help="print debugging information")
    basic_group.add_argument("-v", "--verbose", dest="verbose", action="store_true",
                      default=False, help="print verbose information")
    parser.add_argument_group(basic_group)

 
    uninstall_group = parser.add_argument_group("Uninstall options")
    uninstall_group.add_argument("--uninstall", dest="uninstall", action="store_true",
                      default=False, help="uninstall an existing installation")
    parser.add_argument_group(uninstall_group)

    options = parser.parse_args()

    if (options.unattended and not options.server):
        parser.error("--unattended cannot be used without providing --server")
    if (options.unattended and not options.org):
        parser.error("--unattended cannot be used without providing --org")
    if (options.unattended and not options.activationkey):
        parser.error("--unattended cannot be used without providing --activationkey")
    return options

def logging_setup(options):
        if options.debug:
            log_level = logging.DEBUG
        elif options.verbose:
            log_level = logging.INFO
        else:
            log_level = logging.ERROR
        logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

class get_config():

    def __init__(self):
       pass
       # self.server = ''
       # self.org = ''
       # self.activationkey = ''

    def get_katello_server(self, options):
        if options.server:
            server = options.server
        else:
            # Well will try and guess the katello server if it isn't given, clever huh ?
            try:
                hostname = socket.getfqdn().split()
                for item in hostname:
                    if len( item.split(".") ) >= 2: 
                        data = item.split(".")[-2:]
                        domain = '.' + '.'.join(data)
                guesses = ['sat6', 'sat', 'satellite6', 'satellite', 'katello', 'katello-server']
                potential_servers = [guess + domain for guess in guesses]
                for address in potential_servers:
                    try:
                        socket.socket().connect((address, 443))
                    except:
                        pass
                    else:
                        logging.debug("Guessed katello server is {server} because port 443 is open".format(server=address))
                        server = address
                        break
            except:
                pass
        if not server:
            logging.debug("Couldn't guess katello server") 
        server = raw_input("Please enter the capsule server[{server}]:".format(server=server)) or server
        return server

    def get_katello_org(self, options):
        if options.org:
            org = raw_input("Please enter the organization[{org}]:".format(org=options.org)) or options.org 
        else:
            while True:
                org = raw_input("Please enter the organization[{org}]:".format(org=options.org))
                if org:
                    break 
        return org

    def get_katello_activationkey(self, options):
        if options.activationkey:
            activationkey = raw_input("Please enter the activation key[{activationkey}%s]:".format(activationkey=options.activationkey)) or options.activationkey
        else:
            while True:
                activationkey = raw_input("Please enter the activation key[{activationkey}]:".format(activationkey=options.activationkey))
                if activationkey:
                    break
        return activationkey

class install():

    def __init__(self):
        self.mainversion = platform.dist()[1].split('.')[0]
        pass

    def pkg(self, pkg, config):
        """
        This installs the passed package if required
        """
        yb = yum.YumBase()
        # A bit of a hack but we need to supress the pointless output of yb.conf.cache
        oldstdout = sys.stdout
        sys.stdout = os.devnull
        yb.conf.cache = 1
        if yb.rpmdb.searchNevra(name=pkg):
            sys.stdout = oldstdout
            logging.info("{pkg} is already installed".format(pkg=pkg))
        else:
            sys.stdout = oldstdout
            self.repo(config, add = True)
            install_failed = self.install_pkg(pkg)
            self.repo(config, remove = True)
            if install_failed:
                # If the install failed, we exit here as we want to remove the tmp repo first
                sys.exit(1)

    def repo(self, config, add = False, remove = False):
        """
        This add a repo for temp use
        """
        if add:
            try:
                self.tmprepo = '/etc/yum.repos.d/katello-client-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(9)) + '.repo'
                f = open(self.tmprepo, 'w')
                f.write('[katello-client-tmp]\n')
                f.write('name = katello-client-tmp\n')
                f.write('baseurl=http://{server}/pulp/repos/{org}/Library/content/dist/rhel/server/{version}/$releasever/$basearch/kickstart/\n'.format(server=config.server, org=config.org, version=self.mainversion))
                f.write('enabled=1\n')
                f.write('gpgcheck=1\n')
                f.close()
                logging.info("Added tmp repo {f}".format(f=self.tmprepo))
            except:
                logging.error("Couldn't write tmp repo file: {f}".format(f=self.tmprepo))
                sys.exit(2)
        if remove:
            try:
                os.remove(self.tmprepo)
            except OSError, e:
                logging.info("Failed to remove tmp repo {f}".format(f=self.tmprepo))
            else:
                logging.debug("Removed tmp kickstart repo")
            

    def install_pkg(self, pkg):
        """
        This installs a package
        """
        logging.info("Installing %s using yum" % pkg)
        oldstdout = sys.stdout
        sys.stdout = os.devnull
        try:
            yb = yum.YumBase()
            package = {
                            'name':pkg
            }
            yb.install(**package)
            yb.resolveDeps()
            yb.buildTransaction()
            yb.processTransaction()
            sys.stdout = oldstdout
        except Exception as e:
            logging.fatal(e)
            failed = True
            return failed
        else:
            logging.info("Installed {pkg}".format(pkg=pkg))
 
class config():

    def __init__(self):
        self.mainversion = platform.dist()[1].split('.')[0]
        pass


def main():
    options = parse_options()
    logging_setup(options)

    # only run as root
    if not os.getegid() == 0:
        sys.exit("\nYou must be root to run katello-client.\n")

    if options.uninstall:
        # do uninstall 
        pass
    else:
        if options.unattended:
            config = get_config()
            config.server = options.server
            config.org = options.org
            config.activationkey = options.activationkey
        else:
            # Install and configure
            config = get_config()
            config.server = config.get_katello_server(options)
            config.org = config.get_katello_org(options)
            config.activationkey = config.get_katello_activationkey(options)

    logging.info("server set to %s" % config.server)
    logging.info("organization set to %s" % config.org)
    logging.info("activation key set to %s" % config.activationkey)

    # now we need to do the install!
    i = install()
    i.pkg('katello-agent', config) # needs to be subscription-manager
    



try:
    if __name__ == "__main__":
        sys.exit(main())
except SystemExit, e:
    sys.exit(e)
except KeyboardInterrupt:
    sys.exit(1)
except RuntimeError, e:
    sys.exit(e)
