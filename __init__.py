# -*- coding: utf-8 -*-
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS, SCOPE_LANGUAGE
import gettext, os

PluginLanguageDomain = "E2m3u2bouquet"
PluginLanguagePath = "Extensions/E2m3u2bouquet/locale"

def localeInit():
	# getLanguage returns e.g. "fi_FI" for "language_country"
        # Enigma doesn't set this (or LC_ALL, LC_MESSAGES, LANG). gettext needs it!
	os.environ["LANGUAGE"] = language.getLanguage()[:2]
	gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))
	gettext.bindtextdomain('enigma2', resolveFilename(SCOPE_LANGUAGE, ""))

def _(txt):
	t = gettext.dgettext(PluginLanguageDomain, txt)
	#fallback to default translation for", txt if t == txt
	return gettext.dgettext('enigma2', txt) if t == txt else t

language.addCallback(localeInit())
