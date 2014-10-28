# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import collections
import flask_login
import logging
import time

import re
import rest

from sqlalchemy import desc
from sqlalchemy import not_
from sqlalchemy import or_

from flask import Blueprint
from flask import g
from flask import request
from flask import url_for
from flask.ext.login import current_user

from models import Build
from models import ClobberTime
from models import DB_DECLARATIVE_BASE

from relengapi import apimethod
from relengapi.lib import angular
from relengapi.lib import api

logger = logging.getLogger(__name__)

bp = Blueprint(
    'clobberer',
    __name__,
    template_folder='templates',
    static_folder='static'
)

bp.root_widget_template('clobberer_root_widget.html', priority=100)

# prefix which denotes release builddirs
BUILDDIR_REL_PREFIX = 'rel-'
BUILDER_REL_PREFIX = 'release-'


@bp.route('/')
@bp.route('/<string:branch>')
@flask_login.login_required
def root(branch=None):
    return angular.template(
        'clobberer.html',
        url_for('.static', filename='clobberer.js'),
        url_for('.static', filename='clobberer.css'),
        branches=api.get_data(branches),
        selected_branch=branch
    )


@bp.route('/clobber', methods=['POST'])
@apimethod(None, body=[rest.ClobberRequest])
def clobber(body):
    "Request clobbers for particular branches and builddirs."
    session = g.db.session(DB_DECLARATIVE_BASE)
    who = 'anonymous'
    if current_user.anonymous is False:
        who = current_user.authenticated_email
    for clobber in body:
        if re.search('^' + BUILDDIR_REL_PREFIX + '.*', clobber.builddir) is not None:
            logger.debug('Rejecting clobber of builddir with release prefix: {}'.format(
                clobber.builddir))
            continue
        build = session.query(Build).filter(
            Build.branch == clobber.branch,
            Build.builddir == clobber.builddir,
            Build.buildername == clobber.buildername
        ).one()
        clobber_time = ClobberTime.as_unique(
            session,
            build_id=build.id,
            slave=clobber.slave,
        )
        clobber_time.lastclobber = int(time.time())
        clobber_time.who = who
        session.add(clobber_time)
    session.commit()
    return None


@bp.route('/branches')
@apimethod([unicode])
def branches():
    "Return a list of all the branches clobberer knows about."
    session = g.db.session(DB_DECLARATIVE_BASE)
    branches = session.query(Build.branch).distinct()
    # Users shouldn't see any branch associated with a release builddir
    branches = branches.filter(not_(Build.builddir.startswith(BUILDDIR_REL_PREFIX)))
    branches = branches.order_by(Build.branch)
    return [branch[0] for branch in branches]


@bp.route('/lastclobber/branch/by-builder/<string:branch>', methods=['GET'])
@apimethod({unicode: [rest.ClobberTime]}, unicode)
def lastclobber_by_builder(branch):
    "Return a dictionary of most recent ClobberTimes grouped by buildername."

    session = g.db.session(DB_DECLARATIVE_BASE)

    query = session.query(Build).filter(
        Build.branch == branch,
        not_(Build.buildername.startswith(BUILDER_REL_PREFIX))
    ).distinct()
    summary = collections.defaultdict(list)
    for build in query:
        summary[build.buildername].append(
            rest.ClobberTime(
                branch=build.branch,
                builddir=build.builddir,
                buildername=build.buildername,
                lastclobber=build.max_clobbertime['lastclobber'],
                who=build.max_clobbertime['who']
            )
        )
    return summary


@bp.route('/lastclobber', methods=['GET'])
def lastclobber():
    """
    Get the max/last clobber time for a particular builddir and branch. Also
    record any unique visitors as a Build.
    """

    session = g.db.session(DB_DECLARATIVE_BASE)
    now = int(time.time())
    branch = request.args.get('branch')
    builddir = request.args.get('builddir')
    buildername = request.args.get('buildername')
    slave = request.args.get('slave')
    build = Build.as_unique(
        session,
        branch=branch,
        builddir=builddir,
        buildername=buildername,
    )
    # Always force the time to update
    build.last_build_time = now
    session.add(build)
    session.commit()

    max_ct = session.query(ClobberTime).filter(
        ClobberTime.build_id == build.id,
        # a NULL slave value signifies all slaves
        or_(ClobberTime.slave == slave, ClobberTime.slave == None)  # noqa
    ).order_by(desc(ClobberTime.lastclobber)).first()

    if max_ct:
        # The client parses this result by colon as:
        # builddir, lastclobber, who = urlib2.open.split(':')
        # as such it's important for this to be plain text and have
        # no extra colons within the field values themselves
        return "{}:{}:{}\n".format(max_ct.build.builddir, max_ct.lastclobber, max_ct.who)
    return ""


@bp.route('/forceclobber', methods=['GET'])
def forceclobber():
    """
    Coerce the client to clobber by always returning a future clobber time.
    This works because the client decides to clobber based on a timestamp
    comparrison.
    """
    future_time = int(time.time()) + 3600
    builddir = request.args.get('builddir')
    return "{}:{}:forceclobber".format(builddir, future_time)
