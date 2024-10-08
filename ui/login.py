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

 Main script which handles the login ui.

"""

import os
import os.path

from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.version import ISQGIS3
from ..qgis_api.web_browser_dialog import GISCloudQgisWebBrowserDialog

if ISQGIS3:
    from PyQt5 import QtCore, uic
    from PyQt5.QtCore import QObject, QSize
    from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLineEdit
else:
    from PyQt4 import QtCore, uic
    from PyQt4.QtCore import QObject, QSize
    from PyQt4.QtGui import QGraphicsOpacityEffect, QLineEdit

LOGIN_DOCK_WIDGET_FILE = "login.ui"
LOGIN_PROGRESS_DOCK_WIDGET_FILE = "login_progress.ui"
LOGIN_SSO_DOCK_WIDGET_FILE = "login_sso.ui"
CHANGE_SERVER_WIDGET_FILE = "change_server.ui"

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudUiLogin(QObject):
    """This class controls all login-related GUI elements."""

    def __init__(self, manager):
        QObject.__init__(self)
        self.manager = manager
        self.iface = self.manager.iface
        self.api = self.manager.api
        self.is_auth = False
        self.web_browser = None
        self.animation = None

        path = os.path.dirname(os.path.abspath(__file__))
        self.login_dock = uic.loadUi(os.path.join(
            path, LOGIN_DOCK_WIDGET_FILE))
        self.login_progress_dock = uic.loadUi(os.path.join(
            path, LOGIN_PROGRESS_DOCK_WIDGET_FILE))
        self.login_sso_dock = uic.loadUi(os.path.join(
            path, LOGIN_SSO_DOCK_WIDGET_FILE))
        self.change_server_dock = uic.loadUi(os.path.join(
            path, CHANGE_SERVER_WIDGET_FILE))

        self.login_dock.login.clicked.connect(self.login)
        self.login_dock.username.returnPressed.connect(self.login)
        self.login_dock.password.returnPressed.connect(self.login)
        self.login_dock.sso.mousePressEvent = self.show_sso
        self.login_dock.eye.clicked.connect(
            self.login_toggle_password_visibility)
        self.login_dock.visible_password = True
        self.login_dock.change_server.mousePressEvent = self.show_change_server

        self.login_sso_dock.google.clicked.connect(
            self.authorize_sso_google)
        self.login_sso_dock.google_img.clicked.connect(
            self.authorize_sso_google)
        self.login_sso_dock.back.clicked.connect(
            self.manager.restore_previous_dock_widget)

        self.change_server_dock.back.clicked.connect(
            self.manager.restore_previous_dock_widget)
        self.change_server_dock.save.clicked.connect(self.save_server)

        self.login_toggle_password_visibility()

        self.change_server_dock.server.setText(self.api.host)

    def show_sso(self, event):
        """Show login SSO widget"""
        # pylint: disable=W0613
        self.manager.set_dock_widget(self.login_sso_dock)

    def show_change_server(self, event):
        """Show Change server widget"""
        # pylint: disable=W0613
        self.manager.set_dock_widget(self.change_server_dock)

    def save_server(self):
        """Save server change"""
        self.api.host = self.change_server_dock.server.text()
        self.api.editor_host = self.api.host.replace("api", "editor")
        self.manager.restore_previous_dock_widget()

    def authorize_sso_google(self):
        """Launches browser to login with Google"""
        self.web_browser = GISCloudQgisWebBrowserDialog(
            self,
            QSize(650, 650),
            "https://editor.giscloud.com/auth/google?return=session")
        self.web_browser.show()

    def login_toggle_password_visibility(self):
        """Toggles password visibility in the user login form"""
        if self.login_dock.visible_password:
            effect = QGraphicsOpacityEffect(self.login_dock.eye)
            effect.setOpacity(0.5)
            self.login_dock.eye.setGraphicsEffect(effect)
            self.login_dock.visible_password = False
            self.login_dock.password.setEchoMode(QLineEdit.Password)
        else:
            self.login_dock.eye.setGraphicsEffect(None)
            self.login_dock.visible_password = True
            self.login_dock.password.setEchoMode(QLineEdit.Normal)

    def login_done(self, loggedin):
        """Define action after sucessful/unsucessful login."""
        self.animation.stop()
        LOGGER.info("Logged in {0}".format(loggedin))
        if not loggedin:        # unsucessful login
            message = "Incorrect GIS Cloud username or password. " + \
                      "Please try again."

            self.iface.messageBar().pushCritical("GIS Cloud Publisher Login",
                                                 message)
            self.login_dock.username.setStyleSheet(
                self.login_dock.username.default_input_style_error)
            self.login_dock.password.setStyleSheet(
                self.login_dock.password.default_input_style_error)
            self.manager.restore_previous_dock_widget()
            self.is_auth = False
            return
        self.manager.api.user.get_username(self.login_check)

    def login_check(self):
        """Callback for the login process"""
        self.is_auth = True
        self.manager.logged_in()

    def login(self):
        """Function that takes care of login process."""
        self.manager.set_dock_widget(self.login_progress_dock)

        self.login_dock.username.setStyleSheet(
            self.login_dock.username.default_input_style)
        self.login_dock.password.setStyleSheet(
            self.login_dock.password.default_input_style)

        animation = QtCore.QPropertyAnimation(
            self.login_progress_dock.progress_bar, b'value')
        animation.setDuration(1000)
        animation.setStartValue(0)
        animation.setEndValue(1000)
        animation.start()
        self.animation = animation
        self.manager.api.user.auth_api_key(self.login_dock.username.text(),
                                           self.login_dock.password.text(),
                                           self.login_done)

    def logout(self, event):
        """Function that takes care of logout process."""
        # pylint: disable=W0613
        self.manager.api.user.remove_api_key()
        self.is_auth = False
        self.manager.set_dock_widget(self.login_dock)
        self.login_dock.username.setText("")
        self.login_dock.password.setText("")
        self.login_dock.username.setStyleSheet(
            self.login_dock.username.default_input_style)
        self.login_dock.password.setStyleSheet(
            self.login_dock.password.default_input_style)

        if ISQGIS3:
            self.login_dock.username.setFocus()
