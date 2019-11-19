# for localized messages
from . import _

import time
import os, sys
import tempfile
import enigma
import log
import plugin as E2m3u2b_Plugin

from about import E2m3u2b_About
from providers import E2m3u2b_Providers

from enigma import eTimer
from Components.config import config, ConfigEnableDisable, ConfigSubsection, \
            ConfigYesNo, ConfigClock, getConfigListEntry, ConfigText, \
            ConfigSelection, ConfigNumber, ConfigSubDict, NoSave, ConfigPassword, \
            ConfigSelectionNumber
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Sources.List import List
from Components.Label import Label
from Components.SelectionList import SelectionList, SelectionEntryComponent
from Components.ScrollLabel import ScrollLabel

from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
try:
    from Tools.Directoires import SCOPE_ACTIVE_SKIN
except:
    pass

from Tools.LoadPixmap import LoadPixmap
import e2m3u2bouquet

try:
    import Plugins.Extensions.EPGImport.EPGImport as EPGImport
except ImportError:
    EPGImport = None

class E2m3u2b_Menu(Screen):

    def __init__(self, session):
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'mainmenu.xml'), 'r') as f:
            self.skin = f.read()
        Screen.__init__(self, session)
        Screen.setTitle(self, "IPTV Bouquet Maker - Pepsik edition")
        self.skinName = ['E2m3u2b_Menu', 'AutoBouquetsMaker_Menu']

        self.onChangedEntry = []
        l = []
        self['list'] = List(l)
        self['actions'] = ActionMap(['ColorActions', 'SetupActions', 'MenuActions'],
                                {
                                    'red': self.keyCancel,
                                    'green': self.manual_update,
                                    'cancel': self.keyCancel,
                                    'ok': self.openSelected,
                                    'menu': self.keyCancel
                                }, -2)
        self['key_red'] = Button(_("Exit"))
        self['key_green'] = Button(_("Select"))
        self.epgimport = None

        if EPGImport and config.plugins.e2m3u2b.do_epgimport.value is True:
            # skip channelfilter for IPTV
            self.epgimport = EPGImport.EPGImport(enigma.eEPGCache.getInstance(), lambda x: True)
        self.createSetup()

    def createSetup(self):
        l = [self.build_list_entry(_("Configure"), 'configure.png'),
             self.build_list_entry(_("Providers"), 'providers.png'),
             self.build_list_entry(_("Create Bouquets"), 'createbouquets.png'),
             self.build_list_entry(_("Status"), 'status.png'),
             self.build_list_entry(_("Reset Bouquets"), 'reset.png'),
             self.build_list_entry(_("Show log"), 'log.png'),
             self.build_list_entry(_("About"), 'about.png')]

        self['list'].list = l


    def build_list_entry(self, description, image):
        try:
            pixmap = LoadPixmap(resolveFilename(SCOPE_ACTIVE_SKIN, 'E2m3u2bouquet/' + image))
        except:
            pixmap = None
        if pixmap == None:
            pixmap = LoadPixmap(cached=True, path='{}/images/{}'.format(os.path.dirname(sys.modules[__name__].__file__), image))
        return((pixmap, description))

    def openSelected(self):
        index = self['list'].getIndex()

        if index == 0:
            self.session.openWithCallback(E2m3u2b_Plugin.done_configuring, E2m3u2b_Config)
            return
        if index == 1:
            self.session.open(E2m3u2b_Providers)
            return
        if index == 2:
            self.manual_update()
            return
        if index == 3:
            self.session.open(E2m3u2b_Status)
            return
        if index == 4:
            self.reset_bouquets()
            return
        if index == 5:
            self.session.open(E2m3u2b_Log)
            return
        if index == 6:
            self.session.open(E2m3u2b_About)
            return

    def manual_update(self):
        self.session.open(E2m3u2b_Update, self.epgimport)

    def reset_bouquets(self):
        """Remove any generated bouquets
        and epg importer config
        """
        self.session.openWithCallback(self.reset_bouquets_callback, MessageBox, _("This will remove the IPTV Bouquets\n"
                                                                                "and Epg Importer configs\n"
                                                                                "that have been created.\n"
                                                                                "Proceed?"), MessageBox.TYPE_YESNO,
                                      default=False)

    def reset_bouquets_callback(self, confirmed):
        if not confirmed:
            return
        try:
            E2m3u2b_Plugin.do_reset()
        except Exception, e:
            print>> log, "[e2m3u2b] reset_bouquets_callback Error:", e
            if config.plugins.e2m3u2b.debug.value:
                raise

    def keyCancel(self):
        self.close()


class E2m3u2b_Config(ConfigListScreen, Screen):

    def __init__(self, session):
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'mainconfig.xml'), 'r') as f:
            self.skin = f.read()
        Screen.__init__(self, session)
        self.session = session
        Screen.setTitle(self, 'IPTV Bouquet Maker - %s' % _("Configure"))
        self.skinName = ['E2m3u2b_Config', 'AutoBouquetsMaker_Setup']

        self.onChangedEntry = []
        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self['actions'] = ActionMap(['SetupActions', 'ColorActions', 'VirtualKeyboardActions', 'MenuActions'],
                                    {
                                        'ok': self.keySave,
                                        'cancel': self.keyCancel,
                                        'red': self.keyCancel,
                                        'green': self.keySave,
                                        'menu': self.keyCancel,
                                    }, -2)

        self['key_red'] = Button(_("Exit"))
        self['key_green'] = Button(_("Select"))
        self['description'] = Label()

        self.createSetup()

    def createSetup(self):
        self.editListEntry = None
        self.list = []
        indent = '- '

        self.list.append(getConfigListEntry(_("Automatic bouquet update (schedule):"), config.plugins.e2m3u2b.autobouquetupdate, _("Enable to update bouquets on a schedule")))
        if config.plugins.e2m3u2b.autobouquetupdate.getValue():
            self.list.append(getConfigListEntry(indent + _("Schedule type:"), config.plugins.e2m3u2b.scheduletype, _("Choose either a fixed time or an hourly update interval")))
            if config.plugins.e2m3u2b.scheduletype.value == 'interval':
                self.list.append(getConfigListEntry(2 * indent + _("Update interval (hours):"), config.plugins.e2m3u2b.updateinterval, _("Set the number of hours between automatic bouquet updates")))
            if config.plugins.e2m3u2b.scheduletype.value == 'fixed time':
                self.list.append(getConfigListEntry(2 * indent + _("Time to start update:"), config.plugins.e2m3u2b.schedulefixedtime, _("Set the day of time to perform the bouquet update")))
        self.list.append(getConfigListEntry(_("Automatic bouquet update (when box starts):"), config.plugins.e2m3u2b.autobouquetupdateatboot, _("Update bouquets at startup")))
        self.list.append(getConfigListEntry(_("Picon save path:"), config.plugins.e2m3u2b.iconpath, _("Select where to save picons (if download is enabled)")))
        self.list.append(getConfigListEntry(_("Attempt Epg Import"), config.plugins.e2m3u2b.do_epgimport, _("Automatically run Epg Import after bouquet update")))
        self.list.append(getConfigListEntry(_("Show in extensions:"), config.plugins.e2m3u2b.extensions, _("Show in extensions menu")))
        self.list.append(getConfigListEntry(_("Show in main menu:"), config.plugins.e2m3u2b.mainmenu, _("Show in main menu")))
        self.list.append(getConfigListEntry(_("Debug mode:"), config.plugins.e2m3u2b.debug, _("Enable debug mode. Do not enable unless requested")))

        self['config'].list = self.list
        self['config'].setList(self.list)

    def changedEntry(self):
        self.item = self['config'].getCurrent()
        for x in self.onChangedEntry:
            # for summary desc
            x()

        try:
            # If an option is changed that has additional config options show or hide these options
            if isinstance(self['config'].getCurrent()[1], ConfigYesNo) or isinstance(self['config'].getCurrent()[1], ConfigSelection):
                self.createSetup()
        except:
            pass

    def keySave(self):
        self.saveAll()
        self.reset_legacy_config()
        config.plugins.e2m3u2b.cfglevel.value = '2'
        config.plugins.e2m3u2b.cfglevel.save()
        self.close()

    def reset_legacy_config(self):
        if config.plugins.e2m3u2b.cfglevel.value == '1':
            cfg_list = [config.plugins.e2m3u2b.providername, config.plugins.e2m3u2b.username,
                        config.plugins.e2m3u2b.password, config.plugins.e2m3u2b.iptvtypes,
                        config.plugins.e2m3u2b.multivod, config.plugins.e2m3u2b.bouquetpos,
                        config.plugins.e2m3u2b.allbouquet, config.plugins.e2m3u2b.picons,
                        config.plugins.e2m3u2b.srefoverride, config.plugins.e2m3u2b.bouquetdownload,
                        config.plugins.e2m3u2b.last_provider_update]
            for x in cfg_list:
                x.value = ''
                x.save()


    def cancelConfirm(self, result):
        if not result:
            return
        for x in self['config'].list:
            x[1].cancel()
        self.close()

    def keyCancel(self):
        if self['config'].isChanged():
            self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"))
        else:
            self.close()

class E2m3u2b_Status(Screen):

    def __init__(self, session):
        self.session = session
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'status.xml'), 'r') as f:
            self.skin = f.read()
        Screen.__init__(self, session)
        Screen.setTitle(self, 'IPTV Bouquet Maker - %s' % _("Status"))
        self.skinName = ['E2m3u2b_Status', 'AutoBouquetsMaker_About']

        self["about"] = Label("")
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "MenuActions"],
                                    {
                                        "red": self.keyCancel,
                                        "cancel": self.keyCancel,
                                        "menu": self.keyCancel
                                    }, -2)
        self["key_red"] = Button(_("Close"))

        if config.plugins.e2m3u2b.last_update:
            self["about"].setText('Last channel update: {}'.format(config.plugins.e2m3u2b.last_update.value))

    def keyCancel(self):
        self.close()


class E2m3u2b_Log(Screen):

    def __init__(self, session):
        self.session = session
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'log.xml'), 'r') as f:
            self.skin = f.read()
        Screen.__init__(self, session)
        Screen.setTitle(self, 'IPTV Bouquet Maker - Log')
        self.skinName = ['E2m3u2b_Log', 'AutoBouquetsMaker_Log']

        self["key_red"] = Button(_("Close"))
        self["key_green"] = Button(_("Save"))
        self["key_blue"] = Button(_("Clear"))
        self["list"] = ScrollLabel(log.getvalue())
        self["actions"] = ActionMap(["DirectionActions", "OkCancelActions", "ColorActions", "MenuActions"],
                                    {
                                        "red": self.keyCancel,
                                        "green": self.keySave,
                                        "blue": self.keyClear,
                                        "cancel": self.keyCancel,
                                        "ok": self.keyCancel,
                                        "left": self["list"].pageUp,
                                        "right": self["list"].pageDown,
                                        "up": self["list"].pageUp,
                                        "down": self["list"].pageDown,
                                        "pageUp": self["list"].pageUp,
                                        "pageDown": self["list"].pageDown,
                                        "menu": self.keyCancel,
                                    }, -2)

    def keyCancel(self):
        self.close(False)

    def keyClear(self):
        log.logfile.reset()
        log.logfile.truncate()
        self.close(False)

    def keySave(self):
        with open(os.path.join(tempfile.gettempdir(), 'e2m3u2bouquet.log'), 'w') as f:
            f.write(log.getvalue())
        self.session.open(MessageBox, _("Log file has been saved to the tmp directory"), MessageBox.TYPE_INFO, timeout=30)

class E2m3u2b_Update(Screen):

    def __init__(self, session, epgimport):
        self.session = session
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'update.xml'), 'r') as f:
            self.skin = f.read()
        Screen.__init__(self, session)
        Screen.setTitle(self, "IPTV Bouquet Maker - %s" % _("Create Bouquets"))
        self.skinName = ['E2m3u2b_Update', 'AutoBouquetsMaker_About']

        self["actions"] = ActionMap(["SetupActions", "ColorActions", "MenuActions"],
                                    {
                                        "red": self.keyCancel,
                                        "cancel": self.keyCancel,
                                        "menu": self.keyCancel
                                    }, -2)
        self["key_red"] = Button(_("Close"))

        self['about'] = Label()
        self['about'].setText('Starting...')

        self.activityTimer = eTimer()
        self.activityTimer.timeout.get().append(self.prepare)
        self.update_status_timer = eTimer()
        self.update_status_timer.callback.append(self.update_status)

        self.epgimport = epgimport
        self.onLayoutFinish.append(self.populate)

    def populate(self):
        self.activityTimer.start(1)

    def prepare(self):
        self.activityTimer.stop()
        self.manual_update()

    def keyCancel(self):
        self.update_status_timer.stop()
        self.close()

    def manual_update(self):
        """Manual update
        """
        is_epgimport_running = False
        if self.epgimport:
            is_epgimport_running = self.epgimport.isImportRunning()

        if is_epgimport_running or e2m3u2bouquet.Status.is_running:
            self.session.open(MessageBox, _("Update still in progress. Please wait.")
                              , MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)
            self.close()
            return
        else:
            self.session.openWithCallback(self.manual_update_callback, MessageBox, _("Update of channels will start.\n"
                                          "This may take a few minutes.\n"
                                          "Proceed?"), MessageBox.TYPE_YESNO, timeout=15, default=True)

    def manual_update_callback(self, confirmed):
        if not confirmed:
            self.close()
            return
        try:
            self.start_update()
        except Exception, e:
            print>> log, "[e2m3u2b] manual_update_callback Error:", e
            if config.plugins.e2m3u2b.debug.value:
                raise

    def start_update(self):
        self.update_status_timer.start(2000)
        E2m3u2b_Plugin.start_update(self.epgimport)

    def update_status(self):
        self['about'].setText(e2m3u2bouquet.Status.message)

        if self.epgimport and self.epgimport.isImportRunning():
            self['about'].setText('EPG Import: Importing {} {} events'.format(self.epgimport.source.description,
                                                                              self.epgimport.eventCount))


class E2m3u2b_Check(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.onShown.append(self.epimport_check)

    def epimport_check(self):
        if EPGImport is None:
            self.session.open(MessageBox, _("EPG Import not found\nPlease install the EPG Import plugin"),
                              MessageBox.TYPE_WARNING, timeout=10)
            self.close()


#class SetupSummary(Screen):
#    def __init__(self, session, parent):
#        Screen.__init__(self, session, parent=parent)
#        self['SetupTitle'] = StaticText(parent.setup_title)
#        self['SetupEntry'] = StaticText('')
#        self['SetupValue'] = StaticText('')
#        self.onShow.append(self.addWatcher)
#        self.onHide.append(self.removeWatcher)#
#
#    def addWatcher(self):
#        self.parent.onChangedEntry.append(self.selectionChanged)
#        self.parent['config'].onSelectionChanged.append(self.selectionChanged)
#        self.selectionChanged()#
#
#    def removeWatcher(self):
#        self.parent.onChangedEntry.remove(self.selectionChanged)
#        self.parent['config'].onSelectionChanged.remove(self.selectionChanged)#
#
#    def selectionChanged(self):
#        print('SetupSummary -> selectionChanged')
#        self['SetupEntry'].text = self.parent.getCurrentEntry()
#        self['SetupValue'].text = self.parent.getCurrentValue()
#        if hasattr(self.parent, 'getCurrentDescription'):
#            self.parent['description'].text = self.parent.getCurrentDescription()
