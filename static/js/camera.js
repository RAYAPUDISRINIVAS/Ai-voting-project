(() => {
  const video = document.getElementById("camera-preview");
  const canvas = document.getElementById("camera-canvas");
  const imageField = document.getElementById("face-image");
  const startButton = document.getElementById("start-camera");
  const captureButton = document.getElementById("capture-camera");
  const fileInput = document.getElementById("face-upload");
  const placeholder = document.getElementById("camera-placeholder");
  const status = document.getElementById("camera-status");
  if (!video || !canvas || !imageField) return;

  let stream = null;
  const showStatus = (message) => {
    if (status) status.textContent = message;
  };
  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    if (captureButton) captureButton.disabled = true;
  };

  startButton?.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      showStatus("Webcam access is unavailable in this browser. Choose an image instead.");
      return;
    }
    try {
      stopCamera();
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      video.srcObject = stream;
      video.hidden = false;
      if (placeholder) placeholder.hidden = true;
      if (captureButton) captureButton.disabled = false;
      showStatus("Camera ready. Position one face in the frame.");
    } catch (error) {
      showStatus(`Could not access the webcam (${error.name || "permission error"}). Choose an image instead.`);
    }
  });

  captureButton?.addEventListener("click", () => {
    if (!video.videoWidth || !video.videoHeight) {
      showStatus("The webcam has not produced a frame yet. Wait and try again.");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    imageField.value = canvas.toDataURL("image/jpeg", 0.9);
    stopCamera();
    showStatus("Image captured. Submit the form to continue.");
  });

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 4 * 1024 * 1024) {
      imageField.value = "";
      fileInput.value = "";
      showStatus("Choose a JPEG or PNG image no larger than 4 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        showStatus("The selected image could not be read.");
        return;
      }
      imageField.value = reader.result;
      stopCamera();
      showStatus("Image ready. Submit the form to continue.");
    };
    reader.onerror = () => showStatus("The selected image could not be read.");
    reader.readAsDataURL(file);
  });

  document.getElementById("face-form")?.addEventListener("submit", (event) => {
    if (!imageField.value) {
      event.preventDefault();
      showStatus("Capture a frame or choose an image before continuing.");
      return;
    }
    const submitButton = event.currentTarget.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Processing facial data…";
    }
    showStatus("Processing facial data. Please wait…");
  });

  window.addEventListener("pagehide", stopCamera);
})();
