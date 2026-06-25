from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Doctor(db.Model):
    __tablename__ = "doctor"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    specialization = db.Column(db.String(100))
    experience = db.Column(db.Integer)
    phone = db.Column(db.String(15))

    def __repr__(self):
        return f"<Doctor {self.name}>"