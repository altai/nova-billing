# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Nova Billing
#    Copyright (C) GridDynamics Openstack Core Team, GridDynamics
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Tests for nova_billing.rest
"""

import os
import sys
import json
import datetime
import unittest
import stubout
import tempfile

import routes
import webob

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests


from nova_billing import utils

from nova_billing.heart import app
from nova_billing.heart.database import db


class TestCase(tests.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.db_fd, self.db_filename = tempfile.mkstemp()
        app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:////" + self.db_filename
        app.config['TESTING'] = True
        self.app_client = app.test_client()
        db.create_all()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_filename)
        super(TestCase, self).tearDown()

    def feed_requests(self, filename):
        test_list = []
        for test in self.json_load_from_file(filename):
            uri = test["uri"]
            method = test.get("method", "GET").upper()
            request_body = test.get("request_body", None)
            if request_body is None:
                res = self.app_client.open(
                    uri, method=method)
            else:
                res = self.app_client.open(
                    uri, method=method,
                    data=json.dumps(request_body),
                    content_type=utils.ContentType.JSON)
            try:
                response_json = json.loads(res.data)
            except:
                response_json = None
            if self.write_json:
                test_list.append({
                        "uri": uri,
                        "method": method,
                        "status": res.status_code,
                        "request_body": request_body,
                        "response_body": response_json,
                })
            else:
                self.assertEqual(
                    res.status_code, test["status"],
                    "incorrect status code for %s %s" % (method, uri))
                self.assertEqual(
                    response_json,
                    test["response_body"],
                    "incorrect response body for %s %s" % (method, uri))
        if self.write_json:
            self.json_save_to_file(test_list, filename)

    def assertSuccess(self, res):
        self.assertEqual(res.status_code / 100, 2)

    def create_accounts(self):
        self.feed_requests("rest.v2/account_create.json")

    def create_tariffs(self):
        self.feed_requests("rest.v2/tariff_create.json")

    def populate_db(self):
        self.create_accounts()
        self.create_tariffs()
        for filename in ("os_amqp/instances.out.json",
                         "os_amqp/local_volumes.out.json"):
            json_out = self.json_load_from_file(filename)
            for event in json_out:
                res = self.app_client.post(
                    "/v2/event",
                    data=json.dumps(event),
                    content_type=utils.ContentType.JSON)
                self.assertSuccess(res)

    def fake_now(self):
        return datetime.datetime(2011, 1, 1)

    def test_version(self):
        res = self.app_client.get("/version")
        self.assertSuccess(res)

    def test_tariff(self):
        self.create_tariffs()
        self.feed_requests("rest.v2/tariff_get.json")
        self.feed_requests("rest.v2/tariff_update.json")

    def test_account(self):
        self.create_accounts()
        self.feed_requests("rest.v2/account_get.json")
        self.feed_requests("rest.v2/account_update.json")

    def test_cost_center(self):
        self.populate_db()
        self.feed_requests("rest.v2/cost_center_get.json")
        self.stubs.Set(utils, "now", self.fake_now)
        self.feed_requests("rest.v2/cost_center_delete.json")

    def test_resource(self):
        self.populate_db()
        self.feed_requests("rest.v2/resource_get.json")
        self.feed_requests("rest.v2/resource_update.json")

    def test_report(self):
        self.stubs.Set(utils, "now", self.fake_now)
        self.populate_db()
        self.feed_requests("rest.v2/report_get.json")
        self.stubs.UnsetAll()
