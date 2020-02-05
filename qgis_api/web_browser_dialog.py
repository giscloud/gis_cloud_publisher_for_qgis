# -*- coding: utf-8 -*-
"""
/***************************************************************************
                                 A QGIS plugin
 GIS Cloud Publisher
                              -------------------
        copyright            : (C) 2019 by GIS Cloud Ltd.
        email                : info@giscloud.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *  This program is distributed in the hope that it will be useful,        *
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of         *
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          *
 *  GNU General Public License for more details.                           *
 *                                                                         *
 *  This program is free software; you can redistribute it and/or modify   *
 *  it under the terms of the GNU General Public License as published by   *
 *  the Free Software Foundation; either version 2 of the License, or      *
 *  (at your option) any later version.                                    *
 *                                                                         *
 *  You should have received a copy of the GNU General Public License      *
 *  along with this program.  If not, see <https://www.gnu.org/licenses/>. *
 *                                                                         *
 ***************************************************************************/

 This is web brower dialog that shows up for Google and Facebook SSO.

 We use cookie jar to keep the session state and get session from GIS Cloud to
 authorize and retrieve api key for permanent login.

"""

from .version import ISQGIS3
from ..gis_cloud_api.network_handler import GISCloudNetworkHandler

if ISQGIS3:
    from PyQt5 import QtNetwork
    from PyQt5.QtCore import QUrl
    from PyQt5.QtWebKitWidgets import QWebPage, QWebView
    from PyQt5.QtWidgets import QDialog
else:
    from PyQt4 import QtNetwork
    from PyQt4.QtCore import QUrl
    from PyQt4.QtGui import QDialog
    from PyQt4.QtWebKit import QWebPage, QWebView


class GISCloudQgisWebBrowserDialog(QDialog):
    """Web browser used for Google/Facebook SSO"""

    def __init__(self, parent, size, url):
        super(GISCloudQgisWebBrowserDialog, self).__init__(
            parent.manager.main_widget)
        self.parent = parent
        self.setModal(True)

        self.cookies = None
        self.url = QUrl(url)
        self.nam = QtNetwork.QNetworkAccessManager()

        self.web_page = QWebPage()
        self.web_page.setNetworkAccessManager(self.nam)
        self.web_page.loadFinished.connect(self.loading_finished)

        def customuseragent(url):
            """setting up our own user agent"""
            # pylint: disable=W0613
            return ("Mozilla/5.0 " +
                    GISCloudNetworkHandler.app_id
                    .encode("unicode_escape")
                    .decode("latin-1"))
        self.web_page.userAgentForUrl = customuseragent

        self.web_view = QWebView(self)
        self.web_view.setPage(self.web_page)

        self.resize(size)

    def resizeEvent(self, event):
        """As we resize dialog, we should resize browser as well"""
        # pylint: disable=C0103
        QDialog.resizeEvent(self, event)
        self.web_view.resize(self.size())

    def showEvent(self, event):
        """Loading URL once dialog has shown, also reseting cookie jar"""
        # pylint: disable=C0103
        QDialog.showEvent(self, event)
        self.cookies = QtNetwork.QNetworkCookieJar()
        self.nam.setCookieJar(self.cookies)
        self.web_view.load(self.url)

    def hideEvent(self, event):
        """Once dialog has closed, cleaning up cookie-jar"""
        # pylint: disable=C0103
        self.cookies = QtNetwork.QNetworkCookieJar()
        self.nam.setCookieJar(self.cookies)
        QDialog.hideEvent(self, event)

    def loading_finished(self, finished_ok):
        """This method retrieves session id and passes it on for login """
        # pylint: disable=W0613
        url = self.web_view.url().toString()
        url = url.split("/auth/get_session#")
        if len(url) != 2:
            return

        if url[1]:
            self.parent.api.user.session = url[1]
        else:
            # for some reason # params can be truncated
            # so fallbacking to find session in cookies
            for cookie in self.cookies.allCookies():
                if cookie.domain() == "editor.giscloud.com" and \
                   cookie.name() == "PHPSESSID":
                    self.parent.api.user.session = \
                        cookie.value().data().decode("utf-8")
                    break
        self.parent.web_browser.hide()
        self.parent.login()
