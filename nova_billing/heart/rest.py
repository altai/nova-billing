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
REST API for Nova Billing Heart
"""

import datetime
import json
import logging

from flask import Flask, request, session, redirect, url_for, \
     jsonify, Response
from werkzeug.exceptions import BadRequest, Unauthorized, NotFound
from . import app

from .database import api as db_api
from .database import db
from .database.models import BillingBase, CostCenter, Account, Resource, Segment, Tariff

from nova_billing import utils
from nova_billing.version import version_string


LOG = logging.getLogger(__name__)


def request_json():
    ret = request.json
    if ret == None:
        raise BadRequest("Content-Type should be %s" % utils.ContentType.JSON)
    return ret


def to_json(resp):
    return Response(
            json.dumps(resp,
            default=utils.datetime_to_str),
            mimetype=utils.ContentType.JSON)


def check_attrs(rj, attr_list):
    for attr in attr_list:
        if attr not in rj:
            raise BadRequest(
                description="%s must be specified" % attr)


def check_and_get_datatime(rj):
    ret = utils.str_to_datetime(rj.get("datetime", None))
    if not ret:
        raise BadRequest(
            description="valid datetime must be specified")
    return ret


def get_request_version():
    return request.environ.get("PATH_INFO", "")[1:3]


def account_get_or_create(rj):
    check_attrs(rj, ("rtype", ))
    account_name = rj.get("account_name", rj.get("account", None))
    if not account_name:
        resource = db_api.resource_find(rj["rtype"], rj.get("name", None))
        if not resource:
            raise BadRequest(description="account must be specified")
        account_id = resource.account_id
        cost_center_id = resource.cost_center_id
    else:
        account = db_api.account_get_or_create(
            account_name, rj.get("cost_center_name", None))
        account_id = account.id
        cost_center_id = account.cost_center_id

    return account_id, cost_center_id


def get_period():
    if not request.args.has_key("time_period"):
        if "period_start" in request.args:
            period_start = utils.str_to_datetime(request.args["period_start"])
            try:
                period_end = utils.str_to_datetime(request.args["period_end"])
            except KeyError:
                raise BadRequest(description="period_end is request.ired")
            if not (period_start and period_end):
                raise BadRequest(
                    description="date should be in ISO 8601 format of YYYY-MM-DDThh:mm:ssZ")
            if period_start >= period_end:
                raise BadRequest(
                    description="period_start must be less than period_end")
            return period_start, period_end
        else:
            now = utils.now()
            date_args = (now.year, now.month, 1)
            date_incr = 1
    else:
        time_period_splitted = request.args["time_period"].split("-", 2)
        date_args = [1, 1, 1]
        for i in xrange(min(2, len(time_period_splitted))):
            try:
                date_args[i] = int(time_period_splitted[i])
            except ValueError:
                raise BadRequest(
                    description="invalid time_period `%s'" % request.args["time_period"])
        date_incr = len(time_period_splitted) - 1

    period_start = datetime.datetime(*date_args)
    if date_incr == 2:
        period_end = period_start + datetime.timedelta(days=1)
    else:
        year, month, day = date_args
        if date_incr == 1:
            month += 1
            if month > 12:
                month = 1
                year += 1
        else:
            year += 1
        period_end = datetime.datetime(year=year, month=month, day=day)
    return period_start, period_end


class BillingBaseExt(object):

    @classmethod
    def filter_by_id_name(cls):
        args = request.args
        fld_id = "%s_id" % cls.__tablename__
        value = args.get(fld_id, None)
        if value:
            return {fld_id: value}
        fld_name = "%s_name" % cls.__tablename__
        value = args.get(fld_name)
        if value:
            obj = cls.query.filter_by(name=value).first()
            if obj == None:
                raise NotFound(
                    "Requested %s=%s is not found" % (fld_name, value))
            return {fld_id: obj.id}
        return {}

    @classmethod
    def query_filtered(cls):
        filter = dict(((fld, request.args[fld])
                       for fld in cls.fld_list()
                       if fld in request.args))
        res = cls.query
        if filter:
            res = res.filter_by(**filter)
        return res

    def to_json(self):
        fld_list = self.fld_list()
        return to_json(
            dict(((fld, getattr(self, fld)) for fld in fld_list))
            )

    @classmethod
    def list_to_json(cls, obj_list):
        fld_list = cls.fld_list()
        return to_json([
                dict(((fld, getattr(obj, fld)) for fld in fld_list))
                for obj in obj_list
                ])

    @classmethod
    def fld_list(cls):
        fld_list = cls._fld_list[0]
        if get_request_version() == "v2":
            fld_list += cls._fld_list[1]
        return fld_list


class AccountExt(object):

    @classmethod
    def query_filtered(cls):
        res = super(Account, cls).query_filtered()
        if get_request_version() == "v2":
            filter = CostCenter.filter_by_id_name()
            if filter:
                res = res.filter_by(**filter)
        return res


class ResourceExt(object):

    @classmethod
    def query_filtered(cls):
        res = super(Resource, cls).query_filtered()
        filter = Account.filter_by_id_name()
        if filter:
            res = res.filter_by(**filter)
        if get_request_version() == "v2":
            filter = CostCenter.filter_by_id_name()
            if filter:
                res = res.filter_by(**filter)
        return res


def copy_methods(src, dest):
    for name in src.__dict__:
        fld = getattr(src, name)
        if callable(fld):
            setattr(dest, name, src.__dict__[name])


copy_methods(BillingBaseExt, BillingBase)
copy_methods(AccountExt, Account)
copy_methods(ResourceExt, Resource)

Account._fld_list = [("id", "name"), ("cost_center_id", )]
CostCenter._fld_list = [(), ("id", "name")]
Resource._fld_list = [("id", "name", "rtype", "parent_id", "account_id"), ("cost_center_id", )]


@app.route("/version")
def version_get():
    def links(base_url, url_list):
        return [{
            "href": "%s/%s" % (base_url, url),
            "rel": "self",
        } for url in url_list]

    start_url = "http://%s:%s" % (request.environ["SERVER_NAME"], request.environ["SERVER_PORT"])
    return jsonify({"versions": [
        {
            "status": "CURRENT",
            "id": "v2",
            "links": links("%s/v2" % start_url,
                           ("report", "resource", "account", "tariff", "cost_center"))
        },
        {
            "status": "SUPPORTED",
            "id": "v1",
            "links": links("%s/v1" % start_url,
                           ("bill", "resource", "account", "tariff"))
        },
    ]})


@app.route("/v1/bill")
@app.route("/v2/report")
def report_get():
    period_start, period_end = get_period()
    resource_filter = Account.filter_by_id_name()
    if get_request_version() == "v2":
        accounts_key = "accounts"
        if not resource_filter:
            resource_filter = CostCenter.filter_by_id_name()
    else:
        accounts_key = "bill"
    total_statistics = db_api.bill_on_interval(
        period_start, period_end, resource_filter)

    accounts = db_api.account_map()

    ans_dict = {
        "period_start": period_start,
        "period_end": period_end,
        accounts_key: [{
            "id": key, "name": accounts.get(key, None),
            "resources": value
        } for key, value in total_statistics.iteritems()],
    }
    return to_json(ans_dict)


def process_event(rsrc, parent_id,
                  account_id, cost_center_id,
                  event_datetime, tariffs):
    """
    linear - saved as a non-negative cost
    fixed - saved with opposite sign (as a non-positive cost)
    fixed=None - closes the segment but does not create a new one
    """
    if not "rtype" in rsrc:
        return
    rsrc_obj = db_api.resource_get_or_create(
        account_id, cost_center_id, parent_id,
        rsrc["rtype"], rsrc.get("name", None))
    rsrc_id = rsrc_obj.id

    try:
        attrs = rsrc["attrs"]
    except KeyError:
        pass
    else:
        if rsrc_obj.attrs:
            attrs.update(rsrc_obj.get_attrs())
        rsrc_obj.set_attrs(attrs)
        db.session.merge(rsrc_obj)

    close_segment = True
    if "linear" in rsrc:
        cost = -rsrc["linear"]
    elif "fixed" in rsrc:
        cost = rsrc["fixed"]
    else:
        cost = None
        close_segment = False
    if close_segment:
        db_api.resource_segment_end(rsrc_id, event_datetime)
    if cost is not None:
        obj = Segment(
            resource_id=rsrc_id,
            cost=-cost * tariffs.get(rsrc["rtype"], 1),
            begin_at=event_datetime)
        db.session.add(obj)

    for child in rsrc.get("children", ()):
        process_event(child, rsrc_id,
                      account_id, cost_center_id,
                      event_datetime, tariffs)


def process_resource(rsrc, parent_id, account_id, cost_center_id):
    if not "rtype" in rsrc:
        return
    rsrc_obj = db_api.resource_get_or_create(
        account_id, cost_center_id, parent_id,
        rsrc["rtype"], rsrc.get("name", None))
    rsrc_id = rsrc_obj.id

    try:
        attrs = rsrc["attrs"]
    except KeyError:
        pass
    else:
        rsrc_obj.set_attrs(attrs)
        db.session.merge(rsrc_obj)

    for child in rsrc.get("children", ()):
        process_resource(child, rsrc_id, account_id, cost_center_id)


@app.route("/v1/event", methods=["POST"])
@app.route("/v2/event", methods=["POST"])
def event_create():
    rj = request_json()
    LOG.debug("received event %s" % rj)
    rj_datetime = check_and_get_datatime(rj)
    account_id, cost_center_id = account_get_or_create(rj)

    tariffs = db_api.tariff_map()
    process_event(rj, None,  account_id, cost_center_id, rj_datetime, tariffs)

    db.session.commit()
    return to_json({"account_id": account_id,
                    "rtype": rj["rtype"],
                    "datetime": rj_datetime,
                    "name": rj.get("name", None)})


@app.route("/v1/tariff", methods=["GET"])
@app.route("/v2/tariff", methods=["GET"])
def tariff_get():
    tariffs = db_api.tariff_map()
    return to_json(tariffs)


@app.route("/v1/tariff", methods=["POST"])
@app.route("/v2/tariff", methods=["POST"])
def tariff_update():
    rj = request_json()
    check_attrs(rj, ("values", ))
    rj_datetime = check_and_get_datatime(rj)
    migrate = rj.get("migrate", False)

    if migrate:
        old_tariffs = db_api.tariff_map()
    new_tariffs = rj["values"]
    for key, value in new_tariffs.iteritems():
        if isinstance(value, int) or isinstance(value, float):
            db.session.merge(Tariff(rtype=key, multiplier=value))

    if migrate:
        db_api.tariffs_migrate(
            old_tariffs,
            new_tariffs,
            rj_datetime)

    db.session.commit()

    return to_json(new_tariffs)


@app.route("/v1/account", methods=["GET"])
@app.route("/v2/account", methods=["GET"])
def account_get():
    res = Account.query_filtered()
    return Account.list_to_json(res.all())


@app.route("/v1/resource", methods=["GET"])
@app.route("/v2/resource", methods=["GET"])
def resource_get():
    res = Resource.query_filtered()
    fld_list = Resource.fld_list()

    def get_rsrc_dict(obj):
        rsrc_dict = dict(((fld, getattr(obj, fld)) for fld in fld_list))
        rsrc_dict["attrs"] = obj.get_attrs()
        return rsrc_dict

    return to_json([get_rsrc_dict(obj) for obj in res.all()])


@app.route("/v1/resource", methods=["POST"])
def resource_create():
    rj = request_json()
    account_id, cost_center_id = account_get_or_create(rj)

    process_resource(rj, None, account_id, cost_center_id)

    db.session.commit()
    return to_json({"account_id": account_id,
                    "rtype": rj["rtype"],
                    "name": rj.get("name", None)})


def obj_update_name(cls):
    rj = request_json()
    check_attrs(rj, ("name",))
    ret = cls.query_filtered()
    if ret.count() != 1:
        raise BadRequest(
            "Exactly one %s must be specified."
            % cls.__tablename__)
    obj = ret.first()
    obj.name = rj["name"]
    db.session.merge(obj)
    db.session.commit()
    return obj.to_json()


@app.route("/v2/resource", methods=["PUT"])
def resource_update():
    return obj_update_name(Resource)


@app.route("/v2/account", methods=["POST"])
def account_create():
    rj = request_json()
    check_attrs(rj, ("name", "cost_center_name"))
    obj = db_api.account_get_or_create(
        rj["name"], rj["cost_center_name"])
    return obj.to_json()


@app.route("/v2/account", methods=["PUT"])
def account_update():
    return obj_update_name(Account)


@app.route("/v2/cost_center", methods=["GET"])
def cost_center_get():
    res = CostCenter.query_filtered()
    return CostCenter.list_to_json(res.all())


@app.route("/v2/cost_center", methods=["POST"])
def cost_center_create():
    rj = request_json()
    check_attrs(rj, ("name", ))
    obj = db_api.cost_center_get_or_create(rj["name"])
    return obj.to_json()


@app.route("/v2/cost_center", methods=["PUT"])
def cost_center_update():
    return obj_update_name(CostCenter)


@app.route("/v2/cost_center", methods=["DELETE"])
def cost_center_delete():
    res = CostCenter.query_filtered()
    if res.count() != 1:
        raise BadRequest("Exactly one cost center to delete must be specified.")
    to_delete = res.first()
    to_migrate = None
    filter = {}
    for fld in CostCenter.fld_list():
        key = "migrate_%s" % fld
        if key in request.args:
            filter[fld] = request.args[key]
    if filter:
        res = CostCenter.query.filter_by(**filter)
        if res.count() == 1:
            to_migrate = res.first()
    if not to_migrate:
        raise BadRequest("Exactly one cost center to migrate must be specified.")
    if to_delete.id == to_migrate.id:
        raise BadRequest("Cost centers for delete and migrate are the same.")

    connection = db.session.connection()
    for table in Resource, Account:
        db.session.query(table).filter_by(
            cost_center_id=to_delete.id).update(
            {table.cost_center_id: to_migrate.id})
    db.session.delete(to_delete)
    db.session.commit()
    return Response(status=204)
