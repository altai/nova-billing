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


import os
import sys
import datetime
import unittest

from nova_billing import utils

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests


class UsageTest(tests.TestCase):
    def test_total_seconds(self):
        begin_at = datetime.datetime(2011, 1, 12, 0, 0)
        end_at = datetime.datetime(2011, 1, 12, 0, 1)
        seconds = utils.total_seconds(end_at - begin_at)
        self.assertEquals(seconds, 60)
