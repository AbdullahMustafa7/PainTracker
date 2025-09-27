import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.secret_key = "change-me-in-prod"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "paintrack.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------- App & DB Config --------------------
app = Flask(__name__)
app.secret_key = "change-me-in-prod"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///paintrack.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------- Models --------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "patient" or "doctor"

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


class MedicinePlan(db.Model):
    __tablename__ = "medicine_plans"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    med_name = db.Column(db.String(100), nullable=False)
    dose = db.Column(db.String(100), nullable=False)
    time_of_day = db.Column(db.String(50), nullable=True)  # e.g., "Morning", "Evening"


class Log(db.Model):
    __tablename__ = "logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    pain_level = db.Column(db.Integer, nullable=False)
    pain_type = db.Column(db.String(50), nullable=False)
    pain_location = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # relationship so you can access log.user.username in templates if you want
    user = db.relationship("User", backref="logs")

# -------------------- Helpers --------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)

def login_required(role=None):
    """Decorator to require login and (optionally) a specific role."""
    def decorator(view_func):
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("login"))
            return view_func(*args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator

# -------------------- Routes --------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("meds" if user.role == "patient" else "doctor"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/meds")
@login_required(role="patient")
def meds():
    user = current_user()
    meds = MedicinePlan.query.filter_by(user_id=user.id).all()
    return render_template("meds.html", meds=meds)

@app.route("/patient", methods=["GET", "POST"])
@login_required(role="patient")
def patient():
    user = current_user()
    if request.method == "POST":
        pain = int(request.form.get("pain"))
        pain_type = request.form.get("pain_type")
        pain_location = request.form.get("pain_location")
        notes = request.form.get("notes")

        new_log = Log(
            user_id=user.id,
            pain_level=pain,
            pain_type=pain_type,
            pain_location=pain_location,
            notes=notes,
        )
        db.session.add(new_log)
        db.session.commit()
        return redirect(url_for("patient"))

    # show last 10 logs for this patient
    my_logs = (
        Log.query.filter_by(user_id=user.id)
        .order_by(Log.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template("patient.html", logs=my_logs)

@app.route("/doctor")
@login_required(role="doctor")
def doctor():
    # optional filter by patient
    patient_id = request.args.get("patient_id", type=int)
    patients = User.query.filter_by(role="patient").all()

    if patient_id:
        logs = (
            Log.query.filter_by(user_id=patient_id)
            .order_by(Log.created_at.asc())
            .all()
        )
    else:
        logs = Log.query.order_by(Log.created_at.asc()).all()

    return render_template(
        "doctor.html",
        logs=logs,
        patients=patients,
        selected_id=patient_id,
    )

# -------------------- Bootstrap / Seed --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Seed demo users if they don't exist yet
        patient_user = User.query.filter_by(username="patient").first()
        doctor_user = User.query.filter_by(username="doctor").first()

        if not patient_user:
            patient_user = User(username="patient", role="patient")
            patient_user.set_password("1234")
            db.session.add(patient_user)

        if not doctor_user:
            doctor_user = User(username="doctor", role="doctor")
            doctor_user.set_password("1234")
            db.session.add(doctor_user)

        db.session.commit()

        # Seed a simple medicine plan for the patient if none exists
        has_plan = MedicinePlan.query.filter_by(user_id=patient_user.id).first()
        if not has_plan:
            db.session.add_all(
                [
                    MedicinePlan(
                        user_id=patient_user.id,
                        med_name="Paracetamol",
                        dose="500 mg",
                        time_of_day="Morning",
                    ),
                    MedicinePlan(
                        user_id=patient_user.id,
                        med_name="Insulin",
                        dose="10 units",
                        time_of_day="Evening",
                    ),
                ]
            )
            db.session.commit()

    # Start dev server
    app.run(debug=True)
