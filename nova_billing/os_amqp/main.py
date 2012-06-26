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


"""Starter script for Billing OS AMQP binder."""

import eventlet
eventlet.monkey_patch()

import logging

from nova_billing.os_amqp import amqp
from nova_billing.utils import global_conf


LOG = logging.getLogger(__name__)


def main():
    global_conf.logging()
    LOG.info("starting os_amqp")
    service = amqp.Service()
    service.start()
    service.wait()


if __name__ == '__main__':
    main()
