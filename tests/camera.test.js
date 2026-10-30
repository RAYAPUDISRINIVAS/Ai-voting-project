const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");

const cameraScript = readFileSync("static/js/camera.js", "utf8");

function makeElement() {
  const listeners = {};
  return {
    hidden: false,
    disabled: false,
    value: "",
    textContent: "",
    src: "",
    videoWidth: 640,
    videoHeight: 480,
    readyState: 2,
    srcObject: null,
    listeners,
    addEventListener(name, callback) {
      listeners[name] = callback;
    },
    removeEventListener(name) {
      delete listeners[name];
    },
    removeAttribute(name) {
      if (name === "src") this.src = "";
    },
    async play() {},
    getContext() {
      return { drawImage: () => { this.drawn = true; } };
    },
    toDataURL() {
      return "data:image/jpeg;base64,captured-frame";
    },
    querySelector() {
      return this.submitButton;
    },
  };
}

function loadCameraPage() {
  const ids = [
    "camera-preview",
    "camera-canvas",
    "face-image",
    "face-image-preview",
    "start-camera",
    "capture-camera",
    "face-upload",
    "camera-placeholder",
    "camera-status",
    "face-form",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, makeElement()]));
  const stoppedTracks = [];
  elements["face-form"].submitButton = makeElement();
  const document = { getElementById: (id) => elements[id] || null };
  const window = {
    addEventListener() {},
    setTimeout,
    clearTimeout,
  };
  const navigator = {
    mediaDevices: {
      async getUserMedia() {
        return { getTracks: () => [{ stop: () => stoppedTracks.push(true) }] };
      },
    },
  };

  vm.runInNewContext(cameraScript, {
    document,
    window,
    navigator,
    HTMLMediaElement: { HAVE_CURRENT_DATA: 2 },
    FileReader: class {},
  });
  return { elements, stoppedTracks };
}

test("webcam capture saves and displays the captured frame", async () => {
  const { elements, stoppedTracks } = loadCameraPage();
  await elements["start-camera"].listeners.click();

  assert.equal(elements["capture-camera"].disabled, false);
  assert.equal(elements["camera-placeholder"].hidden, true);
  elements["capture-camera"].listeners.click();

  assert.equal(elements["camera-canvas"].drawn, true);
  assert.equal(elements["face-image"].value, "data:image/jpeg;base64,captured-frame");
  assert.equal(elements["face-image-preview"].src, elements["face-image"].value);
  assert.equal(elements["face-image-preview"].hidden, false);
  assert.equal(elements["camera-preview"].hidden, true);
  assert.equal(elements["capture-camera"].disabled, true);
  assert.equal(stoppedTracks.length, 1);
  assert.match(elements["camera-status"].textContent, /Image captured/);
});

test("form cannot submit until a face image has been captured", () => {
  const { elements } = loadCameraPage();
  let prevented = false;
  elements["face-form"].listeners.submit({
    preventDefault() { prevented = true; },
    currentTarget: elements["face-form"],
  });

  assert.equal(prevented, true);
  assert.match(elements["camera-status"].textContent, /Capture a frame/);
});

test("capture with no available camera frame reports a helpful message", () => {
  const { elements } = loadCameraPage();
  elements["camera-preview"].videoWidth = 0;
  elements["capture-camera"].listeners.click();

  assert.equal(elements["face-image"].value, "");
  assert.match(elements["camera-status"].textContent, /has not produced a clear frame/);
});
