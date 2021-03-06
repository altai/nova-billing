# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Nova Billing
# Copyright (C) 2010-2012 Grid Dynamics Consulting Services, Inc
# All Rights Reserved
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program. If not, see
# <http://www.gnu.org/licenses/>.


import json
import logging
import webob

from nova_billing import utils
from nova_billing.utils import global_conf


LOG = logging.getLogger(__name__)


class GlanceBillingFilter(object):
    def __init__(self, application):
        self.billing_heart = global_conf.clients.billing
        self.application = application

    @webob.dec.wsgify
    def __call__(self, req):
        resp = req.get_response(self.application)
        path_info = req.environ.get("PATH_INFO", "/")
        if not path_info.startswith("/images"):
            return resp
        method = req.environ.get("REQUEST_METHOD", "GET")
        if method == "PUT" or method == "POST":
            try:
                resp_json = json.loads(resp.body)
                img_id, img_size = resp_json["image"]["id"], resp_json["image"]["size"]
            except KeyError:
                return resp
            heart_request = {"name": img_id,
                             "linear": img_size / (1024.0 ** 3)}
        elif method == "DELETE":
            heart_request = {"name": path_info[len("/images/"):],
                             "fixed": None}
        else:
            heart_request = None
        if heart_request is not None:
            heart_request["rtype"] = "glance/image"
            heart_request["account"] = req.headers["X-Tenant-Id"]
            heart_request["datetime"] = utils.datetime_to_str(utils.now())
            try:
                self.billing_heart.event.create(heart_request)
            except:
                LOG.exception("cannot report image info for billing")
        return resp

    @classmethod
    def factory(cls, global_config, **local_config):
        def filter(app):
            return cls(app)

        return filter
