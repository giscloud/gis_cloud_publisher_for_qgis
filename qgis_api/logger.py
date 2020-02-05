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

 This script provides a common logger

"""

import logging
import os

LOGGERS = []
GC_DEFAULT_HANDLER_LOG_FILE = '{}/../gis_cloud_publisher.log'.format(
    os.path.dirname(os.path.abspath(__file__)))
open(GC_DEFAULT_HANDLER_LOG_FILE, 'w').close()
GC_DEFAULT_HANDLER = logging.FileHandler(GC_DEFAULT_HANDLER_LOG_FILE)
FORMATTER = logging.Formatter(
    '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
GC_DEFAULT_HANDLER.setFormatter(FORMATTER)


def get_gc_publisher_logger(_name):
    """With this method we can turn logger on for a particular module."""
    log = logging.getLogger(_name)
    log.setLevel(logging.DEBUG)
    log.addHandler(GC_DEFAULT_HANDLER)
    LOGGERS.append(log)
    return log


def gc_publisher_loggers_unload():
    """This method closes logger and removes handler,
    we should call it on plugin unload"""
    if GC_DEFAULT_HANDLER:
        GC_DEFAULT_HANDLER.close()
    for log in LOGGERS:
        for handler in log.handlers:
            log.removeHandler(handler)
