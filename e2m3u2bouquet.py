#!/usr/bin/env python2
# -*- coding:utf-8 -*-
"""
e2m3u2bouquet.e2m3u2bouquet -- Enigma2 IPTV m3u to bouquet parser

@author:     Dave Sully, Doug Mackay, Dorik1972
@copyright:  2017 All rights reserved.
@license:    GNU GENERAL PUBLIC LICENSE version 3
@deffield    updated: Updated
"""

from __future__ import print_function
import sys, os, glob

# Uppend the directory for custom modules at the front of the path.
ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, 'modules'))
map(lambda x: sys.path.insert(0, x), glob.glob(os.path.join(ROOT_DIR, 'modules', '*.whl')))

import time
import gzip
import errno
import ntplib
import requests
import threading
import ctypes, ctypes.util
import SocketServer
import SimpleHTTPServer
try:
    from PIL import Image
    from io import BytesIO
    USE_PIL=True
except:
    USE_PIL=False
from slugify import slugify
from datetime import datetime
from socket import socket, AF_INET, SOCK_DGRAM
from collections import OrderedDict
from requests_file import FileAdapter
from requests.utils import requote_uri, re
from urllib3.packages.six.moves.urllib.parse import parse_qs, urlparse, quote
from urllib3.exceptions import InsecureRequestWarning
# Suppress the SSL warning from urllib3
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
try:
    from enigma import eDVBDB
except ImportError:
    pass

__all__ = []
__version__ = '0.9.9.9'
__date__ = '2017-06-04'
__updated__ = '2020-03-01'

DEBUG = 0
TESTRUN = 0
IMPORTED = False

ENIGMAPATH = '/etc/enigma2/'
CFGPATH = os.path.join(ENIGMAPATH, 'e2m3u2bouquet/')

EPGIMPORTPATH = '/etc/epgimport/'
CROSSEPGPATH = '/usr/crossepg/providers/'
PICONSPATH = '/usr/share/enigma2/picon/'

# HIDDEN_MARKER = '#SERVICE 1:519:1:0:0:0:0:0:0:0:'
HIDDEN_MARKER = '#SERVICE 1:832:d:0:0:0:0:0:0:0:'

NAMESPACE = '1010101'
PORT = 10001
DEFAULTEPG = 'http://epg.openboxfan.com/xmltv-t-sd.xml.gz'

REQHEADERS = {'User-Agent': 'Mozilla/5.0 (SmartHub; SMART-TV; U; Linux/SmartTV; Maple2012) AppleWebKit/534.7 (KHTML, like Gecko) SmartTV Safari/534.7'}

# Global and local m3u playlist TAG's
TAG_PATTERN = re.compile(r'.*?(url-logo|url-tvg|url-epg|tvg-id|tvg-name|tvg-logo|group-title)=[\'"](.*?)[\'"]')
# URL-link validation
ip_middle_octet = u"(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5]))"
ip_last_octet = u"(?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))"

URL_PATTERN = re.compile(
                         u"^"
                         # protocol identifier
                         u"(?:(?:https?|rtsp|rtp|mmp)://)"
                         # user:pass authentication
                         u"(?:\S+(?::\S*)?@)?"
                         u"(?:"
                         u"(?P<private_ip>"
                         # IP address exclusion
                         # private & local networks
                         u"(?:(?:10|127)" + ip_middle_octet + u"{2}" + ip_last_octet + u")|"
                         u"(?:(?:169\.254|192\.168)" + ip_middle_octet + ip_last_octet + u")|"
                         u"(?:172\.(?:1[6-9]|2\d|3[0-1])" + ip_middle_octet + ip_last_octet + u"))"
                         u"|"
                         # IP address dotted notation octets
                         # excludes loopback network 0.0.0.0
                         # excludes reserved space >= 224.0.0.0
                         # excludes network & broadcast addresses
                         # (first & last IP address of each class)
                         u"(?P<public_ip>"
                         u"(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])"
                         u"" + ip_middle_octet + u"{2}"
                         u"" + ip_last_octet + u")"
                         u"|"
                         # host name
                         u"(?:(?:[a-z\u00a1-\uffff0-9]-?)*[a-z\u00a1-\uffff0-9]+)"
                         # domain name
                         u"(?:\.(?:[a-z\u00a1-\uffff0-9]-?)*[a-z\u00a1-\uffff0-9]+)*"
                         # TLD identifier
                         u"(?:\.(?:[a-z\u00a1-\uffff]{2,}))"
                         u")"
                         # port number
                         u"(?::\d{2,5})?"
                         # resource path
                         u"(?:/\S*)?"
                         # query string
                         u"(?:\?\S*)?"
                         u"$",
                         re.UNICODE | re.IGNORECASE
                        )


class SimpleServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass):
        SocketServer.TCPServer.__init__(self, server_address, RequestHandlerClass)

class CLIError(Exception):
    """Generic exception to raise and log different fatal errors."""
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "E: %s" % msg

    def __str__(self):
        return self.msg

    def __unicode__(self):
        return self.msg

def _set_time():
    """ Get NTP time and set system time
    """
    c = ntplib.NTPClient()
    for host in ['pool.ntp.org', 'time.google.com', 'time.cloudflare.com', 'time.apple.com', 'time.nist.gov']:
        try:
            response = c.request(host, version=3, port=123)
        except Exception as e:
            pass
        else:
            time_tuple = time.localtime(response.tx_time)
            # http://linux.die.net/man/3/clock_settime
            CLOCK_REALTIME = 0

            class timespec(ctypes.Structure):
                _fields_ = [('tv_sec', ctypes.c_long),
                            ('tv_nsec', ctypes.c_long)]

            librt = ctypes.CDLL(ctypes.util.find_library('rt'))
            ts = timespec()
            ts.tv_sec = int( time.mktime(datetime( *time_tuple[:6]).timetuple() ))
            ts.tv_nsec = time_tuple[6] * 1000000 # Millisecond to nanosecond
            librt.clock_settime(CLOCK_REALTIME, ctypes.byref(ts))
            return

def display_welcome():
    print('\n********************************')
    print('Starting Enigma2 IPTV bouquets v{}'.format(__version__))
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    print("********************************\n")

def display_end_msg():
    print("\n********************************")
    print("Enigma2 IPTV bouquets created ! ")
    print("********************************")
    print("\nTo enable EPG data")
    print("Please open EPG-Importer or CrossEPG plugin... ")
    print("Select EPG sources of imported providers and enable the new IPTV source")
    print("and then manually import the data from the selected sources. Save the selected sources.")
    print("(In EPG-Importer will be listed as under 'IPTV Bouquet Maker - E2m3u2bouquet')")
    print("You can then set EPG importers to automatically import according to preferred schedule")

def make_config_folder():
    """Create config folder if it doesn't exist
    """
    try:
        os.makedirs(CFGPATH)
    except OSError, e:  # race condition guard
        if e.errno != errno.EEXIST:
            raise

def url_validate(url):
    """ URL string validation
    """
    return re.compile(URL_PATTERN).match(url)

def uninstaller():
    """Clean up routine to remove any previously made changes
    """
    Provider._update_status('Uninstaller', 'Running uninstall')
    print(Status.message)
    try:
        # Bouquets
        print('Removing old IPTV bouquets...')
        map(lambda fname: os.remove(os.path.join(ENIGMAPATH, fname)) if 'userbouquet.e2m3u2b_iptv_' in fname else os.remove(os.path.join(ENIGMAPATH, fname)) if 'bouquets.tv.bak' in fname else None, os.listdir(ENIGMAPATH))
        # Custom Channels and sources
        print('Removing IPTV custom channels...')
        if os.path.isdir(EPGIMPORTPATH):
            map(lambda fname: os.remove(os.path.join(EPGIMPORTPATH, fname)) if 'e2m3u2b_iptv_' in fname else None, os.listdir(EPGIMPORTPATH))
        if os.path.isdir(CROSSEPGPATH):
            map(lambda fname: os.remove(os.path.join(CROSSEPGPATH, fname)) if 'e2m3u2b_iptv_' in fname else None, os.listdir(CROSSEPGPATH))
        # bouquets.tv
        print('Removing IPTV bouquets from bouquets.tv...')
        os.rename(os.path.join(ENIGMAPATH, 'bouquets.tv'), os.path.join(ENIGMAPATH, 'bouquets.tv.bak'))
        with open(os.path.join(ENIGMAPATH, 'bouquets.tv'), 'w+') as tvfile, \
               open(os.path.join(ENIGMAPATH, 'bouquets.tv.bak'), 'r') as bakfile:
            tvfile.writelines([l for l in bakfile if '.e2m3u2b_iptv_' not in l])

    except Exception:
        print('Unable to uninstall')
        raise
    Provider._update_status('Uninstaller', 'Uninstall complete')
    print(Status.message)

def get_selfip():
    # connecting to a UDP address doesn't send packets
    try:
        return [(s.connect(('1.1.1.1', 0)), s.getsockname()[0], s.close()) for s in [socket(AF_INET, SOCK_DGRAM)]][0][1]
    except:
       Provider._update_status('Network checker', 'Network is unreachable')
       sys.exit()

def web_server():
    os.chdir(os.path.join(CFGPATH, 'epg'))
    server = threading.Thread(target=SimpleServer((get_selfip(), PORT), SimpleHTTPServer.SimpleHTTPRequestHandler).serve_forever)
    server.setDaemon(True)
    server.start()

def get_category_title(cat, category_options):
    """Return the title override if set else the title
    """
    if cat in category_options:
        return category_options[cat]['nameOverride'] if category_options[cat].get('nameOverride', False) else cat
    return cat

def get_service_title(channel):
    """Return the title override if set else the title
    """
    return channel['nameOverride'] if channel.get('nameOverride', False) else channel['stream-name']

def reload_bouquets():
    if not TESTRUN:
        Provider._update_status('Reload bouquets', 'Reloading bouquets')
        print(Status.message)
        try:
            eDVBDB.getInstance().reloadServicelist()
            eDVBDB.getInstance().reloadBouquets()
        except:
            r = requests.get('http://{}/web/servicelistreload?mode=2'.format(get_selfip()), timeout=5, verify=False) # reload Servicelist & Bouquets
            r.close()
        print('bouquets reloaded...')

def progressbar(count, total, bar_len=50, status=''):
    """ Simple progressbar indicator to stdout output
    """
    filled_len = int(round(bar_len * count / float(total)))
    percents = round(100.0 * count / float(total), 1)
    bar = '=' * filled_len + '-' * (bar_len - filled_len)
    sys.stdout.write('\r[%s] %s%% ... %s' % (bar, percents, status))
    sys.stdout.flush()

def get_parser_args(program_license, program_version_message):

    from argparse import ArgumentParser, RawDescriptionHelpFormatter

    parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
    # URL Based Setup
    urlgroup = parser.add_argument_group('URL Based Setup')
    urlgroup.add_argument('-m', '--m3uurl', dest='m3uurl', action='store',
                          help='URL to download m3u data from (required)')
    urlgroup.add_argument('-e', '--epgurl', dest='epgurl', action='store',
                          help='URL source for XML TV epg data sources')
    # Provider based setup
    providergroup = parser.add_argument_group('Provider Based Setup')
    providergroup.add_argument('-n', '--providername', dest='providername', action='store',
                               help='Host IPTV provider name (e.g. FAB/EPIC) (required)')
    # Options
    parser.add_argument('-sttv', '--streamtype_tv', dest='sttv', action='store', type=int,
                        help='Stream type for TV (e.g. 1, 4097, 5001 or 5002)')
    parser.add_argument('-stvod', '--streamtype_vod', dest='stvod', action='store', type=int,
                        help='Stream type for VOD (e.g. 4097, 5001 or 5002)')
    parser.add_argument('-M', '--multivod', dest='multivod', action='store_true',
                        help='Create multiple VOD bouquets rather single VOD bouquet')
    parser.add_argument('-a', '--allbouquet', dest='allbouquet', action='store_true',
                        help='Create all channels bouquet')
    parser.add_argument('-P', '--picons', dest='picons', action='store_true',
                        help='Automatically download of Picons, this option will slow the execution')
    parser.add_argument('-q', '--iconpath', dest='iconpath', action='store',
                        help='Option path to store picons, if not supplied defaults to /usr/share/enigma2/picon/')
    parser.add_argument('-xs', '--xcludesref', dest='xcludesref', action='store_true',
                        help='Disable service ref overriding from override.xml file')
    parser.add_argument('-bt', '--bouquettop', dest='bouquettop', action='store_true',
                        help='Place IPTV bouquets at top')
    parser.add_argument('-U', '--uninstall', dest='uninstall', action='store_true',
                        help='Uninstall all changes made by this script')
    parser.add_argument('-V', '--version', action='version', version=program_version_message)
    return parser

class Status(object):
    is_running = False
    message = ''

class ProviderConfig(object):
    def __init__(self):
        self.name = ''
        self.enabled = False
        self.settings_level = '0'
        self.m3u_url = ''
        self.epg_url = ''
        self.streamtype_tv = '4097'
        self.streamtype_vod = '4097'
        self.multi_vod = False
        self.all_bouquet = False
        self.picons = False
        self.icon_path = ''
        self.sref_override = False
        self.bouquet_top = False
        # 4097 Gstreamer options (0-no buffering, 1-buffering enabled, 3- http progressive download & buffering enabl )
        self.gstreamer = '0'
        # 5002 ExtEplayer3 options
        self.flv2mpeg4 = '0'     # EXT3_FLV2MPEG4_CONVERTER
        self.progressive = '0'   # EXT3_PLAYBACK_PROGRESSIVE
        self.live_ts = '1'       # EXT3_PLAYBACK_LIVETS
        # 5001 GstPlayer options
        self.ring_buffer_maxsize = 32768   # GST_RING_BUFFER_MAXSIZE
        self.buffer_size = 8192            # GST_BUFFER_SIZE
        self.buffer_duration = 0           # GST_BUFFER_DURATION

class Provider(object):
    def __init__(self, config):
        self._panel_bouquet_file = ''
        self._panel_bouquet = {}
        self._category_order = []
        self._category_options = {}
        self._dictchannels = OrderedDict()
        self._xmltv_sources_list = {}
        self.config = config

    def _download_picon_file(self, service, total):

        count, x = service
#        logo_url, title = x['tvg-logo'], slugify(get_service_title(x), separator='', replacements=[['&', 'and'], ['+', 'plus'], ['*', 'star']]) # tvg-logo + SNP
        logo_url, title = x['tvg-logo'], slugify(x['serviceRef'], separator='_', lowercase=False).upper() # tvg-logo + SNR

        # Get the full picon file name with path without ext
        pfile_name = os.path.join(self.config.icon_path, title)

        if not filter(os.path.isfile, glob.glob(pfile_name + '*')):
            if DEBUG:
                print("Picon file doesn't exist downloading\nPiconURL: {}".format(logo_url))
            try:
                with requests.get(logo_url, headers=REQHEADERS, timeout=(5,30), verify=False) as r:
                    r.raise_for_status()
                    im = Image.open(BytesIO(r.content))
                    if im.format is None:
                       raise ValueError('Not valid image format!')
                    im.thumbnail((220, 132))
                    if DEBUG:
                        print('Save picon: {}.{}'.foramt(title, 'png'))
                    im.convert('RGBA').save('{}.{}'.format(pfile_name, 'png'), format='PNG')
            except Exception, e:
                if DEBUG:
                    print('Unable to download or convert logo image to PNG\n{}\n'.format(logo_url), repr(e))
                # create an empty picon so that we don't retry this picon
                open('{}.{}'.format(pfile_name, 'None'), 'a').close()

        if not (IMPORTED and DEBUG):
            # don't output when called from the plugin
            progressbar(count, total, status='Done')

    def _parse_panel_bouquet(self):
        """Check providers bouquet for custom service references
        """
        for line in self._panel_bouquet_file:
             if '#SERVICE' in line:
                 # get service ref values we need (dict value) and stream file (dict key)
                 service = line.strip().split(':')
                 if len(service) == 11:
                     pos = service[10].rfind('/')
                     if pos != -1 and (pos + 1 != len(service[10])):
                         key = service[10][pos + 1:]
                         value = ':'.join(service[1:9])
                         if value != '0:1:0:0:0:0:0:0:0':
                             # only add to dict if a custom service id is present
                             self._panel_bouquet[key] = value

    def _set_streamtypes_vodcats(self, service_dict):
        """Set the stream types and VOD categories
        """
        is_vod = re.search('.*\.(3g2|3gp|3gp2|3gpp|3gpp2|asf|asx|avi|bin|dat|drv|\
                                 f4v|flv|gtp|h264|m4v|mkv|mod|moov|mov|mpeg|mpg|mts|\
                                 mpv|rm|rmvb|spl|swf|qt|vcd|vid|vob|webm|wm|wmv|yuv)',\
                           os.path.splitext(urlparse(service_dict['stream-url']).path)[-1], re.I)

        if is_vod is None:
            service_dict['stream-type'] = str(self.config.streamtype_tv) if self.config.streamtype_tv else '4097'
        else:
            service_dict['category_type'] = 'vod'
            service_dict['group-title'] = 'VOD - {}'.format(service_dict['group-title'])
            service_dict['stream-type'] = '4097' if not self.config.streamtype_vod else str(self.config.streamtype_vod)

    def _parse_map_bouquet_xml(self):
        """Check for bouquets within mapping override file and applies if found
        """
        category_order = []
        mapping_file = self._get_mapping_file()
        if mapping_file:
            Provider._update_status(self.config.name, 'Parsing custom bouquet order')
            print(Status.message)

            try:
                tree = ET.parse(mapping_file).getroot()
                for node in tree.findall(".//category"):
                    dictoption = {}

                    category = node.attrib.get('name').decode('utf-8')
                    cat_title_override = node.attrib.get('nameOverride', '').decode('utf-8')
                    dictoption['nameOverride'] = cat_title_override
                    dictoption['idStart'] = int(node.attrib.get('idStart', '0')) if node.attrib.get('idStart', '0').isdigit() else 0
                    dictoption['enabled'] = node.attrib.get('enabled', True) == 'true'
                    category_order.append(category)

                    # If this category is marked as custom and doesn't exist in self._dictchannels then add
                    if node.attrib.get('customCategory', False) == 'true':
                        dictoption['customCategory'] = True
                        if category not in self._dictchannels:
                            self._dictchannels[category] = []

                    self._category_options[category] = dictoption

                Provider._update_status(self.config.name, 'Custom bouquet order applied')
                print(Status.message)
            except Exception:
                msg = 'Corrupt override.xml file'
                print(msg)
                if DEBUG:
                    raise msg

        return category_order

    def _set_category_type(self):
        """set category type (live/vod)
        """
        for cat in self._category_order:
            if cat != 'VOD':
                if self._dictchannels.get(cat):
                    if self._category_options.get(cat) is None:
                        # dictoption
                        self._category_options[cat] = {'nameOverride': '', 'idStart': 0, 'enabled': True,
                                                       'customCategory': False, type: 'live'}
                    # set category type (live/vod) to same as first stream in cat
                    self._category_options[cat]["type"] = self._dictchannels[cat][0].get("category_type", "live")
            else:
                if self._category_options.get(cat) is None:
                    # dictoption
                    self._category_options[cat] = {'nameOverride': '', 'idStart': 0, 'enabled': True,
                                                   'customCategory': False, type: 'vod'}


    def _parse_map_channels_xml(self):
        """Check for channels within mapping override file and apply if found
        """
        mapping_file = self._get_mapping_file()
        if mapping_file:
            Provider._update_status(self.config.name, 'Parsing custom channel order, please be patient')
            print(Status.message)

            try:
                tree = ET.parse(mapping_file).getroot()
                i = 0
                for cat in self._dictchannels:
                    if self._category_options[cat].get('type', 'live') == 'live':
                        # Only override live (not vod) streams
                        sortedchannels = []

                        # find channels that are to be moved to this category (categoryOverride)
                        for node in tree.findall('.//channel[@categoryOverride="{}"]'.format(cat)):
                            node_name = node.attrib.get('name').decode('utf-8')
                            category = node.attrib.get('category').decode('utf-8')
                            channel_index = None

                            # get index of channel in the current category
                            try:
                                channel_index = next((self._dictchannels[category].index(item) for item in self._dictchannels[category]
                                                      if item['stream-name'] == node_name), None)
                            except KeyError:
                                pass

                            if channel_index is not None:
                                # remove from existing category and add to new
                                self._dictchannels[cat].append(self._dictchannels[category].pop(channel_index))

                        listchannels = [x['stream-name'] for x in self._dictchannels[cat]]

                        for node in tree.findall('.//channel[@category="{}"]'.format(cat)):
                            # Check for placeholders, give unique name, insert into sorted channels and dictchannels[cat]
                            node_name = node.attrib.get('name')

                            if node_name == 'placeholder':
                                node_name = 'placeholder_' + str(i)
                                listchannels.append(node_name)
                                self._dictchannels[cat].append({'stream-name': node_name})
                                i += 1
                            sortedchannels.append(node_name)

                        sortedchannels.extend(listchannels)
                        # remove duplicates, keep order
                        listchannels = OrderedDict((x, True) for x in sortedchannels).keys()

                        # sort the channels by new order
                        channel_order_dict = {channel: index for index, channel in enumerate(listchannels)}
                        self._dictchannels[cat].sort(key=lambda x: channel_order_dict[x['stream-name']])
                Provider._update_status(self.config.name, 'Custom channel order applied')
                print(Status.message)

                # apply overrides
                channel_nodes = tree.iter('channel')
                for override_channel in channel_nodes:
                    name = override_channel.attrib.get('name').decode('utf-8')
                    category = override_channel.attrib.get('category').decode('utf-8')
                    category_override = override_channel.attrib.get('categoryOverride').decode('utf-8')
                    channel_index = None

                    if category_override:
                        # check if the channel has been moved to the new category
                        try:
                            channel_index = next((self._dictchannels[category_override].index(item) for item in self._dictchannels[category_override]
                                              if item['stream-name'] == name), None)
                        except KeyError:
                            pass

                    channels_list = self._dictchannels.get(category_override) if category_override and channel_index is not None else self._dictchannels.get(category)

                    if channels_list and name != 'placeholder':
                        for x in channels_list:
                            if x['stream-name'] == name:
                                if override_channel.attrib.get('enabled') == 'false':
                                    x['enabled'] = False
                                x['nameOverride'] = override_channel.attrib.get('nameOverride', '')
                                x['categoryOverride'] = override_channel.attrib.get('categoryOverride', '')
                                # default to current values if attribute doesn't exist
                                x['tvg-id'] = override_channel.attrib.get('tvg-id', x['tvg-id'])
                                if override_channel.attrib.get('serviceRef', None) and self.config.sref_override:
                                    x['serviceRef'] = override_channel.attrib.get('serviceRef', x['serviceRef'])
                                    x['serviceRefOverride'] = True
                                # streamUrl no longer output to xml file but we still check and process it
                                x['stream-url'] = override_channel.attrib.get('streamUrl', x['stream-url'])
                                if override_channel.attrib.get('clearStreamUrl') == 'true':
                                    x['stream-url'] = ''
                                break
                Provider._update_status(self.config.name, 'Custom overrides applied')
                print(Status.message)
            except Exception:
                msg = 'Corrupt {}-sort-override.xml'.format(slugify(self.config.name))
                print(msg)
                if DEBUG:
                    raise msg

    def _get_mapping_file(self):
        mapping_file = None
        search_path = [os.path.join(CFGPATH, 'epg', slugify(self.config.name)+'-sort-override.xml'),
                       os.path.join(os.getcwd(), 'epg', slugify(self.config.name)+'-sort-override.xml')]
        for path in search_path:
            if os.path.isfile(path):
                mapping_file = path
                break;
        return mapping_file

    def _save_bouquet_entry(self, f, channel):
        """Add service to userbouquet file
        """
        if not channel['stream-name'].startswith('placeholder_'):
            REFTYPE = channel['serviceRef'].split(':')[0]
            player_property = vars(self.config)
            if REFTYPE in ('1', '4097'):
                f.write('#SERVICE {}:{}:{}\n'.format(channel['serviceRef'], quote(channel['stream-url'], safe="!#$%&'()*+,/;=?@[]~"), get_service_title(channel)))
            if REFTYPE == '5001':
                params = '#sapp_ring_buffer_maxsize={ring_buffer_maxsize}&sapp_buffer_size={buffer_size}&sapp_buffer_duration={buffer_duration}'.format(**player_property)
                if channel.get('user-agent'):
                    params += '&User-Agent={}'.format(channel['user-agent'])
                url = quote(channel['stream-url'] + params, safe='!#$%&"()*+,/;=?@[]~')
                f.write('#SERVICE {}:{}:{}\n'.format(channel['serviceRef'], url, get_service_title(channel)))
            if REFTYPE == '5002':
                params = '#sapp_flv2mpeg4={flv2mpeg4}&sapp_progressive={progressive}&sapp_live_ts={live_ts}'.format(**player_property)
                if channel.get('user-agent'):
                    params += '&User-Agent={}'.format(channel['user-agent'])
                url = quote(channel['stream-url'] + params, safe='!#$%&"()*+,/;=?@[]~')
                f.write('#SERVICE {}:{}:{}\n'.format(channel['serviceRef'], url, get_service_title(channel)))

            f.write('#DESCRIPTION {}\n'.format(get_service_title(channel)))
        else:
            f.write('{}\n'.format(HIDDEN_MARKER))

    def _get_bouquet_index_name(self, cat_filename, provider_filename):
        return ('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.e2m3u2b_iptv_{}_{}.tv" ORDER BY bouquet\n'.format(provider_filename, cat_filename))

    def _save_bouquet_index_entries(self, iptv_bouquets):
        """Add to the main bouquets.tv file
        """
        if iptv_bouquets:
            # get current bouquets indexes
            current_bouquet_indexes = self._get_current_bouquet_indexes()
            with open(os.path.join(ENIGMAPATH, 'bouquets.tv'), 'w') as f:
                f.write('#NAME Bouquets (TV)\n')
                if self.config.bouquet_top:
                    f.writelines(iptv_bouquets)
                    f.writelines(current_bouquet_indexes)
                else:
                    f.writelines(current_bouquet_indexes)
                    f.writelines(iptv_bouquets)

    def _get_current_bouquet_indexes(self):
        """Get all the bouquet indexes except this provider
        """
        with open(os.path.join(ENIGMAPATH, 'bouquets.tv'), 'r') as f:
            return [l for l in f if not any([l.startswith('#NAME'), '.e2m3u2b_iptv_{}'.format(slugify(self.config.name)) in l])]

    def _create_all_channels_bouquet(self):
        """Create the Enigma2 all channels bouquet
        """
        bouquet_indexes = []

        vod_categories = [cat for cat in self._category_order if self._category_options[cat].get('type', 'live') == 'vod']
        bouquet_name = 'All Channels'
        cat_filename = slugify(bouquet_name)
        provider_filename = slugify(self.config.name)

        # create file
        bouquet_filepath = os.path.join(ENIGMAPATH, 'userbouquet.e2m3u2b_iptv_{}_{}.tv'.format(provider_filename, cat_filename))
        if DEBUG:
            print("Creating: {}".format(bouquet_filepath))
        Provider._update_status(self.config.name, 'Create all channels bouquet'.format())

        with open(bouquet_filepath, 'w+') as f:
            f.write('#NAME {} - {}\n'.format(self.config.name, bouquet_name))
            # write place holder channels (for channel numbering)
            f.writelines(['{}\n'.format(HIDDEN_MARKER) for i in xrange(100)])
            channel_num = 1

            for cat in self._category_order:
                if cat in self._dictchannels:
                    if cat not in vod_categories:
                        # Insert group description placeholder in bouquet
                        f.write('#SERVICE 1:64:0:0:0:0:0:0:0:0:\n')
                        f.write('#DESCRIPTION {}\n'.format(get_category_title(cat, self._category_options)))
                        for x in self._dictchannels[cat]:
                            if x.get('enabled') or x['stream-name'].startswith('placeholder_'):
                                self._save_bouquet_entry(f, x)
                            channel_num += 1

                        while (channel_num % 100) is not 0:
                            f.write('{}\n'.format(HIDDEN_MARKER))
                            channel_num += 1

        # Add to bouquet index list
        bouquet_indexes.append(self._get_bouquet_index_name(cat_filename, provider_filename))
        Provider._update_status(self.config.name, 'All channels bouquet created')
        print(Status.message)
        return bouquet_indexes

    def _create_crossepg_source(self, sources, group=None):
        """Create CrossEPG source file
        """
        # Channels list xml
        channels_filename = 'http://{}:{}/e2m3u2b_iptv_{}_channels.xml.gz'.format(get_selfip(), PORT, slugify(self.config.name))
        # write providers epg feed
        source_filename = os.path.join(CROSSEPGPATH, 'e2m3u2b_iptv_{}.conf'.format(slugify(self.config.name)))

        with open(source_filename, 'w+') as f:
            f.write('description={}\n'.format(self.config.name))
            f.write('protocol=xmltv\n')
            for count, (k, v) in enumerate(sources.iteritems()):
                f.write('channels_url_{}={}\n'.format(count, channels_filename))
                f.write('epg_url_{}={}\n'.format(count, v[0]))
            f.write('preferred_language=eng\n')

    def _create_epgimport_source(self, sources, group=None):
        """Create EPG-importer source file
        """

        indent = "\t"
        source_name = '{} - {}'.format(slugify(self.config.name, lowercase=False), group) if group else slugify(self.config.name, lowercase=False)
        channels_filename = 'http://{}:{}/e2m3u2b_iptv_{}_channels.xml.gz'.format(get_selfip(), PORT, slugify(self.config.name))

        # write providers epg feed
        source_filename = os.path.join(EPGIMPORTPATH, 'e2m3u2b_iptv_{}.sources.xml'.format(slugify(source_name)))

        with open(source_filename, 'w+') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\r\n')
            f.write('<!-- Automatically generated by the e2m3u2b for {} -->\n'.format(xml_escape(self.config.name)))
            f.write('<sources>\n')
            f.write('{}<sourcecat sourcecatname="IPTV Bouquet Maker/{}">\n'.format(indent, xml_escape(source_name)))
            for k, v in sources.iteritems():
                f.write('{}<source type="gen_xmltv" nocheck="1" channels="{}">\n'.format(2 * indent, channels_filename))
                f.write('{}<description>{}</description>\n'.format(3 * indent, xml_escape(k)))
                f.write('{}<url>{}</url>\n'.format(3 * indent, v[0]))
                f.write('{}</source>\n'.format(2 * indent))
            f.write('{}</sourcecat>\n'.format(indent))
            f.write('</sources>\n')

    def _get_category_id(self, cat):
        """Generate 32 bit category id to help make service refs unique"""
        return requests.auth.hashlib.md5(self.config.name + cat.encode('utf-8')).hexdigest()[:8]

    @staticmethod
    def _update_status(name, message):
        Status.message = '\n[{}]: {}'.format(name, message)

    def process_provider(self):
        Status.is_running = True

        # Set picon path
        if self.config.icon_path is None or TESTRUN == 1:
            self.config.icon_path = PICONSPATH
        if self.config.name is None:
            self.config.name = "E2m3u2Bouquet"

        # Requote URL's after user input to prevent the use of invalid characters
        self.config.m3u_url = requote_uri(self.config.m3u_url)
        self.config.epg_url = requote_uri(self.config.epg_url)

        # Download & parse m3u to _dictchannels
        self.download_m3u()

        if self._dictchannels:
            self.parse_data()

            self.parse_map_xmltvsources_xml()
            # save xml mapping - should be after m3u parsing
            self.save_map_xml()

            # Download picons
            if self.config.picons:
                self.download_picons()
            # Create bouquet files
            self.create_bouquets()
            # Now create custom channels for each bouquet
            Provider._update_status(self.config.name, 'Creating EPGImporter & CrossEPG configs')
            print(Status.message)
            self.create_epg_config()
            Provider._update_status(self.config.name, 'EPGImporter & CrossEPG configs created')
            print(Status.message)

        Status.is_running = False

    def download_epg(self):
        """Get EPG file from link in some cases
        """
        try:
            fname = slugify(self.config.name) + '_' + self.config.epg_url[self.config.epg_url.rfind("/")+1:]
            with requests.get(self.config.epg_url, headers=REQHEADERS, timeout=(5,30), stream=True, allow_redirects=True, verify=False) as epg, \
                open(os.path.join(CFGPATH, 'epg', fname), 'wb') as f:
                    epg.raise_for_status()
                    for chunk in epg.iter_content(chunk_size=8192):
                        f.write(chunk)
            self.config.epg_url = 'http://{}:{}/{}'.format(get_selfip(), PORT, fname)
        except Exception, e:
            if DEBUG:
                raise e
            pass

    def get_tvgid(self, title):
        return slugify(title,
                       replacements=[
                                     ['A1', 'amedia1'], ['A2', 'amedia2'],
                                     ['international', 'int'],
                                     ['ый', 'iy'],
                                     ['ий', 'iy'],
                                     ['сю', 'syu'],
                                     ['лю', 'lyu'],
                                     ['мье', 'me'],
                                     ['ї', 'i'],
                                     ['я', 'ya'],
                                     ['х', 'h'],
                                     [' +2', 'plus2'], [' +4', 'plus4'], [' +6', 'plus6'], [' +7', 'plus7'], [' +8', 'plus8'], ['+', 'plus'],
                                    ])

    def download_m3u(self):
        """Get M3U file and parse it

        tags description: https://howlingpixel.com/i-en/M3U
        m3u example:

        #EXTM3U url-tvg="http://tvguide.epg:8000/1234/987654321.xml" url-logo="http://www.logoserver.com/logos/" m3uautoload=1 cache=1500 deinterlace=auto
        #EXTINF:0 tvg-name="Important Channel" tvg-language="English" tvg-country="US" tvg-id="imp-001" tvg-logo="http://pathlogo/logo.jpg" group-title="Top10", Discovery Channel cCloudTV.ORG (Top10) (US) (English)
        #EXTGRP:Top10  (optional derective)
        http://167.114.102.27/live/Eem9fNZQ8r_FTl9CXevikA/1461268502/a490ae75a3ec2acf16c9f592e889eb4c.m3u8|User-Agent=Mozilla%2F5.0%20(Windows%20NT%206.1%3B%20WOW64)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F47.0.2526.106%20Safari%2F537.36
        """
        Provider._update_status(self.config.name, 'Downloading M3U file')
        print(Status.message)
        if DEBUG:
            print('m3uurl = {}'.format(self.config.m3u_url))
        try:
            s = requests.Session()
            s.mount('file://', FileAdapter())
            s.stream = True
            # Get playlist from URL or local m3u M3U ('file:///path/to/file')
            with s.get(self.config.m3u_url, headers=REQHEADERS, timeout=(5,30), verify=False) as r:
                r.raise_for_status()
                Provider._update_status(self.config.name, 'Parsing M3U file')
                print(Status.message)

                def service_dict_template():
                    dict = {}.fromkeys(['url-logo', 'url-tvg', 'url-epg', 'tvg-id', 'tvg-name', 'tvg-logo', 'user-agent',
                                        'nameOverride', 'categoryOverride', 'serviceRef', ], '')
                    dict.update({'group-title': 'NoGroup', 'category_type': 'live', 'has_archive': False, 'enabled': True, 'serviceRefOverride': False, })
                    return dict

                service_dict = service_dict_template()

                for line in r.iter_lines():
                    line = line.decode('utf-8-sig')

                    if line.startswith('#EXTM3U'):
                        # Global M3U TAGs url-tvg|url-epg|url-logo
                        service_dict.update(dict(TAG_PATTERN.findall(line)))
                        urllogo = service_dict.get('url-logo', '')
                        if self.config.epg_url == '':
                            self.config.epg_url = service_dict.get('url-tvg', service_dict.get('url-epg', DEFAULTEPG))
                        if not url_validate(self.config.epg_url):
                            self.config.epg_url = DEFAULTEPG
                        if self.config.epg_url.startswith('https://'):
                            self.download_epg()
                        service_dict = service_dict_template()
                        continue

                    elif line.startswith('#EXTINF:'):
                        try:
                            extInfData, name = line.split(',')
                        except:
                            extInfData, name = line, None

                        service_dict.update(dict(TAG_PATTERN.findall(extInfData)))

                        if name is None:
                            name = service_dict.get('tvg-name')
                            if name == '':
                                if DEBUG:
                                    print("No TITLE info found for this service - skip")
                                continue
                        service_dict.update({'stream-name': name.strip()})

                        tvglogo = service_dict.get('tvg-logo')
                        if not url_validate(tvglogo) and url_validate(urllogo):
                            service_dict.update({'tvg-logo': requests.compat.urljoin(urllogo, tvglogo)})
                        if self.config.epg_url == DEFAULTEPG:
                            service_dict.update({'tvg-id': self.get_tvgid(service_dict.get('stream-name'))})

                    elif line.startswith('#EXTGRP:') and name:
                        if service_dict.get('group-title') == 'NoGroup':
                            try:
                                service_dict.update({'group-title': line.split(':')[1].strip()})
                            except:
                                pass

                    elif line.startswith('#EXTVLCOPT:') and name:
                        params = {k:v for k,v in [x.split('=') for x in line.split(':') if '=' in x]}
                        if 'http-user-agent' in params:
                            service_dict.update({'user-agent': params.get('http-user-agent').strip()})

                    elif url_validate(line) and name:
                        service_dict.update({'stream-url': line.strip()})
                        self._set_streamtypes_vodcats(service_dict)
                        #Set default name for any blank groups and update channels dict
                        self._dictchannels.setdefault(service_dict['group-title'].decode('utf-8'), []).append(service_dict)
                        service_dict = service_dict_template()

            if not self._dictchannels:
                print("No extended playlist info found. Check m3u url should be 'type=m3u_plus'")

        except Exception, e:
            print(e)
            if DEBUG:
                raise e
            Provider._update_status(self.config.name, 'Unable to download M3U file')
            print(Status.message)

    def parse_data(self):
        # sort categories by custom order (if exists)
        sorted_categories = self._parse_map_bouquet_xml()
        self._category_order = self._dictchannels.keys()
        sorted_categories.extend(self._category_order)
        # remove duplicates, keep order
        self._category_order = OrderedDict((x, True) for x in sorted_categories).keys()
        self._set_category_type()

        # Check for and parse override map
        self._parse_map_channels_xml()

        # Add Service references
        catstartnum = 34000  # serviceid_start
        category_offset = 150

        for cat in self._category_order:
            num = catstartnum
            if cat in self._dictchannels:
                if cat in self._category_options:
                    # check if we have cat idStart from override file
                    if self._category_options[cat]["idStart"] > 0:
                        num = self._category_options[cat]["idStart"]
                    else:
                        self._category_options[cat]["idStart"] = num
                else:
                    self._category_options[cat] = {"idStart": num}

                for x in self._dictchannels[cat]:
                    cat_id = self._get_category_id(cat)
                    #	SID:NS:TSID:ONID:STYPE:UNUSED(channelnumber in enigma1)
                    #	X   X  X    X    D     D

                    #	REFTYPE:FLAGS:STYPE:SID:TSID:ONID:NS:PARENT_SID:PARENT_TSID:UNUSED
                    #	D       D     X     X   X    X    X  X          X           X

                    #               SID : TID  : ONID : Namespace"
                    #             {:04x}:{:04x}:{:04x}:{:08x}
                    service_ref = '{:04x}:{}:{}:{}'.format(num, cat_id[:4].lstrip('0'), cat_id[4:].lstrip('0'), NAMESPACE)

                    if not x['stream-name'].startswith('placeholder_'):
                        if self._panel_bouquet and not x.get('serviceRefOverride'):
                            # check if we have the panels custom service ref
                            pos = x['stream-url'].rfind('/')
                            if pos != -1 and (pos + 1 != len(x['stream-url'])):
                                m3u_stream_file = x['stream-url'][pos + 1:]
                                if m3u_stream_file in self._panel_bouquet:
                                    # have a match use the panels custom service ref
                                    x['serviceRef'] = "{}:{}".format(x['stream-type'],self._panel_bouquet[m3u_stream_file])
                                    continue

                        if not x.get('serviceRefOverride'):
                            # if service ref is not overridden in xml update
                            x['serviceRef'] = {'1'   : "{}:0:1:{}:0:0:{}".format(x['stream-type'], service_ref, self.config.gstreamer),
                                               '4097': "{}:0:1:{}:0:0:{}".format(x['stream-type'], service_ref, self.config.gstreamer),
                                               '5001': "{}:0:1:{}:0:0:0".format(x['stream-type'], service_ref),
                                               '5002': "{}:0:1:{}:0:0:0".format(x['stream-type'], service_ref),
                                               }[x['stream-type']]

                        num += 1
                    else:
                        x['serviceRef'] = HIDDEN_MARKER
            while catstartnum < num:
                catstartnum += category_offset

        vod_index = None
        # if we have the vod category placeholder from the override use it otherwise
        # place at end
        vod_index = self._category_order.index("VOD") if "VOD" in self._category_order else len(self._category_order)

        if vod_index is not None:
            # move all VOD categories to VOD placeholder position or place at end
            vod_categories = list((cat for cat in self._category_order if self._category_options[cat].get('type', 'live') == 'vod'))
            if len(vod_categories):
                # remove the vod category(s) from current position
                self._category_order = [x for x in self._category_order if x not in vod_categories]
                # insert the vod category(s) at the placeholder / first pos
                self._category_order[vod_index:vod_index] = vod_categories
                try:
                    self._category_order.remove("VOD")
                except ValueError:
                    pass  # ignore exception

        # Have a look at what we have
        if DEBUG and TESTRUN:
            with open(os.path.join(CFGPATH, 'channels.debug'), "w+") as datafile:
                for cat in self._category_order:
                    if cat in self._dictchannels:
                        for line in self._dictchannels[cat]:
                            linevals = ""
                            for key, value in line.items():
                                if type(value) is bool:
                                    linevals += str(value) + ":"
                                else:
                                    linevals += value.encode("utf-8") + ":"
                            datafile.write("{}\n".format(linevals))

        Provider._update_status(self.config.name, 'M3U successfully parsed')
        print(Status.message)

    def download_picons(self):
        if not USE_PIL:
            Provider._update_status(self.config.name, 'Python PIL module not found. Download picons - disabled!')
            print(Status.message)
            return

        Provider._update_status(self.config.name, 'Downloading Picon files, please be patient')
        print(Status.message)
        print('If no Picons exist this will take a few minutes')
        try:
            os.makedirs(self.config.icon_path)
        except OSError, e:  # race condition guard
            if e.errno != errno.EEXIST:
                raise

        for cat in self._dictchannels:
            Provider._update_status(self.config.name, 'Update picons for {}'.format(cat))
            print(Status.message)
            # Download picons if not VOD
            services = [ x for x in self._dictchannels[cat]
                             if self._category_options[cat].get('type', 'live') == 'live'
                             and not x['stream-name'].startswith('placeholder_')
                             and url_validate(x.get('tvg-logo'))]
            total = len(services)
            map(lambda x: self._download_picon_file(x, total), enumerate(services, start=1))

        Provider._update_status(self.config.name, 'Picons download completed')
        print(Status.message)
        print('To display picons, you must reboot the device...')

    def parse_map_xmltvsources_xml(self):
        """Check for a mapping override file and parses it if found
        """
        self._xmltv_sources_list = {}
        mapping_file = self._get_mapping_file()
        if mapping_file:
            try:
                tree = ET.parse(mapping_file).getroot()
                for group in tree.findall('.//xmltvextrasources/group'):
                    self._xmltv_sources_list['{} - {}'.format(self.config.name, group.attrib.get('id'))] = [url.text for url in group] # Group-name list
            except Exception:
                msg = 'Corrupt {} file'.format(mapping_file)
                print(msg)
                if DEBUG:
                    raise msg

    def save_map_xml(self):
        """Create mapping file"""
        mappingfile = os.path.join(CFGPATH, 'epg', slugify(self.config.name)+'-sort-current.xml')
        indent = "\t"
        vod_category_output = False

        if self._dictchannels:
            with open(mappingfile, 'wb') as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\r\n')
                f.write('<!-- Automatically generated by the e2m3u2b for {} -->\n'.format(xml_escape(self.config.name)))
                f.write('<!--\r\n')
                f.write('{} E2m3u2bouquet Custom mapping file\r\n'.format(indent))
                f.write('{} Rearrange bouquets or channels in the order you wish\r\n'.format(indent))
                f.write('{} Disable bouquets or channels by setting enabled to "false"\r\n'.format(indent))
                f.write('{} Map DVB EPG to IPTV by changing channel serviceRef attribute to match DVB service reference\r\n'.format(indent))
                f.write('{} Map XML EPG to different feed by changing channel tvg-id attribute\r\n'.format(indent))
                f.write('{} Rename this file as {}-sort-override.xml for changes to apply\r\n'.format(indent, slugify(self.config.name)))
                f.write('-->\r\n')

                f.write('<mapping>\r\n')
                f.write('{}<xmltvextrasources>\r\n'.format(indent))
                if not self._xmltv_sources_list:
                    # output example config
                    f.write('{}<!-- Example Config\r\n'.format((2 * indent)))
                    # IPTV EPG by R.Rusya (gz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'EPG openboxfan full by R.Rusya for IPTV'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://epg.openboxfan.com/xmltv-t-sd.xml.gz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # IPTV EPG by Igor-K (gz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'EPG by Igor-K for IPTV'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://runigma.com.ua/EPG/IPTV/epg-iptv.xml.gz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # IPTV EPG by iptvx.one project (gz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'EPG by iptvx.one for IPTV'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://iptvx.one/epg/epg.xml.gz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # UK - Freeview (xz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'UK - Freeview (xz)'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.xmltvepg.nl/rytecUK_Basic.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.ipservers.eu/epg_data/rytecUK_Basic.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.wanwizard.eu/rytecUK_Basic.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://91.121.106.172/~rytecepg/epg_data/rytecUK_Basic.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.vuplus-community.net/rytec/rytecUK_Basic.xz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # UK - FTA (xz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'UK - FTA (xz)'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.xmltvepg.nl/rytecUK_FTA.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.ipservers.eu/epg_data/rytecUK_FTA.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.wanwizard.eu/rytecUK_FTA.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://91.121.106.172/~rytecepg/epg_data/rytecUK_FTA.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.vuplus-community.net/rytec/rytecUK_FTA.xz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # UK - International (xz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'UK - International (xz)'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.xmltvepg.nl/rytecUK_int.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.ipservers.eu/epg_data/rytecUK_int.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.wanwizard.eu/rytecUK_int.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://91.121.106.172/~rytecepg/epg_data/rytecUK_int.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.vuplus-community.net/rytec/rytecUK_int.xz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # UK - Sky Live (xz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'UK - Sky Live (xz)'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.xmltvepg.nl/rytecUK_SkyLive.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.ipservers.eu/epg_data/rytecUK_SkyLive.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.wanwizard.eu/rytecUK_SkyLive.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://91.121.106.172/~rytecepg/epg_data/rytecUK_SkyLive.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.vuplus-community.net/rytec/rytecUK_SkyLive.xz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # UK - Sky Dead (xz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'UK - Sky Dead (xz)'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.xmltvepg.nl/rytecUK_SkyDead.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.ipservers.eu/epg_data/rytecUK_SkyDead.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.wanwizard.eu/rytecUK_SkyDead.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://91.121.106.172/~rytecepg/epg_data/rytecUK_SkyDead.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.vuplus-community.net/rytec/rytecUK_SkyDead.xz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    # UK - Sports/Movies (xz)
                    f.write('{}<group id="{}">\r\n'.format(2 * indent, 'UK - Sports/Movies (xz)'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.xmltvepg.nl/rytecUK_SportMovies.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.ipservers.eu/epg_data/rytecUK_SportMovies.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://rytecepg.wanwizard.eu/rytecUK_SportMovies.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://91.121.106.172/~rytecepg/epg_data/rytecUK_SportMovies.xz'))
                    f.write('{}<url>{}</url>\r\n'.format(3 * indent, 'http://www.vuplus-community.net/rytec/rytecUK_SportMovies.xz'))
                    f.write('{}</group>\r\n'.format(2 * indent))
                    f.write('{}-->\r\n'.format(2 * indent))

                else:
                    for group in self._xmltv_sources_list:
                        f.write('{}<group id="{}">\r\n'.format(2 * indent, xml_escape(group)))
                        f.writelines(['{}<url>{}</url>\r\n'.format(3 * indent, xml_escape(source)) for source in self._xmltv_sources_list[group]])
                        f.write('{}</group>\r\n'.format(2 * indent))
                f.write('{}</xmltvextrasources>\r\n'.format(indent))

                f.write('{}<categories>\r\n'.format(indent))
                for cat in self._category_order:
                    if cat in self._dictchannels:
                        if self._category_options[cat].get('type', 'live') == 'live':
                            cat_title_override = self._category_options[cat].get('nameOverride', '')
                            f.write('{}<category name="{}" nameOverride="{}" idStart="{}" enabled="{}" customCategory="{}"/>\r\n'
                                    .format(2 * indent,
                                            xml_escape(cat),
                                            xml_escape(cat_title_override),
                                            self._category_options[cat].get('idStart', ''),
                                            str(self._category_options[cat].get('enabled', True)).lower(),
                                            str(self._category_options[cat].get('customCategory', False)).lower()
                                            ))
                        elif not vod_category_output:
                            # Replace multivod categories with single VOD placeholder
                            cat_title_override = ''
                            cat_enabled = True
                            if 'VOD' in self._category_options:
                                cat_title_override = self._category_options['VOD'].get('nameOverride', '')
                                cat_enabled = self._category_options['VOD'].get('enabled', True)
                            f.write('{}<category name="{}" nameOverride="{}" enabled="{}" />\r\n'
                                    .format(2 * indent, 'VOD', xml_escape(cat_title_override), str(cat_enabled).lower()))
                            vod_category_output = True

                f.write('{}</categories>\r\n'.format(indent))
                f.write('{}<channels>\r\n'.format(indent))

                for cat in self._category_order:
                    if cat in self._dictchannels:
                        # Don't output any of the VOD channels
                        if self._category_options[cat].get('type', 'live') == 'live':
                            f.write('{}<!-- {} -->\r\n'.format(2 * indent, xml_escape(cat)))
                            for x in self._dictchannels[cat]:
                                if not x['stream-name'].startswith('placeholder_'):
                                    f.write('{}<channel name="{}" nameOverride="{}" tvg-id="{}" enabled="{}" category="{}" categoryOverride="{}" serviceRef="{}" clearStreamUrl="{}" />\r\n'
                                            .format(2 * indent,
                                                    xml_escape(x['stream-name']),
                                                    xml_escape(x.get('nameOverride', '')),
                                                    xml_escape(x['tvg-id']),
                                                    str(x['enabled']).lower(),
                                                    xml_escape(x['group-title']),
                                                    xml_escape(x.get('categoryOverride', '')),
                                                    xml_escape(x['serviceRef']),'false' if x['stream-url'] else 'true'
                                                    ))
                                else:
                                    f.write('{}<channel name="{}" category="{}" />\r\n'.format(2 * indent, 'placeholder', xml_escape(cat)))

                f.write('{}</channels>\r\n'.format(indent))
                f.write('</mapping>')

    def create_bouquets(self):
        """Create the Enigma2 bouquets
        """
        Provider._update_status(self.config.name, 'Creating category bouquets')
        print(Status.message)
        # clean old bouquets before writing new
        if self._dictchannels:
            map(lambda fname: os.remove(os.path.join(ENIGMAPATH, fname)) if 'userbouquet.e2m3u2b_iptv_{}'.format(slugify(self.config.name)) in fname else None, os.listdir(ENIGMAPATH))
        # If the option not to create Multi Bouquets is selected,
        # then create an All bouquet by default and return
        # If the playlist does not contain group-title tags we do not create uesrbouquets
        # and forcibly create all channels bouquet and return
        if not self.config.multi_vod or len(self._category_order) == 1:
            self._save_bouquet_index_entries(self._create_all_channels_bouquet())
            return

        if self.config.multi_vod and self.config.all_bouquet:
            iptv_bouquet_list = self._create_all_channels_bouquet()
        else:
            iptv_bouquet_list = []

        vod_categories = [cat for cat in self._category_order if self._category_options[cat].get('type', 'live') == 'vod']
        vod_category_output = False
        vod_bouquet_entry_output = False
        channel_number_start_offset_output = False

        for cat in self._category_order:
            if self._category_options[cat].get('type', 'live') == 'live':
                cat_enabled = self._category_options.get(cat, {}).get('enabled', True)
            else:
                cat_enabled = self._category_options.get('VOD', {}).get('enabled', True)

            if cat in self._dictchannels and cat_enabled:
                cat_title = get_category_title(cat, self._category_options)
                # create file
                cat_filename = slugify(cat_title)
                provider_filename = slugify(self.config.name)

                if cat in vod_categories and not self.config.multi_vod:
                    cat_filename = "VOD"

                bouquet_filepath = os.path.join(ENIGMAPATH, 'userbouquet.e2m3u2b_iptv_{}_{}.tv'.format(provider_filename, cat_filename))

                if DEBUG:
                    print("Creating: {}".format(bouquet_filepath))

                if cat not in vod_categories or self.config.multi_vod:
                    with open(bouquet_filepath, 'w+') as f:
                        bouquet_name = '{} - {}'.format(self.config.name, cat_title).decode("utf-8")
                        if self._category_options[cat].get('type', 'live') == 'live':
                            if cat in self._category_options and self._category_options[cat].get('nameOverride', False):
                                bouquet_name = self._category_options[cat]['nameOverride'].decode('utf-8')
                        else:
                            if 'VOD' in self._category_options and self._category_options['VOD'].get('nameOverride', False):
                                bouquet_name = '{} - {}'\
                                    .format(self._category_options['VOD']['nameOverride'].decode('utf-8'),
                                            cat_title.replace('VOD - ', '').decode("utf-8"))
                        channel_num = 0
                        f.write('#NAME {}\n'.format(bouquet_name))
                        if not channel_number_start_offset_output and not self.config.all_bouquet:
                            # write place holder services (for channel numbering)
                            f.writelines(['{}\n'.format(HIDDEN_MARKER) for i in xrange(100)])
                            channel_number_start_offset_output = True
                            channel_num += 1

                        for x in self._dictchannels[cat]:
                            if x.get('enabled') or x['stream-name'].startswith('placeholder_'):
                                self._save_bouquet_entry(f, x)
                            channel_num += 1

                        while (channel_num % 100) is not 0:
                            f.write('{}\n'.format(HIDDEN_MARKER))
                            channel_num += 1

                elif not vod_category_output and not self.config.multi_vod:
                    # not multivod - output all the vod services in one file
                    with open(bouquet_filepath, 'w+') as f:
                        bouquet_name = '{} - VOD'.format(self.config.name).decode('utf-8')
                        if 'VOD' in self._category_options and self._category_options['VOD'].get('nameOverride', False):
                            bouquet_name = self._category_options['VOD']['nameOverride'].decode('utf-8')

                        channel_num = 0
                        f.write('#NAME {}\n'.format(bouquet_name))
                        if not channel_number_start_offset_output and not self.config.all_bouquet:
                            # write place holder services (for channel numbering)
                            f.writelines(['{}\n'.format(HIDDEN_MARKER) for i in xrange(100)])
                            channel_number_start_offset_output = True
                            channel_num += 1

                        for vodcat in vod_categories:
                            if vodcat in self._dictchannels:
                                # Insert group description placeholder in bouquet
                                f.write('#SERVICE 1:64:0:0:0:0:0:0:0:0:\n')
                                f.write('#DESCRIPTION {}\n'.format(vodcat))
                                for x in self._dictchannels[vodcat]:
                                    self._save_bouquet_entry(f, x)
                                    channel_num += 1

                                while (channel_num % 100) is not 0:
                                    f.write('{}\n'.format(HIDDEN_MARKER))
                                    channel_num += 1
                        vod_category_output = True

                # Add to bouquet index list
                if cat not in vod_categories or (cat in vod_categories and not vod_bouquet_entry_output):
                    iptv_bouquet_list.append(self._get_bouquet_index_name(cat_filename, provider_filename))
                    if cat in vod_categories and not self.config.multi_vod:
                        vod_bouquet_entry_output = True

        # write the bouquets.tv indexes
        self._save_bouquet_index_entries(iptv_bouquet_list)

        Provider._update_status(self.config.name, 'Category bouquets created')
        print(Status.message)

    def create_epg_config(self):
        if DEBUG:
            print('creating EPG config')
        # create channels file
        try:
            os.makedirs(os.path.join(CFGPATH, 'epg'))
        except OSError, e:  # race condition guard
            if e.errno != errno.EEXIST:
                raise
        indent = "\t"
        tvg_check = []

        if self._dictchannels:
            with gzip.open(os.path.join(CFGPATH, 'epg', 'e2m3u2b_iptv_{}_channels.xml.gz'.format(slugify(self.config.name))), 'wt') as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\n')
                f.write('<!-- Automatically generated by the e2m3u2b for {} -->\n'.format(xml_escape(self.config.name)))
                f.write('<channels>\n')

                for cat in self._category_order:
                     if cat in self._dictchannels and self._category_options.get(cat, {}).get('enabled', True):
                        if self._category_options[cat].get('type', 'live') == 'live':
                            cat_title = get_category_title(cat, self._category_options)
                            f.write('{}<!-- {} -->\n'.format(indent, xml_escape(cat_title)))

                            for x in self._dictchannels[cat]:
                                if x['enabled']:
                                    tvg_id = x.get('tvg-id')
                                    if tvg_id == '':
                                        tvg_check.append(True)
                                        tvg_id = self.get_tvgid(get_service_title(x))  # force to default value if tvg-id is empty
                                    f.write('{}<channel id="{}">{}:</channel> <!-- {} -->\n'
                                            .format(indent, xml_escape(tvg_id),
                                                       x['serviceRef'].replace(x['stream-type'], '1', 1), # force the epg channels to stream type '1'
                                                           xml_escape(get_service_title(x))))
                f.write('</channels>\n')

            if any(tvg_check) and self.config.epg_url != DEFAULTEPG:
                self._xmltv_sources_list.update({'{} - {}'.format(slugify(self.config.name, lowercase=False), 'Default EPG'): [DEFAULTEPG]})
            self._xmltv_sources_list.update({'{} - {}'.format(slugify(self.config.name, lowercase=False), 'Main EPG'): [self.config.epg_url]})
            # create epg-importer sources file for providers feed
            self._create_epgimport_source(self._xmltv_sources_list)
            # create CrossEPG sources file for providers feed
            self._create_crossepg_source(self._xmltv_sources_list)

class Config(object):
    def __init__(self):
        self.providers = OrderedDict()

    def make_default_config(self, configfile):
        print('Default configuration file created in {}\n'.format(os.path.join(CFGPATH, 'config.xml')))

        f = open(configfile, 'wb')
        f.write("""
<?xml version="1.0" encoding="utf-8"?>\r
<!-- Automatically generated by the e2m3u2b -->\r
<!--\r
    E2m3u2bouquet supplier config file\r
    Add as many suppliers as required and run the script with no parameters\r
    this config file will be used and the relevant bouquets set up for all suppliers entered\r
    0 = No/false\r
    1 = Yes/true\r
    For elements with <![CDATA[]] enter value between brackets e.g. <![CDATA[mypassword]]>\r
-->\r
<config>\r
    <supplier>\r
        <name>Supplier Name</name><!-- Supplier Name -->\r
        <enabled>1</enabled><!-- Enable or disable the supplier (0 or 1) -->\r
        <m3uurl><![CDATA[http://address.yourprovider.com:80/get.php?username=USERNAME&password=PASSWORD&type=m3u_plus&output=ts]]></m3uurl><!-- Extended M3U url -->\r
        <epgurl><![CDATA[http://address.yourprovider.com:80/xmltv.php?username=USERNAME&password=PASSWORD]]></epgurl><!-- XMLTV EPG url -->\r
        <streamtypetv>4097</streamtypetv><!-- (Optional) Custom TV stream type (e.g. 1, 4097, 5001 or 5002) -->\r
        <gstreamer>0</gstreamer><!-- (Optional) Stream type: 0 (no buffering), 1 (buffering enabled) or 3 (progressive download and buffering enabled) -->\r
        <flv2mpeg4>0</flv2mpeg4><!-- (Optional) EXT3_FLV2MPEG4_CONVERTER (0 or 1) -->\r
        <progressive>0</progressive><!-- (Optional) EXT3_PLAYBACK_PROGRESSIVE (0 or 1) -->\r
        <livets>0</livets><!-- (Optional) EXT3_PLAYBACK_LIVETS (0 or 1) -->\r
        <ringbuffermaxsize>32768</ringbuffermaxsize><!-- (Optional) GST_RING_BUFFER_MAXSIZE ring buffer size in kilobytes -->\r
        <buffersize>8192</buffersize><!-- (Optional) GST_BUFFER_SIZE buffer size in kilobytes -->\r
        <bufferduration>0</bufferduration><!-- (Optional) GST_BUFFER_DURATION buffer duration in seconds -->\r
        <streamtypevod></streamtypevod><!-- (Optional) Custom VOD stream type (e.g. 4097, 5001 or 5002) -->\r
        <multivod>1</multivod><!-- Split bouquets into seperate categories (0 or 1) -->\r
        <allbouquet>0</allbouquet><!-- Create all channels bouquet as separate bouquet if multivod enabled -->\r
        <picons>0</picons><!-- Automatically download Picons (0 or 1) -->\r
        <iconpath></iconpath><!-- Location to store picons. Do not fill if using GUI mode -->\r
        <xcludesref>1</xcludesref><!-- Disable service ref overriding from override.xml file (0 or 1) -->\r
        <bouquettop>0</bouquettop><!-- Place IPTV bouquets at top (0 or 1)-->\r
    </supplier>\r
    <supplier>\r
        <name>Supplier Name 1</name><!-- Supplier Name -->\r
        <enabled>0</enabled><!-- Enable or disable the supplier (0 or 1) -->\r
        <m3uurl><![CDATA[http://address.yourprovider.com:80/get.php?username=USERNAME&password=PASSWORD&type=m3u_plus&output=ts]]></m3uurl><!-- Extended M3U url -->\r
        <epgurl><![CDATA[http://address.yourprovider.com:80/xmltv.php?username=USERNAME&password=PASSWORD]]></epgurl><!-- XMLTV EPG url -->\r
        <streamtypetv>4097</streamtypetv><!-- (Optional) Custom TV service type (e.g. 1, 4097, 5001 or 5002) -->\r
        <gstreamer>0</gstreamer><!-- (Optional) Stream type: 0 (no buffering), 1 (buffering enabled) or 3 (progressive download and buffering enabled) -->\r
        <flv2mpeg4>0</flv2mpeg4><!-- (Optional) EXT3_FLV2MPEG4_CONVERTER (0 or 1) -->\r
        <progressive>0</progressive><!-- (Optional) EXT3_PLAYBACK_PROGRESSIVE (0 or 1) -->\r
        <livets>0</livets><!-- (Optional) EXT3_PLAYBACK_LIVETS (0 or 1) -->\r
        <ringbuffermaxsize>32768</ringbuffermaxsize><!-- (Optional) GST_RING_BUFFER_MAXSIZE ring buffer size in kilobytes -->\r
        <buffersize>8192</buffersize><!-- (Optional) GST_BUFFER_SIZE buffer size in kilobytes -->\r
        <bufferduration>0</bufferduration><!-- (Optional) GST_BUFFER_DURATION buffer duration in seconds -->\r
        <streamtypevod></streamtypevod><!-- (Optional) Custom VOD service type (e.g. 4097, 5001 or 5002) -->\r
        <multivod>1</multivod><!-- Split bouquets into seperate categories (0 or 1) -->\r
        <allbouquet>0</allbouquet><!-- Create all channels bouquet as separate bouquet if multivod enabled-->\r
        <picons>0</picons><!-- Automatically download Picons (0 or 1) -->\r
        <iconpath></iconpath><!-- Location to store picons. Do not fill if using GUI mode -->\r
        <xcludesref>1</xcludesref><!-- Disable service ref overriding from override.xml file (0 or 1) -->\r
        <bouquettop>0</bouquettop><!-- Place IPTV bouquets at top (0 or 1)-->\r
    </supplier>\r
</config>""")

    def read_config(self, configfile):
        """ Read Config from file """
        self.providers = OrderedDict()
        try:
            tree = ET.parse(configfile).getroot()
            for node in tree.findall('.//supplier'):
                provider = ProviderConfig()

                if node is not None:
                    for child in node:
                        value = child.text
                        if value:
                            value.strip()
                        if child.tag == 'name':
                            provider.name = '' if value is None else value.encode('utf-8')
                        if child.tag == 'enabled':
                            provider.enabled = (value == '1') == True
                        if child.tag == 'settingslevel':
                            provider.settings_level = '0' if value not in ('0', '1') else value
                        if child.tag == 'm3uurl':
                            provider.m3u_url = '' if value is None else value
                        if child.tag == 'epgurl':
                            provider.epg_url = '' if value is None else value
                        if child.tag == 'streamtypetv':
                            provider.streamtype_tv = '4097' if value not in ('1', '4097', '5001', '5002') else value
                        # 4097 Gstreamer options (0-no buffering, 1-buffering enabled, 3- http progressive download & buffering enabl)
                        if child.tag == 'gstreamer':
                            provider.gstreamer = '0' if value not in ('0', '1', '3') else value
                        # 5002 ExtEplayer3 options
                        if child.tag == 'flv2mpeg4':
                            provider.flv2mpeg4 = '0' if value not in ('0', '1') else value   # EXT3_FLV2MPEG4_CONVERTER
                        if child.tag == 'progressive':
                            provider.progressive = '0' if value not in ('0', '1') else value # EXT3_PLAYBACK_PROGRESSIVE
                        if child.tag == 'livets':
                            provider.live_ts = '0' if value not in ('0', '1') else value     # EXT3_PLAYBACK_LIVETS
                        # 5001 GstPlayer options
                        if child.tag == 'ringbuffermaxsize':
                            provider.ring_buffer_maxsize = 32768 if not value.isdigit() else int(value)         # GST_RING_BUFFER_MAXSIZE
                        if child.tag == 'buffersize ':
                            provider.buffer_size = 8192 if not value.isdigit() else int(value)                  # GST_BUFFER_SIZE
                        if child.tag == 'bufferduration':
                            provider.buffer_duration = 0 if not value.isdigit() else int(value)                 # GST_BUFFER_DURATION
                        if child.tag == 'streamtypevod':
                            provider.streamtype_vod = '' if value not in ('4097', '5001', '5002') else value
                        if child.tag == 'multivod':
                            provider.multi_vod = (value == '1') == True
                        if child.tag == 'allbouquet':
                            provider.all_bouquet = (value == '1') == True
                        if child.tag == 'picons':
                            provider.picons = (value == '1') == True
                        if child.tag == 'iconpath':
                            provider.icon_path = '' if value is None else value
                        if child.tag == 'xcludesref':
                            provider.sref_override = (value == '0') == True
                        if child.tag == 'bouquettop':
                            provider.bouquet_top = (value == '1') == True

                if provider.name:
                    self.providers[provider.name] = provider

        except Exception:
            msg = 'Corrupt {} file in {} provider'.format(configfile, provider.name)
            print(msg)
            if DEBUG:
                raise Exception(msg)

    def write_config(self):
        """Write providers to config file
        Manually write instead of using ElementTree so that we can format the file for easy human editing
        (inc. Windows line endings)
        """

        config_file = os.path.join(os.path.join(CFGPATH, 'config.xml'))
        indent = "\t"

        if self.providers:
            with open(config_file, 'wb') as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\r\n')
                f.write('<!-- Automatically generated by the e2m3u2b -->\r\n')
                f.write('<!--\r\n')
                f.write('{}E2m3u2bouquet supplier config file\r\n'.format(indent))
                f.write('{}Add as many suppliers as required\r\n'.format(indent))
                f.write('{}this config file will be used and the relevant bouquets set up for all suppliers entered\r\n'.format(indent))
                f.write('{}0 = No/False\r\n'.format(indent))
                f.write('{}1 = Yes/True\r\n'.format(indent))
                f.write('{}For elements with <![CDATA[]] enter value between empty brackets e.g. <![CDATA[mypassword]]>\r\n'.format(indent))
                f.write('-->\r\n')
                f.write('<config>\r\n')

                for key, provider in self.providers.iteritems():
                    f.write('{}<supplier>\r\n'.format(indent))
                    f.write('{}<name>{}</name><!-- Supplier Name -->\r\n'.format(2 * indent, xml_escape(provider.name)))
                    f.write('{}<enabled>{}</enabled><!-- Enable or disable the supplier (0 or 1) -->\r\n'.format(2 * indent, '1' if provider.enabled else '0'))
                    f.write('{}<settingslevel>{}</settingslevel><!-- GUI settings level (0 - simle, 1 - expert) -->\r\n'.format(2 * indent, provider.settings_level))
                    f.write('{}<m3uurl><![CDATA[{}]]></m3uurl><!-- Extended M3U url --> \r\n'.format(2 * indent, provider.m3u_url))
                    f.write('{}<epgurl><![CDATA[{}]]></epgurl><!-- XMLTV EPG url -->\r\n'.format(2 * indent, provider.epg_url))
                    f.write('{}<streamtypetv>{}</streamtypetv><!-- (Optional) Custom TV stream type (e.g. 1, 4097, 5001 or 5002) -->\r\n'.format(2 * indent, provider.streamtype_tv))
                    f.write('{}<gstreamer>{}</gstreamer><!-- (Optional) Stream type: 0 (no buffering), 1 (buffering enabled) or 3 (progressive download and buffering enabled) -->\r\n'.format(2 * indent, provider.gstreamer))
                    f.write('{}<flv2mpeg4>{}</flv2mpeg4><!-- (Optional) EXT3_FLV2MPEG4_CONVERTER (0 or 1) -->\r\n'.format(2 * indent, provider.flv2mpeg4))
                    f.write('{}<progressive>{}</progressive><!-- (Optional) EXT3_PLAYBACK_PROGRESSIVE (0 or 1) -->\r\n'.format(2 * indent, provider.progressive))
                    f.write('{}<livets>{}</livets><!-- (Optional) EXT3_PLAYBACK_LIVETS (0 or 1) -->\r\n'.format(2 * indent, provider.live_ts))
                    f.write('{}<ringbuffermaxsize>{}</ringbuffermaxsize><!-- (Optional) GST_RING_BUFFER_MAXSIZE ring buffer size in kilobytes -->\r\n'.format(2 * indent, provider.ring_buffer_maxsize))
                    f.write('{}<buffersize>{}</buffersize><!-- (Optional) GST_BUFFER_SIZE buffer size in kilobytes -->\r\n'.format(2 * indent, provider.buffer_size))
                    f.write('{}<bufferduration>{}</bufferduration><!-- (Optional) GST_BUFFER_DURATION buffer duration in seconds -->\r\n'.format(2 * indent, provider.buffer_duration))
                    f.write('{}<streamtypevod>{}</streamtypevod><!-- (Optional) Custom VOD stream type (e.g. 4097, 5001 or 5002) -->\r\n'.format(2 * indent, provider.streamtype_vod))
                    f.write('{}<multivod>{}</multivod><!-- Split bouquets into seperate categories (0 or 1) -->\r\n'.format(2 * indent, '1' if provider.multi_vod else '0'))
                    f.write('{}<allbouquet>{}</allbouquet><!-- Create all channels bouquet as separate bouquet if multivod enabled (0 or 1) -->\r\n'.format(2 * indent, '1' if provider.all_bouquet else '0'))
                    f.write('{}<picons>{}</picons><!-- Automatically download Picons (0 or 1) -->\r\n'.format(2 * indent, '1' if provider.picons else '0'))
                    f.write('{}<iconpath>{}</iconpath><!-- Location to store picons. Do not fill if using GUI mode -->\r\n'.format(2 * indent, provider.icon_path if provider.icon_path else ''))
                    f.write('{}<xcludesref>{}</xcludesref><!-- Disable service ref overriding from override.xml file (0 or 1) -->\r\n'.format(2 * indent, '0' if provider.sref_override else '1'))
                    f.write('{}<bouquettop>{}</bouquettop><!-- Place IPTV bouquets at top (0 or 1) -->\r\n'.format(2 * indent, '1' if provider.bouquet_top else '0'))
                    f.write('{}</supplier>\r\n'.format(indent))
                f.write('</config>\r\n')
        else:
            # no providers delete config file
            if os.path.isfile(os.path.join(CFGPATH, 'config.xml')):
                print('No providers remove config')
                os.remove(os.path.join(CFGPATH, 'config.xml'))


def main(argv=None):  # IGNORE:C0111
    # Command line options.
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)
    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%(prog)s {} ({})'.format(program_version, program_build_date)
    program_shortdesc = __doc__.split("\n")[1]
    program_license = """{}

  Copyright 2017. All rights reserved.
  Created on {}.
  Licensed under GNU GENERAL PUBLIC LICENSE version 3
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
""".format(program_shortdesc, str(__date__))

    try:
        # Setup argument parser
        parser = get_parser_args(program_license, program_version_message)
        args = parser.parse_args()
        uninstall = args.uninstall

        # Core program logic starts here
        display_welcome()

        if uninstall:
            # Clean up any existing files
            uninstaller()
            # reload bouquets
            reload_bouquets()
            print("Uninstall only, program exiting ...")
            sys.exit(1)  # Quit here if we just want to uninstall
        else:
            make_config_folder()

        # create provider from command line based setup (if passed)
        args_config = ProviderConfig()
        args_config.m3u_url = args.m3uurl
        args_config.epg_url = args.epgurl
        args_config.multi_vod = args.multivod
        args_config.all_bouquet = args.allbouquet
        args_config.picons = args.picons
        args_config.icon_path = args.iconpath
        args_config.sref_override = not args.xcludesref
        args_config.bouquet_top = args.bouquettop
        args_config.name = args.providername
        args_config.streamtype_tv = args.sttv
        args_config.streamtype_vod = args.stvod

        if args_config.m3u_url:
            print('\n**************************************')
            print('E2m3u2bouquet - Command line based setup')
            print('**************************************\n')
            args_provider = Provider(args_config)
            args_provider.process_provider()
            reload_bouquets()
            display_end_msg()
        else:
            print('\n********************************')
            print('E2m3u2bouquet - Config based setup')
            print('********************************\n')
            e2m3u2b_config = Config()
            if os.path.isfile(os.path.join(CFGPATH, 'config.xml')):
                e2m3u2b_config.read_config(os.path.join(CFGPATH, 'config.xml'))

                for key, provider_config in e2m3u2b_config.providers.iteritems():
                    if provider_config.enabled:
                        if provider_config.name.startswith('Supplier Name'):
                            print("Please enter your details in the config file in - {}".format(os.path.join(CFGPATH, 'config.xml')))
                            sys.exit(2)
                        else:
                            print('\n********************************')
                            print('Config based setup - {}'.format(provider_config.name))
                            print('********************************\n')
                            provider = Provider(provider_config)
                            provider.process_provider()
                    else:
                        print('\nProvider: {} is disabled - skipping.........\n'.format(provider_config.name))

                reload_bouquets()
                display_end_msg()
            else:
                e2m3u2b_config.make_default_config(os.path.join(CFGPATH, 'config.xml'))
                print('Please ensure correct command line options are passed to the program \n'
                      'or populate the config file in {} \n'
                      'for help use --help\n'.format(os.path.join(CFGPATH, 'config.xml')))
                parser.print_usage()
                sys.exit(1)

    except KeyboardInterrupt:
        # handle keyboard interrupt
        return 0

    except Exception, e:
        if DEBUG:
            raise e
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2

if __name__ == "__main__":
    try:
        _set_time()
        web_server()
    except: pass
    if TESTRUN:
        EPGIMPORTPATH = "H:/Satelite Stuff/epgimport/"
        CROSSEPGPATH = "H:/Satelite Stuff/usr/crossepg/providers/"
        ENIGMAPATH = "H:/Satelite Stuff/enigma2/"
        PICONSPATH = "H:/Satelite Stuff/picons/"
        CFGPATH = os.path.join(ENIGMAPATH, 'e2m3u2bouquet/')
    sys.exit(main())
else:
    IMPORTED = True
