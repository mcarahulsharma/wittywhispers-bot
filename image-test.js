(() => {
  "use strict";

  const API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions";
  const form = document.getElementById("generator-form");
  const apiKey = document.getElementById("api-key");
  const aspectRatio = document.getElementById("aspect-ratio");
  const imageSize = document.getElementById("image-size");
  const prompt = document.getElementById("prompt");
  const generate = document.getElementById("generate");
  const clear = document.getElementById("clear");
  const toggleKey = document.getElementById("toggle-key");
  const status = document.getElementById("status");
  const result = document.getElementById("result");
  const output = document.getElementById("generated-image");
  const download = document.getElementById("download");

  let objectUrl = null;

  function setStatus(message, kind = "") {
    status.textContent = message;
    status.className = "status " + kind;
  }

  function clearImage() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    output.removeAttribute("src");
    result.hidden = true;
  }

  function safeError(data, response) {
    const error = data && data.error;
    if (error) {
      const code = error.code || response.status;
      const message = error.message || "No error message returned.";
      return "Google API error (" + code + "): " +
        message.replace(/AIza[0-9A-Za-z_-]{20,}/g, "[redacted]");
    }
    return "Google returned HTTP " + response.status +
      ". No structured error was returned. Check the API key, model access, and billing/quota.";
  }

  toggleKey.addEventListener("click", () => {
    const visible = apiKey.type === "text";
    apiKey.type = visible ? "password" : "text";
    toggleKey.textContent = visible ? "Show" : "Hide";
  });

  clear.addEventListener("click", () => {
    form.reset();
    apiKey.value = "";
    prompt.value = "";
    clearImage();
    setStatus("");
  });

  download.addEventListener("click", () => {
    if (!objectUrl) return;
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "wittywhispers-generated.png";
    document.body.appendChild(link);
    link.click();
    link.remove();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearImage();

    const key = apiKey.value.trim();
    const text = prompt.value.trim();

    if (!key) {
      setStatus("Enter your Google Gemini API key.", "error");
      return;
    }

    if (!text) {
      setStatus("Enter an image prompt.", "error");
      return;
    }

    generate.disabled = true;
    generate.textContent = "Generating…";
    setStatus("Generating image with Gemini 3.1 Flash Image…");

    try {
      const requestBody = {
        model: "gemini-3.1-flash-image",
        input: text,
        response_format: {
          type: "image",
          mime_type: "image/jpeg",
          aspect_ratio: aspectRatio.value,
          image_size: imageSize.value
        }
      };

      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": key
        },
        body: JSON.stringify(requestBody),
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer"
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(safeError(data, response));
      }

      // The REST API may expose the image as output_image or inside steps[].content[].
      let image = data && data.output_image;

      if (!image && Array.isArray(data && data.steps)) {
        for (const step of data.steps) {
          if (Array.isArray(step.content)) {
            const found = step.content.find(item =>
              item && item.type === "image" && item.data
            );
            if (found) {
              image = found;
              break;
            }
          }
        }
      }

      const base64 = image && image.data;
      const mime = (image && image.mime_type) || "image/png";

      if (!base64) {
        throw new Error("Google completed the request but returned no image data. Response status: " + (data && data.status || "unknown"));
      }

      const binary = atob(base64);
      const bytes = new Uint8Array(binary.length);

      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }

      objectUrl = URL.createObjectURL(new Blob([bytes], { type: mime }));
      output.src = objectUrl;
      result.hidden = false;
      setStatus("Image generated successfully.", "success");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Image generation failed.", "error");
    } finally {
      generate.disabled = false;
      generate.textContent = "Generate image";
    }
  });
})();