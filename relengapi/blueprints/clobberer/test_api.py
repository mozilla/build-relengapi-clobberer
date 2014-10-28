# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import time

from copy import deepcopy
from nose.tools import assert_greater
from nose.tools import eq_

from relengapi.lib.testing.context import TestContext

from . import BUILDDIR_REL_PREFIX
from . import BUILDER_REL_PREFIX

from models import Build
from models import ClobberTime
from models import DB_DECLARATIVE_BASE

_clobber_args = {
    'branch': 'branch',
    'builddir': 'builddir',
    'buildername': 'buildername',
}

_clobber_args_with_slave = {
    'branch': 'other_branch',
    'builddir': 'other_builddir',
    'buildername': 'other_buildername',
    'slave': 'specific-slave'
}

test_context = TestContext(databases=[DB_DECLARATIVE_BASE], reuse_app=True)

_clobber_args = deepcopy(_clobber_args)
_clobber_args_with_slave = deepcopy(_clobber_args_with_slave)


@test_context
def test_clobber_request_no_builds(client):
    "Clobber requests should fail when set against non-existant builds."
    rv = client.post_json('/clobberer/clobber', data=[_clobber_args, _clobber_args_with_slave])
    eq_(rv.status_code, 500)


@test_context
def test_lastclobber_makes_build(client):
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    rv = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}'.format(**_clobber_args)
    )
    eq_(rv.status_code, 200)

    # Ensure a new build has been recorded matching the request args
    for k, v in _clobber_args.items():
        build = session.query(Build).first()
        eq_(getattr(build, k), v)


@test_context
def test_clobber_request(client):
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)

    clobber_count_initial = session.query(ClobberTime).count()
    rv = client.post_json('/clobberer/clobber', data=[_clobber_args])
    eq_(rv.status_code, 200)
    clobber_count_final = session.query(ClobberTime).count()

    eq_(clobber_count_final, clobber_count_initial + 1,
        'No new clobbers were detected, clobber request failed.')


@test_context
def test_lastclobber(client):
    rv = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}'.format(**_clobber_args)
    )
    eq_(rv.status_code, 200)
    lastclobber_data = rv.data.strip().split(':')
    eq_(lastclobber_data[0], _clobber_args['builddir'])
    eq_(lastclobber_data[1].isdigit(), True,
        'lastclobber did not return a valid timestamp => {}'.format(lastclobber_data[1]))
    eq_(lastclobber_data[2], 'anonymous',
        'lastclobber did not return a valid username')


@test_context
def test_clobber_with_slave(client):
    rv = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}&slave={slave}'.format(**_clobber_args_with_slave)
    )
    eq_(rv.data, "")

    session = test_context._app.db.session(DB_DECLARATIVE_BASE)

    clobber_count_initial = session.query(ClobberTime).count()
    rv = client.post_json('/clobberer/clobber', data=[_clobber_args_with_slave])
    eq_(rv.status_code, 200)
    clobber_count_final = session.query(ClobberTime).count()

    eq_(clobber_count_final, clobber_count_initial + 1,
        'No new clobbers were detected, clobber request failed.')


@test_context
def test_lastclobber_with_slave(client):
    rv = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}&slave={slave}'.format(**_clobber_args_with_slave)
    )
    builddir, lastclobber, who = rv.data.strip().split(':')
    eq_(builddir, _clobber_args_with_slave['builddir'])
    eq_(lastclobber.isdigit(), True)

    rv = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}&slave=does-not-exist'.format(**_clobber_args_with_slave)
    )
    # even though we don't expect data, the return status should be OK
    eq_(rv.status_code, 200)
    # because a specific slave, not named does-not-exist,  was clobbered
    # this should return nothing
    eq_(rv.data, "")


@test_context
def test_lastclobber_clobber_args_with_slave(client):
    """
    Here we make sure that clobberer can handle a mix of NULL(i.e. ALL) and
    specific slave clobbers.
    """
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)

    build_with_slave_clobber = session.query(Build).filter(
        Build.branch == _clobber_args_with_slave['branch'],
        Build.builddir == _clobber_args_with_slave['builddir']
    ).first()

    session.add(ClobberTime(
        lastclobber=int(time.time()) + 3600,
        who='anonymous', build_id=build_with_slave_clobber.id))
    session.commit()

    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    rv_with_slave = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}&slave={slave}'.format(**_clobber_args_with_slave)
    )
    last_clobber_with_slave = rv_with_slave.data.strip().split(':')[1]

    rv_no_slave = client.get(
        '/clobberer/lastclobber?branch={branch}&builddir={builddir}&'
        'buildername={buildername}'.format(**_clobber_args)
    )
    last_clobber_no_slave = rv_no_slave.data.strip().split(':')[1]

    eq_(last_clobber_with_slave.isdigit(), True)
    eq_(last_clobber_no_slave.isdigit(), True)

    assert_greater(int(last_clobber_with_slave), 0)
    assert_greater(int(last_clobber_no_slave), 0)

    # The specific slave clobber's "lastclobber" should be higher than the
    # wildcard clobber that's already happened
    assert_greater(int(last_clobber_with_slave), int(last_clobber_no_slave))


@test_context
def test_empty_lastclobber(client):
    # Ensure that a request for non-existant data returns nothing gracefully
    rv = client.get('/clobberer/lastclobber?branch=fake&builddir=bogus')
    eq_(rv.status_code, 200)
    eq_(rv.data, "")


@test_context
def test_lastclobber_by_builder(client):
    rv = client.get('/clobberer/lastclobber/branch/by-builder/branch')
    eq_(rv.status_code, 200)
    buildername = _clobber_args.get("buildername")
    clobbertimes = json.loads(rv.data)["result"]
    eq_(type(clobbertimes.get(buildername)), list)
    eq_(len(clobbertimes.get(buildername)), 1)
    # Make sure all of our clobber fields were retrieved
    for key, value in _clobber_args.items():
        if key is not 'buildername':
            eq_(clobbertimes.get(buildername)[0].get(key), value)


@test_context
def test_forceclobber(client):
    rv = client.get('/clobberer/forceclobber?builddir=lamesauce')
    eq_(rv.status_code, 200)
    builddir, future_time, who = rv.data.split('\n')[0].split(':')
    eq_(builddir, 'lamesauce')
    assert_greater(int(future_time), int(time.time()))


@test_context
def test_branches(client):
    rv = client.get('/clobberer/branches')
    eq_(rv.status_code, 200)
    eq_(json.loads(rv.data)['result'],
        [_clobber_args['branch'], 'fake', _clobber_args_with_slave['branch']])


@test_context
def test_release_branch_hiding(client):
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    # clear all the old branches
    session.query(Build).delete()
    session.commit()

    # users should not see this branch because it's associated with a release
    # builddir
    release_builddir = '{}builddir'.format(BUILDDIR_REL_PREFIX)
    session.add(Build(branch='see-no-evil', builddir=release_builddir))
    session.commit()

    rv = client.get('/clobberer/branches')
    eq_(json.loads(rv.data)['result'], [])


@test_context
def test_release_builder_hiding(client):
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    buildername = BUILDER_REL_PREFIX + 'test'
    release_build = Build(
        branch='branch',
        builddir='test',
        buildername=buildername
    )
    session.add(release_build)
    session.commit()
    rv = client.get('/clobberer/lastclobber/branch/by-builder/branch')
    eq_(rv.status_code, 200)
    clobbertimes = json.loads(rv.data)["result"]
    eq_(clobbertimes.get(buildername), None)


@test_context
def test_clobber_request_of_release(client):
    "Ensures that attempting to clobber a release build will fail."
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    clobber_count_initial = session.query(ClobberTime).count()
    evil_clobber_args = {
        'branch': 'none',
        'builddir': BUILDDIR_REL_PREFIX + 'directory',
        'buildername': 'buildername',
    }
    session.add(Build(**evil_clobber_args))
    session.commit()

    rv = client.post_json('/clobberer/clobber', data=[evil_clobber_args])
    eq_(rv.status_code, 200)
    clobber_count_final = session.query(ClobberTime).count()

    eq_(clobber_count_final, clobber_count_initial,
        'A release was clobbered, no bueno!')
    session.query(Build).delete()
    session.commit()


@test_context
def test_clobber_request_of_non_release(client):
    "This looks like a release clobber, but actually isn't."
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    clobber_count_initial = session.query(ClobberTime).count()
    not_evil_clobber_args = {
        'branch': 'none',
        'builddir': 'directory-' + BUILDDIR_REL_PREFIX + 'tricky',
        'buildername': 'buildername'
    }
    session.add(Build(**not_evil_clobber_args))
    session.commit()

    rv = client.post_json('/clobberer/clobber', data=[not_evil_clobber_args])
    eq_(rv.status_code, 200)
    clobber_count_final = session.query(ClobberTime).count()

    eq_(clobber_count_final, clobber_count_initial + 1)
    session.query(Build).delete()
    session.commit()
