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

 This is our implementation of handling network requests using
 QgsNetworkAccessManager

 We implemented blocking and non-blocking for REST requests
 as well as file uploader with progress tracking.

"""

import json
import platform
import os

from qgis.core import QgsNetworkAccessManager

from ..qgis_api.version import ISQGIS3
from ..qgis_api.version import GIS_CLOUD_PUBLISHER_VERSION, QGIS_VERSION

if ISQGIS3:
    from PyQt5.QtCore import QByteArray, QEventLoop, QFile, QIODevice, QUrl
    from PyQt5 import QtNetwork
else:
    from PyQt4.QtCore import QByteArray, QEventLoop, QFile, QIODevice, QUrl
    from PyQt4 import QtNetwork


class GISCloudNetworkHandler(object):
    """GIS Cloud helper class that doest REST requests on the API"""
    GET = 1
    POST = 2
    PUT = 3
    DELETE = 4

    app_id = "QGISPublisher/{} QGIS/{} ({}; {})".format(
        GIS_CLOUD_PUBLISHER_VERSION,
        QGIS_VERSION,
        platform.system(),
        platform.release())
    default_request = QtNetwork.QNetworkRequest()
    default_request.setHeader(QtNetwork.QNetworkRequest.ContentTypeHeader,
                              QByteArray(b'application/json'))
    default_request.setRawHeader(QByteArray(b'X-GIS-CLOUD-APP'),
                                 QByteArray(app_id.encode("utf-8")))

    reply_handlers = {}

    def __init__(self, reply, handle_reply, handle_error=None):
        self.reply = reply
        self.handle_reply = handle_reply
        self.handle_error = handle_error
        if self.handle_reply:
            self.reply.finished.connect(self.finished)
        if self.handle_error:
            self.reply.error.connect(self.error)
        GISCloudNetworkHandler.reply_handlers[self] = True

    def finished(self):
        """Called when request has been finished.
        We are parsing status code and data that we can forward
        to a callback function"""
        status_code = self.reply.attribute(
            QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)
        try:
            data = json.loads(self.reply.readAll().data().decode("utf-8"))
        except Exception:
            data = None

        if self.handle_reply:
            self.handle_reply(status_code, data, self)

        if self in GISCloudNetworkHandler.reply_handlers:
            del GISCloudNetworkHandler.reply_handlers[self]

    def error(self, error):
        """Invoking error callback in case of a fail"""
        errors = (QtNetwork.QNetworkReply.ContentNotFoundError,
                  QtNetwork.QNetworkReply.ContentAccessDenied,
                  QtNetwork.QNetworkReply.ContentOperationNotPermittedError)
        if error not in errors:
            if self.handle_error:
                self.handle_error(self)
            if self in GISCloudNetworkHandler.reply_handlers:
                del GISCloudNetworkHandler.reply_handlers[self]

    @staticmethod
    def auth_with_login(username, password):
        """Creating network request to autohorize with login"""
        req = QtNetwork.QNetworkRequest(GISCloudNetworkHandler.default_request)
        req.setRawHeader(QByteArray(b'api-username'),
                         QByteArray(username.encode('utf-8')))
        req.setRawHeader(QByteArray(b'api-password'),
                         QByteArray(password.encode('utf-8')))
        return req

    @staticmethod
    def auth_with_session(session):
        """Creating network request to autohorize with session"""
        req = QtNetwork.QNetworkRequest(GISCloudNetworkHandler.default_request)
        req.setRawHeader(QByteArray(b'api-sessid'),
                         QByteArray(session.encode('utf-8')))
        return req

    @staticmethod
    def request(request_type, url, key, payload=None,
                handle_reply=None, handle_error=None, default_request=None):
        """This is an blocking request method we use in threads"""
        # pylint: disable=R0913

        if not default_request:
            default_request = GISCloudNetworkHandler.default_request
        req = QtNetwork.QNetworkRequest(default_request)

        if key:
            req.setRawHeader(QByteArray(b'API-Key'),
                             QByteArray(str(key).encode("utf-8")))
        req.setUrl(QUrl(url))

        if payload:
            payload = QByteArray(json.dumps(payload).encode("utf-8"))
        if request_type == GISCloudNetworkHandler.POST:
            reply = QgsNetworkAccessManager.instance().post(req, payload)
        else:
            reply = QgsNetworkAccessManager.instance().get(req)

        handler = GISCloudNetworkHandler(reply,
                                         handle_reply,
                                         handle_error)

        return handler

    @staticmethod
    def blocking_request(request_type, url, key, payload=None,
                         default_request=None, progress_callback=None):
        """This is an universal blocking request method we use in threads"""
        # pylint: disable=R0913
        nam = QgsNetworkAccessManager.instance()

        if payload and not default_request:
            payload = QByteArray(json.dumps(payload).encode("utf-8"))

        if not default_request:
            default_request = GISCloudNetworkHandler.default_request
        req = QtNetwork.QNetworkRequest(default_request)
        req.setRawHeader(QByteArray(b'API-Key'),
                         QByteArray(str(key).encode("utf-8")))
        req.setUrl(QUrl(url))

        if request_type == GISCloudNetworkHandler.POST:
            reply = nam.post(req, payload)
        elif request_type == GISCloudNetworkHandler.PUT:
            reply = nam.put(req, payload)
        elif request_type == GISCloudNetworkHandler.DELETE:
            reply = nam.deleteResource(req)
        else:
            reply = nam.get(req)

        loop = QEventLoop()
        if progress_callback:
            reply.uploadProgress.connect(progress_callback)
        reply.finished.connect(loop.quit)
        reply.error.connect(loop.quit)
        loop.exec_()

        result = {}
        result["status_code"] = reply.attribute(
            QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)

        try:
            result["response"] = json.loads(
                reply.readAll().data().decode("utf-8"))
        except Exception:
            result["response"] = None

        location = reply.rawHeader(QByteArray(b'Location'))
        result["location"] = \
            location.data().decode("utf-8") if location else None
        return result

    @staticmethod
    def upload_file(file_to_upload, post_url, key, callback):
        """Method for uploading files to GIS Cloud"""
        zip_part = QtNetwork.QHttpPart()
        zip_part_content_disposition = QByteArray(
            'form-data; name="upfile"; filename="{}"'
            .format(os.path.basename(file_to_upload)).encode('utf-8'))
        zip_part.setHeader(QtNetwork.QNetworkRequest.ContentTypeHeader,
                           QByteArray(b'application/json'))
        zip_part.setHeader(QtNetwork.QNetworkRequest.ContentDispositionHeader,
                           zip_part_content_disposition)

        file_handler = QFile(file_to_upload)
        file_handler.open(QIODevice.ReadOnly)
        zip_part.setBodyDevice(file_handler)

        multi_part = QtNetwork.QHttpMultiPart(
            QtNetwork.QHttpMultiPart.FormDataType)
        file_handler.setParent(multi_part)
        multi_part.append(zip_part)

        request = QtNetwork.QNetworkRequest()
        request.setRawHeader(QByteArray(b'X-GIS-CLOUD-APP'),
                             GISCloudNetworkHandler.app_id.encode("utf-8"))
        result = GISCloudNetworkHandler.blocking_request(
            GISCloudNetworkHandler.POST,
            post_url,
            key,
            multi_part,
            request,
            callback)
        return result

    @staticmethod
    def cancel():
        """"Cancel all current network requests"""
        GISCloudNetworkHandler.reply_handlers = {}
