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

 Main script which handles the publish ui.

"""

import json
import os
import os.path

from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.version import ISQGIS3
from ..workers.map_check import GISCloudWorkerMapCheck
from ..workers.sync import GISCloudWorkerSync

if ISQGIS3:
    from PyQt5 import QtGui, uic
    from PyQt5.QtCore import QObject, QSize
    from PyQt5.QtWidgets import QMessageBox
else:
    from PyQt4 import QtGui, uic
    from PyQt4.QtCore import QObject, QSize
    from PyQt4.QtGui import QMessageBox

PUBLISH_DOCK_WIDGET_FILE = "publish.ui"
PUBLISH_DETAILS_DOCK_WIDGET_FILE = "publish_details.ui"
PUBLISH_PROGRESS_DOCK_WIDGET_FILE = "publish_progress.ui"

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudUiPublish(QObject):
    """This class controls all publish-related GUI elements."""

    def __init__(self, manager):
        QObject.__init__(self)
        self.manager = manager
        self.api = self.manager.api
        self.qgis_api = self.manager.qgis_api
        self.iface = self.manager.iface
        self.current_progress_text = None
        self.last_analysis_backup = None
        self.map_id_backup = None

        self.progress_gif = QtGui.QMovie(
            ":/plugins/gis_cloud_publisher/ui/img/loader.gif")
        self.progress_gif.setScaledSize(QSize(32, 32))

        path = os.path.dirname(os.path.abspath(__file__))
        self.publish_dock = uic.loadUi(os.path.join(
            path, PUBLISH_DOCK_WIDGET_FILE))
        self.publish_details_dock = uic.loadUi(os.path.join(
            path, PUBLISH_DETAILS_DOCK_WIDGET_FILE))
        self.publish_progress_dock = uic.loadUi(os.path.join(
            path, PUBLISH_PROGRESS_DOCK_WIDGET_FILE))

        self.publish_dock.publish.clicked.connect(self.publish_details)
        self.publish_dock.logout.mousePressEvent = \
            self.manager.login_control.logout

        self.publish_details_dock.cancel.clicked.connect(
            self.publish_cancel)
        self.publish_details_dock.publish.clicked.connect(
            self.publish_new_project)
        self.publish_details_dock.logout.mousePressEvent = \
            self.manager.login_control.logout

        self.publish_progress_dock.loader.setVisible(False)
        self.publish_progress_dock.cancel.clicked.connect(
            self.manager.publishing_cancel)

        self.map_check_task = GISCloudWorkerMapCheck(self.api, self.qgis_api)
        self.map_check_task.new_map_name.connect(self.update_map_name)

        self.sync_task = GISCloudWorkerSync(self.api, self.qgis_api)
        self.sync_task.notifyProgress.connect(self.on_progress)
        self.sync_task.notifyUploadProgress.connect(self.update_progress)
        self.sync_task.taskFinished.connect(self.publish_done)
        self.sync_task.somethingFailed.connect(self.publish_failed)
        self.sync_task.noMapToUpdate.connect(self.manager.deleted_map_message)

        self.message_box = QMessageBox()

    def check_map_for_publish(self):
        """check if map is eligible for publish"""
        is_new_map = self.api.map.map_id is None
        if not ISQGIS3 or is_new_map:
            self.qgis_api.analyze_layers(False,
                                         is_new_map)
        if (is_new_map and
                self.qgis_api.last_analysis["result"]["layers_new"] == 0):
            message = 'To proceed, mark as visible all layers ' + \
                      'you wish to publish to GIS Cloud.'
            self.message_box.warning(self.iface.mainWindow(), 'Warning',
                                     message,
                                     self.message_box.Ok,
                                     self.message_box.Ok)
            return False
        return True

    def publish_details(self, checked=False, is_new_map=False):
        """Method that shows form with public details.
        This is used for new maps, but also for maps that
        user want to publish as new"""
        # pylint: disable=W0613
        if is_new_map:
            self.last_analysis_backup = self.qgis_api.last_analysis
            self.qgis_api.last_analysis = {"time": 0}
            self.map_id_backup = self.api.map.map_id
            self.api.map.map_id = None
        else:
            self.qgis_api.use_all_layers = \
                self.publish_dock.all_layers.isChecked()

        if not self.check_map_for_publish():
            self.publish_restore_prev_map_state()
            return

        current_map_name = self.qgis_api.get_map_name()
        self.manager.set_login_info(self.publish_details_dock.user)
        self.publish_details_dock.map_name.setText(
            self.qgis_api.get_map_name())
        if self.api.user.is_user_premium:
            self.publish_details_dock.private_map.setChecked(True)
        else:
            self.publish_details_dock.public_map.setChecked(True)

        if self.qgis_api.use_all_layers:
            self.publish_details_dock.info_layers.setText(
                "All layers will be published to GIS Cloud.")
        else:
            self.publish_details_dock.info_layers.setText(
                "Layers marked as visible will be published to GIS Cloud.")

        self.manager.set_dock_widget(self.publish_details_dock)
        self.map_check_task.map_name = current_map_name
        self.map_check_task.start()

    def publish_new_project(self):
        """Method for start publishing a new map"""
        if not self.check_map_for_publish():
            return
        self.api.map.is_map_public = \
            self.publish_details_dock.public_map.isChecked()
        if not self.api.user.is_user_premium and \
           not self.api.map.is_map_public:
            self.message_box.warning(
                self.iface.mainWindow(),
                "Publish as public map or upgrade plan",
                "Your subscription does not allow private maps.\n\n" +
                "Choose to publish your map as public, " +
                "or upgrade your plan to a Premium subscription " +
                "inside your GIS Cloud account. \n\n" +
                "You can also contact sales@giscloud.com " +
                "to get a Premium subscription.",
                self.message_box.Ok,
                self.message_box.Ok)
            return
        self.qgis_api.map_name_override = \
            self.publish_details_dock.map_name.text()
        self.api.map.detach_map()
        self.publish_project()

    def publish_project(self):
        """Method that starts the publishing process"""
        LOGGER.debug("Publish project started")

        self.publish_progress_dock.progress_bar.setValue(0)
        self.publish_progress_dock.progress_bar.setVisible(False)
        self.publish_progress_dock.loader.setMovie(self.progress_gif)
        self.progress_gif.start()
        self.publish_progress_dock.loader.setVisible(True)

        self.publish_progress_dock.progress_info.setText("Syncing...")
        self.manager.set_dock_widget(self.publish_progress_dock)

        LOGGER.debug('Ready to start syncThread')
        self.manager.check_task.start()
        self.manager.check_task.finished.connect(self.start_sync_task)

    def publish_write_state(self):
        """Write published map state."""
        self.qgis_api.project.writeEntry(
            'giscloud_layers_data_state',
            'state',
            json.dumps(self.qgis_api.layer_data_timestamps))

        map_name = self.qgis_api.get_map_name(True)
        self.qgis_api.project.writeEntry(
            'giscloud_map_name',
            'name',
            map_name)
        self.api.map.map_name = map_name

    def publish_done(self):
        """Finish publishing and write new config info."""
        self.publish_write_state()
        self.manager.published()

    def update_progress(self, current_layer, total_layers, percentage):
        """Updating progres bar during the publish process"""
        progress = int(1000.0 / total_layers *
                       ((current_layer - 1) + percentage / 100.0))
        self.publish_progress_dock.progress_info.setText(
            self.current_progress_text + " ({}%)".format(percentage))
        self.publish_progress_dock.progress_bar.setValue(progress)
        self.publish_progress_dock.progress_bar.repaint()

    def on_progress(self, current_layer, total_layers):
        """Progress bar current layer information."""
        if not self.publish_progress_dock.progress_bar.isVisible():
            self.publish_progress_dock.progress_bar.setVisible(True)
            self.publish_progress_dock.loader.setVisible(False)
            self.progress_gif.stop()

        self.publish_progress_dock.progress_info.show()
        if current_layer > 0:
            self.current_progress_text = \
                "Uploading {}/{} layers".format(current_layer,
                                                total_layers)
            self.publish_progress_dock.progress_info.setText(
                self.current_progress_text)

    def publish_restore_prev_map_state(self):
        """If user has decided to cancel publish as a new map,
        we should restore state"""
        if self.last_analysis_backup:
            self.qgis_api.last_analysis = self.last_analysis_backup
            self.last_analysis_backup = None
            self.api.map.map_id = self.map_id_backup
            self.map_id_backup = None
            self.qgis_api.project.writeEntry("giscloud_project",
                                             "save_as",
                                             self.api.map.map_id)
            self.qgis_api.analyze_layers()

    def publish_cancel(self):
        """If user decides to not publish, we restore back the state."""
        self.publish_restore_prev_map_state()
        self.manager.restore_previous_dock_widget()

    def publish_failed(self, layer, error_details):
        """Handle failed publish and restore previous state."""
        self.publish_restore_prev_map_state()
        self.manager.inform_fail(layer, error_details)

    def update_map_name(self, name):
        """Updating map name, used for retrieving unique map name"""
        self.publish_details_dock.map_name.setText(name)
        self.publish_details_dock.map_name.setFocus()

    def start_sync_task(self):
        """Starting the sync"""
        self.sync_task.start()
