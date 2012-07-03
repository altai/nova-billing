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


"""
Nova Billing API.
"""

from itertools import repeat
from datetime import datetime

from sqlalchemy.sql import func, and_, or_
from sqlalchemy.sql.expression import text

from .models import CostCenter, Account, Resource, Segment, Tariff
from . import db

from nova_billing import utils


def bill_on_interval(period_start, period_stop, filter={}):
    """
    Retrieve statistics for the given interval [``period_start``, ``period_stop``].
    ``filter`` is a dict with possible keys account_id and cost_center_id.

    Example of the returned value:

    .. code-block:: python

        {
            1: [
                {
                    "name": "16",
                    "rtype": "nova/instance",
                    "created_at": "2011-01-02T00:00:00Z",
                    "destroyed_at": null,
                    "parent_id": null,
                    "cost": 0.0,
                    "id": 1
                },
                {
                    "name": null,
                    "rtype": "local_gb",
                    "created_at": "2011-01-02T00:00:00Z",
                    "destroyed_at": null,
                    "parent_id": 1,
                    "cost": 1200.0,
                    "id": 2
                },
                {
                    "name": null,
                    "rtype": "memory_mb",
                    "created_at": "2011-01-02T00:00:00Z",
                    "destroyed_at": null,
                    "parent_id": 1,
                    "cost": 380928.0,
                    "id": 3
                }
            ]
        }

    :returns: a dictionary where keys are account ids and values are billing lists.
    """
    now = datetime.utcnow()
    if now <= period_start:
        return {}

    def apply_filter(res):
        for attr in "account_id", "cost_center_id":
            if attr in filter:
                res = res.filter(getattr(Resource, attr) == filter[attr])
        return res

    result = apply_filter(db.session.query(Segment, Resource).
                join(Resource).
                filter(Segment.begin_at < period_stop).
                filter(or_(Segment.end_at > period_start,
                           Segment.end_at == None)))

    retval = {}
    rsrc_by_id = {}
    for segment, rsrc in result:
        if not retval.has_key(rsrc.account_id):
            retval[rsrc.account_id] = []
        try:
            rsrc_descr = rsrc_by_id[rsrc.id]
        except KeyError:
            rsrc_descr = {
                "id": rsrc.id,
                "created_at": None,
                "destroyed_at": None,
                "cost": 0.0,
                "parent_id": rsrc.parent_id,
                "name": rsrc.name,
                "rtype": rsrc.rtype,
            }
            retval[rsrc.account_id].append(rsrc_descr)
            rsrc_by_id[rsrc.id] = rsrc_descr
        begin_at = max(segment.begin_at, period_start)
        end_at = min(segment.end_at or now, period_stop)
        rsrc_descr["cost"] += utils.cost_add(segment.cost, begin_at, end_at)

    result = apply_filter(db.session.query(Segment,
        func.min(Segment.begin_at).label("min_start"),
        func.max(Segment.begin_at).label("max_start"),
        func.max(Segment.end_at).label("max_stop"),
        Resource.id).
        join(Resource).
        group_by(Resource.id).
        filter(Segment.begin_at < period_stop).
        filter(or_(Segment.end_at > period_start,
                   Segment.end_at == None)))

    for row in result:
        rsrc_descr = rsrc_by_id.get(row.id, None)
        if not rsrc_descr:
            continue
        rsrc_descr["created_at"] = row.min_start
        if row.max_stop is None or row.max_start < row.max_stop:
            rsrc_descr["destroyed_at"] = row.max_stop

    return retval


def cost_center_get_or_create(name):
    obj = CostCenter.query.filter_by(name=name).first()
    if obj == None:
        obj = CostCenter(name=name)
        db.session.add(obj)
        db.session.commit()
    return obj


def account_get_or_create(name, cost_center_name=None):
    obj = Account.query.filter_by(name=name).first()
    if obj == None:
        if cost_center_name:
            cost_center_id = cost_center_get_or_create(
                cost_center_name).id
        else:
            cost_center_id = None
        obj = Account(name=name, cost_center_id=cost_center_id)
        db.session.add(obj)
        db.session.commit()
    return obj


def resource_get_or_create(account_id, cost_center_id, parent_id, rtype, name):
    obj = Resource.query.filter_by(
        account_id=account_id,
        parent_id=parent_id,
        rtype=rtype,
        name=name).first()
    if obj == None:
        obj = Resource(
            account_id=account_id,
            cost_center_id=cost_center_id,
            parent_id=parent_id,
            rtype=rtype,
            name=name)
        db.session.add(obj)
        db.session.commit()
    return obj


def resource_segment_end(resource_id, end_at):
    db.session.execute(Segment.__table__.update().
        values(end_at=end_at).where(
            Segment.resource_id == resource_id))


def account_map():
    return dict(((obj.id, obj.name)
                 for obj in Account.query.all()))


def tariff_map():
    return dict(((obj.rtype, obj.multiplier)
                 for obj in Tariff.query.all()))


def resource_find(rtype, name):
    resource_account = (db.session.query(Resource, Account).
        filter(and_(Resource.rtype == rtype,
               and_(Resource.name == name,
               Resource.account_id == Account.id))).first())
    return resource_account[0] if resource_account else None


def tariffs_migrate(old_tariffs, new_tariffs, event_datetime):
    new_tariffs = dict(
        ((key, float(value))
         for key, value in new_tariffs.iteritems()
         if value != old_tariffs.get(key, 1.0)))
    if not new_tariffs:
        return

    connection = db.session.connection()
    for rtype in new_tariffs:
        old_t = old_tariffs.get(rtype, 1.0)
        if abs(old_t) < 1e-12:
            old_t = 1.0

        connection.execute(
            text(
                "insert into %(segment)s"
                " (resource_id, cost, begin_at, end_at)"
                " select resource_id, cost * :mpy, :event_datetime, NULL"
                " from %(segment)s, %(resource)s"
                " where end_at is NULL "
                " and %(segment)s.resource_id = %(resource)s.id"
                " and %(resource)s.rtype = :rtype" %
                {"segment": Segment.__tablename__,
                 "resource": Resource.__tablename__}),
            mpy=new_tariffs[rtype] / old_t,
            event_datetime=event_datetime,
            rtype=rtype)

    for rtype in new_tariffs.keys():
        connection.execute(
            text(
                "update %(segment)s"
                " set end_at = :event_datetime"
                " where end_at is NULL"
                " and begin_at != :event_datetime"
                " and resource_id in"
                " (select id from %(resource)s where rtype=:rtype)" %
                {"segment": Segment.__tablename__,
                 "resource": Resource.__tablename__}),
            event_datetime=event_datetime,
            rtype=rtype)
