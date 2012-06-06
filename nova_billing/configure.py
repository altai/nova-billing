#!/usr/bin/python2
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


import json
import logging
import sys

try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser

from nova import flags
from nova import utils

from nova_billing.utils import CONFIG_FILE, global_conf


LOG = logging.getLogger(__name__)


def main():
    global_conf.logging()

    utils.default_flagfile("nova.conf")
    flags.FLAGS(sys.argv)
    FLAGS = flags.FLAGS
    conf = global_conf._conf
    for param in ("rabbit_host",
                  "rabbit_port",
                  "rabbit_userid",
                  "rabbit_password",
                  "rabbit_virtual_host",
                  "rabbit_durable_queues",
                  "control_exchange"):
        conf[param] = getattr(FLAGS, param)

    nova_api_config = ConfigParser()
    nova_api_config.read(["/etc/nova/api-paste.ini"])
    for param in ("auth_uri",
                  "admin_tenant_name",
                  "admin_user",
                  "admin_password"):
        try:
            value = nova_api_config.get("filter:authtoken", param)
        except Exception as e:
            print e
        else:
            conf[param] = value

    json.dump(conf, open(CONFIG_FILE, "w"), indent=4, sort_keys=True)


if __name__ == "__main__":
    main()
