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


target_methods = (
    "create_local_volume",
    "delete_local_volume",
    "resize_local_volume",
)


def create_heart_request(method, body):
    if method not in target_methods:
        return None

    heart_request = {
        "rtype": "nova/volume",
        "name": body["args"]["volume_id"],
    }

    if method == "create_local_volume":
        heart_request["linear"] = body["args"]["size"] / (1024.0 ** 3)
    elif method == "resize_local_volume":
        heart_request["linear"] = body["args"]["new_size"] / (1024.0 ** 3)
    else:
        heart_request["fixed"] = None
    return heart_request
