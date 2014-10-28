# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy as sa
import time

from relengapi.lib import db

DB_DECLARATIVE_BASE = 'clobberer'


class Build(db.declarative_base(DB_DECLARATIVE_BASE), db.UniqueMixin):
    "A clobberable build."

    __tablename__ = 'builds'

    id = sa.Column(sa.Integer, primary_key=True)
    branch = sa.Column(sa.String(50), index=True)
    builddir = sa.Column(sa.String(100), index=True)
    buildername = sa.Column(sa.String(100))
    last_build_time = sa.Column(
        sa.Integer,
        nullable=False,
        default=int(time.time())
    )

    @property
    def max_clobbertime(self):
        try:
            m_ct = self.clobbertimes[0]
            return dict(lastclobber=m_ct.lastclobber, who=m_ct.who)
        except IndexError:
            return dict(lastclobber=None, who=None)

    @classmethod
    def unique_hash(cls, branch, builddir, buildername, *args, **kwargs):
        return "{}:{}:{}".format(branch, builddir, buildername)

    @classmethod
    def unique_filter(cls, query, branch, builddir, buildername, *args, **kwargs):
        return query.filter(
            cls.branch == branch,
            cls.builddir == builddir,
            cls.buildername == buildername
        )


class ClobberTime(db.declarative_base(DB_DECLARATIVE_BASE), db.UniqueMixin):
    "A clobber request."

    __tablename__ = 'clobber_times'

    id = sa.Column(sa.Integer, primary_key=True)
    build_id = sa.Column(
        sa.Integer,
        sa.ForeignKey('builds.id'),
        nullable=False,
    )
    build = sa.orm.relationship(
        'Build',
        backref=sa.orm.backref('clobbertimes', order_by='desc(ClobberTime.lastclobber)')
    )
    lastclobber = sa.Column(
        sa.Integer,
        nullable=False,
        default=int(time.time()),
        index=True
    )
    slave = sa.Column(sa.String(30), index=True)
    who = sa.Column(sa.String(50))

    @classmethod
    def unique_hash(cls, build_id, slave, *args, **kwargs):
        return "{}:{}".format(build_id, slave)

    @classmethod
    def unique_filter(cls, query, build_id, slave, *args, **kwargs):
        return query.filter(
            cls.build_id == build_id,
            cls.slave == slave
        )
