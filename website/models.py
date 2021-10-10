# this is where the database models goes, import db object from init
from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from datetime import datetime

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique = True)
    password = db.Column(db.String(150))
    notification = db.relationship('Notification')
    requests = db.relationship('Request')

class Warehouse(db.Model):
    location = db.Column(db.String(7), primary_key=True)
    north_south = db.Column(db.String(7))
    ns_weight = db.Column(db.Integer)
    east = db.Column(db.String(7))
    e_weight = db.Column(db.Integer)
    west = db.Column(db.String(7))
    w_weight = db.Column(db.Integer)
    north_south_extra = db.Column(db.String(7))
    ns_weight_extra = db.Column(db.Integer)

class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    enter_date = db.Column(db.DateTime(timezone=True), default=func.now())
    load_weight = db.Column(db.Integer)
    end_location = db.Column(db.Integer)
    closing_time = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    status = db.Column(db.String(50))
    warehouse_location = db.Column(db.Integer, db.ForeignKey('warehouse.location'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Lorry(db.Model):
    plate_number = db.Column(db.String, primary_key=True)
    total_load = db.Column(db.Integer)
    status = db.Column(db.String(12))
    warehouse_id =  db.Column(db.Integer, db.ForeignKey('warehouse.location'))
    user_id =  db.Column(db.Integer, db.ForeignKey('user.id'))

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    request_status = db.Column(db.String(50), db.ForeignKey('request.status'))
    request_id = db.Column(db.Integer, db.ForeignKey('request.id'))

class Matched(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_request_id = db.Column(db.Integer)
    second_request_id = db.Column(db.Integer)
    lorry_plate_number = db.Column(db.Integer)