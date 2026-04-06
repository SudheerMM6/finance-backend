from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), default='active')

    def __repr__(self):
        return f"<User {self.username} {self.role}>"

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Numeric instead of Float to avoid binary floating point drift on money values
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    txn_type = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False, server_default=db.func.current_date())
    description = db.Column(db.String(200), default='')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<Record {self.txn_type} {self.amount}>"
