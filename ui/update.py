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

 Main script which handles the update ui.

"""

import os
import os.path

from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.utils import GISCloudQgisUtils
from ..qgis_api.version import ISQGIS3

if ISQGIS3:
    from PyQt5 import uic
    from PyQt5.QtCore import QUrl, QObject
    from PyQt5.QtWidgets import QMessageBox
    from PyQt5.QtGui import QDesktopServices
else:
    from PyQt4 import uic
    from PyQt4.QtCore import QUrl, QObject
    from PyQt4.QtGui import QMessageBox, QDesktopServices

UPDATE_DOCK_WIDGET_FILE = "update.ui"
UPDATE_DETAILS_DOCK_WIDGET_FILE = "update_details.ui"
UPDATE_DONE_DOCK_WIDGET_FILE = "update_done.ui"
UPDATE_SELECT_DOCK_WIDGET_FILE = "update_select.ui"

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudUiUpdate(QObject):
    """This class controls all update-related GUI elements."""

    def __init__(self, manager):
        QObject.__init__(self)
        self.manager = manager
        self.api = self.manager.api
        self.qgis_api = self.manager.qgis_api
        self.iface = self.manager.iface
        self.current_map_url = None
        self.is_update = True

        self.message_box = QMessageBox()

        path = os.path.dirname(os.path.abspath(__file__))
        self.update_dock = uic.loadUi(os.path.join(
            path, UPDATE_DOCK_WIDGET_FILE))
        self.update_details_dock = uic.loadUi(os.path.join(
            path, UPDATE_DETAILS_DOCK_WIDGET_FILE))
        self.update_done_dock = uic.loadUi(os.path.join(
            path, UPDATE_DONE_DOCK_WIDGET_FILE))
        self.update_select_dock = uic.loadUi(os.path.join(
            path, UPDATE_SELECT_DOCK_WIDGET_FILE))

        self.update_dock.publish_new.clicked.connect(
            self.new_map_upload)
        self.update_dock.update.clicked.connect(
            self.show_update_select)
        self.update_dock.open_map.clicked.connect(self.open_map)
        self.update_dock.logout.mousePressEvent = \
            self.manager.login_control.logout

        self.update_details_dock.update.clicked.connect(
            self.manager.publish_control.publish_project)
        self.update_details_dock.cancel.clicked.connect(
            self.manager.restore_previous_dock_widget)
        self.update_details_dock.logout.mousePressEvent = \
            self.manager.login_control.logout

        self.update_done_dock.open_map.clicked.connect(self.open_map)
        self.update_done_dock.copy_map_link.clicked.connect(self.copy_link)
        self.update_done_dock.logout.mousePressEvent = \
            self.manager.login_control.logout

        self.update_select_dock.publish.clicked.connect(self.run_update)
        self.update_select_dock.logout.mousePressEvent = \
            self.manager.login_control.logout
        self.update_select_dock.back.clicked.connect(
            self.show_update)

    def open_map(self):
        """Open map in a default browser"""
        QDesktopServices.openUrl(QUrl(self.current_map_url))

    def copy_link(self):
        """Copies map link to the clipboard"""
        GISCloudQgisUtils.copy_to_cliboard(self.current_map_url)

    def get_map_link(self):
        """Create hyperlink depending on map_id and map_name."""
        map_name_sef = self.api.map.map_name\
            .replace(" ", "-").replace(".", "").lower()
        sef_url = QUrl.toPercentEncoding(map_name_sef).data().decode('utf-8')
        self.current_map_url = '{0}map/{1}/{2}'.format(self.api.editor_host,
                                                       self.api.map.map_id,
                                                       sef_url)
        tooltip = ('This is a link to the {0} map published ' +
                   'from QGIS to GIS Cloud.').format(self.api.map.map_name)
        self.update_done_dock.open_map.setToolTip(tooltip)
        tooltip += ("\nChanges you made to your QGIS project " +
                    "since publishing the map are not synced yet.")
        self.update_dock.open_map.setToolTip(tooltip)

    def show_update(self):
        """show update form"""
        self.manager.set_dock_widget(self.update_dock)

    def show_update_select(self, checked=False, is_update=True):
        """show update select form"""
        # pylint: disable=W0613
        self.is_update = is_update
        if is_update:
            self.update_select_dock.publish.setText("Update map")
            self.update_select_dock.select_info.setText("Update:")
        else:
            self.update_select_dock.publish.setText("Publish map to GIS Cloud")
            self.update_select_dock.select_info.setText("Publish:")
        self.manager.set_login_info(self.update_select_dock.user)
        self.manager.set_dock_widget(self.update_select_dock)

    def run_update(self):
        """start update or new map"""
        self.qgis_api.use_all_layers = \
            self.update_select_dock.all_layers.isChecked()
        if self.is_update:
            self.show_update_form()
        else:
            self.manager.publish_control.publish_details(False, True)

    def show_update_form(self):
        """Before update we inform the user
        why update is needed and what will happen."""
        if self.qgis_api.use_all_layers:
            self.manager.publish_control.publish_project()
            return

        if not ISQGIS3:
            self.qgis_api.analyze_layers()

        if not self.api.map.map_id:
            self.manager.deleted_map_message()
            return

        analysis = self.qgis_api.last_analysis["result"]
        text = ""
        msg_prefix1 = "All layers set to \"visible\" " + \
                      "will be updated in GIS Cloud."
        msg_prefix11 = "All layers set to \"visible\" " + \
                       "will be updated in GIS Cloud, reflecting " + \
                       "the changes made in QGIS."
        msg_prefix2 = "All previously published layers will be updated " + \
                      "because you changed layer ordering."
        msg_removed = " Previously uploaded layers, removed from QGIS, " + \
                      "will also be removed from GIS Cloud."
        msg_n_layers = " Any not previously published layers " + \
                       "set to \"visible\" will also be uploaded."

        if not analysis["folders_order_changed"] and \
           not analysis["layers_order_changed"]:
            text = msg_prefix1 \
                if analysis["layers_to_delete"] != 0 and \
                analysis["layers_new"] != 0 \
                else msg_prefix11
            if analysis["layers_new"] != 0:
                text += msg_n_layers
            if analysis["layers_to_delete"] != 0:
                text += msg_removed
        else:
            text = msg_prefix2
            if analysis["layers_to_delete"] != 0:
                text += msg_removed
            if analysis["layers_new"] != 0:
                text += msg_n_layers

        self.update_details_dock.info.setText(
            "<span style=\"font-size:11px; color:rgb(255,255,255);\">" + text +
            "<br/><br/>You will not be able to revert " +
            "to the previously published version of the GIS Cloud map. " +
            "Continue?<span>")
        self.manager.set_login_info(self.update_details_dock.user)
        self.manager.set_dock_widget(self.update_details_dock)

    def new_map_upload(self):
        """Create New Project"""
        LOGGER.info('Upload new map started')
        new_share_info = self.message_box.warning(
            self.iface.mainWindow(),
            'Are you sure you want to upload this map as new?',
            'You won\'t be able to update ' +
            'the previously uploaded version of this map.',
            self.message_box.Yes,
            self.message_box.Cancel)
        if new_share_info == self.message_box.Yes:
            self.show_update_select(False, False)
