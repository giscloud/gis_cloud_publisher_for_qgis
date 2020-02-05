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

 Worker that checks if connection is good towards GIS Cloud.

"""

from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.version import ISQGIS3

if ISQGIS3:
    from PyQt5.QtCore import pyqtSignal, QThread
else:
    from PyQt4.QtCore import pyqtSignal, QThread

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudWorkerCheckConnection(QThread):
    """Check if connection is good before upload."""

    alertSignal = pyqtSignal()
    wrongApiSignal = pyqtSignal()

    def __init__(self, api, qgis_api):
        self.api = api
        self.qgis_api = qgis_api
        QThread.__init__(self)

    def __del__(self):
        self.wait()

    def run(self):
        """Checking if api key is valid"""
        try:
            response = self.api.user.api_key_check_validity()
            if response["status_code"] is None:
                raise Exception()
            if response["status_code"] != 200:
                LOGGER.info('Api_key_not_valid')
                self.wrongApiSignal.emit()
            self.quit()
        except Exception:
            LOGGER.info('Exception while trying to publish', exc_info=True)
            self.alertSignal.emit()
            self.quit()
