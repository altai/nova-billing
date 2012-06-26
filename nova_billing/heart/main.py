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


"""Starter script for Nova Billing heart."""

import argparse
import logging

from nova_billing.heart import app
from nova_billing.heart.database import db
from nova_billing.utils import global_conf


LOG = logging.getLogger(__name__)


def main():
    global_conf.logging()

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--reload", "-r", default=False,
                            action="store_true",
                            help="reload when the source changes")
    arg_parser.add_argument("host:port", nargs="?",
                            default="%s:%s" % (
                                global_conf.host,
                                global_conf.port),
                            help="host:port")
    args = arg_parser.parse_args()

    LOG.info("starting heart")
    db.create_all()
    listen = getattr(args, "host:port").split(':')
    app.debug = True
    app.run(host=listen[0], port=int(listen[1]), use_reloader=args.reload)


if __name__ == '__main__':
    main()
