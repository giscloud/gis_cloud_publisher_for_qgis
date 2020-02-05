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

 Worker that we use to calculate unique GIS Cloud map name
 that is suggested to the user.

"""

from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.version import ISQGIS3

if ISQGIS3:
    from PyQt5.QtCore import pyqtSignal, QThread
else:
    from PyQt4.QtCore import pyqtSignal, QThread

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudWorkerMapCheck(QThread):
    """Thread that check for a unique map name."""
    # pylint: disable=R0903
    new_map_name = pyqtSignal(str)

    def __init__(self, api, qgis_api):
        self.api = api
        self.qgis_api = qgis_api
        self.map_name = ""
        QThread.__init__(self)

    def __del(self):
        self.wait()

    def run(self):
        """Checking map name and emitting the result."""
        try:
            unique_name = self.api.map.get_unique_map_name(self.map_name)
            self.new_map_name.emit(unique_name)
        except Exception:
            LOGGER.info('Exception while trying to check map connection',
                        exc_info=True)
