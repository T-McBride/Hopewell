(() => {
  "use strict";

  const screens = {
    welcome: document.getElementById("screen-welcome"),
    form: document.getElementById("screen-form"),
    camera: document.getElementById("screen-camera"),
    photoReview: document.getElementById("screen-photo-review"),
    review: document.getElementById("screen-review"),
    done: document.getElementById("screen-done"),
  };

  let cameraStream = null;
  let capturedPhotoBlob = null; // null means "skipped" or not yet captured
  let photoReviewUrl = null; // tracks the current blob: URL so we can revoke it on retake
  let countdownInterval = null;
  let idleTimer = null;
  const IDLE_TIMEOUT_MS = 45_000;
  const COUNTDOWN_SECONDS = 3;

  const state = {
    full_name: "",
    phone_mobile: "",
    email: "",
    home_address: "",
    city: "",
  };

  function showScreen(name) {
    Object.values(screens).forEach((el) => el.classList.remove("active"));
    screens[name].classList.add("active");
    resetIdleTimer();
  }

  function resetIdleTimer() {
    if (idleTimer) clearTimeout(idleTimer);
    // Don't time out while sitting on the welcome screen - nothing to lose.
    if (screens.welcome.classList.contains("active")) return;
    idleTimer = setTimeout(resetToWelcome, IDLE_TIMEOUT_MS);
  }

  function resetToWelcome() {
    cancelCountdown();
    stopCamera();
    capturedPhotoBlob = null;
    if (photoReviewUrl) {
      URL.revokeObjectURL(photoReviewUrl);
      photoReviewUrl = null;
    }
    state.full_name = state.phone_mobile = state.email = state.home_address = "";
    document.getElementById("contact-form").reset();
    document.getElementById("field-consent").checked = false;
    showScreen("welcome");
  }

  // Any tap/click anywhere resets the idle clock, except on the welcome screen.
  document.addEventListener("pointerdown", resetIdleTimer);

  // --- Screen 1: welcome ---
  document.getElementById("btn-start").addEventListener("click", () => {
    showScreen("form");
  });

  // --- Screen 2: form ---
  document.getElementById("form-back").addEventListener("click", resetToWelcome);
  document.getElementById("form-next").addEventListener("click", () => {
    const name = document.getElementById("field-name").value.trim();
    if (!name) {
      document.getElementById("field-name").focus();
      return;
    }
    state.full_name = name;
    state.phone_mobile = document.getElementById("field-phone").value.trim();
    state.email = document.getElementById("field-email").value.trim();
    state.home_address = document.getElementById("field-address").value.trim();
    state.city = document.getElementById("field-city").value.trim();
    state.state = document.getElementById("field-state").value.trim();
    state.zip = document.getElementById("field-zip").value.trim();
    showScreen("camera");
    startCamera();
  });

  // --- Screen 3: camera ---
  async function startCamera() {
    const hint = document.getElementById("camera-hint");
    hint.textContent = "Center your face in the circle, then tap capture.";
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      document.getElementById("camera-video").srcObject = cameraStream;
    } catch (err) {
      hint.textContent = "Camera unavailable - you can skip the photo and continue.";
    }
  }

  function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach((t) => t.stop());
      cameraStream = null;
    }
  }

  document.getElementById("camera-back").addEventListener("click", () => {
    cancelCountdown();
    stopCamera();
    showScreen("form");
  });

  function setCameraControlsDisabled(disabled) {
    document.getElementById("camera-back").disabled = disabled;
    document.getElementById("camera-capture").disabled = disabled;
    document.getElementById("camera-skip").disabled = disabled;
  }

  function cancelCountdown() {
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }
    document.getElementById("countdown-overlay").hidden = true;
    setCameraControlsDisabled(false);
  }

  document.getElementById("camera-capture").addEventListener("click", () => {
    const video = document.getElementById("camera-video");
    if (!video.videoWidth) return; // camera not ready yet
    startCountdown();
  });

  function startCountdown() {
    const overlay = document.getElementById("countdown-overlay");
    const numberEl = document.getElementById("countdown-number");
    let secondsLeft = COUNTDOWN_SECONDS;

    setCameraControlsDisabled(true);
    numberEl.textContent = secondsLeft;
    overlay.hidden = false;

    countdownInterval = setInterval(() => {
      secondsLeft -= 1;
      if (secondsLeft > 0) {
        numberEl.textContent = secondsLeft;
      } else {
        clearInterval(countdownInterval);
        countdownInterval = null;
        overlay.hidden = true;
        setCameraControlsDisabled(false);
        capturePhoto();
      }
    }, 1000);
  }

  function capturePhoto() {
    const video = document.getElementById("camera-video");
    const canvas = document.getElementById("camera-canvas");
    if (!video.videoWidth) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        capturedPhotoBlob = blob;
        stopCamera();
        showPhotoReviewScreen();
      },
      "image/jpeg",
      0.9
    );
  }

  document.getElementById("camera-skip").addEventListener("click", () => {
    cancelCountdown();
    capturedPhotoBlob = null;
    stopCamera();
    goToReview();
  });

  // --- Screen 3.5: photo review / retake ---
  function showPhotoReviewScreen() {
    if (photoReviewUrl) URL.revokeObjectURL(photoReviewUrl);
    photoReviewUrl = URL.createObjectURL(capturedPhotoBlob);
    document.getElementById("photo-review-img").src = photoReviewUrl;
    showScreen("photoReview");
  }

  document.getElementById("photo-retake").addEventListener("click", () => {
    showScreen("camera");
    startCamera();
  });

  document.getElementById("photo-continue").addEventListener("click", () => {
    goToReview();
  });

  // --- Screen 4: review ---
  function goToReview() {
    document.getElementById("review-name").textContent = state.full_name;
    document.getElementById("review-phone").textContent = state.phone_mobile || "";
    document.getElementById("review-email").textContent = state.email || "";
    document.getElementById("review-address").textContent = state.home_address
      ? `Address on file (private)`
      : "";
    document.getElementById("review-city").textContent = state.city;
    document.getElementById("review-state").textContent = state.state;
    document.getElementById("review-city").textContent = state.zip;

    const img = document.getElementById("review-photo");
    if (capturedPhotoBlob) {
      img.src = photoReviewUrl || URL.createObjectURL(capturedPhotoBlob);
    } else {
      img.src =
        "data:image/svg+xml;utf8," +
        encodeURIComponent(
          `<svg xmlns="http://www.w3.org/2000/svg" width="90" height="90"><rect width="90" height="90" fill="#e4e1d8"/></svg>`
        );
    }
    document.getElementById("review-error").hidden = true;
    document.getElementById("field-consent").checked = false;
    console.log(state.full_name);
    showScreen("review");
  }

  document.getElementById("review-back").addEventListener("click", () => {
    if (capturedPhotoBlob) {
      showPhotoReviewScreen();
    } else {
      showScreen("camera");
      startCamera();
    }
  });

  document.getElementById("review-submit").addEventListener("click", async () => {
    const errorEl = document.getElementById("review-error");
    const consent = document.getElementById("field-consent").checked;
    if (!consent) {
      errorEl.textContent = "Please check the consent box to continue.";
      errorEl.hidden = false;
      return;
    }

    const submitBtn = document.getElementById("review-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting...";

    const formData = new FormData();
    formData.append("full_name", state.full_name);
    formData.append("phone_mobile", state.phone_mobile);
    formData.append("email", state.email);
    formData.append("home_address", state.home_address);
    formData.append("city", state.city);
    formData.append("state", state.state);
    formData.append("zip", state.zip);
    formData.append("consent_given", "true");
    if (capturedPhotoBlob) {
      formData.append("photo", capturedPhotoBlob, "photo.jpg");
    }

    try {
      const res = await fetch("/api/contacts", { method: "POST", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Something went wrong. Please try again.");
      }
      showDoneScreen();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit";
    }
  });

  // --- Screen 5: done ---
  function showDoneScreen() {
    showScreen("done");
    let secondsLeft = 10;
    const counter = document.getElementById("countdown");
    counter.textContent = secondsLeft;
    const interval = setInterval(() => {
      secondsLeft -= 1;
      counter.textContent = secondsLeft;
      if (secondsLeft <= 0) {
        clearInterval(interval);
        resetToWelcome();
      }
    }, 1000);
  }
})();
