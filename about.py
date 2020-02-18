# -*- coding: utf-8 -*-
# for localized messages
from . import _

import e2m3u2bouquet

from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Button import Button
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from skin_templates import skin_about

class E2m3u2b_About(Screen):

    skin = skin_about()

    def __init__(self, session):

        self.session = session
        Screen.__init__(self, session)
        Screen.setTitle(self, "IPTV Bouquet Maker - %s" % _("About"))
        self.skinName = 'AutoBouquetsMaker_About'

        self["about"] = Label('')
        self["oealogo"] = Pixmap()
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "MenuActions"],
                                    {
                                        "red": self.keyCancel,
                                        "ok": self.keyCancel,
                                        "cancel": self.keyCancel,
                                        "menu": self.keyCancel
                                    }, -2)

        self["key_red"] = Button(_('Close'))

        credit = "IPTV Bouquet Maker Plugin: ver. {}\n".format(e2m3u2bouquet.__version__)
        try:
           from boxbranding import getBoxType, getImageDistro, getImageVersion
           credit += _("BoxType:") + " {}\n".format(getBoxType())
           credit += _("Image:") + " {} ver. {}\n\n".format(getImageDistro(), getImageVersion())
        except:
           credit += "\n"
        credit += _("Multi provider IPTV bouquet maker for Enigma2\n")
        credit += _("This plugin is free and should not be resold\n\n")
        credit += _("Plugin authors:\n")
        credit += "- Doug Mackay (main developer)\n"
        credit += "- Dave Sully aka suls (main developer)\n"
        credit += "-- https://github.com/su1s/e2m3u2bouquet\n"
        credit += "- Dorik1972 aka Pepsik (journe:)yman)\n"
        credit += "-- https://github.com/pepsik-kiev/e2m3u2bouquet\n"
        self["about"].setText(credit)
        self.onFirstExecBegin.append(self.setImages)

    def setImages(self):
	self["oealogo"].instance.setPixmapFromFile(resolveFilename(SCOPE_PLUGINS, 'Extensions/E2m3u2bouquet/images/') + 'celentano.png')

    def keyCancel(self):
        self.close()
