
from flask_login import UserMixin
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from enum import Enum
from sqlalchemy import Enum as SQLAlchemyEnum

from extensions import db

class Court(db.Model):
    __tablename__ = 'tblcourt'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    users = db.relationship('User', backref='court', lazy=True)
    cases = db.relationship('Case', backref='court', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('name', name='uq_court_name'),
    )

class User(UserMixin, db.Model):
    __tablename__ = 'tbluser'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    password = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    tel = db.Column(db.String(20), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    court_id = db.Column(db.Integer, db.ForeignKey('tblcourt.id', ondelete='SET NULL', name='fk_user_court'), nullable=True)

    cases = db.relationship('Case', backref='user', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('username', name='uq_user_username'),
        db.UniqueConstraint('email', name='uq_user_email')
    )

class CaseStatus(Enum):
    active = 'active'
    inactive = 'inactive'
    finished = 'finished'
    postponed = 'postponed'
    in_session = 'in session'

class Case(db.Model):
    __tablename__ = 'tblcase'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('tbluser.id', ondelete='SET NULL'), nullable=True)
    case_number = db.Column(db.String(50), nullable=False)
    case_date = db.Column(db.Date, nullable=True)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)
    c_order = db.Column(db.Integer, nullable=False)
    next_session_date = db.Column(db.String(100), nullable=True)
    session_result = db.Column(db.Text, nullable=True)
    num_sessions = db.Column(db.Integer, nullable=False, default=1)
    case_subject = db.Column(db.String(200), nullable=True)
    defendant = db.Column(db.String(100), nullable=True)
    plaintiff = db.Column(db.String(100), nullable=True)
    prosecution_number = db.Column(db.String(50), nullable=True)
    police_department = db.Column(db.String(150), nullable=True)
    police_case_number = db.Column(db.String(50), nullable=True)
    status = db.Column(SQLAlchemyEnum(CaseStatus), nullable=True, default=CaseStatus.inactive)
    court_id = db.Column(db.Integer, db.ForeignKey('tblcourt.id', ondelete='SET NULL', name='fk_case_court'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('court_id', 'case_number', name='uq_case_number_per_court'),
    )

class DisplayCase(db.Model):
    __tablename__ = 'tbldisply'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('tblcase.id', ondelete='CASCADE', name='fk_display_case'), nullable=False)
    court_id = db.Column(db.Integer, db.ForeignKey('tblcourt.id', ondelete='CASCADE', name='fk_display_court'), nullable=False)
    display_order = db.Column(db.Integer, nullable=False)
    custom_order = db.Column(db.Integer, nullable=True)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)
    case = db.relationship('Case', backref=db.backref('display_entries', cascade='all, delete-orphan'))
    court = db.relationship('Court', backref=db.backref('display_entries', cascade='all, delete-orphan'))

class DisplaySettings(db.Model):
    __tablename__ = 'display_settings'
    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(50), nullable=False, unique=True)
    field_name_ar = db.Column(db.String(50), nullable=True)
    is_visible = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('field_name', name='uq_display_settings_field_name'),
    )

class ActivityLog(db.Model):
    __tablename__ = 'tblactivity_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('tbluser.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    case_id = db.Column(db.Integer, db.ForeignKey('tblcase.id', ondelete='CASCADE'), nullable=True)
    court_id = db.Column(db.Integer, db.ForeignKey('tblcourt.id', ondelete='CASCADE'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='activity_logs')
    case = db.relationship('Case', backref='activity_logs')
    court = db.relationship('Court', backref='activity_logs')
