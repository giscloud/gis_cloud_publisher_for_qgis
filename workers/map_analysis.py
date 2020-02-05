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

 Worker that does layer analysis in the background and suggests an update
 if needed.

"""

from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.version import ISQGIS3

if ISQGIS3:
    from PyQt5.QtCore import pyqtSignal, QThread
else:
    from PyQt4.QtCore import pyqtSignal, QThread

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudWorkerMapAnalysis(QThread):
    """Handling map analysis to decide if update is needed"""
    # pylint: disable=R0903
    result = pyqtSignal(dict)

    def __init__(self, qgis_api):
        self.qgis_api = qgis_api
        QThread.__init__(self)

    def __del(self):
        self.wait()

    def run(self):
        """Running map analysis and returning back the result."""
        try:
            result_analysis = self.qgis_api.analyze_layers()
            self.result.emit(result_analysis)
        except Exception:
            LOGGER.critical('MapAnalysis has failed with exception: ',
                            exc_info=True)
