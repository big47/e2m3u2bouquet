# -*- coding: utf-8 -*-
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
import gettext

PluginLanguageDomain = "E2m3u2bouquet"

def localeInit():
        gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, 'Extensions/E2m3u2bouquet/locale'))

def _(txt):
	t = gettext.dgettext(PluginLanguageDomain, txt)
	#fallback to default translation for", txt if t == txt
	return gettext.gettext(txt) if t == txt else t

language.addCallback(localeInit())
