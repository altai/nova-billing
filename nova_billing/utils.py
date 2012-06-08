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
Miscellaneous utility functions:

- usage calculations for different VM states;
- datetime manipulations;
- other.
"""

import json
import logging
import sys
import os
from datetime import datetime

from nova_billing.client import BillingHeartClient


LOG = logging.getLogger(__name__)


class ContentType(object):
    JSON = "application/json"


def total_seconds(td):
    """This function is added for portability
    because timedelta.total_seconds()
    was introduced only in python 2.7."""
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6


def now():
    """
    Return current time in UTC.
    """
    return datetime.utcnow()


def str_to_datetime(dtstr):
    """
    Convert string to datetime.datetime. String should be in ISO 8601 format.
    The function returns ``None`` for invalid date string.
    """
    if not dtstr:
        return None
    if dtstr.endswith("Z"):
        dtstr = dtstr[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(dtstr, fmt)
        except ValueError:
            pass
    return None


def datetime_to_str(dt):
    """
    Convert datetime.datetime instance to string.
    Used for JSONization.
    """
    return ("%sZ" % dt.isoformat()) if isinstance(dt, datetime) else None


def usage_to_hours(usage):
    """
    Convert usage measured for seconds to hours.
    """
    return dict([(key + "_h", usage[key] / 3600.0) for key in usage])


def dict_add(a, b):
    """
    Increment all keys in ``a`` on keys in ``b``.
    """
    for key in b:
        a[key] = a.get(key, 0) + b[key]


def cost_add(cost, begin_at, end_at):
    # 31556952 seconds - an average Gregorian year
    return cost if cost < 0 else cost * total_seconds(end_at - begin_at) / 31556952.0


class GlobalConf(object):
    _conf = {
        "host": "127.0.0.1",
        "port": 8787,
        "log_dir": "/var/log/nova-billing",
        "log_format": "%(asctime)-15s:nova-billing:%(levelname)s:%(name)s:%(message)s",
        "log_level": "DEBUG",
        "keystone_conf": {},
    }

    def load_from_file(self, filename):
        try:
            with open(filename, "r") as file:
                self._conf.update(json.loads(file.read()))
        except:
            pass

    def __getattr__(self, name):
        try:
            return self._conf[name]
        except KeyError:
            raise AttributeError(name)

    def logging(self):
        try:
            log_file = self.log_file
        except AttributeError:
            log_name = os.path.basename(sys.argv[0])
            if not log_name:
                log_name = "unknown"
            log_file = "%s/%s.log" % (self.log_dir, log_name)

        def get_logging_level(name):
            if name in ("DEBUG", "INFO", "WARN", "ERROR"):
                return getattr(logging, name)
            return logging.DEBUG

        level = get_logging_level(self.log_level)
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(self.log_format))
        LOG = logging.getLogger()
        LOG.addHandler(handler)
        LOG.setLevel(level)


CONFIG_FILE = "/etc/nova-billing/settings.json"
global_conf = GlobalConf()
global_conf.load_from_file(CONFIG_FILE)


class ClientSet(object):

    @staticmethod
    def strip_version(endpoint):
        if not endpoint:
            return ""
        if endpoint.endswith("/"):
            endpoint = endpoint[:-1]
        if endpoint.endswith("/v2.0"):
            endpoint = endpoint[:-5]
        if endpoint.endswith("/v1"):
            endpoint = endpoint[:-3]
        return endpoint

    def __init__(self, **conf):
        """
        Acceptable arguments:
        - auth_uri or auth_url;
        - username, password;
        - tenant_id, tenant_name=None;
        - token, region_name.
        """
        self.conf = conf.copy()
        self.conf["auth_uri"] = "%s/v2.0" % self.strip_version(
            conf.get("auth_uri") or conf.get("auth_url"))

    @property
    def keystone(self):
        conf = self.conf
        from keystoneclient.v2_0.client import Client as KeystoneClient
        keystone = KeystoneClient(
            username=conf.get("username"),
            password=conf.get("password"),
            tenant_id=conf.get("tenant_id"),
            tenant_name=conf.get("tenant_name"),
            auth_url=conf.get("auth_uri"),
            region_name=conf.get("region_name"),
            token=conf.get("token"))
        # the __init__ calls authenticate() immediately
        return keystone

    @property
    def nova(self):
        conf = self.conf
        keystone = self.keystone
        from novaclient.v1_1.client import Client as NovaClient
        nova = NovaClient(
            conf.get("username"),
            conf.get("password"),
            conf.get("tenant_name"),
            conf.get("auth_uri"),
            region_name=conf.get("region_name"),
            token=keystone.token)
        nova.client.management_url = (
            keystone.service_catalog.url_for(
                service_type="compute"))
        return nova

    @property
    def glance(self):
        keystone = self.keystone
        from glanceclient.v1.client import Client as GlanceClient
        self.glance = GlanceClient(
            endpoint=self.strip_version(
                keystone.service_catalog.url_for(
                    service_type="image")),
            token=keystone.auth_token)

    @property
    def billing(self):
        keystone = self.keystone
        return BillingHeartClient(
            management_url=keystone.service_catalog.url_for(
                service_type="nova-billing"))

clients = None

def get_clients():
    global clients
    if not clients:
        clients = ClientSet(**global_conf.keystone_conf)
    return clients
