# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from nose.tools import eq_

from relengapi.lib.testing.context import TestContext

from models import Build
from models import ClobberTime
from models import DB_DECLARATIVE_BASE

test_context = TestContext(databases=[DB_DECLARATIVE_BASE], reuse_app=True)


@test_context
def test_build_max_clobbertime(client):
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    build = Build(branch='a', builddir='b', buildername='c')
    session.add(build)
    session.commit()

    session.add(ClobberTime(lastclobber=1, build_id=build.id))
    session.add(ClobberTime(lastclobber=2, build_id=build.id))
    session.add(ClobberTime(who='beefcake', lastclobber=4, build_id=build.id))
    session.commit()
    eq_(build.max_clobbertime['who'], 'beefcake')
    eq_(build.max_clobbertime['lastclobber'], 4)

    session.add(ClobberTime(who='maximus', lastclobber=99, build_id=build.id))
    session.commit()
    eq_(build.max_clobbertime['lastclobber'], 99)
    eq_(build.max_clobbertime['who'], 'maximus')


@test_context
def test_build_max_clobbertime_empty(client):
    session = test_context._app.db.session(DB_DECLARATIVE_BASE)
    build = Build(branch='x', builddir='y', buildername='z')
    session.add(build)
    session.commit()
    eq_(build.max_clobbertime['who'], None)
    eq_(build.max_clobbertime['lastclobber'], None)
