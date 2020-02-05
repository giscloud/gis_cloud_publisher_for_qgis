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

 Worker that does the sync. It transfer layer data, assets and creates/updates
 maps/layers on GIS Cloud.

"""
import os
from ..qgis_api.version import ISQGIS3
from ..qgis_api.logger import get_gc_publisher_logger

if ISQGIS3:
    from PyQt5.QtCore import QThread, pyqtSignal
else:
    from PyQt4.QtCore import QThread, pyqtSignal

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudWorkerSync(QThread):
    """Syncs layers from QGIS to GIS Cloud."""

    taskFinished = pyqtSignal()
    notifyProgress = pyqtSignal(int, int)
    somethingFailed = pyqtSignal(object, str)
    noMapToUpdate = pyqtSignal()
    notifyUploadProgress = pyqtSignal(int, int, int)

    def __init__(self, api, qgis_api):
        self.api = api
        self.qgis_api = qgis_api
        self.layer_index = 0
        self.total_layers = 0
        self.abort = False
        QThread.__init__(self)

    def upload_progress(self, bytes_sent, bytes_total):
        """This emits upload progress so that progress bar can be updated.
        The upload progress is set on range 5% to 99%, beside upload there
        are other requests so those are filing this gap."""
        if bytes_total > 0:
            progress = 5 + int(94.0 * bytes_sent / bytes_total)
            self.notifyUploadProgress.emit(self.layer_index,
                                           self.total_layers,
                                           progress)

    def run(self):
        """Start the sync."""
        last_layer = None
        self.abort = False
        LOGGER.info('syncTask started')
        try:
            # whole upload process is contained here
            if not os.path.exists(self.qgis_api.tmp_dir):
                os.makedirs(self.qgis_api.tmp_dir)

            last_map_id = self.api.map.map_id
            status = self.qgis_api.analyze_layers(True, False, True)

            if self.api.map.map_id:
                self.api.map.update_map()
                self.api.delete_layers()
            else:
                if last_map_id != self.api.map.map_id:
                    self.noMapToUpdate.emit()
                    self.quit()
                    return

                self.api.map.create_map(status["dirname"])

            self.api.create_folders()
            self.api.purge_folders()

            layers = self.qgis_api.get_layers_file_source()
            self.api.get_current_gc_files()
            self.api.datasources_cache = {}

            self.total_layers = len(layers)
            self.layer_index = 1

            LOGGER.info('Numbers of layers to upload: {}'.format(
                self.total_layers))

            for layer in layers:
                if self.abort:
                    break
                last_layer = layer
                self.notifyProgress.emit(self.layer_index, self.total_layers)

                layer.create_datasource()
                self.notifyUploadProgress.emit(self.layer_index,
                                               self.total_layers,
                                               5)

                layer.upload_files(self.upload_progress)
                self.notifyUploadProgress.emit(self.layer_index,
                                               self.total_layers,
                                               100)

                layer.create_layer()
                layer.create_option()
                self.layer_index += 1

            self.api.clean_up_tmp_files()
            if not self.abort:
                self.qgis_api.last_analysis["time"] = 0
                self.msleep(500)
                self.taskFinished.emit()
        except Exception as exception:
            self.api.clean_up_tmp_files()
            self.qgis_api.last_analysis["time"] = 0
            LOGGER.critical('SyncTask has failed with exception: ',
                            exc_info=True)
            msg = exception.args[0] \
                if exception.__class__.__name__ == "GISCloudException" \
                else None
            if not self.abort:
                self.somethingFailed.emit(last_layer, msg)
        self.quit()

    def quit(self):
        """graceful exit when quiting the task"""
        self.abort = True
        QThread.quit(self)
        QThread.wait(self)
