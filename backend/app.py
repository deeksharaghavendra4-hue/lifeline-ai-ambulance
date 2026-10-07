# ============================================================================
# LIFELINE — FLASK BACKEND
# ============================================================================
#
# Workflow:
#
# Patient submits ambulance request
#             ↓
# Request saved as PENDING
#             ↓
# Driver dashboard receives PENDING request
#             ↓
# Driver accepts
#             ↓
# Ambulance assigned
#             ↓
# Request becomes ACCEPTED
#             ↓
# Hospital dashboard receives live information
#
# ============================================================================

import os
import uuid
import hashlib
import math

from datetime import datetime, timedelta

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    make_response
)

from flask_cors import CORS


# ============================================================================
# DATABASE / AI IMPORT
# ============================================================================

try:
    from . import database as db
    from . import ai
except ImportError:
    import database as db
    import ai


# ============================================================================
# CONFIGURATION
# ============================================================================

FRONTEND_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend"
    )
)


app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path="/static-assets"
)


CORS(app)


# ============================================================================
# FRONTEND STATIC FILES
# ============================================================================

@app.route("/<path:filename>")
def frontend_static(filename):
    """
    Serve frontend HTML, CSS, JavaScript and other static files.
    """

    return send_from_directory(
        FRONTEND_DIR,
        filename
    )


# ============================================================================
# HELPERS
# ============================================================================

def _dist_km(
    lat1,
    lon1,
    lat2,
    lon2
):
    """
    Calculate approximate distance between two
    latitude / longitude points.
    """

    try:

        lat1, lon1, lat2, lon2 = map(
            float,
            [
                lat1,
                lon1,
                lat2,
                lon2
            ]
        )

    except (
        TypeError,
        ValueError
    ):

        return None


    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )


    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(
            math.radians(lat1)
        )
        *
        math.cos(
            math.radians(lat2)
        )
        *
        math.sin(dlon / 2) ** 2
    )


    return (
        2
        * 6371
        * math.asin(
            math.sqrt(a)
        )
    )


# ----------------------------------------------------------------------------

def _enrich_patient(
    patient,
    users
):
    """
    Fill missing patient information from
    registered patient information.
    """

    pat = dict(
        patient or {}
    )


    mobile = (
        pat.get("mobile")
        or pat.get("id")
    )


    if mobile:

        user = next(
            (
                u
                for u in users

                if (
                    u.get("role")
                    == "patient"
                )

                and (
                    u.get("mobile")
                    == mobile
                )
            ),
            None
        )


        if user:

            for field in (
                "full_name",
                "age",
                "gender",
                "blood_group",
                "email"
            ):

                if (
                    not pat.get(field)
                    and user.get(field)
                ):

                    pat[field] = user[field]


    if not pat.get("name"):

        pat["name"] = (
            pat.get("full_name")
            or pat.get("id")
            or "Patient"
        )


    if not pat.get("mobile"):

        pat["mobile"] = (
            pat.get("id")
            or ""
        )


    return pat


# ----------------------------------------------------------------------------

def _safe_user(user):
    """
    Remove password information before
    sending user data to frontend.
    """

    return {
        key: value
        for key, value in user.items()
        if key not in (
            "password",
            "password_hash"
        )
    }


# ----------------------------------------------------------------------------

def _find_request(
    data,
    request_id
):

    return next(
        (
            r
            for r in data.get(
                "requests",
                []
            )

            if r.get("id")
            == request_id
        ),
        None
    )


# ----------------------------------------------------------------------------

def _find_ambulance(
    data,
    ambulance_id
):

    return next(
        (
            a
            for a in data.get(
                "ambulances",
                []
            )

            if a.get("id")
            == ambulance_id
        ),
        None
    )


# ----------------------------------------------------------------------------

def _find_hospital(
    data,
    hospital_id
):

    return next(
        (
            h
            for h in data.get(
                "hospitals",
                []
            )

            if h.get("id")
            == hospital_id
        ),
        None
    )


# ----------------------------------------------------------------------------

def _request_timestamp(req):
    """
    Get a sortable timestamp from a request.
    """

    return (
        req.get("timestamp")
        or req.get("created_at")
        or req.get("requested_at")
        or ""
    )



# ============================================================================
# AUTOMATIC DRIVER DISPATCH
# ============================================================================

DISPATCH_OFFER_SECONDS = 30

ACTIVE_TRIP_STATUSES = {
    "active",
    "accepted",
    "en_route",
    "arrived",
    "picked_up"
}


def _offer_expired(request_obj):
    """Return True when the current driver offer has timed out."""
    expires = request_obj.get("offer_expires_at")
    if not expires:
        return False

    try:
        return datetime.fromisoformat(expires) <= datetime.now()
    except (TypeError, ValueError):
        return True


def _driver_is_busy(data, ambulance_id):
    """An ambulance is busy if it has an active assigned request."""
    for req in data.get("requests", []):
        if (
            req.get("ambulance") == ambulance_id
            and str(req.get("status", "")).lower() in ACTIVE_TRIP_STATUSES
        ):
            return True
    return False


def _dispatch_request_to_nearest(request_obj, data=None):
    """
    Offer a pending request to the nearest available ambulance.

    The request is NOT assigned here.  It stays pending until the
    offered driver presses Accept.
    """
    if not request_obj or request_obj.get("status") != "pending":
        return None

    if data is None:
        data = db.load_data()

    # Keep the current driver offer until the driver explicitly
    # accepts or rejects the request. There is no automatic timeout.
    offered_to = request_obj.get("offered_to")
    if offered_to:
        return offered_to

    patient = request_obj.get("patient") or {}
    try:
        patient_lat = float(patient.get("latitude"))
        patient_lon = float(patient.get("longitude"))
    except (TypeError, ValueError):
        return None

    rejected_by = set(request_obj.get("rejected_by") or [])

    candidates = []

    for ambulance in data.get("ambulances", []):
        ambulance_id = ambulance.get("id")
        if not ambulance_id:
            continue

        if not ambulance.get("available", False):
            continue

        # A rejected ambulance is excluded. Old timed_out_by values are
        # ignored because requests no longer expire automatically.
        if ambulance_id in rejected_by:
            continue

        if _driver_is_busy(data, ambulance_id):
            continue

        try:
            lat = float(ambulance.get("latitude"))
            lon = float(ambulance.get("longitude"))
        except (TypeError, ValueError):
            continue

        distance = _dist_km(patient_lat, patient_lon, lat, lon)
        if distance is None:
            continue

        # One active offer per available driver.
        already_offered = any(
            r.get("status") == "pending"
            and r.get("offered_to") == ambulance_id
            and r.get("id") != request_obj.get("id")
            for r in data.get("requests", [])
        )
        if already_offered:
            continue

        candidates.append((distance, ambulance))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    distance, ambulance = candidates[0]
    ambulance_id = ambulance["id"]

    request_obj["offered_to"] = ambulance_id
    request_obj["offer_distance_km"] = round(distance, 3)
    request_obj["offered_at"] = datetime.now().isoformat(timespec="seconds")
    return ambulance_id


def _refresh_dispatch_offers(data=None):
    """
    Refresh pending requests:
    - send unoffered requests to the nearest eligible ambulance
    - keep each offer until the driver accepts or rejects
    - keep the request pending until accepted
    """
    if data is None:
        data = db.load_data()

    changed = False

    pending = [
        req for req in data.get("requests", [])
        if str(req.get("status", "")).lower() == "pending"
        and not req.get("ambulance")
    ]

    # Newest patient requests are dispatched first.
    pending.sort(key=_request_timestamp, reverse=True)

    for req in pending:
        before = (
            req.get("offered_to"),
            tuple(req.get("rejected_by") or [])
        )
        _dispatch_request_to_nearest(req, data)
        after = (
            req.get("offered_to"),
            tuple(req.get("rejected_by") or [])
        )
        if before != after:
            changed = True

    if changed:
        db.save_data(data)

    return data


# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route("/")
def index():

    return send_from_directory(
        FRONTEND_DIR,
        "index_role.html"
    )


@app.route("/login")
def login_page():

    return send_from_directory(
        FRONTEND_DIR,
        "login_page.html"
    )


@app.route("/register/patient")
def reg_patient():

    return send_from_directory(
        FRONTEND_DIR,
        "register_patient.html"
    )


@app.route("/register/driver")
def reg_driver():

    return send_from_directory(
        FRONTEND_DIR,
        "register_driver.html"
    )


@app.route("/register/hospital")
def reg_hospital():

    return send_from_directory(
        FRONTEND_DIR,
        "register_hospital.html"
    )


@app.route("/patient")
def patient_page():

    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


@app.route("/driver")
def driver_page():

    return send_from_directory(
        FRONTEND_DIR,
        "driver_dashboard.html"
    )


@app.route("/hospital")
def hospital_page():

    response = make_response(
        send_from_directory(
            FRONTEND_DIR,
            "hospital_dashboard.html"
        )
    )


    response.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )

    response.headers["Pragma"] = "no-cache"

    response.headers["Expires"] = "0"


    return response


@app.route("/tracking")
def tracking_page():

    return send_from_directory(
        FRONTEND_DIR,
        "tracking.html"
    )


@app.route("/dashboard")
def dashboard_page():

    return send_from_directory(
        FRONTEND_DIR,
        "dashboard.html"
    )


@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "LifeLine",
        "timestamp": datetime.now().isoformat(
            timespec="seconds"
        )
    })


# ============================================================================
# AUTHENTICATION
# ============================================================================

@app.route(
    "/auth/register",
    methods=["POST"]
)
def register():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        role = body.get("role")


        if role not in (
            "patient",
            "driver",
            "hospital"
        ):

            return jsonify({
                "error": "Invalid role"
            }), 400


        mobile = "".join(
            str(
                body.get(
                    "mobile",
                    ""
                )
            ).split()
        )


        if not mobile:

            return jsonify({
                "error": "mobile is required"
            }), 400


        existing_user = db.find_user(
            mobile,
            role
        )


        if existing_user:

            return jsonify({
                "error": (
                    "Account already exists. "
                    "Please login."
                )
            }), 409


        password = str(
            body.get(
                "password",
                ""
            )
        )


        if len(password) < 6:

            return jsonify({
                "error": (
                    "Password must be at least "
                    "6 characters"
                )
            }), 400


        user = {
            key: value
            for key, value in body.items()
            if key != "password"
        }


        user.update({

            "mobile": mobile,

            "role": role,

            "password_hash":
                hashlib.sha256(
                    password.encode(
                        "utf-8"
                    )
                ).hexdigest(),

            "registered_at":
                datetime.now().isoformat(
                    timespec="seconds"
                )
        })


        db.create_user(
            user
        )


        return jsonify({

            "message":
                "Registered successfully",

            "user":
                _safe_user(user)

        }), 201


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ----------------------------------------------------------------------------

@app.route(
    "/auth/login",
    methods=["POST"]
)
def login_api():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        role = body.get(
            "role"
        )


        password = str(
            body.get(
                "password",
                ""
            )
        )


        mobile = "".join(
            str(
                body.get(
                    "mobile",
                    ""
                )
            ).split()
        )


        if (
            not role
            or not mobile
            or not password
        ):

            return jsonify({
                "error": (
                    "role, mobile and password "
                    "are required"
                )
            }), 400


        if role not in (
            "patient",
            "driver",
            "hospital"
        ):

            return jsonify({
                "error": "Invalid role"
            }), 400


        user = db.find_user(
            mobile,
            role
        )


        if not user:

            return jsonify({
                "error": (
                    "No account found. "
                    "Please register first."
                )
            }), 404


        password_hash = hashlib.sha256(
            password.encode(
                "utf-8"
            )
        ).hexdigest()


        if user.get(
            "password_hash"
        ) != password_hash:

            return jsonify({
                "error":
                    "Incorrect password"
            }), 401


        if role == "driver":

            redirect_url = "/driver"

        elif role == "hospital":

            redirect_url = "/hospital"

        else:

            redirect_url = "/patient"


        return jsonify({

            "message":
                "Login successful",

            "user":
                _safe_user(user),

            "redirect":
                redirect_url
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# PATIENT — REQUEST AMBULANCE
# ============================================================================

@app.route(
    "/api/request-ambulance",
    methods=["POST"]
)
def request_ambulance():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        required_fields = [
            "patient_id",
            "latitude",
            "longitude",
            "emergency_type"
        ]


        for field in required_fields:

            if field not in body:

                return jsonify({
                    "error":
                        f"Missing field: {field}"
                }), 400


        try:

            patient_lat = float(
                body["latitude"]
            )

            patient_lon = float(
                body["longitude"]
            )

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                "error": (
                    "latitude and longitude "
                    "must be valid numbers"
                )
            }), 400


        patient = {

            "id":
                body["patient_id"],

            "name":
                body.get(
                    "patient_name",
                    "Patient"
                ),

            "age":
                body.get("age"),

            "gender":
                body.get("gender"),

            "blood_group":
                body.get(
                    "blood_group"
                ),

            "mobile":
                body.get("mobile"),

            "latitude":
                patient_lat,

            "longitude":
                patient_lon,

            "emergency_type":
                body["emergency_type"],

            "voice_description":
                body.get(
                    "voice_description",
                    ""
                )
        }


        request_id = (
            "REQ"
            + str(
                uuid.uuid4()
            )[:6].upper()
        )

        new_request = {
            "id": request_id,
            "patient": patient,
            "ambulance": None,
            "hospital": None,
            "status": "pending",
            "priority": "high",
            "timestamp": datetime.now().isoformat(
                timespec="seconds"
            ),
            "timed_out_by": [],
            "rejected_by": []
        }

        # Save patient request as PENDING.
        # No ambulance is assigned until driver accepts.
        db.create_request(new_request)

        # Immediately offer the request to the nearest available driver.
        dispatch_data = db.load_data()
        _refresh_dispatch_offers(dispatch_data)

        created_request = _find_request(
            dispatch_data,
            request_id
        ) or new_request

        # Hospital is only recommended.
        # It is not assigned until driver accepts.

        hospital = ai.recommend_hospital(
            patient_lat,
            patient_lon,
            db.get_hospitals()
        )


        print(
            "NEW PATIENT AMBULANCE REQUEST:",
            request_id
        )


        offered_to = created_request.get("offered_to")
        offered_ambulance = (
            _find_ambulance(dispatch_data, offered_to)
            if offered_to else None
        )

        return jsonify({

            "success":
                True,

            "request_id":
                request_id,

            # The ambulance is NOT assigned until the driver accepts.
            # offered_ambulance tells the UI which driver currently has
            # the request waiting in their dashboard.
            "ambulance_assigned":
                bool(created_request.get("ambulance")),

            "offered_to":
                offered_to,

            "ambulance":
                offered_ambulance,

            "hospital":
                hospital,

            "eta_minutes":
                None,

            "status":
                created_request.get("status", "pending")

        }), 201


    except Exception as e:

        print(
            "REQUEST AMBULANCE ERROR:",
            str(e)
        )

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# PATIENT — REQUEST STATUS
# ============================================================================

@app.route(
    "/api/patient/request-status/<request_id>",
    methods=["GET"]
)
def api_patient_request_status(
    request_id
):

    try:

        data = db.load_data()

        # Keep dispatch state live. If a driver has just become available,
        # a waiting patient request can be offered without requiring a
        # separate manual action.
        data = _refresh_dispatch_offers(data)

        users = data.get(
            "users",
            []
        )


        req = _find_request(
            data,
            request_id
        )


        if not req:

            return jsonify({
                "error":
                    "Request not found"
            }), 404


        ambulance = None

        eta_minutes = None


        if req.get(
            "ambulance"
        ):

            ambulance = _find_ambulance(
                data,
                req["ambulance"]
            )


            if ambulance:

                eta_minutes = ai.calculate_eta(
                    ambulance,
                    req["patient"]["latitude"],
                    req["patient"]["longitude"]
                )


        hospital = None


        if req.get(
            "hospital"
        ):

            hospital = _find_hospital(
                data,
                req["hospital"]
            )


        if ambulance:

            driver = None


            if ambulance.get(
                "driver_mobile"
            ):

                driver = next(
                    (
                        u
                        for u in users

                        if u.get("role")
                        == "driver"

                        and u.get("mobile")
                        == ambulance.get(
                            "driver_mobile"
                        )
                    ),
                    None
                )


            if not driver:

                driver = next(
                    (
                        u
                        for u in users

                        if u.get("role")
                        == "driver"

                        and (
                            u.get(
                                "full_name"
                            )
                            or ""
                        ).lower()
                        ==
                        (
                            ambulance.get(
                                "driver"
                            )
                            or ""
                        ).lower()
                    ),
                    None
                )


            if driver:

                ambulance = {

                    **ambulance,

                    "driver_name":
                        driver.get(
                            "full_name"
                        ),

                    "driver_mobile":
                        driver.get(
                            "mobile"
                        )
                }


        step_map = {

            "pending":
                0,

            "active":
                1,

            "accepted":
                2,

            "en_route":
                3,

            "arrived":
                4,

            "picked_up":
                5,

            "completed":
                6
        }


        return jsonify({

            "request_id":
                req["id"],

            "status":
                req.get(
                    "status",
                    "pending"
                ),

            "step":
                step_map.get(
                    req.get(
                        "status",
                        "pending"
                    ),
                    0
                ),

            "ambulance_assigned":
                req.get(
                    "ambulance"
                ) is not None,

            "ambulance":
                ambulance,

            "hospital":
                hospital,

            "eta_minutes":
                eta_minutes,

            "patient":
                _enrich_patient(
                    req.get(
                        "patient",
                        {}
                    ),
                    users
                ),

            "timestamp":
                req.get(
                    "timestamp"
                ),

            "status_updated_at":
                req.get(
                    "status_updated_at"
                )
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# PATIENT — MY REQUESTS
# ============================================================================

@app.route(
    "/api/patient/my-requests",
    methods=["GET"]
)
def api_patient_my_requests():

    try:

        mobile = request.args.get(
            "mobile",
            ""
        ).strip()


        if not mobile:

            return jsonify({
                "error":
                    "mobile is required"
            }), 400


        requests_data = [

            r

            for r in db.get_requests()

            if (
                r.get(
                    "patient",
                    {}
                ).get("mobile")
                == mobile
            )

            or (

                r.get(
                    "patient",
                    {}
                ).get("id")
                == mobile

            )
        ]


        requests_data.sort(
            key=lambda r:
                _request_timestamp(r),
            reverse=True
        )


        return jsonify({
            "requests":
                requests_data
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# PATIENT — CANCEL REQUEST
# ============================================================================

@app.route(
    "/api/patient/cancel-request",
    methods=["POST"]
)
def api_patient_cancel_request():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        request_id = body.get(
            "request_id"
        )


        if not request_id:

            return jsonify({
                "error":
                    "request_id is required"
            }), 400


        data = db.load_data()


        req = _find_request(
            data,
            request_id
        )


        if not req:

            return jsonify({
                "error":
                    "Request not found"
            }), 404


        ambulance_id = req.get(
            "ambulance"
        )


        if ambulance_id:

            ambulance = _find_ambulance(
                data,
                ambulance_id
            )


            if ambulance:

                ambulance["available"] = True


        req["status"] = "cancelled"


        req["cancelled_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )


        req["status_updated_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )


        db.save_data(
            data
        )


        return jsonify({

            "success":
                True,

            "message":
                "Request cancelled"
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — FIND / CREATE AMBULANCE
# ============================================================================

@app.route(
    "/api/driver/my-ambulance",
    methods=["GET"]
)
def api_driver_my_ambulance():

    try:

        mobile = request.args.get(
            "mobile",
            ""
        ).strip()


        driver_id = request.args.get(
            "driver_id",
            ""
        ).strip()


        ambulance_reg_number = (
            request.args.get(
                "ambulance_reg_number",
                ""
            ).strip()
        )


        data = db.load_data()


        ambulances = data.get(
            "ambulances",
            []
        )


        ambulance = None


        # ----------------------------------------------------------------
        # 1. Registration number
        # ----------------------------------------------------------------

        if ambulance_reg_number:

            ambulance = next(
                (
                    a

                    for a in ambulances

                    if (

                        a.get(
                            "id",
                            ""
                        ).upper()
                        ==
                        ambulance_reg_number.upper()

                    )

                    or (

                        a.get(
                            "ambulance_reg_number",
                            ""
                        ).upper()
                        ==
                        ambulance_reg_number.upper()

                    )
                ),
                None
            )


        # ----------------------------------------------------------------
        # 2. Driver mobile
        # ----------------------------------------------------------------

        if not ambulance and mobile:

            ambulance = next(
                (
                    a

                    for a in ambulances

                    if a.get(
                        "driver_mobile"
                    )
                    == mobile
                ),
                None
            )


        # ----------------------------------------------------------------
        # 3. Driver ID
        # ----------------------------------------------------------------

        if not ambulance and driver_id:

            ambulance = next(
                (
                    a

                    for a in ambulances

                    if a.get(
                        "driver_id"
                    )
                    == driver_id
                ),
                None
            )


        # ----------------------------------------------------------------
        # 4. Legacy driver name
        # ----------------------------------------------------------------

        user = None


        if mobile:

            user = db.find_user(
                mobile,
                "driver"
            )


        if not ambulance and user:

            driver_name = (
                user.get(
                    "full_name"
                )
                or ""
            ).lower().strip()


            ambulance = next(
                (
                    a

                    for a in ambulances

                    if (
                        a.get(
                            "driver"
                        )
                        or ""
                    ).lower().strip()
                    == driver_name
                ),
                None
            )


        # ----------------------------------------------------------------
        # 5. Create ambulance if driver has none
        # ----------------------------------------------------------------

        if not ambulance:

            new_id = (

                ambulance_reg_number

                or (

                    "AMB-"
                    +
                    (
                        driver_id
                        or mobile
                        or "NEW"
                    )[:8].upper()
                )
            )


            ambulance = {

                "id":
                    new_id,

                "driver":
                    (
                        (user or {}).get(
                            "full_name",
                            "Driver"
                        )
                    ),

                "driver_mobile":
                    mobile,

                "driver_id":
                    driver_id,

                "ambulance_reg_number":
                    ambulance_reg_number,

                "vehicle_type":
                    (
                        (user or {}).get(
                            "vehicle_type",
                            "Basic Life Support"
                        )
                    ),

                "organisation":
                    (
                        (user or {}).get(
                            "organisation",
                            ""
                        )
                    ),

                "latitude":
                    13.028,

                "longitude":
                    77.600,

                "available":
                    True
            }


            data.setdefault(
                "ambulances",
                []
            ).append(
                ambulance
            )


            db.save_data(
                data
            )


        return jsonify({
            "ambulance":
                ambulance
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — REQUESTS
# ============================================================================

@app.route(
    "/api/driver/requests",
    methods=["GET"]
)
def api_driver_requests():

    """
    Driver receives:
      1. pending requests currently offered to THIS ambulance
      2. active trips already assigned to THIS ambulance

    A busy driver never receives a new request.
    """

    try:
        ambulance_id = request.args.get("ambulance_id", "").strip()

        data = _refresh_dispatch_offers(db.load_data())
        users = data.get("users", [])
        requests_data = data.get("requests", [])

        pending = []

        if ambulance_id and not _driver_is_busy(data, ambulance_id):
            for req in requests_data:
                status = str(req.get("status", "")).lower().strip()

                if status != "pending" or req.get("ambulance"):
                    continue

                if req.get("offered_to") != ambulance_id:
                    continue

                enriched = dict(req)
                enriched["patient"] = _enrich_patient(
                    req.get("patient", {}),
                    users
                )
                pending.append(enriched)

        assigned = []

        for req in requests_data:
            if (
                req.get("ambulance") == ambulance_id
                and str(req.get("status", "")).lower() in ACTIVE_TRIP_STATUSES
            ):
                enriched = dict(req)
                enriched["patient"] = _enrich_patient(
                    req.get("patient", {}),
                    users
                )
                assigned.append(enriched)

        pending.sort(key=_request_timestamp, reverse=True)
        assigned.sort(key=_request_timestamp, reverse=True)

        return jsonify({
            "success": True,
            "pending": pending,
            "assigned": assigned,
            "pending_count": len(pending),
            "assigned_count": len(assigned),
            "ambulance_id": ambulance_id,
            "message": (
                "New patient request waiting for driver action."
                if pending else
                "No new patient request for this ambulance."
            )
        })

    except Exception as e:
        print("DRIVER REQUEST ERROR:", str(e))
        return jsonify({
            "success": False,
            "error": str(e),
            "pending": [],
            "assigned": [],
            "pending_count": 0,
            "assigned_count": 0
        }), 500


# ============================================================================
# DRIVER — ACCEPT REQUEST
# ============================================================================

@app.route(
    "/api/driver/accept",
    methods=["POST"]
)
def api_driver_accept():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        ambulance_id = body.get(
            "ambulance_id"
        )


        request_id = body.get(
            "request_id"
        )


        if (
            not ambulance_id
            or not request_id
        ):

            return jsonify({
                "error": (
                    "ambulance_id and "
                    "request_id required"
                )
            }), 400


        data = db.load_data()


        users = data.get(
            "users",
            []
        )


        req = _find_request(
            data,
            request_id
        )


        if not req:

            return jsonify({
                "error":
                    "Request not found"
            }), 404


        # Only pending requests can be accepted.

        if (
            req.get(
                "status"
            )
            != "pending"
        ):

            return jsonify({
                "error":
                    (
                        "Request already "
                        f"{req.get('status')}"
                    )
            }), 409

        # A driver can accept only a request currently offered to
        # this ambulance. This prevents two drivers accepting the
        # same patient at the same time.
        if req.get("offered_to") != ambulance_id:
            return jsonify({
                "error":
                    "This request is not currently assigned to your ambulance."
            }), 409


        ambulance = _find_ambulance(
            data,
            ambulance_id
        )


        if not ambulance:

            return jsonify({
                "error":
                    "Ambulance not found"
            }), 404


        # Ambulance must be available.

        if (
            ambulance.get(
                "available"
            )
            is False
        ):

            return jsonify({
                "error":
                    (
                        "This ambulance is "
                        "currently unavailable."
                    )
            }), 409


        patient = req.get(
            "patient",
            {}
        )


        hospital = ai.recommend_hospital(
            patient.get(
                "latitude"
            ),
            patient.get(
                "longitude"
            ),
            data.get(
                "hospitals",
                []
            )
        )


        hospital_id = (
            hospital.get("id")
            if hospital
            else None
        )


        now = datetime.now().isoformat(
            timespec="seconds"
        )


        req["ambulance"] = (
            ambulance_id
        )


        req["hospital"] = (
            hospital_id
        )


        req["status"] = (
            "accepted"
        )


        req["accepted_at"] = now


        req["status_updated_at"] = now

        # Clear the temporary dispatch offer once the driver accepts.
        req.pop("offered_to", None)
        req.pop("offer_expires_at", None)
        req.pop("offer_distance_km", None)
        req.pop("offered_at", None)


        ambulance["available"] = (
            False
        )


        if "rejected_by" in req:

            req["rejected_by"] = [
                item

                for item in req[
                    "rejected_by"
                ]

                if item
                != ambulance_id
            ]


        db.save_data(
            data
        )


        eta = ai.calculate_eta(
            ambulance,
            patient.get(
                "latitude"
            ),
            patient.get(
                "longitude"
            )
        )


        req["patient"] = (
            _enrich_patient(
                patient,
                users
            )
        )


        print(
            "REQUEST ACCEPTED:",
            request_id,
            "BY:",
            ambulance_id
        )


        return jsonify({

            "success":
                True,

            "request":
                req,

            "ambulance":
                ambulance,

            "hospital":
                hospital,

            "eta_minutes":
                eta
        })


    except Exception as e:

        print(
            "ACCEPT ERROR:",
            str(e)
        )

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — REJECT REQUEST
# ============================================================================

@app.route(
    "/api/driver/reject",
    methods=["POST"]
)
def api_driver_reject():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        ambulance_id = body.get(
            "ambulance_id"
        )


        request_id = body.get(
            "request_id"
        )


        if (
            not ambulance_id
            or not request_id
        ):

            return jsonify({
                "error": (
                    "ambulance_id and "
                    "request_id required"
                )
            }), 400


        data = db.load_data()


        req = _find_request(
            data,
            request_id
        )


        if not req:

            return jsonify({
                "error":
                    "Request not found"
            }), 404


        if req.get(
            "status"
        ) != "pending":

            return jsonify({
                "error": (
                    "Only pending requests "
                    "can be rejected."
                )
            }), 409

        if req.get("offered_to") != ambulance_id:
            return jsonify({
                "error":
                    "This request is not currently offered to your ambulance."
            }), 409


        rejected_by = req.setdefault(
            "rejected_by",
            []
        )


        if (
            ambulance_id
            not in rejected_by
        ):

            rejected_by.append(
                ambulance_id
            )

        # Release this offer and immediately try the next nearest driver.
        req.pop("offered_to", None)
        req.pop("offer_expires_at", None)
        req.pop("offer_distance_km", None)
        req.pop("offered_at", None)

        data = _refresh_dispatch_offers(data)
        # Persist the rejected_by information even if there is currently
        # no other available ambulance to receive the request.
        db.save_data(data)


        return jsonify({
            "success": True,
            "message": "Request rejected and sent to the next available driver.",
            "request": _find_request(data, request_id)
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — UPDATE LOCATION
# ============================================================================

@app.route(
    "/api/driver/location",
    methods=["POST"]
)
def api_driver_location():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        ambulance_id = body.get(
            "ambulance_id"
        )


        latitude = body.get(
            "latitude"
        )


        longitude = body.get(
            "longitude"
        )


        if (
            not ambulance_id
            or latitude is None
            or longitude is None
        ):

            return jsonify({
                "error": (
                    "ambulance_id, latitude, "
                    "longitude required"
                )
            }), 400


        try:

            latitude = float(
                latitude
            )

            longitude = float(
                longitude
            )

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                "error": (
                    "latitude and longitude "
                    "must be valid numbers"
                )
            }), 400


        updated = db.update_ambulance(
            ambulance_id,
            {
                "latitude":
                    latitude,

                "longitude":
                    longitude,

                "last_seen":
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
            }
        )


        if not updated:

            return jsonify({
                "error":
                    "Ambulance not found"
            }), 404

        # A newly available/currently moving ambulance may become the
        # nearest eligible driver for waiting patient requests.
        _refresh_dispatch_offers(db.load_data())


        return jsonify({
            "success":
                True,

            "ambulance":
                updated
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — TRIP STATUS
# ============================================================================

@app.route(
    "/api/driver/trip-status",
    methods=["POST"]
)
def api_driver_trip_status():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        request_id = body.get(
            "request_id"
        )


        status = body.get(
            "status"
        )


        if (
            not request_id
            or not status
        ):

            return jsonify({
                "error": (
                    "request_id and "
                    "status required"
                )
            }), 400


        allowed_statuses = {
            "active",
            "accepted",
            "en_route",
            "arrived",
            "picked_up",
            "completed",
            "trip_completed"
        }


        if status not in allowed_statuses:

            return jsonify({
                "error":
                    "Invalid trip status"
            }), 400


        req = db.update_request(
            request_id,
            {
                "status":
                    status,

                "status_updated_at":
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
            }
        )


        if not req:

            return jsonify({
                "error":
                    "Request not found"
            }), 404


        if status in (
            "completed",
            "trip_completed"
        ):

            ambulance_id = req.get(
                "ambulance"
            )


            if ambulance_id:

                db.update_ambulance(
                    ambulance_id,
                    {
                        "available":
                            True,

                        "emergency":
                            False
                    }
                )

                # Immediately dispatch the next waiting patient to the
                # newly available ambulance if it is the nearest one.
                _refresh_dispatch_offers(db.load_data())


        # Keep the next waiting patient moving through the dispatch queue.
        _refresh_dispatch_offers(db.load_data())

        return jsonify({

            "success":
                True,

            "request":
                req
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — SUMMARY
# ============================================================================

@app.route(
    "/api/driver/summary",
    methods=["GET"]
)
def api_driver_summary():

    try:

        ambulance_id = request.args.get(
            "ambulance_id",
            ""
        ).strip()


        if not ambulance_id:

            return jsonify({
                "error":
                    "ambulance_id required"
            }), 400


        data = db.load_data()


        today = datetime.now().date()


        trips_today = 0

        earnings_today = 0

        total_completed = 0

        ratings = []


        for req in data.get(
            "requests",
            []
        ):

            if (
                req.get(
                    "ambulance"
                )
                != ambulance_id
            ):

                continue


            if req.get(
                "status"
            ) in (
                "completed",
                "trip_completed"
            ):

                total_completed += 1


                try:

                    timestamp = datetime.fromisoformat(
                        req["timestamp"]
                    )


                    if (
                        timestamp.date()
                        == today
                    ):

                        trips_today += 1


                        earnings_today += float(
                            req.get(
                                "fare",
                                50
                            )
                        )


                except Exception:

                    pass


            if req.get(
                "rating"
            ):

                try:

                    ratings.append(
                        float(
                            req["rating"]
                        )
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    pass


        average_rating = (

            round(
                sum(ratings)
                / len(ratings),
                2
            )

            if ratings

            else 5.0
        )


        return jsonify({

            "ambulance_id":
                ambulance_id,

            "trips_today":
                trips_today,

            "earnings_today":
                round(
                    earnings_today,
                    2
                ),

            "rating":
                average_rating,

            "total_completed":
                total_completed
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER — EMERGENCY
# ============================================================================

@app.route(
    "/api/driver/emergency",
    methods=["POST"]
)
def api_driver_emergency():

    try:

        body = (
            request.get_json(
                silent=True
            )
            or {}
        )


        ambulance_id = body.get(
            "ambulance_id"
        )


        reason = body.get(
            "reason",
            "Driver emergency"
        )


        if not ambulance_id:

            return jsonify({
                "error":
                    "ambulance_id required"
            }), 400


        data = db.load_data()


        ambulance = _find_ambulance(
            data,
            ambulance_id
        )


        if not ambulance:

            return jsonify({
                "error":
                    "Ambulance not found"
            }), 404


        ambulance["available"] = False

        ambulance["emergency"] = True


        ambulance[
            "last_emergency_at"
        ] = datetime.now().isoformat(
            timespec="seconds"
        )


        emergency_id = (
            "EMR"
            + str(
                uuid.uuid4()
            )[:6].upper()
        )


        data.setdefault(
            "emergencies",
            []
        ).append({

            "id":
                emergency_id,

            "ambulance_id":
                ambulance_id,

            "reason":
                reason,

            "timestamp":
                datetime.now().isoformat(
                    timespec="seconds"
                )
        })


        db.save_data(
            data
        )


        return jsonify({

            "success":
                True,

            "message":
                "Emergency recorded",

            "emergency_id":
                emergency_id
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# HOSPITAL DASHBOARD
# ============================================================================

@app.route(
    "/api/hospital/dashboard",
    methods=["GET"]
)
def api_hospital_dashboard():

    try:

        data = db.load_data()
        data = _refresh_dispatch_offers(data)


        users = data.get(
            "users",
            []
        )


        hospitals = data.get(
            "hospitals",
            []
        )


        raw_requests = data.get(
            "requests",
            []
        )


        ambulance_data = data.get(
            "ambulances",
            []
        )


        # ================================================================
        # AMBULANCE ROWS
        # ================================================================

        ambulance_rows = []


        for ambulance in ambulance_data:

            row = dict(
                ambulance
            )


            if ambulance.get(
                "emergency"
            ):

                row["status"] = (
                    "emergency"
                )

            elif ambulance.get(
                "available"
            ) is False:

                row["status"] = (
                    "enroute"
                )

            else:

                row["status"] = (
                    "available"
                )


            driver = None


            if ambulance.get(
                "driver_mobile"
            ):

                driver = db.find_user(
                    ambulance[
                        "driver_mobile"
                    ],
                    "driver"
                )


            if not driver:

                driver = next(
                    (
                        u

                        for u in users

                        if (
                            u.get(
                                "role"
                            )
                            == "driver"
                        )

                        and (

                            (
                                u.get(
                                    "full_name",
                                    ""
                                ).lower()

                                ==

                                (
                                    ambulance.get(
                                        "driver",
                                        ""
                                    )
                                ).lower()
                            )

                            or

                            (
                                u.get(
                                    "ambulance_reg_number",
                                    ""
                                )

                                ==

                                ambulance.get(
                                    "id",
                                    ""
                                )
                            )
                        )
                    ),
                    None
                )


            if driver:

                row["driver_name"] = (
                    driver.get(
                        "full_name"
                    )
                    or ambulance.get(
                        "driver"
                    )
                    or "Driver"
                )


                row["driver_mobile"] = (
                    driver.get(
                        "mobile"
                    )
                )


                row["vehicle_type"] = (
                    driver.get(
                        "vehicle_type"
                    )
                    or ambulance.get(
                        "vehicle_type"
                    )
                )


                row["organisation"] = (
                    driver.get(
                        "organisation"
                    )
                    or ambulance.get(
                        "organisation"
                    )
                )

            else:

                row["driver_name"] = (
                    ambulance.get(
                        "driver"
                    )
                    or "Unassigned"
                )


            ambulance_rows.append(
                row
            )


        # ================================================================
        # ENRICH REQUESTS
        # ================================================================

        enriched_requests = []


        for request_item in raw_requests:

            enriched = dict(
                request_item
            )


            enriched["patient"] = (
                _enrich_patient(
                    request_item.get(
                        "patient",
                        {}
                    ),
                    users
                )
            )


            if request_item.get(
                "ambulance"
            ):

                ambulance_row = next(
                    (
                        a

                        for a in ambulance_rows

                        if a.get(
                            "id"
                        )
                        == request_item.get(
                            "ambulance"
                        )
                    ),
                    None
                )


                if ambulance_row:

                    enriched[
                        "ambulance_info"
                    ] = {

                        "id":
                            ambulance_row.get(
                                "id"
                            ),

                        "driver_name":
                            ambulance_row.get(
                                "driver_name"
                            ),

                        "vehicle_type":
                            ambulance_row.get(
                                "vehicle_type"
                            ),

                        "latitude":
                            ambulance_row.get(
                                "latitude"
                            ),

                        "longitude":
                            ambulance_row.get(
                                "longitude"
                            ),

                        "status":
                            ambulance_row.get(
                                "status"
                            )
                    }


            if request_item.get(
                "hospital"
            ):

                hospital = _find_hospital(
                    data,
                    request_item.get(
                        "hospital"
                    )
                )


                if hospital:

                    enriched[
                        "hospital_name"
                    ] = hospital.get(
                        "name"
                    )


            enriched_requests.append(
                enriched
            )


        enriched_requests.sort(
            key=lambda r:
                _request_timestamp(r),
            reverse=True
        )


        # ================================================================
        # ACTIVE REQUESTS
        # ================================================================

        active_requests = [

            r

            for r in enriched_requests

            if r.get(
                "status"
            ) in (
                "pending",
                "active",
                "accepted",
                "en_route",
                "picked_up"
            )
        ]


        # ================================================================
        # RESPONSE TIME
        # ================================================================

        response_times = []


        for req in active_requests:

            ambulance_info = req.get(
                "ambulance_info"
            )


            patient_info = req.get(
                "patient",
                {}
            )


            if (
                ambulance_info
                and ambulance_info.get(
                    "latitude"
                ) is not None
                and ambulance_info.get(
                    "longitude"
                ) is not None
                and patient_info.get(
                    "latitude"
                ) is not None
                and patient_info.get(
                    "longitude"
                ) is not None
            ):

                distance = _dist_km(

                    ambulance_info[
                        "latitude"
                    ],

                    ambulance_info[
                        "longitude"
                    ],

                    patient_info[
                        "latitude"
                    ],

                    patient_info[
                        "longitude"
                    ]
                )


                if distance is not None:

                    estimated_minutes = max(

                        3,

                        round(
                            distance
                            * 2.2
                        )
                    )


                    response_times.append(
                        estimated_minutes
                    )


        # ================================================================
        # KPI
        # ================================================================

        stats = {

            "total_ambulances":
                len(
                    ambulance_rows
                ),

            "active_ambulances":
                sum(

                    1

                    for ambulance
                    in ambulance_rows

                    if ambulance.get(
                        "status"
                    )
                    == "enroute"
                ),

            "available_ambulances":
                sum(

                    1

                    for ambulance
                    in ambulance_rows

                    if ambulance.get(
                        "status"
                    )
                    == "available"
                ),

            "emergency_requests":
                len(
                    active_requests
                ),

            "pending_requests":
                sum(

                    1

                    for req
                    in active_requests

                    if req.get(
                        "status"
                    )
                    == "pending"
                ),

            "average_response_time":
                (
                    round(
                        sum(
                            response_times
                        )
                        /
                        len(
                            response_times
                        ),
                        1
                    )

                    if response_times

                    else 0
                )
        }


        # ================================================================
        # ALERTS
        # ================================================================

        alerts = []


        for req in active_requests[:6]:

            patient = req.get(
                "patient",
                {}
            )


            if req.get(
                "status"
            ) == "pending":

                alert_type = "warning"

                alert_icon = "warning"

            else:

                alert_type = "info"

                alert_icon = "info"


            status_text = (
                req.get(
                    "status",
                    "pending"
                )
                .replace(
                    "_",
                    " "
                )
            )


            alerts.append({

                "type":
                    alert_type,

                "icon":
                    alert_icon,

                "message":
                    (
                        f"{patient.get('name', 'Patient')}"
                        f" — {req.get('id')}"
                        f" — {status_text}"
                    ),

                "timestamp":
                    req.get(
                        "timestamp"
                    ),

                "request_id":
                    req.get(
                        "id"
                    )
            })


        for ambulance in ambulance_rows:

            if ambulance.get(
                "status"
            ) == "emergency":

                alerts.append({

                    "type":
                        "critical",

                    "icon":
                        "critical",

                    "message":
                        (
                            "DRIVER EMERGENCY — "
                            f"{ambulance.get('id', '')}"
                            f" ({ambulance.get('driver_name', '')})"
                        ),

                    "timestamp":
                        ambulance.get(
                            "last_emergency_at"
                        ),

                    "ambulance_id":
                        ambulance.get(
                            "id"
                        )
                })


        # ================================================================
        # LAST 7 DAYS
        # ================================================================

        trend = []


        for days_ago in range(
            6,
            -1,
            -1
        ):

            day = (
                datetime.now()
                - timedelta(
                    days=days_ago
                )
            )


            date_string = day.strftime(
                "%Y-%m-%d"
            )


            count = sum(

                1

                for req in enriched_requests

                if req.get(
                    "timestamp",
                    ""
                )[:10]
                == date_string
            )


            trend.append({

                "label":
                    day.strftime(
                        "%a"
                    ),

                "count":
                    count
            })


        # ================================================================
        # STATUS SUMMARY
        # ================================================================

        status_summary = {

            "available":
                stats[
                    "available_ambulances"
                ],

            "enroute":
                stats[
                    "active_ambulances"
                ],

            "maintenance":
                sum(

                    1

                    for ambulance
                    in ambulance_rows

                    if ambulance.get(
                        "status"
                    )
                    == "maintenance"
                )
        }


        return jsonify({

            "stats":
                stats,

            "ambulances":
                ambulance_rows,

            "requests":
                enriched_requests,

            "active_requests":
                active_requests,

            "alerts":
                alerts[:8],

            "emergency_trend":
                trend,

            "status_summary":
                status_summary,

            "hospitals":
                hospitals
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# RAW DATA ENDPOINTS
# ============================================================================

@app.route(
    "/ambulances"
)
def ambulances():

    try:

        return jsonify(
            db.get_ambulances()
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ----------------------------------------------------------------------------

@app.route(
    "/hospitals"
)
def hospitals():

    try:

        return jsonify(
            db.get_hospitals()
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ----------------------------------------------------------------------------

@app.route(
    "/requests"
)
def requests_list():

    try:

        return jsonify(
            db.get_requests()
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# DRIVER DATA
# ============================================================================

@app.route(
    "/driver-data"
)
def driver_data():

    try:

        ambulance_id = request.args.get(
            "ambulance_id",
            ""
        ).strip()


        if not ambulance_id:

            return jsonify({
                "error":
                    "ambulance_id required"
            }), 400


        data = db.load_data()


        users = data.get(
            "users",
            []
        )


        ambulance = _find_ambulance(
            data,
            ambulance_id
        )


        if not ambulance:

            return jsonify({
                "error":
                    "Ambulance not found"
            }), 404


        hospitals_map = {

            hospital["id"]:
                hospital

            for hospital
            in data.get(
                "hospitals",
                []
            )

            if hospital.get(
                "id"
            )
        }


        active_request = next(
            (

                r

                for r
                in data.get(
                    "requests",
                    []
                )

                if (

                    r.get(
                        "ambulance"
                    )
                    == ambulance_id

                    and r.get(
                        "status"
                    )
                    in (
                        "active",
                        "accepted",
                        "en_route",
                        "arrived",
                        "picked_up"
                    )
                )
            ),
            None
        )


        if active_request:

            active_request = dict(
                active_request
            )


            active_request["patient"] = (
                _enrich_patient(
                    active_request.get(
                        "patient",
                        {}
                    ),
                    users
                )
            )


            hospital_id = (
                active_request.get(
                    "hospital"
                )
            )


            active_request[
                "hospital_name"
            ] = (

                hospitals_map.get(
                    hospital_id,
                    {}
                ).get(
                    "name",
                    ""
                )
            )


            active_request[
                "eta_minutes"
            ] = ai.calculate_eta(

                ambulance,

                active_request[
                    "patient"
                ].get(
                    "latitude"
                ),

                active_request[
                    "patient"
                ].get(
                    "longitude"
                )
            )


        return jsonify({

            "ambulance":
                ambulance,

            "active_request":
                active_request
        })


    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":

    print(
        "Starting LifeLine server at "
        "http://localhost:5000"
    )


    app.run(
        debug=True,
        port=5000,
        use_reloader=True
    )