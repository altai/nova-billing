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

import logging
from nova_billing import utils
from nova_billing.utils import global_conf


LOG = logging.getLogger(__name__)


class vm_states(object):
    ACTIVE = 0
    BUILDING = 1
    REBUILDING = 2

    PAUSED = 3
    SUSPENDED = 4
    RESCUED = 5
    DELETED = 6
    STOPPED = 7

    MIGRATING = 8
    RESIZING = 9

    ERROR = 10


instance_resources = ("local_gb", "memory_mb", "vcpus")

flavor_map = {"disk": "local_gb", "ram": "memory_mb", "vcpus": "vcpus"}

used_resources = {
    vm_states.ACTIVE: ("memory_mb", "vcpus", "local_gb"),
    vm_states.SUSPENDED: ("memory_mb", "local_gb"),
    vm_states.PAUSED: ("memory_mb", "local_gb"),
    vm_states.STOPPED: ("local_gb", ),
}


target_state = {
    "run_instance": vm_states.ACTIVE,
    "terminate_instance": vm_states.DELETED,
    "start_instance": vm_states.ACTIVE,
    "stop_instance": vm_states.STOPPED,
    "unpause_instance": vm_states.ACTIVE,
    "pause_instance": vm_states.PAUSED,
    "resume_instance": vm_states.ACTIVE,
    "suspend_instance": vm_states.SUSPENDED,
}


# Cache flavors here
flavors = {}
no_flavor = {
    "name": "<none>",
    "local_gb": 0,
    "memory_mb": 0,
    "vcpus": 0,
}

nova = None

def get_flavor(flavor_id):
    try:
        return flavors[flavor_id]
    except KeyError:
        pass
    try:
        flav = nova.flavors.get(flavor_id)
    except:
        return no_flavor
    b_flav = {"name": flav.name}
    for nova, billing in flavor_map.iteritems():
        b_flav[billing] = getattr(flav, nova)
    flavors[flavor_id] = b_flav
    return b_flav


def get_instance_flavor(instance_id):
    try:
        return get_flavor(
            nova.servers.get(instance_id).flavor["id"])
    except:
        return no_flavor


def create_heart_request(method, body):
    global nova
    if not nova:
        nova = utils.get_clients().nova

    try:
        state = target_state[method]
    except KeyError:
        return None

    heart_request = {"rtype": "nova/instance"}

    release = getattr(global_conf, "os_release", None)
    checked_keys = {"diablo": ("instance_id", ),
                    "essex": ("instance_uuid", )}
    checked_keys = checked_keys.get(release, ("instance_uuid", "instance_id"))
    for key in checked_keys:
        try:
            heart_request["name"] = body["args"][key]
            break
        except KeyError:
            pass
    if "name" not in heart_request:
        LOG.error("cannot find keys %s (maybe incorrect OpenStack release)" %
                  (checked_keys, ))
        return None

    child_keys = ("local_gb", "memory_mb", "vcpus")
    if method == "terminate_instance":
        heart_request["fixed"] = None
        heart_request["children"] = [
            {"rtype": key, "fixed": None}
            for key in child_keys]
    else:
        used = used_resources[state]
        try:
            flav = body["args"]["request_spec"]["instance_type"]
        except KeyError:
            flav = get_instance_flavor(heart_request["name"])
        if method == "run_instance":
            heart_request["fixed"] = 0
            heart_request["attrs"] = {"instance_type": flav["name"]}
        else:
            child_keys = child_keys[1:]
        heart_request["children"] = [
            {"rtype": key, "linear": flav[key] if key in used else 0}
            for key in child_keys
        ]
    return heart_request
