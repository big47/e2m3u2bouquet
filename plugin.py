# -*- coding: utf-8 -*-
#for localized messages
from . import _

import os
import log
import time
import errno
import enigma

from menu import E2m3u2b_Menu
from menu import E2m3u2b_Check

from enigma import eTimer
from Components.config import config, ConfigOnOff, ConfigSubsection, \
                              ConfigYesNo, ConfigClock, ConfigText, \
                              ConfigSelection, ConfigSubDict, ConfigSelectionNumber
from Components.PluginComponent import plugins
from Components.Harddisk import harddiskmanager
from Screens.MessageBox import MessageBox
from Plugins.Plugin import PluginDescriptor
from Tools.Directories import fileExists, createDir
from twisted.internet import threads
import twisted.python.runtime
try:
	from Tools.StbHardware import setRTCtime
except:
	from Tools.DreamboxHardware import setRTCtime

import e2m3u2bouquet

try:
    import Plugins.Extensions.EPGImport.EPGImport as EPGImport
    import Plugins.Extensions.EPGImport.EPGConfig as EPGConfig
except ImportError:
    EPGImport = EPGConfig = None

# Global variable
autoStartTimer = None
_session = None
providers_list = {}
piconPaths = []

try:
    e2m3u2bouquet._set_time()
    nowTime = time.time()
    if nowTime > 1514808000:
	setRTCtime(nowTime)
        print>>log, '[e2m3u2b] [{}] Set system time from NTP'.format(time.strftime('%c', time.localtime(int(time.time()))))
except: pass

try:
    e2m3u2bouquet.web_server()
    print>>log, '[e2m3u2b] [{}] Web service on port {} started'.format(time.strftime('%c', time.localtime(int(time.time()))), e2m3u2bouquet.PORT)
except: pass

def initPiconPaths():
    global piconPaths
    piconPaths = []
    piconPaths.append(e2m3u2bouquet.PICONSPATH)
    map(lambda part: onMountpointAdded(part.mountpoint), harddiskmanager.getMountedPartitions())

def onMountpointAdded(mountpoint):
    global piconPaths
    path = os.path.join(mountpoint, 'picon') + '/'
    if path not in piconPaths:
        piconPaths.append(path)

def onMountpointRemoved(mountpoint):
    global piconPaths
    path = os.path.join(mountpoint, 'picon') + '/'
    try:
        piconPaths.remove(path)
    except:
        pass

def onPartitionChange(why, part):
    if why == 'add':
        onMountpointAdded(part.mountpoint)
    elif why == 'remove':
        onMountpointRemoved(part.mountpoint)

def getMounted():
    global piconPaths
    harddiskmanager.on_partition_list_change.append(onPartitionChange)
    initPiconPaths()
    return piconPaths

# Set default configuration
config.plugins.e2m3u2b = ConfigSubsection()
config.plugins.e2m3u2b.autobouquetupdate = ConfigYesNo(default=False)
config.plugins.e2m3u2b.scheduletype = ConfigSelection(default='interval', choices=['interval', 'fixed time'])
config.plugins.e2m3u2b.updateinterval = ConfigSelectionNumber(default=6, min=2, max=48, stepwidth=1)
config.plugins.e2m3u2b.schedulefixedtime = ConfigClock(default=0)
config.plugins.e2m3u2b.autobouquetupdateatboot = ConfigYesNo(default=False)
config.plugins.e2m3u2b.iconpath = ConfigSelection(default=e2m3u2bouquet.PICONSPATH, choices=getMounted())
config.plugins.e2m3u2b.last_update = ConfigText()
config.plugins.e2m3u2b.extensions = ConfigYesNo(default=False)
config.plugins.e2m3u2b.mainmenu = ConfigYesNo(default=False)
config.plugins.e2m3u2b.do_epgimport = ConfigYesNo(default=False)
config.plugins.e2m3u2b.debug = ConfigOnOff(default=False)
config.plugins.e2m3u2b.cfglevel = ConfigText(default='')

class AutoStartTimer:
    def __init__(self, session):
        self.session = session
        self.timer = eTimer()
        self.timer.callback.append(self.on_timer)
        self.update()

    def get_wake_time(self):
        print>> log, '[e2m3u2b] [{}] AutoStartTimer -> get_wake_time'.format(time.strftime('%c', time.localtime(int(time.time()))))
        if config.plugins.e2m3u2b.autobouquetupdate.value:
            if config.plugins.e2m3u2b.scheduletype.value == 'interval':
                interval = int(config.plugins.e2m3u2b.updateinterval.value)
                nowt = time.time()
                # set next wakeup value to now + interval
                return int(nowt) + (interval * 60 * 60)
            elif config.plugins.e2m3u2b.scheduletype.value == 'fixed time':
                # convert the config clock to a time
                fixed_time_clock = config.plugins.e2m3u2b.schedulefixedtime.value
                now = time.localtime(time.time())

                fixed_wake_time = int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, fixed_time_clock[0],
                                                   fixed_time_clock[1], now.tm_sec, now.tm_wday, now.tm_yday, now.tm_isdst)))
                return fixed_wake_time
        else:
            return -1

    def update(self):
        print>>log, '[e2m3u2b] [{}] AutoStartTimer -> update'.format(time.strftime('%c', time.localtime(int(time.time()))))
        self.timer.stop()
        wake = self.get_wake_time()
        nowt = time.time()
        now = int(nowt)

        if wake > 0:
            if wake <= now:
                # new wake time is in past set to the future time / interval
                if config.plugins.e2m3u2b.scheduletype.value == 'interval':
                    interval = int(config.plugins.e2m3u2b.updateinterval.value)
                    wake += interval * 60 * 60  # add interval in hours if wake up time is in past
                elif config.plugins.e2m3u2b.scheduletype.value == 'fixed time':
                    wake += 60 * 60 * 24  # add 1 day to fixed time if wake up time is in past

            next_wake = wake - now
            self.timer.startLongTimer(next_wake)
        else:
            wake = -1

        print>> log, '[e2m3u2b] [{}] Next wake up time {}'.format(time.strftime('%c', time.localtime(now)), time.strftime('%c', time.localtime(wake)))
        return wake

    def on_timer(self):
        self.timer.stop()
        now = int(time.time())
        wake = now
        print>> log, '[e2m3u2b] [{}] on_timer occured'.format(time.strftime('%c', time.localtime(now)))
        print>> log, '[e2m3u2b] Stating bouquet update because auto update bouquet schedule is enabled'

        if config.plugins.e2m3u2b.scheduletype.value == 'fixed time':
            wake = self.get_wake_time()

        # if close enough to wake time do bouquet update
        if wake - now < 60:
            try:
                start_update()
            except Exception, e:
                print>> log, "[e2m3u2b] on_timer Error:", e
                if config.plugins.e2m3u2b.debug.value:
                    raise
        self.update()

    def get_status(self):
        print>> log, '[e2m3u2b] [{}] AutoStartTimer -> getStatus'.format(time.strftime('%c', time.localtime(int(time.time()))))

def start_update(epgimport=None):
    """Run m3u channel update
    """
    e2m3u2b_config = e2m3u2bouquet.Config()
    if fileExists(os.path.join(e2m3u2bouquet.CFGPATH, 'config.xml')):
        e2m3u2b_config.read_config(os.path.join(e2m3u2bouquet.CFGPATH, 'config.xml'))

        providers_to_process = []
        epgimport_sourcefiles = []

        for key, provider_config in e2m3u2b_config.providers.iteritems():
            if provider_config.enabled and not provider_config.name.startswith('Supplier Name'):
                providers_to_process.append(provider_config)
                epgimport_sourcefilename = os.path.join(e2m3u2bouquet.EPGIMPORTPATH, 'e2m3u2b_iptv_{}.sources.xml'
                                                        .format(e2m3u2bouquet.slugify(provider_config.name)))
                epgimport_sourcefiles.append(epgimport_sourcefilename)

        if twisted.python.runtime.platform.supportsThreads():
            d = threads.deferToThread(start_process_providers, providers_to_process, e2m3u2b_config)
            d.addCallback(start_update_callback, epgimport_sourcefiles, int(time.time()), epgimport)
        else:
            start_process_providers(providers_to_process, e2m3u2b_config)
            start_update_callback(None, epgimport_sourcefiles, int(time.time()), epgimport)


def start_update_callback(result, epgimport_sourcefiles, start_time, epgimport=None):
    elapsed_secs = (int(time.time())) - start_time

    msg = 'Finished bouquets update in {}s'.format(str(elapsed_secs))
    e2m3u2bouquet.Status.message = msg
    print>> log, '[e2m3u2b] [{}] {}'.format(time.strftime('%c', time.localtime(int(time.time()))), msg)

    # Attempt automatic epg import is option enabled and epgimport plugin detected
    if EPGImport and config.plugins.e2m3u2b.do_epgimport.value is True:
        if epgimport is None:
            epgimport = EPGImport.EPGImport(enigma.eEPGCache.getInstance(), lambda x: True)

        sources = [s for s in epgimport_sources(epgimport_sourcefiles)]
        sources.reverse()
        epgimport.sources = sources
        epgimport.onDone = epgimport_done
        epgimport.beginImport(longDescUntil=time.time() + (5 * 24 * 3600))


def start_process_providers(providers_to_process, e2m3u2b_config):
    try:
        e2m3u2bouquet._set_time()
        nowTime = time.time()
        if nowTime > 1514808000:
            setRTCtime(nowTime)
            print>>log, '[e2m3u2b] [{}] Set system time from NTP'.format(time.strftime('%c', time.localtime(int(time.time()))))
    except: pass

    for provider_config in providers_to_process:
        provider = e2m3u2bouquet.Provider(provider_config)

        # Use plugin config picon path if none set
        if not provider.config.icon_path:
            provider.config.icon_path = config.plugins.e2m3u2b.iconpath.value

        print>> log, '[e2m3u2b] [{}] Starting update: {}'.format(time.strftime('%c', time.localtime(int(time.time()))), provider.config.name)
        provider.process_provider()
        print>> log, '[e2m3u2b] [{}] Finished update: {}'.format(time.strftime('%c', time.localtime(int(time.time()))), provider.config.name)

    config.plugins.e2m3u2b.last_update.value = time.strftime('%c', time.localtime(time.time()))
    config.plugins.e2m3u2b.last_update.save()

    e2m3u2bouquet.reload_bouquets()

def epgimport_sources(sourcefiles):
    for sourcefile in sourcefiles:
        try:
            for s in EPGConfig.enumSourcesFile(sourcefile):
                yield s
        except Exception, e:
            print>> log, '[e2m3u2b] Failed top open epg source ', sourcefile, ' Error: ', e


def epgimport_done(reboot=False, epgfile=None):
    print>> log, '[e2m3u2b] [{}] Automatic epg import finished'.format(time.strftime('%c', time.localtime(int(time.time()))))


def do_reset():
    """Reset bouquets and
    epg importer config by running the script uninstall method
    """
    e2m3u2bouquet.uninstaller()
    e2m3u2bouquet.reload_bouquets()


def main(session, **kwargs):
    check_cfg_folder()
    set_default_do_epgimport()

    # Show message if EPG Import is not detected
    if not EPGImport:
        session.openWithCallback(open_menu(session), E2m3u2b_Check)
    else:
        open_menu(session)


def set_default_do_epgimport():
    if config.plugins.e2m3u2b.cfglevel.value == '1':
        # default to not try epg import if existing config exists
        config.plugins.e2m3u2b.do_epgimport.value = False
        config.plugins.e2m3u2b.do_epgimport.save()

def open_menu(session):
    session.open(E2m3u2b_Menu)

def check_cfg_folder():
    """Make config folder if it doesn't exist
    """
    try:
        createDir(e2m3u2bouquet.CFGPATH)
    except OSError, e:      # race condition guard
        if e.errno != errno.EEXIST:
            print>> log, "[e2m3u2b] unable to create config dir:", e
            if config.plugins.e2m3u2b.debug.value:
                raise

def done_configuring():
    """Check for new config values for auto start
    """
    print>>log, '[e2m3u2b] [{}] Done configuring'.format(time.strftime('%c', time.localtime(int(time.time()))))
    if autoStartTimer is not None:
        autoStartTimer.update()


def on_boot_start_check():
    """This will only execute if the
    config option autobouquetupdateatboot is true
    """
    now = int(time.time())
    # TODO Skip if there is an upcoming scheduled update
    print>>log, '[e2m3u2b] [{}] Stating bouquet update because auto update bouquet at start enabled'.format(time.strftime('%c', time.localtime(int(time.time()))))
    try:
        start_update()
    except Exception, e:
        print>> log, "[e2m3u2b] on_boot_start_check Error:", e
        if config.plugins.e2m3u2b.debug.value:
            raise

def autostart(reason, session=None, **kwargs):
    # reason is 0 at start and 1 at shutdown
    # these globals need declared as they are reassigned here
    global autoStartTimer
    global _session
    set_default_do_epgimport()

    print>>log, '[e2m3u2b] [{}] Autostart {} occured'.format(time.strftime('%c', time.localtime(time.time())), reason)
    if reason == 0 and _session is None:
        if session is not None:
            _session = session
            if autoStartTimer is None:
                autoStartTimer = AutoStartTimer(session)
            if config.plugins.e2m3u2b.autobouquetupdateatboot.value:
                on_boot_start_check()
    else:
        print>>log, '[e2m3u2b] [{}] Stop'.format(time.strftime('%c', time.localtime(time.time())))

def get_next_wakeup():
    # don't enable waking from deep standby for now
    print>> log, '[e2m3u2b] [{}] get_next_wakeup'.format(time.strftime('%c', time.localtime(time.time())))
    return -1

def menuHook(menuid):
    """ Called whenever a menu is created"""
    if menuid == "mainmenu":
        return [(plugin_name, quick_import_menu, plugin_name, 45)]
    return []

def extensions_menu(session, **kwargs):
    """ Needed for the extension menu descriptor
    """
    main(session, **kwargs)

def quick_import_menu(session, **kwargs):
    session.openWithCallback(quick_import_callback, MessageBox, _('Update of channels will start.\n'
                                                                  'This may take a few minutes.\n'
                                                                  'Proceed?'), MessageBox.TYPE_YESNO,
                                                                timeout=15, default=True)
def quick_import_callback(confirmed):
    if not confirmed:
        return
    try:
        start_update()
    except Exception, e:
        print>> log, "[e2m3u2b] manual_update_callback Error:", e
        if config.plugins.e2m3u2b.debug.value:
            raise

def update_extensions_menu(cfg_el):
    print>> log, '[e2m3u2b] [{}] update extensions menu'.format(time.strftime('%c', time.localtime(time.time())))
    try:
        if cfg_el.value:
            plugins.addPlugin(extDescriptorQuick)
        else:
            plugins.removePlugin(extDescriptorQuick)
    except Exception, e:
        print>> log, '[e2m3u2b] Failed to update extensions menu: ', e

def update_main_menu(cfg_el):
    print>> log, '[e2m3u2b] [{}] update main menu'.format(time.strftime('%c', time.localtime(time.time())))
    try:
        if cfg_el.value:
            plugins.addPlugin(extDescriptorQuickMain)
        else:
            plugins.removePlugin(extDescriptorQuickMain)
    except Exception, e:
        print>> log, '[e2m3u2b] Failed to update main menu: ', e

plugin_name = _('IPTV Bouquet Maker - Dorik edition')
plugin_description = _("Automated M3U playlists importer")

extDescriptor = PluginDescriptor(name=plugin_name, description=plugin_description, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=extensions_menu)
extDescriptorQuick = PluginDescriptor(name=plugin_name, description=plugin_description, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=quick_import_menu)
extDescriptorQuickMain = PluginDescriptor(name=plugin_name, description=plugin_description, where=PluginDescriptor.WHERE_MENU, fnc=menuHook)
config.plugins.e2m3u2b.extensions.addNotifier(update_extensions_menu, initial_call=False)
config.plugins.e2m3u2b.mainmenu.addNotifier(update_main_menu, initial_call=False)

def Plugins(**kwargs):
    result = [
        PluginDescriptor(
            name=plugin_name,
            description=plugin_description,
            where=[
                PluginDescriptor.WHERE_AUTOSTART,
                PluginDescriptor.WHERE_SESSIONSTART,
            ],
            fnc=autostart,
            wakeupfnc=get_next_wakeup
        ),
        PluginDescriptor(
            name=plugin_name,
            description=plugin_description,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon='images/e2m3ubouquetlogo.png',
            fnc=main
        ) #,
#        PluginDescriptor(
#            name=plugin_name,
#            description=plugin_description,
#            where=PluginDescriptor.WHERE_MENU,
#            icon='images/e2m3ubouquetlogo.png',
#            fnc=menuHook
#        )
    ]

    if config.plugins.e2m3u2b.extensions.value:
        result.append(extDescriptorQuick)
    if config.plugins.e2m3u2b.mainmenu.value:
        result.append(extDescriptorQuickMain)
    return result
