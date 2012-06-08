
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


from sqlalchemy import create_engine
from flask import _request_ctx_stack

from nova_billing import utils
from nova_billing.utils import global_conf, get_clients
from nova_billing.heart.database import db
from nova_billing.heart.database import api as db_api
from nova_billing.heart.database.models import Segment, Resource

from nova_billing.os_amqp.instances import instance_resources, flavor_map


LOG = logging.getLogger(__name__)



usage = "usage: nova-billing-migrate glance|nova|billing_v1 [-o|-overwrite] [URI]"


def complain_usage():
    print >>sys.stderr, usage
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        complain_usage()

    global_conf.logging()
    # make Flask-SQLalchemy happy
    _request_ctx_stack.push(1)
    db.create_all()
    if sys.argv[1] == "sync":
        return
    overwrite = False
    uri = None
    for i in sys.argv[2:]:
        if i == "-o" or i == "--overwrite":
            overwrite = True
        else:
            uri = i
    if sys.argv[1] == "glance":
        migrate_glance(overwrite)
    elif sys.argv[1] == "nova":
        migrate_nova(overwrite)
    elif sys.argv[1] == "billing_v1" and uri:
        migrate_billing_v1(uri)
    else:
        complain_usage()


class ResourceTypes(object):
    Instance = "nova/instance"
    Image = "glance/image"


class AccountManager(object):
    _avail = {}

    def get_or_create(self, name):
        try:
            return self._avail[name]
        except KeyError:
            obj = db_api.account_get_or_create(
                name)
            self._avail[name] = obj
            return obj


def check_skip_on_exists(resource, overwrite):
    if overwrite:
        Segment.query.filter_by(resource_id=resource.id).delete()
        connection = db.session.connection()
        connection.execute(
            "delete from %(segment)s"
            " where resource_id in"
            " (select id from %(resource)s where parent_id = ?)" %
            {"segment": Segment.__tablename__,
             "resource": Resource.__tablename__},
            resource.id)
    else:
        if Segment.query.filter_by(resource_id=resource.id).first():
            LOG.debug("segments for resource %s (name=%s) already exist" %
                      (resource.id, resource.name))
            return True


def migrate_glance(overwrite):
    client = get_clients().glance
    tariffs = db_api.tariff_map()
    acc_man = AccountManager()

    images = client.images.list()
    for img1 in images:
        if not img1.owner:
            LOG.debug("image %s has no owner" %
                      img1.id)
            continue
        account_id = acc_man.get_or_create(img1.owner).id
        img2 = db_api.resource_get_or_create(
            account_id, None, None,
            ResourceTypes.Image,
            img1.id)
        if check_skip_on_exists(img2, overwrite):
            continue
        LOG.debug("adding info for image %s (name=%s)" % (img2.id, img2.name))
        seg = Segment(
            resource_id=img2.id,
            cost=img1.size * tariffs.get(ResourceTypes.Image, 1) /
            (1024.0 ** 3),
            begin_at=utils.str_to_datetime(img1.created_at),
            end_at=utils.str_to_datetime(img1.deleted_at))
        db.session.add(seg)

    db.session.commit()


def migrate_nova(overwrite):
    client = get_clients().nova
    tariffs = db_api.tariff_map()
    acc_man = AccountManager()
    flavors = {}
    for flav in client.flavors.list():
        flavors[str(flav.id)] = flav
    deleted_flavors = set()
    counter = 0
    for deleted in 0, 1:
        inst1_list = client.servers.list(
            detailed=True,
            search_opts={"deleted": deleted, "all_tenants": 1})
        for inst1 in inst1_list:
            acc_id = acc_man.get_or_create(inst1.tenant_id).id
            inst2 = db_api.resource_get_or_create(
                acc_id, None, None,
                ResourceTypes.Instance,
                inst1.id)
            if check_skip_on_exists(inst2, overwrite):
                continue

            try:
                flav_id = str(inst1.flavor["id"])
                flav = flavors[flav_id]
            except KeyError:
                LOG.error("cannot add info for instance %s (name=%s) "
                          "flavor %s is not found (perhaps it was deleted" %
                          (inst2.id, inst2.name, flav_id))
                continue
            LOG.debug("adding info for instance %s (name=%s)" % (inst2.id, inst2.name))
            begin_at = utils.str_to_datetime(inst1.created)
            end_at = utils.str_to_datetime(inst1.updated) if deleted else None
            for nova, billing in flavor_map.iteritems():
                child = db_api.resource_get_or_create(
                    acc_id, None, inst2.id,
                    billing,
                    None)
                seg = Segment(
                    resource_id=child.id,
                    cost=getattr(flav, nova) * tariffs.get(billing, 1),
                    begin_at=begin_at,
                    end_at=end_at)
                db.session.add(seg)
            seg = Segment(
                resource_id=inst2.id,
                cost=tariffs.get(ResourceTypes.Instance, 0),
                begin_at=begin_at,
                end_at=end_at)
            db.session.add(seg)
            counter += 1
            if counter % 32 == 0:
                db.session.commit()
    db.session.commit()


def migrate_billing_v1(old_db_url):
    engine1 = create_engine(old_db_url)

    tariffs = db_api.tariff_map()
    instance_info_attrs = (
        "id", "instance_id", "project_id",
        "local_gb", "memory_mb", "vcpus")
    instance_segment_attrs = (
        "id", "instance_info_id",
        "segment_type", "begin_at",
        "end_at")
    instance_infos = {}
    accounts = {}
    for inst1 in engine1.execute(
        "select distinct project_id from billing_instance_info"):
        accounts[inst1.project_id] = \
            db_api.account_get_or_create(inst1.project_id).id

    for inst1 in engine1.execute(
        "select %s from billing_instance_info" %
        ", ".join(instance_info_attrs)):
        account_id = accounts[inst1.project_id]
        inst2 = db_api.resource_get_or_create(
            account_id, None,
            ResourceTypes.Instance,
            inst1.instance_id
        )
        inst_dict = {
            "inst1": inst1,
            "inst2": inst2,
        }
        for rtype in instance_resources:
            inst_dict[rtype + "_id"] = db_api.resource_get_or_create(
                account_id, inst2.id,
                rtype,
                None
            )
        instance_infos[inst1.id] = inst_dict

    for iseg in engine1.execute(
        "select %s from billing_instance_segment" %
        ", ".join(instance_segment_attrs)):
        inst_dict = instance_infos[iseg.instance_info_id]
        inst1 = inst_dict["inst1"]
        begin_at = utils.str_to_datetime(iseg.begin_at)
        end_at = utils.str_to_datetime(iseg.end_at)
        inst_dict["begin_at"] = (min(inst_dict["begin_at"], begin_at)
                                 if "begin_at" in inst_dict else begin_at)
        try:
            prev = inst_dict["end_at"]
        except KeyError:
            inst_dict["end_at"] = end_at
        else:
            inst_dict["end_at"] = (
                max(prev, end_at) if prev
                else None)
        for rtype in instance_resources:
            seg = Segment(
                resource_id=inst_dict[rtype + "_id"].id,
                cost=getattr(inst1, rtype) * tariffs.get(rtype, 1),
                begin_at=begin_at,
                end_at=end_at)
            db.session.add(seg)

    for inst_dict in instance_infos.values():
        seg = Segment(
            resource_id=inst_dict["inst2"].id,
            cost=tariffs.get(ResourceTypes.Instance, 0),
            begin_at=inst_dict.get("begin_at", None),
            end_at=inst_dict.get("end_at", None))
        db.session.add(seg)

    db.session.commit()


if __name__ == "__main__":
    main()
