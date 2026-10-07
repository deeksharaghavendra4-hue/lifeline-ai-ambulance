/* =========================================================
   LIFELINE — DRIVER DASHBOARD
   COMPLETE DRIVER REQUEST + ACCEPT/REJECT FLOW

   FLOW:
   Patient requests ambulance
          ↓
   Request is offered to this driver's ambulance
          ↓
   Driver sees patient details
          ↓
   Driver clicks ACCEPT or REJECT
          ↓
   ACCEPT:
       Request becomes accepted
       Active trip is shown
       Hospital is selected by backend
       Hospital dashboard can see the trip
          ↓
   REJECT:
       Request is released
       Backend searches for another driver

   IMPORTANT:
   A request is NEVER accepted automatically.
   It remains pending until the driver clicks ACCEPT.
   ========================================================= */


/* =========================================================
   SETTINGS
   ========================================================= */

const POLL_MS = 3000;


/* =========================================================
   GLOBAL VARIABLES
   ========================================================= */

let ambulanceId = null;

let driverUser = null;

let pollTimer = null;

let currentRequest = null;

let pendingRequest = null;

let map = null;

let driverMarker = null;

let patientMarker = null;

let hospitalMarker = null;

let routeLineToPatient = null;

let routeLineToHospital = null;


/* =========================================================
   HELPER
   ========================================================= */

function getElement(id) {
    return document.getElementById(id);
}


/* =========================================================
   MESSAGE
   ========================================================= */

function showMessage(message, type = "info") {

    console.log(`[${type}] ${message}`);

    const possibleIds = [
        "driverMessage",
        "message",
        "statusMessage",
        "toast"
    ];

    for (const id of possibleIds) {

        const element = getElement(id);

        if (element) {

            element.textContent = message;

            element.className = `message ${type}`;

            return;
        }
    }
}


/* =========================================================
   NORMALIZE STATUS
   ========================================================= */

function normalizeStatus(status) {

    return String(status || "")
        .trim()
        .toLowerCase()
        .replace(/-/g, "_");
}


/* =========================================================
   CHECK ACTIVE TRIP
   ========================================================= */

function isActiveTrip(status) {

    const normalized = normalizeStatus(status);

    return [
        "accepted",
        "active",
        "en_route",
        "enroute",
        "arrived",
        "picked_up"
    ].includes(normalized);
}


/* =========================================================
   REQUEST TIME
   ========================================================= */

function getRequestTime(request) {

    const value =
        request?.timestamp ||
        request?.created_at ||
        request?.requested_at ||
        null;

    if (!value) {
        return 0;
    }

    const time = new Date(value).getTime();

    return Number.isFinite(time)
        ? time
        : 0;
}


/* =========================================================
   GET NEWEST PENDING REQUEST
   ========================================================= */

function getNewestPendingRequest(requests) {

    if (!Array.isArray(requests)) {
        return null;
    }

    if (requests.length === 0) {
        return null;
    }

    const pending = requests.filter(request => {

        return normalizeStatus(request?.status) === "pending";

    });

    if (pending.length === 0) {
        return null;
    }

    pending.sort((a, b) => {

        return (
            getRequestTime(b) -
            getRequestTime(a)
        );

    });

    return pending[0];
}


/* =========================================================
   LOAD DRIVER USER
   ========================================================= */

function loadDriverUser() {

    let user = null;

    try {

        const sessionUser =
            sessionStorage.getItem("user");

        const localUser =
            localStorage.getItem("driver_data");

        if (sessionUser) {

            user = JSON.parse(sessionUser);

        } else if (localUser) {

            user = JSON.parse(localUser);
        }

    } catch (error) {

        console.error(
            "Unable to read driver user:",
            error
        );
    }


    const sessionRole =
        sessionStorage.getItem("role");

    const registeredDriver =
        localStorage.getItem("driver_registered");


    const role =
        sessionRole ||
        (
            registeredDriver
                ? "driver"
                : null
        );


    if (
        role !== "driver" ||
        !user ||
        !user.mobile
    ) {

        window.location.href = "/login";

        return null;
    }


    driverUser = user;


    console.log(
        "Logged in driver:",
        driverUser
    );


    return driverUser;
}


/* =========================================================
   RESOLVE DRIVER'S AMBULANCE
   ========================================================= */

async function resolveDriverAmbulance() {

    if (!driverUser) {
        return false;
    }


    const params = new URLSearchParams({

        mobile:
            driverUser.mobile || "",

        driver_id:
            driverUser.driver_id || "",

        ambulance_reg_number:
            driverUser.ambulance_reg_number || ""
    });


    try {

        const response =
            await fetch(
                `/api/driver/my-ambulance?${params.toString()}`,
                {
                    cache: "no-store"
                }
            );


        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        if (
            data &&
            data.ambulance &&
            data.ambulance.id
        ) {

            ambulanceId =
                data.ambulance.id;


            console.log(
                "Driver ambulance:",
                ambulanceId
            );


            return true;
        }


        showMessage(
            "No ambulance is linked to this driver account.",
            "error"
        );


        return false;


    } catch (error) {

        console.error(
            "Ambulance resolution failed:",
            error
        );


        showMessage(
            "Unable to load your ambulance details.",
            "error"
        );


        return false;
    }
}


/* =========================================================
   DRIVER SUMMARY
   ========================================================= */

async function loadDriverSummary() {

    if (!ambulanceId) {
        return;
    }


    try {

        const response =
            await fetch(
                `/api/driver/summary?ambulance_id=${encodeURIComponent(ambulanceId)}`,
                {
                    cache: "no-store"
                }
            );


        if (!response.ok) {
            return;
        }


        const data =
            await response.json();


        console.log(
            "Driver summary:",
            data
        );


        const totalTrips =
            getElement("stat-total");


        if (
            totalTrips &&
            data.total_trips !== undefined
        ) {

            totalTrips.textContent =
                data.total_trips;
        }


        const todayTrips =
            getElement("stat-trips");


        if (
            todayTrips &&
            data.today_trips !== undefined
        ) {

            todayTrips.textContent =
                data.today_trips;

        } else if (
            todayTrips &&
            data.total_trips !== undefined
        ) {

            todayTrips.textContent =
                data.total_trips;
        }


    } catch (error) {

        console.error(
            "Unable to load driver summary:",
            error
        );
    }
}


/* =========================================================
   FETCH DRIVER REQUESTS
   ========================================================= */

async function fetchDriverRequests() {

    if (!ambulanceId) {
        return null;
    }


    try {

        const response =
            await fetch(
                `/api/driver/requests?ambulance_id=${encodeURIComponent(ambulanceId)}`,
                {
                    cache: "no-store"
                }
            );


        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        if (data.success === false) {

            throw new Error(
                data.error ||
                "Driver request API failed."
            );
        }


        return {

            pending:
                Array.isArray(data.pending)
                    ? data.pending
                    : [],

            assigned:
                Array.isArray(data.assigned)
                    ? data.assigned
                    : []
        };


    } catch (error) {

        console.error(
            "Unable to load driver requests:",
            error
        );


        return null;
    }
}


/* =========================================================
   LOAD HOSPITAL DETAILS
   ========================================================= */

async function getHospitalById(hospitalId) {

    if (!hospitalId) {
        return null;
    }


    try {

        const response =
            await fetch(
                "/hospitals",
                {
                    cache: "no-store"
                }
            );


        if (!response.ok) {
            return null;
        }


        const hospitals =
            await response.json();


        if (!Array.isArray(hospitals)) {
            return null;
        }


        return (
            hospitals.find(
                hospital =>
                    hospital.id === hospitalId
            )
            || null
        );


    } catch (error) {

        console.error(
            "Unable to load hospital:",
            error
        );


        return null;
    }
}


/* =========================================================
   POLLING
   ========================================================= */

async function poll() {

    if (!ambulanceId) {
        return;
    }


    const data =
        await fetchDriverRequests();


    if (!data) {
        return;
    }


    const pending =
        data.pending || [];


    const assigned =
        data.assigned || [];


    console.log(
        "Driver request update:",
        {
            ambulanceId,
            pendingCount: pending.length,
            assignedCount: assigned.length,
            pendingIds:
                pending.map(
                    request => request.id
                ),
            assignedIds:
                assigned.map(
                    request => request.id
                )
        }
    );


    /* =====================================================
       ACTIVE ASSIGNED TRIP
       ===================================================== */

    const activeAssigned =
        assigned.filter(
            request =>
                isActiveTrip(
                    request.status
                )
        );


    /* =====================================================
       RESTORE ACTIVE TRIP AFTER REFRESH
       ===================================================== */

    if (
        activeAssigned.length > 0 &&
        !currentRequest
    ) {

        activeAssigned.sort(
            (a, b) =>
                getRequestTime(b) -
                getRequestTime(a)
        );


        const trip =
            activeAssigned[0];


        trip.hospital_obj =
            await getHospitalById(
                trip.hospital
            );


        currentRequest =
            trip;


        showActiveTrip(
            currentRequest
        );


        hideRequestCard();


        return;
    }


    /* =====================================================
       UPDATE CURRENT ACTIVE TRIP
       ===================================================== */

    if (currentRequest) {

        const fresh =
            assigned.find(
                request =>
                    request.id ===
                    currentRequest.id
            );


        if (fresh) {

            const oldStatus =
                normalizeStatus(
                    currentRequest.status
                );


            const newStatus =
                normalizeStatus(
                    fresh.status
                );


            currentRequest = {

                ...currentRequest,

                ...fresh
            };


            if (
                !currentRequest.hospital_obj &&
                currentRequest.hospital
            ) {

                currentRequest.hospital_obj =
                    await getHospitalById(
                        currentRequest.hospital
                    );
            }


            updateTripStatusUI(
                currentRequest
            );


            showActiveTrip(
                currentRequest
            );


            /*
             * Driver is already handling
             * this patient.
             *
             * Do not show another request.
             */

            hideRequestCard();


            if (
                oldStatus !==
                newStatus
            ) {

                console.log(
                    "Trip status changed:",
                    oldStatus,
                    "→",
                    newStatus
                );
            }


            return;
        }


        /* =================================================
           CURRENT TRIP NO LONGER ACTIVE
           ================================================= */

        const currentStatus =
            normalizeStatus(
                currentRequest.status
            );


        if (
            [
                "completed",
                "cancelled",
                "rejected"
            ].includes(
                currentStatus
            )
        ) {

            currentRequest = null;

            hideActiveTrip();

            await loadDriverSummary();

            await poll();

            return;
        }


        if (
            activeAssigned.length === 0
        ) {

            currentRequest = null;

            hideActiveTrip();
        }
    }


    /* =====================================================
       SHOW NEW PATIENT REQUEST
       ===================================================== */

    if (!currentRequest) {

        const newestPending =
            getNewestPendingRequest(
                pending
            );


        if (newestPending) {

            console.log(
                "NEW PATIENT REQUEST:",
                newestPending
            );


            /*
             * Only update the request
             * card when a new request arrives.
             */

            if (
                !pendingRequest ||
                pendingRequest.id !==
                newestPending.id
            ) {

                showRequestCard(
                    newestPending
                );
            }

        } else {

            hideRequestCard();
        }
    }
}


/* =========================================================
   SHOW PATIENT REQUEST CARD
   ========================================================= */

function showRequestCard(request) {

    if (!request) {
        return;
    }


    /*
     * IMPORTANT:
     * This stores the request only.
     *
     * It does NOT accept the request.
     */

    pendingRequest =
        request;


    console.log(
        "Displaying patient request:",
        request
    );


    /* =====================================================
       ACTUAL HTML ID FROM YOUR PAGE
       ===================================================== */

    const card =
        getElement("request-card");


    if (!card) {

        console.error(
            "request-card was not found."
        );


        showMessage(
            "New ambulance request received, but the request card is missing.",
            "error"
        );


        return;
    }


    /* =====================================================
       PATIENT
       ===================================================== */

    const patient =
        request.patient || {};


    const name =
        patient.name ||
        patient.full_name ||
        "Patient";


    const age =
        patient.age ??
        "—";


    const gender =
        patient.gender ||
        "—";


    const blood =
        patient.blood_group ||
        patient.bloodGroup ||
        "—";


    const mobile =
        patient.mobile ||
        patient.phone ||
        patient.phone_number ||
        "—";


    const emergency =
        patient.emergency_type ||
        request.emergency_type ||
        request.emergency ||
        "Emergency";


    /* =====================================================
       DISTANCE
       ===================================================== */

    let distance = "—";


    if (
        request.offer_distance_km !==
        undefined &&
        request.offer_distance_km !==
        null
    ) {

        distance =
            `${request.offer_distance_km} km`;

    } else if (
        request.distance_km !==
        undefined &&
        request.distance_km !==
        null
    ) {

        distance =
            `${request.distance_km} km`;
    }


    /* =====================================================
       ETA
       ===================================================== */

    let eta = "—";


    if (
        request.eta_minutes !==
        undefined &&
        request.eta_minutes !==
        null
    ) {

        eta =
            `${request.eta_minutes} min`;
    }


    /* =====================================================
       PICKUP
       ===================================================== */

    const pickup =
        request.pickup_address ||
        request.pickup_location ||
        patient.address ||
        "Patient current location";


    /* =====================================================
       PUT DATA INTO THE ACTUAL HTML ELEMENTS
       ===================================================== */

    const reqType =
        getElement("req-type");


    if (reqType) {
        reqType.textContent =
            emergency;
    }


    const reqPatient =
        getElement("req-patient");


    if (reqPatient) {
        reqPatient.textContent =
            name;
    }


    const reqAgeGender =
        getElement("req-age-gender");


    if (reqAgeGender) {
        reqAgeGender.textContent =
            `${age} / ${gender}`;
    }


    const reqBlood =
        getElement("req-blood");


    if (reqBlood) {
        reqBlood.textContent =
            blood;
    }


    const reqMobile =
        getElement("req-mobile");


    if (reqMobile) {
        reqMobile.textContent =
            mobile;
    }


    const reqDistance =
        getElement("req-distance");


    if (reqDistance) {
        reqDistance.textContent =
            distance;
    }


    const reqEta =
        getElement("req-eta");


    if (reqEta) {
        reqEta.textContent =
            eta;
    }


    const reqPickup =
        getElement("req-pickup");


    if (reqPickup) {
        reqPickup.textContent =
            pickup;
    }


    /* =====================================================
       PRIORITY
       ===================================================== */

    const priority =
        getElement("req-priority");


    if (priority) {

        priority.textContent =
            "High";
    }


    /* =====================================================
       SHOW CARD
       ===================================================== */

    card.classList.remove("hidden");

    card.style.display = "block";


    /* =====================================================
       ACCEPT BUTTON
       ===================================================== */

    const acceptButton =
        getElement("accept-btn");


    if (acceptButton) {

        acceptButton.disabled =
            false;


        acceptButton.onclick =
            handleAccept;
    }


    /* =====================================================
       REJECT BUTTON
       ===================================================== */

    const rejectButton =
        getElement("reject-btn");


    if (rejectButton) {

        rejectButton.disabled =
            false;


        rejectButton.onclick =
            handleReject;
    }


    showMessage(
        `New ambulance request from ${name}`,
        "info"
    );


    console.log(
        "Patient request is waiting for DRIVER ACTION."
    );
}


/* =========================================================
   HIDE REQUEST CARD
   ========================================================= */

function hideRequestCard() {

    /*
     * Do NOT hide current trip.
     * This only hides the pending request.
     */

    pendingRequest = null;


    const card =
        getElement("request-card");


    if (card) {

        card.classList.add("hidden");

        card.style.display = "none";
    }
}


/* =========================================================
   ACCEPT REQUEST
   ========================================================= */

async function handleAccept() {

    /*
     * IMPORTANT:
     * Nothing happens unless a pending request
     * exists.
     */

    if (!pendingRequest) {

        showMessage(
            "No ambulance request selected.",
            "error"
        );

        return;
    }


    if (!ambulanceId) {

        showMessage(
            "Your ambulance is not available.",
            "error"
        );

        return;
    }


    const requestId =
        pendingRequest.id;


    if (!requestId) {

        showMessage(
            "Request ID is missing.",
            "error"
        );

        return;
    }


    /* =====================================================
       DISABLE BUTTONS WHILE ACCEPTING
       ===================================================== */

    const acceptButton =
        getElement("accept-btn");


    const rejectButton =
        getElement("reject-btn");


    if (acceptButton) {
        acceptButton.disabled = true;
    }


    if (rejectButton) {
        rejectButton.disabled = true;
    }


    try {

        const response =
            await fetch(
                "/api/driver/accept",
                {

                    method: "POST",

                    headers: {
                        "content-type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            ambulance_id:
                                ambulanceId,

                            request_id:
                                requestId
                        })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                data.message ||
                "Unable to accept request."
            );
        }


        console.log(
            "REQUEST ACCEPTED:",
            data
        );


        /* =================================================
           GET HOSPITAL
           ================================================= */

        let hospitalObj = null;


        const hospitalId =
            data.request?.hospital ||
            data.hospital?.id ||
            pendingRequest.hospital ||
            null;


        if (hospitalId) {

            hospitalObj =
                await getHospitalById(
                    hospitalId
                );
        }


        /* =================================================
           CREATE ACTIVE TRIP
           ================================================= */

        currentRequest = {

            ...pendingRequest,

            ...(data.request || {}),

            hospital_obj:
                hospitalObj,

            eta_minutes:
                data.eta_minutes ??
                pendingRequest.eta_minutes
        };


        /*
         * Clear pending request.
         */

        pendingRequest = null;


        /*
         * Hide incoming request.
         */

        hideRequestCard();


        /*
         * Show active trip.
         */

        showActiveTrip(
            currentRequest
        );


        /*
         * Update status timeline.
         */

        updateTripStatusUI(
            currentRequest
        );


        showMessage(
            "Ambulance request accepted.",
            "success"
        );


        await loadDriverSummary();


        /*
         * Refresh from backend.
         */

        setTimeout(
            () => {

                poll();

            },
            500
        );


    } catch (error) {

        console.error(
            "Accept request failed:",
            error
        );


        /*
         * Re-enable buttons if
         * accepting failed.
         */

        if (acceptButton) {
            acceptButton.disabled = false;
        }


        if (rejectButton) {
            rejectButton.disabled = false;
        }


        showMessage(
            error.message ||
            "Unable to accept request.",
            "error"
        );
    }
}


/* =========================================================
   REJECT REQUEST
   ========================================================= */

async function handleReject() {

    if (!pendingRequest) {

        showMessage(
            "No ambulance request selected.",
            "error"
        );

        return;
    }


    if (!ambulanceId) {

        showMessage(
            "Your ambulance is not available.",
            "error"
        );

        return;
    }


    const requestId =
        pendingRequest.id;


    if (!requestId) {

        showMessage(
            "Request ID is missing.",
            "error"
        );

        return;
    }


    const acceptButton =
        getElement("accept-btn");


    const rejectButton =
        getElement("reject-btn");


    if (acceptButton) {
        acceptButton.disabled = true;
    }


    if (rejectButton) {
        rejectButton.disabled = true;
    }


    try {

        const response =
            await fetch(
                "/api/driver/reject",
                {

                    method: "POST",

                    headers: {
                        "content-type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            ambulance_id:
                                ambulanceId,

                            request_id:
                                requestId
                        })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                data.message ||
                "Unable to reject request."
            );
        }


        console.log(
            "REQUEST REJECTED:",
            data
        );


        pendingRequest =
            null;


        hideRequestCard();


        showMessage(
            "Ambulance request rejected.",
            "info"
        );


        /*
         * Check immediately whether
         * another request is waiting.
         */

        setTimeout(
            () => {

                poll();

            },
            300
        );


    } catch (error) {

        console.error(
            "Reject request failed:",
            error
        );


        if (acceptButton) {
            acceptButton.disabled = false;
        }


        if (rejectButton) {
            rejectButton.disabled = false;
        }


        showMessage(
            error.message ||
            "Unable to reject request.",
            "error"
        );
    }
}


/* =========================================================
   SHOW ACTIVE TRIP
   ========================================================= */

function showActiveTrip(request) {

    if (!request) {
        return;
    }


    const card =
        getElement("current-trip");


    if (card) {

        card.classList.remove("hidden");

        card.style.display = "block";
    }


    const patient =
        request.patient || {};


    const name =
        patient.name ||
        patient.full_name ||
        "Patient";


    const age =
        patient.age ??
        "—";


    const gender =
        patient.gender ||
        "—";


    const blood =
        patient.blood_group ||
        patient.bloodGroup ||
        "—";


    const mobile =
        patient.mobile ||
        patient.phone ||
        "—";


    const emergency =
        patient.emergency_type ||
        request.emergency_type ||
        "Emergency";


    const pickup =
        request.pickup_address ||
        request.pickup_location ||
        patient.address ||
        "Patient location";


    const hospital =
        request.hospital_obj ||
        {};


    const hospitalName =
        hospital.name ||
        hospital.hospital_name ||
        "Hospital";


    /* =====================================================
       PATIENT
       ===================================================== */

    const tripPatient =
        getElement("trip-patient");


    if (tripPatient) {

        tripPatient.textContent =
            name;
    }


    /* =====================================================
       AGE / GENDER
       ===================================================== */

    const tripAgeGender =
        getElement("trip-age-gender");


    if (tripAgeGender) {

        tripAgeGender.textContent =
            `${age} / ${gender}`;
    }


    /* =====================================================
       BLOOD
       ===================================================== */

    const tripBlood =
        getElement("trip-blood");


    if (tripBlood) {

        tripBlood.textContent =
            blood;
    }


    /* =====================================================
       MOBILE
       ===================================================== */

    const tripMobile =
        getElement("trip-mobile");


    if (tripMobile) {

        tripMobile.textContent =
            mobile;
    }


    /* =====================================================
       EMERGENCY
       ===================================================== */

    const tripEmergency =
        getElement("trip-emergency");


    if (tripEmergency) {

        tripEmergency.textContent =
            emergency;
    }


    /* =====================================================
       PICKUP
       ===================================================== */

    const tripPickup =
        getElement("trip-pickup");


    if (tripPickup) {

        tripPickup.textContent =
            pickup;
    }


    /* =====================================================
       HOSPITAL
       ===================================================== */

    const tripDestination =
        getElement("trip-dest");


    if (tripDestination) {

        tripDestination.textContent =
            hospitalName;
    }


    /* =====================================================
       ETA
       ===================================================== */

    const tripEta =
        getElement("trip-eta");


    if (tripEta) {

        if (
            request.eta_minutes !==
            undefined &&
            request.eta_minutes !==
            null
        ) {

            tripEta.textContent =
                `${request.eta_minutes} min`;

        } else {

            tripEta.textContent =
                "—";
        }
    }


    /* =====================================================
       DISTANCE
       ===================================================== */

    const tripDistance =
        getElement("trip-dist");


    if (tripDistance) {

        if (
            request.offer_distance_km !==
            undefined &&
            request.offer_distance_km !==
            null
        ) {

            tripDistance.textContent =
                `${request.offer_distance_km} km`;

        } else {

            tripDistance.textContent =
                "—";
        }
    }


    /* =====================================================
       NAVIGATION
       ===================================================== */

    const navigateButton =
        getElement("navigate-btn");


    if (
        navigateButton &&
        patient.latitude != null &&
        patient.longitude != null
    ) {

        navigateButton.href =
            `https://www.google.com/maps/dir/?api=1&destination=${patient.latitude},${patient.longitude}`;
    }


    /* =====================================================
       PATIENT MAP
       ===================================================== */

    if (
        patient.latitude != null &&
        patient.longitude != null
    ) {

        updatePatientLocation(
            patient.latitude,
            patient.longitude
        );
    }


    /* =====================================================
       HOSPITAL MAP
       ===================================================== */

    if (
        hospital.latitude != null &&
        hospital.longitude != null
    ) {

        updateHospitalLocation(
            hospital.latitude,
            hospital.longitude
        );
    }


    updateTripStatusUI(
        request
    );
}


/* =========================================================
   HIDE ACTIVE TRIP
   ========================================================= */

function hideActiveTrip() {

    const card =
        getElement("current-trip");


    if (card) {

        card.classList.add("hidden");

        card.style.display = "none";
    }
}


/* =========================================================
   UPDATE TRIP STATUS UI
   ========================================================= */

function updateTripStatusUI(request) {

    if (!request) {
        return;
    }


    const status =
        normalizeStatus(
            request.status
        );


    /*
     * Your HTML has six tracker steps:
     *
     * 0 Request Received
     * 1 Accepted
     * 2 En Route to Patient
     * 3 Patient Picked Up
     * 4 En Route to Hospital
     * 5 Trip Completed
     */


    let activeStep = 0;


    if (
        status === "accepted"
    ) {

        activeStep = 1;

    } else if (
        status === "en_route" ||
        status === "enroute"
    ) {

        activeStep = 2;

    } else if (
        status === "arrived"
    ) {

        activeStep = 2;

    } else if (
        status === "picked_up"
    ) {

        activeStep = 3;

    } else if (
        status === "en_route_to_hospital"
    ) {

        activeStep = 4;

    } else if (
        status === "completed"
    ) {

        activeStep = 5;
    }


    const tracker =
        getElement("tracker");


    if (!tracker) {
        return;
    }


    const steps =
        tracker.querySelectorAll(
            ".step"
        );


    steps.forEach(
        (step, index) => {

            step.classList.remove(
                "active"
            );


            step.classList.remove(
                "completed"
            );


            if (
                index <
                activeStep
            ) {

                step.classList.add(
                    "completed"
                );
            }


            if (
                index ===
                activeStep
            ) {

                step.classList.add(
                    "active"
                );
            }
        }
    );
}


/* =========================================================
   MAP INITIALIZATION
   ========================================================= */

function initializeMap() {

    if (
        typeof L ===
        "undefined"
    ) {

        console.warn(
            "Leaflet is not loaded."
        );

        return;
    }


    const mapElement =
        getElement("map");


    if (!mapElement) {
        return;
    }


    if (map) {
        return;
    }


    map =
        L.map("map")
            .setView(
                [
                    13.2025,
                    77.6221
                ],
                13
            );


    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {

            maxZoom: 19,

            attribution:
                "&copy; OpenStreetMap contributors"
        }
    ).addTo(map);
}


/* =========================================================
   DRIVER LOCATION ON MAP
   ========================================================= */

function updateDriverLocation(
    latitude,
    longitude
) {

    if (
        !map ||
        latitude == null ||
        longitude == null
    ) {

        return;
    }


    const position = [
        latitude,
        longitude
    ];


    if (!driverMarker) {

        driverMarker =
            L.marker(position)
                .addTo(map)
                .bindPopup(
                    "Ambulance"
                );

    } else {

        driverMarker.setLatLng(
            position
        );
    }
}


/* =========================================================
   PATIENT LOCATION ON MAP
   ========================================================= */

function updatePatientLocation(
    latitude,
    longitude
) {

    if (
        !map ||
        latitude == null ||
        longitude == null
    ) {

        return;
    }


    const position = [
        latitude,
        longitude
    ];


    if (!patientMarker) {

        patientMarker =
            L.marker(position)
                .addTo(map)
                .bindPopup(
                    "Patient"
                );

    } else {

        patientMarker.setLatLng(
            position
        );
    }
}


/* =========================================================
   HOSPITAL LOCATION ON MAP
   ========================================================= */

function updateHospitalLocation(
    latitude,
    longitude
) {

    if (
        !map ||
        latitude == null ||
        longitude == null
    ) {

        return;
    }


    const position = [
        latitude,
        longitude
    ];


    if (!hospitalMarker) {

        hospitalMarker =
            L.marker(position)
                .addTo(map)
                .bindPopup(
                    "Hospital"
                );

    } else {

        hospitalMarker.setLatLng(
            position
        );
    }
}


/* =========================================================
   GPS
   ========================================================= */

function startGPS() {

    if (!navigator.geolocation) {

        console.warn(
            "Geolocation is not supported."
        );

        return;
    }


    navigator.geolocation.watchPosition(

        async position => {

            const latitude =
                position.coords.latitude;


            const longitude =
                position.coords.longitude;


            updateDriverLocation(
                latitude,
                longitude
            );


            if (!ambulanceId) {
                return;
            }


            try {

                const response =
                    await fetch(
                        "/api/driver/location",
                        {

                            method: "POST",

                            headers: {
                                "content-type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify({

                                    ambulance_id:
                                        ambulanceId,

                                    latitude:
                                        latitude,

                                    longitude:
                                        longitude
                                })
                        }
                    );


                if (!response.ok) {
                    return;
                }


                /*
                 * Only update automatic
                 * trip status after the
                 * driver has accepted.
                 */

                if (currentRequest) {

                    await updateTripByDistance(
                        latitude,
                        longitude
                    );
                }


            } catch (error) {

                console.error(
                    "GPS update failed:",
                    error
                );
            }
        },


        error => {

            console.warn(
                "GPS error:",
                error.message
            );
        },


        {

            enableHighAccuracy: true,

            maximumAge: 5000,

            timeout: 10000
        }
    );
}


/* =========================================================
   CALCULATE DISTANCE
   ========================================================= */

function calculateDistance(
    lat1,
    lon1,
    lat2,
    lon2
) {

    const R = 6371;


    const dLat =
        (
            lat2 -
            lat1
        ) *
        Math.PI /
        180;


    const dLon =
        (
            lon2 -
            lon1
        ) *
        Math.PI /
        180;


    const a =

        Math.sin(
            dLat / 2
        ) *
        Math.sin(
            dLat / 2
        )

        +

        Math.cos(
            lat1 *
            Math.PI /
            180
        )

        *

        Math.cos(
            lat2 *
            Math.PI /
            180
        )

        *

        Math.sin(
            dLon / 2
        ) *
        Math.sin(
            dLon / 2
        );


    const c =
        2 *
        Math.atan2(
            Math.sqrt(a),
            Math.sqrt(
                1 - a
            )
        );


    return R * c;
}


/* =========================================================
   AUTOMATIC TRIP STATUS
   ========================================================= */

async function updateTripByDistance(
    driverLat,
    driverLon
) {

    if (!currentRequest) {
        return;
    }


    const patient =
        currentRequest.patient ||
        {};


    const hospital =
        currentRequest.hospital_obj ||
        {};


    const status =
        normalizeStatus(
            currentRequest.status
        );


    let newStatus = null;


    /* =====================================================
       ACCEPTED → EN ROUTE TO PATIENT
       ===================================================== */

    if (
        status === "accepted" &&
        patient.latitude != null &&
        patient.longitude != null
    ) {

        const distance =
            calculateDistance(

                driverLat,
                driverLon,

                patient.latitude,
                patient.longitude
            );


        if (distance <= 0.3) {

            newStatus =
                "en_route";
        }
    }


    /* =====================================================
       EN ROUTE → PATIENT PICKED UP
       ===================================================== */

    else if (
        status === "en_route" ||
        status === "enroute"
    ) {

        if (
            patient.latitude != null &&
            patient.longitude != null
        ) {

            const distance =
                calculateDistance(

                    driverLat,
                    driverLon,

                    patient.latitude,
                    patient.longitude
                );


            if (distance <= 0.15) {

                newStatus =
                    "picked_up";
            }
        }
    }


    /* =====================================================
       PICKED UP → COMPLETED
       ===================================================== */

    else if (
        status === "picked_up"
    ) {

        if (
            hospital.latitude != null &&
            hospital.longitude != null
        ) {

            const distance =
                calculateDistance(

                    driverLat,
                    driverLon,

                    hospital.latitude,
                    hospital.longitude
                );


            if (distance <= 0.3) {

                newStatus =
                    "completed";
            }
        }
    }


    if (!newStatus) {
        return;
    }


    try {

        const response =
            await fetch(
                "/api/driver/trip-status",
                {

                    method: "POST",

                    headers: {
                        "content-type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            ambulance_id:
                                ambulanceId,

                            request_id:
                                currentRequest.id,

                            status:
                                newStatus
                        })
                }
            );


        if (!response.ok) {
            return;
        }


        const data =
            await response.json();


        console.log(
            "Trip status updated:",
            data
        );


        currentRequest.status =
            newStatus;


        updateTripStatusUI(
            currentRequest
        );


        if (
            newStatus ===
            "completed"
        ) {

            setTimeout(
                async () => {

                    currentRequest =
                        null;


                    hideActiveTrip();


                    await loadDriverSummary();


                    await poll();

                },
                1500
            );
        }


    } catch (error) {

        console.error(
            "Trip status update failed:",
            error
        );
    }
}


/* =========================================================
   LOGOUT
   ========================================================= */

function logout() {

    try {

        sessionStorage.removeItem(
            "user"
        );


        sessionStorage.removeItem(
            "role"
        );


        sessionStorage.removeItem(
            "mobile"
        );


        localStorage.removeItem(
            "driver_registered"
        );


        localStorage.removeItem(
            "driver_data"
        );


    } catch (error) {

        console.error(
            "Logout cleanup failed:",
            error
        );
    }


    if (pollTimer) {

        clearInterval(
            pollTimer
        );


        pollTimer =
            null;
    }


    window.location.href =
        "/";
}


/* =========================================================
   INITIALIZE DRIVER DASHBOARD
   ========================================================= */

async function initializeDriverDashboard() {

    console.log(
        "Initializing LifeLine Driver Dashboard..."
    );


    const user =
        loadDriverUser();


    if (!user) {
        return;
    }


    /* =====================================================
       GET THIS DRIVER'S AMBULANCE
       ===================================================== */

    const ambulanceResolved =
        await resolveDriverAmbulance();


    if (!ambulanceResolved) {
        return;
    }


    console.log(
        "Dashboard using ambulance:",
        ambulanceId
    );


    /* =====================================================
       MAP
       ===================================================== */

    initializeMap();


    /* =====================================================
       SUMMARY
       ===================================================== */

    await loadDriverSummary();


    /* =====================================================
       CHECK FOR REQUEST IMMEDIATELY
       ===================================================== */

    await poll();


    /* =====================================================
       CONTINUE CHECKING
       ===================================================== */

    if (pollTimer) {

        clearInterval(
            pollTimer
        );
    }


    pollTimer =
        setInterval(
            poll,
            POLL_MS
        );


    /* =====================================================
       START GPS
       ===================================================== */

    startGPS();
}


/* =========================================================
   PAGE LOAD
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        initializeDriverDashboard();
    }
);


/* =========================================================
   GLOBAL FUNCTIONS
   ========================================================= */

window.handleAccept =
    handleAccept;


window.handleReject =
    handleReject;


window.logout =
    logout;


window.pollDriverRequests =
    poll;


window.showRequestCard =
    showRequestCard;


window.hideRequestCard =
    hideRequestCard;