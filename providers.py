# -*- coding: utf-8 -*-
# for localized messages
from . import _

import os, log
#import providersmanager as PM
import e2m3u2bouquet
from enigma import eTimer, eEnv
from Components.config import ConfigOnOff, ConfigYesNo, getConfigListEntry, \
                              ConfigText, ConfigInteger, ConfigSelection, ConfigPassword
from Components.Label import Label
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Sources.List import List
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, fileExists, SCOPE_PLUGINS
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
try:
    from Tools.Directoires import SCOPE_ACTIVE_SKIN
except:
    pass
from skin_templates import skin_hidesections, skin_setup, skin_about

class E2m3u2b_Providers(Screen):

    skin = skin_hidesections()

    def __init__(self, session):

        self.session = session
        Screen.__init__(self, session)
        Screen.setTitle(self, "IPTV Bouquet Maker - %s" % _("Providers"))
        self.skinName = 'AutoBouquetsMaker_HideSections'

        self.drawList = []
        self['list'] = List(self.drawList)

        self.activityTimer = eTimer()
        self.activityTimer.timeout.get().append(self.prepare)

        self['actions'] = ActionMap(['ColorActions', 'SetupActions', 'MenuActions'],
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
        self['no_providers'].setText(_('No providers please add one (use green button) or create config.xml file'))
        self['no_providers'].hide()

        self.onLayoutFinish.append(self.populate)

    def populate(self):
        self['actions'].setEnabled(False)

        self['pleasewait'].setText('Please wait...')
        self.activityTimer.start(1)

    def prepare(self):
        self.activityTimer.stop()

        self.e2m3u2b_config = e2m3u2bouquet.Config()

        if fileExists(os.path.join(e2m3u2bouquet.CFGPATH, 'config.xml')):
            self.e2m3u2b_config.read_config(os.path.join(e2m3u2bouquet.CFGPATH, 'config.xml'))

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
        pixmap = LoadPixmap(cached=True, path=resolveFilename(SCOPE_PLUGINS, 'Extensions/E2m3u2bouquet/images/lock_%s.png' % ('on' if provider.enabled else 'off')))
        return (pixmap, str(provider.name), '')

    def refresh(self):
        self['list'].setList([self.buildListEntry(provider) for key, provider in self.e2m3u2b_config.providers.iteritems()])

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

    skin = skin_setup()

    def __init__(self, session, providers_config, provider):

        self.session = session
        Screen.__init__(self, session)
        self.e2m3u2b_config = providers_config
        self.provider = provider
        Screen.setTitle(self, "IPTV Bouquet Maker - %s: %s" % (_("Provider"), provider.name))
        self.skinName = 'AutoBouquetsMaker_ProvidersSetup'

        self.onChangedEntry = []
        self.list = []
        ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)

        self.activityTimer = eTimer()
        self.activityTimer.timeout.get().append(self.prepare)

        self['actions'] = ActionMap(['SetupActions', 'ColorActions', 'MenuActions', 'VirtualKeyboardActions'],
                                    {
                                        'ok': self.keySave,
                                        'cancel': self.keyCancel,
                                        'red': self.keyCancel,
                                        'green': self.keySave,
                                        'yellow': self.key_delete,
                                        'blue': self.openKeyboard,
                                        'menu': self.keyCancel,
                                    }, -2)

        self['key_red'] = Button(_("Cancel"))
        self['key_green'] = Button(_("Save"))
        self['key_yellow'] = Button(_("Delete"))
        self['key_blue'] = Button(_("Keyboard"))

        self['description'] = Label()
        self['pleasewait'] = Label()

        self.onLayoutFinish.append(self.populate)

    def populate(self):
        self['actions'].setEnabled(False)
        self['pleasewait'].setText("Please wait...")
        self.activityTimer.start(1)

    @staticmethod
    def isExtEplayer3Available():
        return fileExists(eEnv.resolve('$bindir/exteplayer3'))

    @staticmethod
    def isGstPlayerAvailable():
        return fileExists(eEnv.resolve('$bindir/gstplayer_gst-1.0'))

    def prepare(self):
        self.activityTimer.stop()

        available_players = [('1', _('internal')), ('4097', _('Gstreamer'))]
        if self.isGstPlayerAvailable():
            available_players.append(('5001', _('GstPlayer')))
        if self.isExtEplayer3Available():
            available_players.append(('5002', _('ExtEplayer3')))

        self.provider_delete = ConfigYesNo(default=False)
        self.provider_enabled = ConfigYesNo(default=False)
        self.provider_enabled.value = self.provider.enabled
        self.provider_name = ConfigText(default='', fixed_size=False, visible_width=20)
        self.provider_name.value = self.provider.name if self.provider.name != 'New' else ''
        self.provider_settings_level = ConfigSelection(default=_('simple'), choices=[_('simple'), _('expert')])
        self.provider_settings_level.value = self.provider.settings_level
        self.provider_m3u_url = ConfigText(default='', fixed_size=False, visible_width=20)
        self.provider_m3u_url.value = self.provider.m3u_url
        self.provider_used_epg = ConfigSelection(default=_('custom'), choices=[_('default'), _('custom')])
        if self.provider_used_epg.value == _('default'):
            self.provider_epg_url = e2m3u2bouquet.DEFAULTEPG
        self.provider_epg_url = ConfigText(default='', fixed_size=False, visible_width=20)
        self.provider_epg_url.value = self.provider.epg_url
        self.provider_username = ConfigText(default='', fixed_size=False)
        self.provider_username.value = self.provider.username
        self.provider_password = ConfigPassword(default='', fixed_size=False)
        self.provider_password.value = self.provider.password
        self.provider_multi_vod = ConfigOnOff(default=False)
        self.provider_multi_vod.value = self.provider.multi_vod
        self.provider_picons = ConfigYesNo(default=False)
        self.provider_picons.value = self.provider.picons
        self.provider_bouquet_pos = ConfigSelection(default=_('bottom'), choices=[_('bottom'), _('top')])
        if self.provider.bouquet_top:
            self.provider_bouquet_pos.value = _('top')
        self.provider_all_bouquet = ConfigYesNo(default=True)
        self.provider_all_bouquet.value = self.provider.all_bouquet
        self.provider_iptv_types = ConfigOnOff(default=False)
        self.provider_iptv_types.value = self.provider.iptv_types
        self.provider_streamtype_tv = ConfigSelection(default='4097', choices=available_players)
        self.provider_streamtype_tv.value = self.provider.streamtype_tv
        # 4097 Gstreamer options (0-no buffering, 1-buffering enabled, 3-http progressive download & buffering enabl)
        self.provider_gstreamer = ConfigSelection(default='0', choices=[('0', _('no buffring')), ('1', _('buffering enabled')),('3', _('http & buffering enabled'))])
        self.provider_gstreamer.value = self.provider.gstreamer
        # 5002 ExtEplayer3 options
        self.provider_flv2mpeg4 = ConfigSelection(default='0', choices=[('0', _('no')), ('1', _('yes'))])   # EXT3_FLV2MPEG4_CONVERTER
        self.provider_flv2mpeg4.value = self.provider.flv2mpeg4
        self.provider_progressive = ConfigSelection(default='0', choices=[('0', _('no')), ('1', _('yes'))]) # EXT3_PLAYBACK_PROGRESSIVE
        self.provider_progressive.value = self.provider.progressive
        self.provider_live_ts = ConfigSelection(default='0', choices=[('0', _('no')), ('1', _('yes'))])     # EXT3_PLAYBACK_LIVETS
        self.provider_live_ts.value = self.provider.live_ts
        self.provider_ffmpeg_option = ConfigText(default='', fixed_size=False, visible_width=20)  # EXT3_FFMPEG_SETTING_STRING
        self.provider_ffmpeg_option.value = self.provider.ffmpeg_option
        # 5001 GstPlayer options
        self.provider_ring_buffer_maxsize = ConfigInteger(32768, (1024, 1024 * 64))  # GST_RING_BUFFER_MAXSIZE
        self.provider_ring_buffer_maxsize.value = self.provider.ring_buffer_maxsize
        self.provider_buffer_size = ConfigInteger(8192, (1024, 1024 * 64))           # GST_BUFFER_SIZE
        self.provider_buffer_size.value = self.provider.buffer_size
        self.provider_buffer_duration = ConfigInteger(0, (0, 100))                   # GST_BUFFER_DURATION
        self.provider_buffer_duration.value = self.provider.buffer_duration

        self.provider_streamtype_vod = ConfigSelection(default='4097', choices=available_players)
        self.provider_streamtype_vod.value = self.provider.streamtype_vod
        self.provider_sref_override = ConfigOnOff(default=False)
        self.provider_sref_override.value = self.provider.sref_override
        self.provider_bouquet_download = ConfigOnOff(default=False)
        self.provider_bouquet_download.value = self.provider.bouquet_download

        self.create_setup()
        self['pleasewait'].hide()
        self['actions'].setEnabled(True)

    def create_setup(self):
        self.editListEntry = None
        self.list = []
        indent = '- '

        self.list.append(getConfigListEntry("%s:" % _("Name"), self.provider_name, _("Provider name")))
        self.list.append(getConfigListEntry("%s:" % _("Delete"), self.provider_delete, _("Delete provider %s") % self.provider.name))
        if not self.provider_delete.value:
            self.list.append(getConfigListEntry("%s:" % _("Enabled"), self.provider_enabled, _("Enable provider %s") % self.provider.name))
            if self.provider_enabled.value:
                self.list.append(getConfigListEntry("%s:" % _("Setup mode"), self.provider_settings_level, _("Choose level of settings. Expert shows all options")))
                self.list.append(getConfigListEntry("%s:" % _("M3U url"), self.provider_m3u_url, _("Providers M3U url. If it contains USERNAME & PASSWORD templates,\nthey will be replaced by values below")))
                if 'USERNAME' and 'PASSWORD' in self.provider_m3u_url.value:
                    self.list.append(getConfigListEntry(indent + "%s:" % _("Username"), self.provider_username, _("If set will replace USERNAME placeholder in urls")))
                    self.list.append(getConfigListEntry(indent + "%s:" % _("Password"), self.provider_password, _("If set will replace PASSWORD placeholder in urls")))
                self.list.append(getConfigListEntry(_("Used EPG:"), self.provider_used_epg, _("If selected default, the plugin will use a predefined EPG by r.rusya")))
                if self.provider_used_epg.value == _('custom'):
                    self.list.append(getConfigListEntry(indent + "%s:" % _("EPG url"), self.provider_epg_url, _("url link to EPG issued by provider. Leave blank if the m3u playlist has url-tvg or url-epg tags")))
                self.list.append(getConfigListEntry("%s:" % _("Multi VOD"), self.provider_multi_vod, _("Enable to create multiple VOD bouquets rather than single VOD bouquet")))
                self.list.append(getConfigListEntry("%s:" % _("Picons"), self.provider_picons, _("Automatically download Picons")))
                self.list.append(getConfigListEntry(_("IPTV bouquet position:"), self.provider_bouquet_pos, _("Select where to place IPTV bouquets")))
                self.list.append(getConfigListEntry(_("Create all channels bouquet:"), self.provider_all_bouquet, _("Create a bouquet containing all channels")))
                if self.provider_settings_level.value == _('expert'):
                    self.list.append(getConfigListEntry(_("All IPTV type:"), self.provider_iptv_types, _("Normally should be left disabled. Setting to enabled may allow recording on some boxes.\nIf you playback issues (e.g. stuttering on channels) set back to disabled")))
                    self.list.append(getConfigListEntry(_("Live Player Type:"), self.provider_streamtype_tv, _("Stream player type for TV services")))

                    if self.provider_streamtype_tv.value == '4097':
                        self.list.append(getConfigListEntry(indent + _("Stream Type:"), self.provider_gstreamer, _("Stream type: no buffering; buffering enabled; progressive download and buffering enabled")))

                    if self.provider_streamtype_tv.value == '5002':
                        self.list.append(getConfigListEntry(indent + _("FLV2 to MPEG4 converter:"), self.provider_flv2mpeg4, _("Convert flv2 stream to mpeg4")))
                        self.list.append(getConfigListEntry(indent + _("Use http progressive download:"), self.provider_progressive, _("It should be enabled if the provider gives a stream in http progressive download")))
                        self.list.append(getConfigListEntry(indent + _("Live TS:"), self.provider_live_ts, _("Enable if broadcast is Live TS")))
                        self.list.append(getConfigListEntry(indent + _("Additional ffmpeg options:"), self.provider_ffmpeg_option, _("Additional ffmpeg options for stream decoding")))

                    if self.provider_streamtype_tv.value == '5001':
                        self.list.append(getConfigListEntry(indent + _("Ring Buffer Size:"), self.provider_ring_buffer_maxsize, _("Ring buffer size (Stack) in Kbytes")))
                        self.list.append(getConfigListEntry(indent + _("Data buffer size:"), self.provider_buffer_size, _("Data buffer size in Kbytes")))
                        self.list.append(getConfigListEntry(indent + _("Data buffer duration:"), self.provider_buffer_duration, _("Data buffer duration in seconds")))

                    self.list.append(getConfigListEntry(_("VOD Player Type:"), self.provider_streamtype_vod, _("Stream player type for VOD services")))
                    self.list.append(getConfigListEntry(_("Override service refs:"), self.provider_sref_override, _("Should be left disabled unless you need to use the override.xml to override service refs\n(e.g. for DVB to IPTV EPG mapping)")))
                    self.list.append(getConfigListEntry(_("Check providers bouquet:"), self.provider_bouquet_download, _("Enable this option to check and use providers custom service refs")))

        self['config'].list = self.list
        self['config'].setList(self.list)

    def keyBoardCallback(self, answer = None):
        if answer is not None and len(answer):
            self['config'].getCurrent()[1].setValue(answer.strip())
            self['config'].invalidate(self['config'].getCurrent())

    def changedEntry(self):
        self.item = self['config'].getCurrent()
        map(lambda x: x(), self.onChangedEntry)
        try:
            # if an option is changed that has additional config options show or hide these options
            if ( isinstance(self["config"].getCurrent()[1], ConfigText) or isinstance(self["config"].getCurrent()[1], ConfigPassword) ):
                self.openKeyboard()
            else:
                self.create_setup()
        except:
            pass

    def openKeyboard(self):
        if isinstance(self['config'].getCurrent()[1], ConfigText) or isinstance(self['config'].getCurrent()[1], ConfigPassword):
    	    self.session.openWithCallback(self.keyBoardCallback, VirtualKeyBoard, title="%s %s" % (_("Please enter"), self['config'].getCurrent()[0]), text=self['config'].getCurrent()[1].value)

    def keySave(self):
        previous_name = self.provider.name

        # if delete is set to true or empty name show message box to confirm deletion
        if self.provider_name.value == '' or self.provider_delete.value:
            self.session.openWithCallback(self.delete_confirm, MessageBox, _("Confirm deletion of provider: %s") % previous_name)
        self.provider.enabled = self.provider_enabled.value
        self.provider.name = self.provider_name.value
        self.provider.settings_level = self.provider_settings_level.value
        self.provider.m3u_url = self.provider_m3u_url.value
        if self.provider_used_epg.value == _('default'):
           self.provider.epg_url = e2m3u2bouquet.DEFAULTEPG
        else:
           self.provider.epg_url = self.provider_epg_url.value
        self.provider.username = self.provider_username.value
        self.provider.password = self.provider_password.value
        self.provider.multi_vod = self.provider_multi_vod.value
        self.provider.picons = self.provider_picons.value
        if self.provider_bouquet_pos.value == _('top'):
            self.provider.bouquet_top = True
        else:
            self.provider.bouquet_top = False
        self.provider.all_bouquet = self.provider_all_bouquet.value
        self.provider.iptv_types = self.provider_iptv_types.value
        self.provider.streamtype_tv = self.provider_streamtype_tv.value.strip()
        # 4097 Gstreamer options
        self.provider.gstreamer = self.provider_gstreamer.value
        # 5002 ExtEplayer3 options
        self.provider.flv2mpeg4 = self.provider_flv2mpeg4.value
        self.provider.progressive = self.provider_progressive.value
        self.provider.live_ts = self.provider_live_ts.value
        self.provider.ffmpeg_option = self.provider_ffmpeg_option.value.strip()
        # 5001 GstPlayer options
        self.provider.ring_buffer_maxsize = self.provider_ring_buffer_maxsize.value
        self.provider.buffer_size = self.provider_buffer_size.value
        self.provider.buffer_duration = self.provider_buffer_duration.value

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
        map(lambda x: x[1].cancel(), self['config'].list)
        self.close()

    def keyCancel(self):
        if self['config'].isChanged():
            self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"), MessageBox.TYPE_YESNO,
                                                                            timeout=3, default=True)
        else:
            self.close()

    def key_delete(self):
        self.session.openWithCallback(self.delete_confirm, MessageBox, _("Confirm deletion of provider: %s") % self.provider.name)

    def delete_confirm(self, result):
        if not result:
            return
        print>> log, '[e2m3u2b] Provider {} delete'.format(self.provider.name)
        self.e2m3u2b_config.providers.pop(self.provider.name, None)
        self.e2m3u2b_config.write_config()
        self.close()
