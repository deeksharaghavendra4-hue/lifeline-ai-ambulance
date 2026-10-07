/* =========================================================
   LIFELINE — API.JS
   All backend API calls using fetch().
   No UI code here.
   ========================================================= */

const BASE = "";


/* =========================================================
   GENERIC API FETCH
   ========================================================= */

async function apiFetch(path, options = {}) {

  const response = await fetch(BASE + path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  let data = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new Error(
      data.error ||
      data.message ||
      `Request failed with status ${response.status}`
    );
  }

  return data;
}


/* =========================================================
   AUTH
   ========================================================= */

export const sendOtp = (mobile, role) =>
  apiFetch("/auth/send-otp", {
    method: "POST",
    body: JSON.stringify({
      mobile,
      role
    })
  });


export const verifyOtp = (mobile, otp) =>
  apiFetch("/auth/verify-otp", {
    method: "POST",
    body: JSON.stringify({
      mobile,
      otp
    })
  });


export const registerUser = (role, payload) =>
  apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      role,
      ...payload
    })
  });


export const loginUserApi = (role, mobile, password) =>
  apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      role,
      mobile,
      password
    })
  });


/* =========================================================
   GENERAL DATA
   ========================================================= */

export const getAmbulances = () =>
  apiFetch("/ambulances");


export const getHospitals = () =>
  apiFetch("/hospitals");


export const getRequests = () =>
  apiFetch("/requests");


export const getDriverData = (ambulanceId) =>
  apiFetch(
    `/driver-data?ambulance_id=${encodeURIComponent(ambulanceId)}`
  );


/* =========================================================
   PATIENT
   ========================================================= */

/*
   Create a new ambulance request.

   payload should contain:
   {
     patient_id,
     patient_name,
     age,
     gender,
     blood_group,
     mobile,
     latitude,
     longitude,
     emergency_type,
     voice_description
   }
*/

export const requestAmbulance = (payload) =>
  apiFetch("/api/request-ambulance", {
    method: "POST",
    body: JSON.stringify(payload)
  });


/*
   Get all requests belonging to a patient.
*/

export const getPatientRequests = (mobile) =>
  apiFetch(
    `/api/patient/my-requests?mobile=${encodeURIComponent(mobile)}`
  );


/*
   Get the current status of one patient request.
*/

export const getPatientRequestStatus = (requestId) =>
  apiFetch(
    `/api/patient/request-status/${encodeURIComponent(requestId)}`
  );


/*
   Cancel a patient request.
*/

export const cancelPatientRequest = (requestId, mobile = "") =>
  apiFetch("/api/patient/cancel-request", {
    method: "POST",
    body: JSON.stringify({
      request_id: requestId,
      mobile
    })
  });


/* =========================================================
   DRIVER
   ========================================================= */

/*
   Find the ambulance belonging to the logged-in driver.
*/

export const getDriverAmbulance = ({
  mobile = "",
  driver_id = "",
  ambulance_reg_number = ""
} = {}) => {

  const params = new URLSearchParams();

  if (mobile) {
    params.set("mobile", mobile);
  }

  if (driver_id) {
    params.set("driver_id", driver_id);
  }

  if (ambulance_reg_number) {
    params.set(
      "ambulance_reg_number",
      ambulance_reg_number
    );
  }

  return apiFetch(
    `/api/driver/my-ambulance?${params.toString()}`
  );
};


/*
   Get requests relevant to this ambulance.

   Backend should return:
   {
     success: true,
     pending: [],
     assigned: []
   }

   With the new dispatch system, "pending" should contain
   requests currently offered to THIS ambulance.
*/

export const getDriverRequests = (ambulanceId) =>
  apiFetch(
    `/api/driver/requests?ambulance_id=${encodeURIComponent(ambulanceId)}`
  );


/*
   Accept an ambulance request.
*/

export const acceptDriverRequest = (
  ambulanceId,
  requestId
) =>
  apiFetch("/api/driver/accept", {
    method: "POST",
    body: JSON.stringify({
      ambulance_id: ambulanceId,
      request_id: requestId
    })
  });


/*
   Reject an ambulance request.

   Backend will then dispatch the request to the
   next nearest available driver.
*/

export const rejectDriverRequest = (
  ambulanceId,
  requestId
) =>
  apiFetch("/api/driver/reject", {
    method: "POST",
    body: JSON.stringify({
      ambulance_id: ambulanceId,
      request_id: requestId
    })
  });


/*
   Update driver's / ambulance's current GPS location.
*/

export const updateDriverLocation = (
  ambulanceId,
  latitude,
  longitude
) =>
  apiFetch("/api/driver/location", {
    method: "POST",
    body: JSON.stringify({
      ambulance_id: ambulanceId,
      latitude,
      longitude
    })
  });


/*
   Update current trip status.

   Examples:
   accepted
   en_route
   arrived
   picked_up
   completed
*/

export const updateDriverTripStatus = (
  ambulanceId,
  requestId,
  status
) =>
  apiFetch("/api/driver/trip-status", {
    method: "POST",
    body: JSON.stringify({
      ambulance_id: ambulanceId,
      request_id: requestId,
      status
    })
  });


/*
   Driver dashboard statistics.
*/

export const getDriverSummary = (ambulanceId) =>
  apiFetch(
    `/api/driver/summary?ambulance_id=${encodeURIComponent(ambulanceId)}`
  );


/*
   Driver emergency action.
*/

export const driverEmergency = (
  ambulanceId,
  requestId = ""
) =>
  apiFetch("/api/driver/emergency", {
    method: "POST",
    body: JSON.stringify({
      ambulance_id: ambulanceId,
      request_id: requestId
    })
  });


/* =========================================================
   HOSPITAL
   ========================================================= */

export const getHospitalDashboard = () =>
  apiFetch("/api/hospital/dashboard");


/* =========================================================
   HEALTH CHECK
   ========================================================= */

export const healthCheck = () =>
  apiFetch("/health");