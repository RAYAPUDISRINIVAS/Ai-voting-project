(() => {
  const video = document.getElementById("camera-preview");
  const canvas = document.getElementById("camera-canvas");
  const imageField = document.getElementById("face-image");
  const imagePreview = document.getElementById("face-image-preview");
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
  const clearImage = () => {
    imageField.value = "";
    if (imagePreview) {
      imagePreview.removeAttribute("src");
      imagePreview.hidden = true;
    }
  };
  const showCapturedImage = (imageData, message) => {
    imageField.value = imageData;
    if (imagePreview) {
      imagePreview.src = imageData;
      imagePreview.hidden = false;
    }
    video.hidden = true;
    if (placeholder) placeholder.hidden = true;
    if (startButton) startButton.textContent = "Retake with webcam";
    showStatus(message);
  };

  startButton?.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      showStatus("Webcam access is unavailable in this browser. Choose an image instead.");
      return;
    }
    stopCamera();
    clearImage();
    video.hidden = false;
    if (imagePreview) imagePreview.hidden = true;
    if (placeholder) placeholder.hidden = false;
    startButton.disabled = true;
    showStatus("Requesting webcam access…");
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
        await new Promise((resolve, reject) => {
          const timeout = window.setTimeout(() => {
            cleanup();
            reject(new Error("The webcam did not provide a frame in time."));
          }, 10000);
          const cleanup = () => {
            window.clearTimeout(timeout);
            video.removeEventListener("loadeddata", onLoaded);
            video.removeEventListener("error", onError);
          };
          const onLoaded = () => {
            cleanup();
            resolve();
          };
          const onError = () => {
            cleanup();
            reject(new Error("The webcam frame could not be read."));
          };
          video.addEventListener("loadeddata", onLoaded, { once: true });
          video.addEventListener("error", onError, { once: true });
        });
      }
      if (!video.videoWidth || !video.videoHeight) {
        throw new Error("The webcam did not provide a usable image.");
      }
      if (placeholder) placeholder.hidden = true;
      captureButton.disabled = false;
      showStatus("Webcam ready. Center your face, then capture a frame.");
    } catch (error) {
      stopCamera();
      video.srcObject = null;
      video.hidden = true;
      if (placeholder) placeholder.hidden = false;
      showStatus(`Could not capture from the webcam: ${error.message || error.name || "unknown error"}. Choose an image instead.`);
    } finally {
      startButton.disabled = false;
    }
  });

  captureButton?.addEventListener("click", () => {
    if (!video.videoWidth || !video.videoHeight || video.readyState < 2) {
      showStatus("The webcam has not produced a clear frame. Wait for the preview and try again.");
      return;
    }
    const scale = Math.min(1, 1280 / video.videoWidth, 960 / video.videoHeight);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) {
      showStatus("Could not prepare the captured image. Please try again or choose an image.");
      return;
    }
    try {
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const imageData = canvas.toDataURL("image/jpeg", 0.85);
      if (!imageData || imageData === "data:,") {
        throw new Error("The captured frame was empty.");
      }
      stopCamera();
      video.srcObject = null;
      showCapturedImage(imageData, "Image captured. Check the preview below; choose Retake with webcam to try again.");
    } catch (error) {
      showStatus(`Could not save the captured frame: ${error.message || "unknown error"}. Please try again.`);
    }
  });

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 4 * 1024 * 1024) {
      clearImage();
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
      stopCamera();
      video.srcObject = null;
      showCapturedImage(reader.result, "Image ready. Check the preview below before submitting.");
    };
    reader.onerror = () => showStatus("The selected image could not be read. Try another image.");
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
