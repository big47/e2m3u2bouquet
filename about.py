# for localized messages
from . import _

import os, sys
import e2m3u2bouquet

from enigma import getDesktop
from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Button import Button

ScreenWidth = getDesktop(0).size().width()
ScreenWidth = 'HD' if ScreenWidth and ScreenWidth >= 1280 else 'SD'

class E2m3u2b_About(Screen):

    def __init__(self, session):
        with open('{}/skins/{}/{}'.format(os.path.dirname(sys.modules[__name__].__file__), ScreenWidth, 'about.xml'), 'r') as f:
            self.skin = f.read()

        self.session = session
        Screen.__init__(self, session)
        Screen.setTitle(self, "IPTV Bouquet Maker - %s" % _("About"))
        self.skinName = ['E2m3u2b_About', 'AutoBouquetsMaker_About']

        self["about"] = Label('')
        self["oealogo"] = Pixmap()
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "MenuActions"],
                                    {
                                        "red": self.keyCancel,
                                        "cancel": self.keyCancel,
                                        "menu": self.keyCancel
                                    }, -2)
        self["key_red"] = Button(_('Close'))

        credit = "IPTV Bouquet Maker Plugin v{}\n".format(e2m3u2bouquet.__version__)
        credit += "Doug Mackay, Dave Sully, Dorik1972\n"
        credit += "Multi provider IPTV bouquet maker for Enigma2\n"
        credit += "This plugin is free and should not be resold\n"
        credit += "https://github.com/su1s/e2m3u2bouquet\n"
        credit += "https://github.com/pepsik-kiev/e2m3u2bouquet\n\n"
        credit += "Application credits:\n"
        credit += "- Doug Mackay (main developer) \n"
        credit += "- Dave Sully aka suls (main developer) \n"
        credit += "- Dorik1972 aka Pepsik (journe:)yman) \n"
        self["about"].setText(credit)
        self.onFirstExecBegin.append(self.setImages)

    def setImages(self):
	self["oealogo"].instance.setPixmapFromFile("%s/images/celentano.png" % (os.path.dirname(sys.modules[__name__].__file__)))

    def keyCancel(self):
        self.close()
