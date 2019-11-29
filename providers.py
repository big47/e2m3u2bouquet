# for localized messages
from . import _

import os, sys
import log
#import providersmanager as PM
import e2m3u2bouquet
from enigma import eTimer
from Components.config import config, ConfigEnableDisable, ConfigSubsection, \
			 ConfigYesNo, ConfigClock, getConfigListEntry, ConfigText, \
			 ConfigSelection, ConfigNumber, ConfigSubDict, NoSave, ConfigPassword, \
                         ConfigSelectionNumber
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.config import config, getConfigListEntry
from Components.Label import Label
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Sources.List import List
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
try:
    from Tools.Directoires import SCOPE_ACTIVE_SKIN
except:
    pass

ENIGMAPATH = '/etc/enigma2/'
CFGPATH = os.path.join(ENIGMAPATH, 'e2m3u2bouquet/')

class E2m3u2b_Providers(Screen):

    def __init__(self, session):
        self.session = session
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'providers.xml'), 'r') as f:
            self.skin = f.read()

        Screen.__init__(self, session)
        Screen.setTitle(self, "IPTV Bouquet Maker - %s" % _("Providers"))
        self.skinName = ["E2m3u2b_Providers", "AutoBouquetsMaker_HideSections"]

        self.drawList = []
        self['list'] = List(self.drawList)

        self.activityTimer = eTimer()
        self.activityTimer.timeout.get().append(self.prepare)

        self['actions'] = ActionMap(["ColorActions", "SetupActions", "MenuActions"],
                                    {
                                        'ok': self.openSelected,
                                        'cancel': self.keyCancel,
                                        'red': self.keyCancel,
                                        'green': self.key_add,
                                        'menu': self.keyCancel
                                    }, -2)
        self['key_red'] = Button(_("Cancel"))
        self['key_green'] = Button(_("Add"))
        self['pleasewait'] = Label()
        self['no_providers'] = Label()
        self['no_providers'].setText('No providers please add one (use green button) or create config.xml file')
        self['no_providers'].hide()

        self.onLayoutFinish.append(self.populate)

    def populate(self):
        self['actions'].setEnabled(False)

        self['pleasewait'].setText('Please wait...')
        self.activityTimer.start(1)

    def prepare(self):
        self.activityTimer.stop()

        self.e2m3u2b_config = e2m3u2bouquet.Config()
        if os.path.isfile(os.path.join(e2m3u2bouquet.CFGPATH, 'config.xml')):
            self.e2m3u2b_config.read_config(os.path.join(CFGPATH, 'config.xml'))

        self.refresh()
        self['pleasewait'].hide()
        self['actions'].setEnabled(True)

    def keyCancel(self):
        self.close()

    def key_add(self):
        provider = e2m3u2bouquet.ProviderConfig()
        provider.name = 'New'
        provider.enabled = True

        self.e2m3u2b_config.providers[provider.name] = provider
        self.session.openWithCallback(self.provider_add_callback, E2m3u2b_Providers_Config, self.e2m3u2b_config, provider)

    def openSelected(self):
        provider_name = self['list'].getCurrent()[1]
        self.session.openWithCallback(self.provider_config_callback, E2m3u2b_Providers_Config, self.e2m3u2b_config, self.e2m3u2b_config.providers[provider_name])

    def buildListEntry(self, provider):
        if provider.enabled:
            try:
                pixmap = LoadPixmap(cached=True, path=resolveFilename(SCOPE_ACTIVE_SKIN, 'icons/lock_on.png'))
            except:
                pixmap = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, 'skin_default/icons/lock_on.png'))
        else:
            try:
                pixmap = LoadPixmap(cached=True, path=resolveFilename(SCOPE_ACTIVE_SKIN, 'icons/lock_off.png'))
            except:
                pixmap = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, 'skin_default/icons/lock_off.png'))

        return (pixmap, str(provider.name), '')

    def refresh(self):
        self.drawList = []

        for key, provider in self.e2m3u2b_config.providers.iteritems():
            self.drawList.append(self.buildListEntry(provider))
        self['list'].setList(self.drawList)

        if not self.e2m3u2b_config.providers:
            self['no_providers'].show()
        else:
            self['no_providers'].hide()

    def provider_config_callback(self):
        self.refresh()

    def provider_add_callback(self):
        if 'New' in self.e2m3u2b_config.providers:
            self.e2m3u2b_config.providers.pop('New', None)
        self.refresh()

class E2m3u2b_Providers_Config(ConfigListScreen, Screen):

    def __init__(self, session, providers_config, provider):
        self.session = session
        with open('{}/skins/{}'.format(os.path.dirname(sys.modules[__name__].__file__), 'providerconfig.xml'), 'r') as f:
            self.skin = f.read()

        Screen.__init__(self, session)
        self.e2m3u2b_config = providers_config
        self.provider = provider
        Screen.setTitle(self, "IPTV Bouquet Maker - %s: %s" % (_("Provider"), provider.name))
        self.skinName = ["E2m3u2b_Providers_Config", "AutoBouquetsMaker_ProvidersSetup"]

        self.onChangedEntry = []
        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self.activityTimer = eTimer()
        self.activityTimer.timeout.get().append(self.prepare)

        self['actions'] = ActionMap(['SetupActions', 'ColorActions', 'MenuActions'],
                                    {
                                        'ok': self.keySave,
                                        'cancel': self.keyCancel,
                                        'red': self.keyCancel,
                                        'green': self.keySave,
                                        'yellow': self.key_delete,
                                        'menu': self.keyCancel,
                                    }, -2)

        self['key_red'] = Button(_("Cancel"))
        self['key_green'] = Button(_("Save"))
        self['key_yellow'] = Button(_("Delete"))

        self['description'] = Label()
        self['pleasewait'] = Label()

        self.onLayoutFinish.append(self.populate)

    def populate(self):
        self['actions'].setEnabled(False)
        self['pleasewait'].setText("Please wait...")
        self.activityTimer.start(1)

    def prepare(self):
        self.activityTimer.stop()

        self.provider_delete = ConfigYesNo(default=False)
        self.provider_enabled = ConfigYesNo(default=False)
        self.provider_enabled.value = self.provider.enabled
        self.provider_name = ConfigText(default='', fixed_size=False, visible_width=20)
        self.provider_name.value = self.provider.name if self.provider.name != 'New' else ''
        self.provider_settings_level = ConfigSelection(default='simple', choices=['simple', 'expert'])
        self.provider_settings_level.value = self.provider.settings_level
        self.provider_m3u_url = ConfigText(default='', fixed_size=False, visible_width=20)
        self.provider_m3u_url.value = self.provider.m3u_url
        self.provider_used_epg = ConfigSelection(default='custom', choices=['default', 'custom'])
        if self.provider_used_epg.value == 'default':
            self.provider_epg_url = e2m3u2bouquet.DEFAULTEPG
        self.provider_epg_url = ConfigText(default='', fixed_size=False, visible_width=20)
        self.provider_epg_url.value = self.provider.epg_url
        self.provider_username = ConfigText(default='', fixed_size=False)
        self.provider_username.value = self.provider.username
        self.provider_password = ConfigPassword(default='', fixed_size=False)
        self.provider_password.value = self.provider.password
        self.provider_multi_vod = ConfigEnableDisable(default=False)
        self.provider_multi_vod.value = self.provider.multi_vod
        self.provider_picons = ConfigYesNo(default=False)
        self.provider_picons.value = self.provider.picons
        self.provider_bouquet_pos = ConfigSelection(default='bottom', choices=['bottom', 'top'])
        if self.provider.bouquet_top:
            self.provider_bouquet_pos.value = 'top'
        self.provider_all_bouquet = ConfigYesNo(default=True)
        self.provider_all_bouquet.value = self.provider.all_bouquet
        self.provider_iptv_types = ConfigEnableDisable(default=False)
        self.provider_iptv_types.value = self.provider.iptv_types
        self.provider_streamtype_tv = ConfigSelection(default='', choices=[' ', '1', '4097', '5001', '5002'])
        self.provider_streamtype_tv.value = self.provider.streamtype_tv
        self.provider_streamtype_vod = ConfigSelection(default='', choices=[' ', '4097', '5001', '5002'])
        self.provider_streamtype_vod.value = self.provider.streamtype_vod
        # n.b. first option in stream type choice lists is an intentional single space
        self.provider_sref_override = ConfigEnableDisable(default=False)
        self.provider_sref_override.value = self.provider.sref_override
        self.provider_bouquet_download = ConfigEnableDisable(default=False)
        self.provider_bouquet_download.value = self.provider.bouquet_download

        self.create_setup()
        self['pleasewait'].hide()
        self['actions'].setEnabled(True)

    def create_setup(self):
        self.editListEntry = None
        self.list = []

        self.list.append(getConfigListEntry("%s:" % _("Name"), self.provider_name, _("Provider name")))
        self.list.append(getConfigListEntry("%s:" % _("Delete"), self.provider_delete, _("Delete provider %s") % self.provider.name))
        if not self.provider_delete.value:
            self.list.append(getConfigListEntry("%s:" % _("Enabled"), self.provider_enabled, _("Enable provider %s") % self.provider.name))
            if self.provider_enabled.value:
                self.list.append(getConfigListEntry("%s:" % _("Setup mode"), self.provider_settings_level, _("Choose level of settings. Expert shows all options")))
                self.list.append(getConfigListEntry("%s:" % _("M3U url"), self.provider_m3u_url, _("Providers M3U url. USERNAME & PASSWORD will be replaced by values below")))
                self.list.append(getConfigListEntry(_("Used EPG:"), self.provider_used_epg, _("If selected default, the plugin will use a predefined EPG by r.rusya")))
                if self.provider_used_epg.value == 'custom':
                    self.list.append(getConfigListEntry("%s:" % _("EPG url"), self.provider_epg_url, _("Providers EPG url. USERNAME & PASSWORD will be replaced by values below")))
                self.list.append(getConfigListEntry("%s:" % _("Username"), self.provider_username, _("If set will replace USERNAME placeholder in urls")))
                self.list.append(getConfigListEntry("%s:" % _("Password"), self.provider_password, _("If set will replace PASSWORD placeholder in urls")))
                self.list.append(getConfigListEntry("%s:" % _("Multi VOD"), self.provider_multi_vod, _("Enable to create multiple VOD bouquets rather than single VOD bouquet")))
                self.list.append(getConfigListEntry("%s:" % _("Picons"), self.provider_picons, _("Automatically download Picons")))
                self.list.append(getConfigListEntry(_("IPTV bouquet position"), self.provider_bouquet_pos, _("Select where to place IPTV bouquets")))
                self.list.append(getConfigListEntry(_("Create all channels bouquet:"), self.provider_all_bouquet, _("Create a bouquet containing all channels")))
                if self.provider_settings_level.value == 'expert':
                    self.list.append(getConfigListEntry(_("All IPTV type:"), self.provider_iptv_types, _("Normally should be left disabled. Setting to enabled may allow recording on some boxes. If you playback issues (e.g. stuttering on channels) set back to disabled")))
                    self.list.append(getConfigListEntry(_("TV Stream Type:"), self.provider_streamtype_tv, _("Stream type for TV services")))
                    self.list.append(getConfigListEntry(_("VOD Stream Type:"), self.provider_streamtype_vod, _("Stream type for VOD services")))
                    self.list.append(getConfigListEntry(_("Override service refs"), self.provider_sref_override, _("Should be left disabled unless you need to use the override.xml to override service refs (e.g. for DVB to IPTV EPG mapping)")))
                    self.list.append(getConfigListEntry(_("Check providers bouquet"), self.provider_bouquet_download, _("Enable this option to check and use providers custom service refs")))

        self['config'].list = self.list
        self['config'].setList(self.list)

    def renameEntryCallback(self, answer):
        config = self['config'].getCurrent()[1]
	config.help_window.instance.show()
        if answer:
            self.item[1].value = answer.strip()
            self.create_setup()

    def changedEntry(self):
        self.item = self['config'].getCurrent()
        for x in self.onChangedEntry:
            # for summary desc
            x()
        try:
            # if an option is changed that has additional config options show or hide these options
            if self.item[1] in (self.provider_name, self.provider_m3u_url, self.provider_epg_url, self.provider_username, self.provider_password):
                self.item[1].help_window.instance.hide()
                self.session.openWithCallback(self.renameEntryCallback, VirtualKeyBoard, title="%s %s" % (_("Please enter"), self.item[0]), text=self.item[1].value)
            if isinstance(self.item[1], ConfigYesNo) or isinstance(self.item[1], ConfigSelection):
                self.create_setup()
        except:
            pass

    def keySave(self):
        previous_name = self.provider.name

        # if delete is set to true or empty name show message box to confirm deletion
        if self.provider_name.value == '' or self.provider_delete.value:
            self.session.openWithCallback(self.delete_confirm, MessageBox, _("Confirm deletion of provider: %s") % previous_name)
        self.provider.enabled = self.provider_enabled.value
        self.provider.name = self.provider_name.value
        self.provider.settings_level = self.provider_settings_level.value
        self.provider.m3u_url = self.provider_m3u_url.value
        if self.provider_used_epg.value == 'default':
           self.provider.epg_url = e2m3u2bouquet.DEFAULTEPG
        else:
           self.provider.epg_url = self.provider_epg_url.value
        self.provider.username = self.provider_username.value
        self.provider.password = self.provider_password.value
        self.provider.multi_vod = self.provider_multi_vod.value
        self.provider.picons = self.provider_picons.value
        if self.provider_bouquet_pos.value == 'top':
            self.provider.bouquet_top = True
        else:
            self.provider.bouquet_top = False
        self.provider.all_bouquet = self.provider_all_bouquet.value
        self.provider.iptv_types = self.provider_iptv_types.value
        self.provider.streamtype_tv = self.provider_streamtype_tv.value.strip()
        self.provider.streamtype_vod = self.provider_streamtype_vod.value.strip()
        self.provider.sref_override = self.provider_sref_override.value
        self.provider.bouquet_download = self.provider_bouquet_download.value

        # disable provider if no m3u url
        if not self.provider_m3u_url.value:
            self.provider.enabled = False

        if self.provider_name.value != '' and self.provider_name.value != previous_name:
            # update provider dict key if name changed
            self.e2m3u2b_config.providers[self.provider_name.value] = self.e2m3u2b_config.providers.pop(previous_name)
            print>> log, '[e2m3u2b] Provider {} updated'.format(self.provider_name.value)

        # save xml config
        self.e2m3u2b_config.write_config()
        self.close()

    def cancelConfirm(self, result):
        if not result:
            return
        for x in self['config'].list:
            x[1].cancel()
        self.close()

    def keyCancel(self):
        self.close()

        # TODO detect if provider config screen is closed without saving
        #if self['config'].isChanged():
        #    self.session.openWithCallback(self.cancelConfirm, MessageBox, 'Really close without saving settings?')
        #else:
        #    self.close()

    def key_delete(self):
        self.session.openWithCallback(self.delete_confirm, MessageBox, _("Confirm deletion of provider: %s") % self.provider.name)

    def delete_confirm(self, result):
        if not result:
            return
        print>> log, '[e2m3u2b] Provider {} delete'.format(self.provider.name)
        self.e2m3u2b_config.providers.pop(self.provider.name, None)
        self.e2m3u2b_config.write_config()
        self.close()
