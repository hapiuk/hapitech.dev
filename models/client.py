from . import db

class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    primary_email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)  # active/paused/archived

    users = db.relationship("User", backref="client", lazy=True)
