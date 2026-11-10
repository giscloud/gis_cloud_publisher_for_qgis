# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GIS Cloud Publisher
                                 A QGIS plugin
 Publish and sync your QGIS projects with GIS Cloud
                             -------------------
        begin                : 2019-02-01
        copyright            : (C) 2019 by GIS Cloud Ltd.
        email                : info@giscloud.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

 Qt compatibility helpers for QGIS 2 (PyQt4), QGIS 3 (PyQt5) and
 QGIS 4 (PyQt6).

 Imports throughout the plugin go through the version independent
 ``qgis.PyQt`` package (available since QGIS 2.14) and fall back to the
 concrete PyQt4/PyQt5 packages on older QGIS builds.

"""


def qt_enum(owner, scope, name):
    """Return the enum member ``name`` defined on ``owner``.

    PyQt4/PyQt5 expose enum members directly on the owning class
    (e.g. ``Qt.Unchecked``), while PyQt6 only exposes them through the
    scoped enum type (e.g. ``Qt.CheckState.Unchecked``)."""
    try:
        return getattr(owner, name)
    except AttributeError:
        return getattr(getattr(owner, scope), name)


def exec_(obj):
    """Run ``obj.exec_()``/``obj.exec()`` (PyQt6 dropped ``exec_``)."""
    method = getattr(obj, 'exec_', None)
    if method is None:
        method = getattr(obj, 'exec')
    return method()


def connect_reply_error(reply, slot):
    """Connect ``slot`` to a QNetworkReply error signal.

    The ``error`` signal was renamed to ``errorOccurred`` in Qt 5.15 and
    removed in Qt 6."""
    signal = getattr(reply, 'errorOccurred', None)
    if signal is None:
        signal = reply.error
    signal.connect(slot)
